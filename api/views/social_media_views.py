import uuid
from datetime import datetime, timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Count, Q

from api.models import (
    SmCustomer, SmContact, SmAddress, SmAccount, SmAccountManager,
    SmCredentialVersion, SmAuditEvent, SmBusinessCategory, SmPlatform,
    SmTermsVersion, SmContract, User
)
from api.permissions import IsAdminUser
from api.helpers import safe_user, verify_password
from api.vault import seal, unseal
from api.s3_util import s3_upload, s3_delete, get_s3_client
from api.contract_pdf import make_contract_pdf
from django.conf import settings


class SmCustomerListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        search = request.query_params.get('search', '').strip()
        page = max(1, int(request.query_params.get('page', 1)))
        take = 20
        skip = (page - 1) * take

        qs = SmCustomer.objects.filter(archived_at__isnull=True)
        if search:
            qs = qs.filter(name__icontains=search)

        total = qs.count()
        customers = qs.annotate(accounts_count=Count('accounts', filter=Q(accounts__archived_at__isnull=True))).order_by('-updated_at')[skip:skip + take]

        actor_ids = set()
        for c in customers:
            if c.created_by_id:
                actor_ids.add(c.created_by_id)
            if c.updated_by_id:
                actor_ids.add(c.updated_by_id)

        user_map = {u.id: u.name for u in User.objects.filter(id__in=actor_ids)}

        items = []
        for c in customers:
            items.append({
                'id': c.id,
                'name': c.name,
                'businessCategory': c.business_category,
                'status': c.status,
                'handledBy': c.handled_by,
                'planDetails': c.plan_details,
                'notes': c.notes,
                'createdById': c.created_by_id,
                'updatedById': c.updated_by_id,
                'createdByName': user_map.get(c.created_by_id),
                'updatedByName': user_map.get(c.updated_by_id),
                'createdAt': c.created_at.isoformat() if c.created_at else None,
                'updatedAt': c.updated_at.isoformat() if c.updated_at else None,
                '_count': {'accounts': c.accounts_count}
            })

        return Response({
            'items': items,
            'total': total,
            'page': page
        })

    def post(self, request):
        user = request.user
        data = request.data

        name = data.get('name', '').strip()
        if not name:
            return Response({'success': False, 'message': 'Customer name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        category = data.get('businessCategory')
        if category and not SmBusinessCategory.objects.filter(name=category.strip()).exists():
            return Response({'success': False, 'message': 'Select a valid business category from the master list.'}, status=status.HTTP_400_BAD_REQUEST)

        accounts_data = data.get('accounts', [])
        contacts_data = data.get('contacts', [])
        addresses_data = data.get('addresses', [])

        prepared_accounts = []
        for acc in accounts_data:
            platform_id = acc.get('platformId')
            platform = SmPlatform.objects.filter(id=platform_id, is_active=True).first() if platform_id else None
            if not platform:
                return Response({'success': False, 'message': 'Select an active platform from Platform Master.'}, status=status.HTTP_400_BAD_REQUEST)

            pwd = acc.get('password')
            acc_type = acc.get('accessType', 'password')
            acc_status = acc.get('accessStatus', 'available')
            if acc_type == 'password' and acc_status == 'available' and not pwd:
                return Response({'success': False, 'message': 'Account password is required for available password-login access.'}, status=status.HTTP_400_BAD_REQUEST)

            seal_data = seal(pwd) if pwd else None
            prepared_accounts.append({
                'platform': platform.name,
                'platform_record': platform,
                'label': acc.get('label'),
                'handle': acc.get('handle'),
                'profile_url': acc.get('profileUrl'),
                'login_email': acc.get('loginEmail'),
                'login_phone': acc.get('loginPhone'),
                'account_user_id': acc.get('accountUserId'),
                'access_type': acc_type,
                'access_status': acc_status,
                'notes': acc.get('notes'),
                'managers': acc.get('managers', []),
                'seal': seal_data,
            })

        with transaction.atomic():
            cust = SmCustomer.objects.create(
                name=name,
                business_category=category or None,
                status=data.get('status', 'active'),
                handled_by=data.get('handledBy') or None,
                plan_details=data.get('planDetails') or None,
                notes=data.get('notes') or None,
                created_by_id=user.id,
                updated_by_id=user.id
            )

            for ct in contacts_data:
                SmContact.objects.create(
                    customer=cust,
                    name=ct.get('name') or None,
                    designation=ct.get('designation') or None,
                    kind=ct.get('kind', 'email'),
                    value=ct.get('value', ''),
                    is_primary=bool(ct.get('isPrimary', False))
                )

            for addr in addresses_data:
                SmAddress.objects.create(
                    customer=cust,
                    label=addr.get('label') or None,
                    address=addr.get('address', '')
                )

            for pa in prepared_accounts:
                managers = pa.pop('managers', [])
                seal_val = pa.pop('seal', None)

                account = SmAccount.objects.create(customer=cust, **pa)

                for mgr in managers:
                    SmAccountManager.objects.create(
                        account=account,
                        name=mgr.get('name') or None,
                        email=mgr.get('email', ''),
                        contact=mgr.get('contact') or None
                    )

                if seal_val:
                    SmCredentialVersion.objects.create(
                        account=account,
                        version=1,
                        created_by_id=user.id,
                        **seal_val
                    )

            SmAuditEvent.objects.create(
                customer=cust,
                actor_id=user.id,
                action='customer.created',
                subject='customer',
                changes={'socialAccountCount': len(prepared_accounts)}
            )

        return Response({'success': True, 'id': cust.id, 'name': cust.name}, status=status.HTTP_201_CREATED)


class SmCustomerDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, id):
        cust = SmCustomer.objects.filter(id=id, archived_at__isnull=True).prefetch_related(
            'contacts', 'addresses', 'accounts__platform_record', 'accounts__managers', 'accounts__versions'
        ).first()

        if not cust:
            return Response({'success': False, 'message': 'Social media customer not found.'}, status=status.HTTP_404_NOT_FOUND)

        users = {u.id: u.name for u in User.objects.filter(id__in=[cust.created_by_id, cust.updated_by_id])}

        accounts_list = []
        for a in cust.accounts.filter(archived_at__isnull=True):
            platform_data = None
            if a.platform_record:
                platform_data = {
                    'id': a.platform_record.id,
                    'name': a.platform_record.name,
                    'code': a.platform_record.code,
                    'iconKey': a.platform_record.icon_key,
                    'logoData': a.platform_record.logo_data,
                    'isActive': bool(a.platform_record.is_active),
                }

            managers_data = [{
                'id': m.id, 'name': m.name, 'email': m.email, 'contact': m.contact
            } for m in a.managers.all()]

            accounts_list.append({
                'id': a.id,
                'platform': a.platform,
                'platformId': a.platform_record_id,
                'label': a.label,
                'handle': a.handle,
                'profileUrl': a.profile_url,
                'loginEmail': a.login_email,
                'loginPhone': a.login_phone,
                'accountUserId': a.account_user_id,
                'accessType': a.access_type,
                'accessStatus': a.access_status,
                'notes': a.notes,
                'platformRecord': platform_data,
                'managers': managers_data,
                'updatedAt': a.updated_at.isoformat() if a.updated_at else None,
                '_count': {'versions': a.versions.count()}
            })

        return Response({
            'id': cust.id,
            'name': cust.name,
            'businessCategory': cust.business_category,
            'status': cust.status,
            'handledBy': cust.handled_by,
            'planDetails': cust.plan_details,
            'notes': cust.notes,
            'createdById': cust.created_by_id,
            'updatedById': cust.updated_by_id,
            'createdByName': users.get(cust.created_by_id),
            'updatedByName': users.get(cust.updated_by_id),
            'createdAt': cust.created_at.isoformat() if cust.created_at else None,
            'updatedAt': cust.updated_at.isoformat() if cust.updated_at else None,
            'contacts': [{
                'id': ct.id, 'name': ct.name, 'designation': ct.designation,
                'kind': ct.kind, 'value': ct.value, 'isPrimary': bool(ct.is_primary)
            } for ct in cust.contacts.all()],
            'addresses': [{
                'id': addr.id, 'label': addr.label, 'address': addr.address
            } for addr in cust.addresses.all()],
            'accounts': accounts_list
        })

    def patch(self, request, id):
        cust = SmCustomer.objects.filter(id=id, archived_at__isnull=True).first()
        if not cust:
            return Response({'success': False, 'message': 'Social media customer not found.'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        user = request.user

        category = data.get('businessCategory')
        if category and not SmBusinessCategory.objects.filter(name=category.strip()).exists():
            return Response({'success': False, 'message': 'Select a valid business category from the master list.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for k, attr in [
                ('name', 'name'), ('businessCategory', 'business_category'), ('status', 'status'),
                ('handledBy', 'handled_by'), ('planDetails', 'plan_details'), ('notes', 'notes')
            ]:
                if k in data:
                    setattr(cust, attr, data[k] or None)

            cust.updated_by_id = user.id
            cust.save()

            if 'contacts' in data:
                cust.contacts.all().delete()
                for ct in data['contacts']:
                    SmContact.objects.create(
                        customer=cust,
                        name=ct.get('name') or None,
                        designation=ct.get('designation') or None,
                        kind=ct.get('kind', 'email'),
                        value=ct.get('value', ''),
                        is_primary=bool(ct.get('isPrimary', False))
                    )

            if 'addresses' in data:
                cust.addresses.all().delete()
                for addr in data['addresses']:
                    SmAddress.objects.create(
                        customer=cust,
                        label=addr.get('label') or None,
                        address=addr.get('address', '')
                    )

            SmAuditEvent.objects.create(
                customer=cust,
                actor_id=user.id,
                action='customer.updated',
                subject='customer',
                changes={'status': cust.status}
            )

        return Response({'success': True, 'id': cust.id})

    def delete(self, request, id):
        cust = SmCustomer.objects.filter(id=id, archived_at__isnull=True).first()
        if not cust:
            return Response({'success': False, 'message': 'Social media customer not found.'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            cust.archived_at = datetime.now(timezone.utc)
            cust.status = 'archived'
            cust.updated_by_id = request.user.id
            cust.save()

            SmAuditEvent.objects.create(
                customer=cust,
                actor_id=request.user.id,
                action='customer.archived',
                subject='customer'
            )

        return Response({'id': cust.id, 'archived': True})


class SmCustomerHistoryView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, id):
        page = max(1, int(request.query_params.get('page', 1)))
        take = 30
        skip = (page - 1) * take

        events = SmAuditEvent.objects.filter(customer_id=id).order_by('-created_at')[skip:skip + take]
        results = [{
            'id': e.id,
            'actorId': e.actor_id,
            'action': e.action,
            'subject': e.subject,
            'changes': e.changes,
            'createdAt': e.created_at.isoformat() if e.created_at else None
        } for e in events]

        return Response(results)


class SmPlatformsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        platforms = SmPlatform.objects.all().order_by('name')
        results = [{
            'id': p.id,
            'name': p.name,
            'code': p.code,
            'iconKey': p.icon_key,
            'logoData': p.logo_data,
            'isActive': bool(p.is_active),
            'createdAt': p.created_at.isoformat() if p.created_at else None
        } for p in platforms]
        return Response(results)

    def post(self, request):
        name = request.data.get('name', '').strip()
        if not name:
            return Response({'success': False, 'message': 'Platform name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        code = name.lower().replace(' ', '-').strip('-')[:95]
        logo_data = request.data.get('logoData')

        if SmPlatform.objects.filter(Q(name=name) | Q(code=code)).exists():
            return Response({'success': False, 'message': 'Platform already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        icon_key = code if code in ['instagram', 'facebook', 'youtube', 'whatsapp', 'linkedin', 'x', 'pinterest', 'tiktok'] else ('google' if code == 'google-business-profile' else None)

        p = SmPlatform.objects.create(
            name=name,
            code=code,
            icon_key=icon_key,
            logo_data=logo_data,
            created_by_id=request.user.id
        )

        return Response({
            'id': p.id,
            'name': p.name,
            'code': p.code,
            'iconKey': p.icon_key,
            'isActive': bool(p.is_active)
        }, status=status.HTTP_201_CREATED)


class SmPlatformDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, platformId):
        p = SmPlatform.objects.filter(id=platformId).first()
        if not p:
            return Response({'success': False, 'message': 'Platform not found.'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        if 'name' in data and data['name'].strip():
            p.name = data['name'].strip()
        if 'isActive' in data:
            p.is_active = bool(data['isActive'])
        if 'logoData' in data:
            p.logo_data = data['logoData']

        p.save()
        return Response({'id': p.id, 'name': p.name, 'isActive': bool(p.is_active)})


class SmBusinessCategoriesView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        cats = SmBusinessCategory.objects.all().order_by('name')
        return Response([{'id': c.id, 'name': c.name, 'createdAt': c.created_at.isoformat() if c.created_at else None} for c in cats])

    def post(self, request):
        name = request.data.get('name', '').strip()
        if not name:
            return Response({'success': False, 'message': 'Category name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if SmBusinessCategory.objects.filter(name=name).exists():
            return Response({'success': False, 'message': 'Business category already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        cat = SmBusinessCategory.objects.create(name=name, created_by_id=request.user.id)
        return Response({'id': cat.id, 'name': cat.name}, status=status.HTTP_201_CREATED)


class SmBusinessCategoryDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, categoryId):
        cat = SmBusinessCategory.objects.filter(id=categoryId).first()
        if not cat:
            return Response({'success': False, 'message': 'Business category not found.'}, status=status.HTTP_404_NOT_FOUND)

        name = request.data.get('name', '').strip()
        if not name:
            return Response({'success': False, 'message': 'Category name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if SmBusinessCategory.objects.filter(name=name).exclude(id=categoryId).exists():
            return Response({'success': False, 'message': 'Business category already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        old_name = cat.name
        cat.name = name
        cat.save(update_fields=['name'])

        SmCustomer.objects.filter(business_category=old_name).update(business_category=name, updated_by_id=request.user.id)
        return Response({'id': cat.id, 'name': cat.name})


class SmTermsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        latest = SmTermsVersion.objects.order_by('-version').first()
        if not latest:
            return Response(None)
        return Response({
            'id': latest.id,
            'version': latest.version,
            'title': latest.title,
            'body': latest.body,
            'createdAt': latest.created_at.isoformat() if latest.created_at else None
        })

    def post(self, request):
        title = request.data.get('title', '').strip()
        body = request.data.get('body', '').strip()

        if not title or not body:
            return Response({'success': False, 'message': 'Title and Body are required.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            latest = SmTermsVersion.objects.order_by('-version').first()
            next_ver = (latest.version + 1) if latest else 1

            term = SmTermsVersion.objects.create(
                version=next_ver,
                title=title,
                body=body,
                created_by_id=request.user.id
            )

        return Response({
            'id': term.id,
            'version': term.version,
            'title': term.title,
            'body': term.body,
            'createdAt': term.created_at.isoformat() if term.created_at else None
        }, status=status.HTTP_201_CREATED)


class SmTermsHistoryView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        history = SmTermsVersion.objects.order_by('-version')
        return Response([{
            'id': t.id,
            'version': t.version,
            'title': t.title,
            'body': t.body,
            'createdById': t.created_by_id,
            'createdAt': t.created_at.isoformat() if t.created_at else None
        } for t in history])


class SmContractListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, id):
        contracts = SmContract.objects.filter(customer_id=id).select_related('terms_version').order_by('-created_at')
        return Response([{
            'id': c.id,
            'startsAt': c.starts_at.isoformat() if c.starts_at else None,
            'endsAt': c.ends_at.isoformat() if c.ends_at else None,
            'amount': str(c.amount),
            'frequency': c.frequency,
            'createdAt': c.created_at.isoformat() if c.created_at else None,
            'createdById': c.created_by_id,
            'status': c.status,
            'termsVersion': {
                'version': c.terms_version.version,
                'title': c.terms_version.title
            }
        } for c in contracts])

    def post(self, request, id):
        customer = SmCustomer.objects.filter(id=id, archived_at__isnull=True).prefetch_related('contacts', 'addresses', 'accounts').first()
        if not customer:
            return Response({'success': False, 'message': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)

        terms = SmTermsVersion.objects.order_by('-version').first()
        if not terms:
            return Response({'success': False, 'message': 'Create and save Terms & Conditions before generating a contract.'}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        start_date_str = data.get('startDate')
        end_date_str = data.get('endDate')
        amount_val = data.get('amount')
        frequency = data.get('frequency', 'monthly')

        try:
            start_date = datetime.fromisoformat(str(start_date_str).replace('Z', '+00:00'))
            end_date = datetime.fromisoformat(str(end_date_str).replace('Z', '+00:00'))
            amount = float(amount_val)
        except Exception:
            return Response({'success': False, 'message': 'Invalid dates or amount.'}, status=status.HTTP_400_BAD_REQUEST)

        if start_date >= end_date:
            return Response({'success': False, 'message': 'End date must be later than start date.'}, status=status.HTTP_400_BAD_REQUEST)

        snapshot_input = {
            'customer': {
                'name': customer.name,
                'businessCategory': customer.business_category,
                'status': customer.status,
                'handledBy': customer.handled_by,
                'planDetails': customer.plan_details,
            },
            'start': start_date_str,
            'end': end_date_str,
            'amount': f"{amount:.2f}",
            'frequency': frequency,
            'terms': {
                'version': terms.version,
                'title': terms.title,
                'body': terms.body,
            },
            'generatedAt': datetime.now(timezone.utc).isoformat()
        }

        pdf_bytes = make_contract_pdf(snapshot_input)
        s3_key = f"social-media-contracts/{customer.id}/{uuid.uuid4()}.pdf"

        try:
            s3_upload(s3_key, pdf_bytes, 'application/pdf')
        except Exception as e:
            return Response({'success': False, 'message': f'Failed to store contract PDF: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        with transaction.atomic():
            contract = SmContract.objects.create(
                customer=customer,
                terms_version=terms,
                starts_at=start_date,
                ends_at=end_date,
                amount=f"{amount:.2f}",
                frequency=frequency,
                s3_key=s3_key,
                status='ready',
                snapshot=snapshot_input,
                created_by_id=request.user.id
            )

            SmAuditEvent.objects.create(
                customer=customer,
                actor_id=request.user.id,
                action='contract.generated',
                subject=f"contract:{contract.id}",
                changes={'contractId': contract.id, 'termsVersion': terms.version, 'frequency': frequency}
            )

        return Response({
            'id': contract.id,
            'createdAt': contract.created_at.isoformat() if contract.created_at else None,
            'termsVersion': terms.version
        }, status=status.HTTP_201_CREATED)


class SmContractPdfDownloadView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, id, contractId):
        contract = SmContract.objects.filter(id=contractId, customer_id=id).first()
        if not contract:
            return Response({'success': False, 'message': 'Contract not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            s3 = get_s3_client()
            obj = s3.get_object(Bucket=settings.AWS_S3_BUCKET_NAME, Key=contract.s3_key)
            pdf_data = obj['Body'].read()
        except Exception as e:
            # Fallback generate dynamically from snapshot if s3 file isn't reachable
            pdf_data = make_contract_pdf(contract.snapshot)

        response = HttpResponse(pdf_data, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="social-media-contract-{contractId}.pdf"'
        response['Cache-Control'] = 'no-store, private'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class SmAccountActionView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, id):
        # Add account
        customer = SmCustomer.objects.filter(id=id, archived_at__isnull=True).first()
        if not customer:
            return Response({'success': False, 'message': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        platform_id = data.get('platformId')
        platform = SmPlatform.objects.filter(id=platform_id, is_active=True).first() if platform_id else None
        if not platform:
            return Response({'success': False, 'message': 'Select an active platform from Platform Master.'}, status=status.HTTP_400_BAD_REQUEST)

        pwd = data.get('password')
        seal_data = seal(pwd) if pwd else None

        with transaction.atomic():
            account = SmAccount.objects.create(
                customer=customer,
                platform=platform.name,
                platform_record=platform,
                label=data.get('label') or None,
                handle=data.get('handle') or None,
                profile_url=data.get('profileUrl') or None,
                login_email=data.get('loginEmail') or None,
                login_phone=data.get('loginPhone') or None,
                account_user_id=data.get('accountUserId') or None,
                access_type=data.get('accessType', 'password'),
                access_status=data.get('accessStatus', 'available'),
                notes=data.get('notes') or None
            )

            for mgr in data.get('managers', []):
                SmAccountManager.objects.create(
                    account=account,
                    name=mgr.get('name') or None,
                    email=mgr.get('email', ''),
                    contact=mgr.get('contact') or None
                )

            if seal_data:
                SmCredentialVersion.objects.create(
                    account=account,
                    version=1,
                    created_by_id=request.user.id,
                    **seal_data
                )

            SmAuditEvent.objects.create(
                customer=customer,
                actor_id=request.user.id,
                action='account.created',
                subject=f"account:{account.id}",
                changes={'platform': platform.name}
            )

        return Response({'success': True, 'id': account.id})

    def patch(self, request, id, aid):
        account = SmAccount.objects.filter(id=aid, customer_id=id, archived_at__isnull=True).first()
        if not account:
            return Response({'success': False, 'message': 'Account not found.'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        platform_id = data.get('platformId')
        if platform_id:
            platform = SmPlatform.objects.filter(id=platform_id).first()
            if platform:
                account.platform = platform.name
                account.platform_record = platform

        for k, attr in [
            ('label', 'label'), ('handle', 'handle'), ('profileUrl', 'profile_url'),
            ('loginEmail', 'login_email'), ('loginPhone', 'login_phone'),
            ('accountUserId', 'account_user_id'), ('accessType', 'access_type'),
            ('accessStatus', 'access_status'), ('notes', 'notes')
        ]:
            if k in data:
                setattr(account, attr, data[k] or None)

        pwd = data.get('password')
        seal_data = seal(pwd) if pwd else None

        with transaction.atomic():
            account.save()

            if 'managers' in data:
                account.managers.all().delete()
                for mgr in data['managers']:
                    SmAccountManager.objects.create(
                        account=account,
                        name=mgr.get('name') or None,
                        email=mgr.get('email', ''),
                        contact=mgr.get('contact') or None
                    )

            if seal_data:
                latest = SmCredentialVersion.objects.filter(account=account).order_by('-version').first()
                next_v = (latest.version + 1) if latest else 1
                SmCredentialVersion.objects.create(
                    account=account,
                    version=next_v,
                    created_by_id=request.user.id,
                    **seal_data
                )

            SmAuditEvent.objects.create(
                customer_id=id,
                actor_id=request.user.id,
                action='account.updated',
                subject=f"account:{aid}",
                changes={'status': account.access_status}
            )

        return Response({'success': True, 'id': account.id})

    def delete(self, request, id, aid):
        account = SmAccount.objects.filter(id=aid, customer_id=id, archived_at__isnull=True).first()
        if not account:
            return Response({'success': False, 'message': 'Account not found.'}, status=status.HTTP_404_NOT_FOUND)

        account.archived_at = datetime.now(timezone.utc)
        account.save(update_fields=['archived_at'])

        SmAuditEvent.objects.create(
            customer_id=id,
            actor_id=request.user.id,
            action='account.archived',
            subject=f"account:{aid}"
        )

        return Response({'archived': True})


class SmAccountVersionsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, id, aid):
        versions = SmCredentialVersion.objects.filter(account_id=aid).order_by('-version')
        return Response([{
            'id': v.id,
            'version': v.version,
            'createdById': v.created_by_id,
            'createdAt': v.created_at.isoformat() if v.created_at else None,
            'keyVersion': v.key_version
        } for v in versions])


class SmAccountRevealView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, id, aid, vid):
        user = request.user
        login_password = request.data.get('loginPassword', '')
        reason = request.data.get('reason', '')

        if not verify_password(login_password, user.password):
            SmAuditEvent.objects.create(
                customer_id=id,
                actor_id=user.id,
                action='credential.reveal_denied',
                subject=f"account:{aid}",
                changes={'reason': 'reauthentication_failed'}
            )
            return Response({'success': False, 'message': 'Credential verification failed.'}, status=status.HTTP_401_UNAUTHORIZED)

        row = SmCredentialVersion.objects.filter(id=vid, account_id=aid).first()
        if not row:
            return Response({'success': False, 'message': 'Credential version not found.'}, status=status.HTTP_404_NOT_FOUND)

        SmAuditEvent.objects.create(
            customer_id=id,
            actor_id=user.id,
            action='credential.revealed',
            subject=f"account:{aid}/version:{row.version}",
            changes={'reason': reason}
        )

        plaintext = unseal(row)
        return Response({'password': plaintext, 'version': row.version})
