import hmac
import hashlib
import io
import csv
import openpyxl
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.conf import settings
from django.db import transaction

from api.models import User, DomainType, Lead
from api.helpers import verify_password, create_audit_log
from api.import_util import (
    clean_email, norm_phone, map_import_row, validate_import_row
)


def authenticate_integration(request, email, password):
    security_key = request.headers.get('x-import-key')
    configured_key = getattr(settings, 'LEAD_IMPORT_SECURITY_KEY', '').strip()

    if not configured_key or not security_key:
        return None

    h1 = hashlib.sha256(configured_key.encode()).digest()
    h2 = hashlib.sha256(security_key.encode()).digest()
    if not hmac.compare_digest(h1, h2):
        return None

    clean_em = str(email or '').strip().lower()
    if not clean_em or not password:
        return None

    user = User.objects.filter(email=clean_em, is_active=True).first()
    if not user or user.role not in ['lead_user', 'admin', 'super_admin']:
        return None

    if not verify_password(password, user.password):
        return None

    return user


class IntegrationImportLeadsView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data
        user = authenticate_integration(request, data.get('email'), data.get('password'))
        if not user:
            return Response({'success': False, 'message': 'Invalid integration credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        domain_type_id = data.get('domainTypeId')
        if not domain_type_id:
            return Response({'success': False, 'message': 'domainTypeId is required.'}, status=status.HTTP_400_BAD_REQUEST)

        domain = DomainType.objects.filter(id=domain_type_id, is_active=True).first()
        if not domain:
            return Response({'success': False, 'message': 'This domain does not exist. Please contact your admin.'}, status=status.HTTP_400_BAD_REQUEST)

        leads_input = data.get('leads', [])
        if not leads_input or not isinstance(leads_input, list):
            return Response({'success': False, 'message': 'At least one lead is required.'}, status=status.HTTP_400_BAD_REQUEST)

        existing_leads = Lead.objects.values('email', 'phone')
        existing_emails = {clean_email(x['email']) for x in existing_leads if clean_email(x['email'])}
        existing_phones = {norm_phone(x['phone']) for x in existing_leads if norm_phone(x['phone'])}

        seen_emails = set()
        seen_phones = set()
        created_leads = []
        errors = []

        for i, raw in enumerate(leads_input):
            x = map_import_row(raw)
            if not x.get('name') and not x.get('phone') and not x.get('email'):
                continue

            if not x.get('name'):
                errors.append({'row': i + 1, 'reason': 'Missing a name/business name.'})
                continue

            err = validate_import_row(x)
            if err:
                errors.append({'row': i + 1, 'reason': err})
                continue

            row_email = clean_email(x.get('email'))
            row_phone = norm_phone(x.get('phone'))

            if row_email and (row_email in existing_emails or row_email in seen_emails):
                errors.append({'row': i + 1, 'reason': f'Duplicate email: {row_email}'})
                continue
            if row_phone and (row_phone in existing_phones or row_phone in seen_phones):
                errors.append({'row': i + 1, 'reason': f'Duplicate phone: {row_phone}'})
                continue

            if row_email:
                seen_emails.add(row_email)
            if row_phone:
                seen_phones.add(row_phone)

            created_leads.append(Lead(
                name=x['name'],
                email=row_email,
                phone=x.get('phone'),
                company=x.get('company'),
                message=x.get('message'),
                website=x.get('website'),
                address=x.get('address'),
                primary_domain=domain.name,
                final_domain=x.get('final_domain'),
                country=x.get('country'),
                state=x.get('state'),
                city=x.get('city'),
                pincode=x.get('pincode'),
                source=x.get('source') or 'External API',
                status='new',
                creation_method='api_import',
                created_by=user,
                domain_type=domain,
                image_urls=x.get('image_urls'),
                top_comments=x.get('top_comments')
            ))

        if created_leads:
            with transaction.atomic():
                Lead.objects.bulk_create(created_leads)
                create_audit_log(
                    actor_id=user.id,
                    entity_type='lead',
                    entity_id=0,
                    action='leads_imported_api',
                    new_value={'count': len(created_leads), 'domainTypeId': domain.id}
                )

        return Response({
            'success': True,
            'imported': len(created_leads),
            'skipped': len(errors),
            'errors': errors
        })


class IntegrationImportLeadsFileView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        user = authenticate_integration(request, request.data.get('email'), request.data.get('password'))
        if not user:
            return Response({'success': False, 'message': 'Invalid integration credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        domain_type_id = request.data.get('domainTypeId')
        if not domain_type_id:
            return Response({'success': False, 'message': 'A valid domainTypeId is required.'}, status=status.HTTP_400_BAD_REQUEST)

        domain = DomainType.objects.filter(id=domain_type_id, is_active=True).first()
        if not domain:
            return Response({'success': False, 'message': 'This domain does not exist. Please contact your admin.'}, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES.get('file')
        if not file:
            return Response({'success': False, 'message': 'Please upload a spreadsheet file in the "file" field.'}, status=status.HTTP_400_BAD_REQUEST)

        # Delegate to import parsing
        filename = file.name.lower()
        rows_data = []

        if filename.endswith('.csv'):
            decoded = file.read().decode('utf-8', errors='ignore')
            reader = csv.DictReader(io.StringIO(decoded))
            rows_data = list(reader)
        elif filename.endswith(('.xlsx', '.xls')):
            wb = openpyxl.load_workbook(file, data_only=True)
            ws = wb.active
            headers = [str(cell.value or '').strip() for cell in ws[1]]
            for row in ws.iter_rows(min_row=2, values_only=True):
                row_dict = {}
                for idx, h in enumerate(headers):
                    if h and idx < len(row):
                        row_dict[h] = row[idx]
                if any(v is not None and str(v).strip() for v in row_dict.values()):
                    rows_data.append(row_dict)

        existing_leads = Lead.objects.values('email', 'phone')
        existing_emails = {clean_email(x['email']) for x in existing_leads if clean_email(x['email'])}
        existing_phones = {norm_phone(x['phone']) for x in existing_leads if norm_phone(x['phone'])}

        seen_emails = set()
        seen_phones = set()
        created_leads = []
        errors = []

        for i, raw in enumerate(rows_data):
            x = map_import_row(raw)
            if not x.get('name') and not x.get('phone') and not x.get('email'):
                continue

            if not x.get('name'):
                errors.append({'row': i + 2, 'reason': 'Missing a name/business name.'})
                continue

            err = validate_import_row(x)
            if err:
                errors.append({'row': i + 2, 'reason': err})
                continue

            row_email = clean_email(x.get('email'))
            row_phone = norm_phone(x.get('phone'))

            if row_email and (row_email in existing_emails or row_email in seen_emails):
                errors.append({'row': i + 2, 'reason': f'Duplicate email: {row_email}'})
                continue
            if row_phone and (row_phone in existing_phones or row_phone in seen_phones):
                errors.append({'row': i + 2, 'reason': f'Duplicate phone: {row_phone}'})
                continue

            if row_email:
                seen_emails.add(row_email)
            if row_phone:
                seen_phones.add(row_phone)

            created_leads.append(Lead(
                name=x['name'],
                email=row_email,
                phone=x.get('phone'),
                company=x.get('company'),
                message=x.get('message'),
                website=x.get('website'),
                address=x.get('address'),
                primary_domain=domain.name,
                final_domain=x.get('final_domain'),
                country=x.get('country'),
                state=x.get('state'),
                city=x.get('city'),
                pincode=x.get('pincode'),
                source=x.get('source') or 'External API File',
                status='new',
                creation_method='api_import',
                created_by=user,
                domain_type=domain,
                image_urls=x.get('image_urls'),
                top_comments=x.get('top_comments')
            ))

        if created_leads:
            with transaction.atomic():
                Lead.objects.bulk_create(created_leads)
                create_audit_log(
                    actor_id=user.id,
                    entity_type='lead',
                    entity_id=0,
                    action='leads_imported_api_file',
                    new_value={'count': len(created_leads), 'domainTypeId': domain.id}
                )

        return Response({
            'success': True,
            'imported': len(created_leads),
            'skipped': len(errors),
            'errors': errors
        })
