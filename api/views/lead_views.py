import io
import csv
from datetime import datetime, timezone, timedelta
import openpyxl
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.db.models import Count, Q

from api.models import Lead, DomainType, User, TeamMember, LeadAssignmentHistory, Customer, LeadNote, LeadFollowUp
from api.permissions import IsAuthenticated, IsAdminUser
from api.helpers import safe_user, present_lead, create_audit_log
from api.import_util import (
    clean_email, norm_phone, norm_website, map_import_row, validate_import_row
)
from api.views.domain_views import DomainEligibleAssigneesView


def get_view_scope(user):
    if user.role in ['admin', 'super_admin']:
        return Q()
    return Q(assigned_to_id=user.id)


def check_duplicate_lead(d, exclude_id=None):
    email = clean_email(d.get('email')) or ''
    phone = norm_phone(d.get('phone'))
    website = norm_website(d.get('website'))

    if not email and not phone and not website:
        return None

    qs = Lead.objects.all()
    if exclude_id:
        qs = qs.exclude(id=exclude_id)

    q_or = Q()
    if email:
        q_or |= Q(email=email)
    if phone:
        q_or |= Q(phone__isnull=False)
    if website:
        q_or |= Q(website__isnull=False)

    candidates = list(qs.filter(q_or)[:500])
    for c in candidates:
        if email and clean_email(c.email) == email:
            return c
        if phone and norm_phone(c.phone) == phone:
            return c
        if website and norm_website(c.website) == website:
            return c

    return None


class LeadListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        scope = request.query_params.get('scope', 'my')
        q_filter = Q()

        if user.role == 'lead_user':
            if scope == 'uploaded':
                q_filter &= Q(created_by_id=user.id)
            elif scope == 'lost':
                q_filter &= Q(assigned_to_id=user.id, status='lost')
            else:
                q_filter &= Q(assigned_to_id=user.id)
        else:
            if scope == 'my':
                q_filter &= Q(assigned_to_id=user.id)
            elif scope == 'uploaded':
                q_filter &= Q(created_by_id=user.id)
            elif scope == 'lost':
                q_filter &= Q(status='lost')
            elif scope == 'unassigned':
                q_filter &= Q(assigned_to__isnull=True)

        search = request.query_params.get('search', '').strip()
        if search:
            q_filter &= (
                Q(name__icontains=search) |
                Q(email__icontains=search) |
                Q(company__icontains=search) |
                Q(city__icontains=search) |
                Q(state__icontains=search)
            )

        status_param = request.query_params.get('status')
        if status_param and status_param != 'all':
            q_filter &= Q(status=status_param)

        domain_type_id = request.query_params.get('domainTypeId')
        if domain_type_id:
            q_filter &= Q(domain_type_id=domain_type_id)

        assigned_to_id = request.query_params.get('assignedToId')
        if assigned_to_id:
            q_filter &= Q(assigned_to_id=assigned_to_id)

        source = request.query_params.get('source')
        if source and source != 'all':
            q_filter &= Q(source=source)

        order_by = 'created_at' if request.query_params.get('sort') == 'oldest' else '-created_at'
        rows = Lead.objects.filter(q_filter).select_related(
            'domain_type', 'assigned_to', 'created_by'
        ).prefetch_related('notes', 'follow_ups').order_by(order_by)

        leads_data = [present_lead(l) for l in rows]
        return Response({
            'success': True,
            'count': len(leads_data),
            'leads': leads_data
        })

    def post(self, request):
        user = request.user
        data = request.data

        name = data.get('name', '').strip()
        if not name:
            return Response({'success': False, 'message': 'Name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        domain_type_id = data.get('domainTypeId')
        if not domain_type_id:
            return Response({'success': False, 'message': 'Domain type is required.'}, status=status.HTTP_400_BAD_REQUEST)

        domain = DomainType.objects.filter(id=domain_type_id, is_active=True).first()
        if not domain:
            return Response({'success': False, 'message': 'Domain type does not exist or is inactive.'}, status=status.HTTP_400_BAD_REQUEST)

        assigned_to_id = data.get('assignedToId')
        assignee = None
        if assigned_to_id and assigned_to_id != 'unassigned':
            assignee = User.objects.filter(id=assigned_to_id, role__in=['admin', 'lead_user'], is_active=True).first()
            if not assignee:
                return Response({'success': False, 'message': 'Selected assignee is not available.'}, status=status.HTTP_400_BAD_REQUEST)

            eligible = TeamMember.objects.filter(
                user_id=assignee.id,
                team__domain_type_id=domain.id,
                team__is_active=True
            ).exists()
            if not eligible:
                return Response({'success': False, 'message': 'Selected assignee must be an active member of this Domain Type team.'}, status=status.HTTP_400_BAD_REQUEST)

        duplicate = check_duplicate_lead(data)
        if duplicate:
            return Response({
                'success': False,
                'message': f'Possible duplicate lead: {duplicate.name}. Email, phone or website already matches an existing lead.'
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            lead = Lead.objects.create(
                name=name,
                email=clean_email(data.get('email')),
                phone=data.get('phone') or None,
                company=data.get('company') or None,
                message=data.get('message') or None,
                website=data.get('website') or None,
                address=data.get('address') or None,
                primary_domain=domain.name,
                final_domain=data.get('finalDomain') or None,
                country=data.get('country') or None,
                state=data.get('state') or None,
                city=data.get('city') or None,
                pincode=data.get('pincode') or None,
                source=data.get('source') or 'Website',
                status='new',
                creation_method='manual',
                created_by=user,
                assigned_to=assignee,
                domain_type=domain
            )

            if assignee:
                LeadAssignmentHistory.objects.create(
                    lead=lead,
                    to_user=assignee,
                    performed_by=user,
                    action='assigned'
                )

            create_audit_log(
                actor_id=user.id,
                entity_type='lead',
                entity_id=lead.id,
                action='lead_created',
                new_value={'domainTypeId': domain.id, 'assignedToId': assignee.id if assignee else None, 'method': 'manual'}
            )

        lead.refresh_from_db()
        return Response({
            'success': True,
            'message': 'Lead created and assigned successfully.' if assignee else 'Lead created and added to Unassigned.',
            'lead': present_lead(lead)
        }, status=status.HTTP_201_CREATED)


class LeadStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        scope_q = get_view_scope(user)

        total = Lead.objects.filter(scope_q).count()

        statuses = [
            'new', 'contacted', 'replied', 'interested',
            'meeting_scheduled', 'proposal_sent', 'negotiation', 'won', 'lost'
        ]
        status_counts = Lead.objects.filter(scope_q).values('status').annotate(c=Count('id'))
        s_map = {item['status']: item['c'] for item in status_counts}
        stats_dict = {s: s_map.get(s, 0) for s in statuses}
        stats_dict['total'] = total
        converted = stats_dict.get('won', 0)
        stats_dict['converted'] = converted
        stats_dict['conversionRate'] = round((converted / total * 100), 1) if total > 0 else 0

        sources_counts = Lead.objects.filter(scope_q).values('source').annotate(c=Count('id'))
        sources_list = [{'_id': sc['source'], 'count': sc['c']} for sc in sources_counts]

        return Response({
            'success': True,
            'stats': stats_dict,
            'sources': sources_list
        })


class LeadDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        scope_q = get_view_scope(user)

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        seven_days_ago = today_start - timedelta(days=6)
        tomorrow_start = today_start + timedelta(days=1)

        new_count = Lead.objects.filter(
            scope_q, status='new', created_at__gte=seven_days_ago, created_at__lt=tomorrow_start
        ).count()
        won_count = Lead.objects.filter(
            scope_q, status='won', won_at__gte=seven_days_ago, won_at__lt=tomorrow_start
        ).count()
        lost_count = Lead.objects.filter(
            scope_q, status='lost', lost_at__gte=seven_days_ago, lost_at__lt=tomorrow_start
        ).count()

        conversion_trend = []
        for i in range(6, -1, -1):
            day_start = today_start - timedelta(days=i)
            day_end = day_start + timedelta(days=1)

            w = Lead.objects.filter(scope_q, status='won', won_at__gte=day_start, won_at__lt=day_end).count()
            l = Lead.objects.filter(scope_q, status='lost', lost_at__gte=day_start, lost_at__lt=day_end).count()

            conversion_trend.append({
                'date': day_start.strftime('%Y-%m-%d'),
                'won': w,
                'lost': l
            })

        return Response({
            'success': True,
            'stats': {
                'new': new_count,
                'won': won_count,
                'lost': lost_count,
            },
            'conversionTrend': conversion_trend
        })


class LeadAdvancedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        scope_q = get_view_scope(user)

        source_groups = Lead.objects.filter(
            scope_q, status__in=['won', 'lost']
        ).values('source', 'status').annotate(c=Count('id'))

        source_map = {}
        for g in source_groups:
            src = g['source'] or 'Unknown'
            if src not in source_map:
                source_map[src] = {'source': g['source'], 'won': 0, 'lost': 0}
            source_map[src][g['status']] = g['c']

        lost_groups = Lead.objects.filter(
            scope_q, status='lost'
        ).values('lost_reason').annotate(c=Count('id')).order_by('-c')

        return Response({
            'success': True,
            'sourceConversion': list(source_map.values()),
            'lostReasons': [{'reason': lg['lost_reason'], 'count': lg['c']} for lg in lost_groups]
        })


class LeadFollowUpsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        scope_q = get_view_scope(user)

        leads = Lead.objects.filter(
            scope_q, follow_up_date__isnull=False
        ).select_related('domain_type', 'assigned_to', 'created_by').order_by('follow_up_date')

        all_list = [present_lead(l) for l in leads]

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)

        overdue = []
        today = []
        upcoming = []

        for lead_item in all_list:
            f_str = lead_item.get('followUpDate')
            if not f_str:
                continue
            dt = datetime.fromisoformat(f_str.replace('Z', '+00:00'))
            if dt < today_start:
                overdue.append(lead_item)
            elif dt < tomorrow_start:
                today.append(lead_item)
            else:
                upcoming.append(lead_item)

        return Response({
            'success': True,
            'all': all_list,
            'overdue': overdue,
            'today': today,
            'upcoming': upcoming
        })


class LeadImportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        domain_type_id = request.query_params.get('domainTypeId')
        if not domain_type_id:
            return Response({'success': False, 'message': 'domainTypeId query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        domain = DomainType.objects.filter(id=domain_type_id, is_active=True).first()
        if not domain:
            return Response({'success': False, 'message': 'Domain type does not exist or is inactive.'}, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES.get('file')
        if not file:
            return Response({'success': False, 'message': 'Please upload a spreadsheet file (.xlsx, .xls, or .csv).'}, status=status.HTTP_400_BAD_REQUEST)

        assigned_to_id = request.query_params.get('assignedToId')
        assignee = None
        if assigned_to_id:
            try:
                assignee = User.objects.filter(id=int(assigned_to_id), is_active=True, role__in=['admin', 'lead_user']).first()
            except ValueError:
                assignee = None

        filename = file.name.lower()
        rows_data = []

        if filename.endswith('.csv'):
            try:
                decoded = file.read().decode('utf-8', errors='ignore')
                reader = csv.DictReader(io.StringIO(decoded))
                rows_data = list(reader)
            except Exception as e:
                return Response({'success': False, 'message': f'Failed to parse CSV file: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        elif filename.endswith(('.xlsx', '.xls')):
            try:
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
            except Exception as e:
                return Response({'success': False, 'message': f'Failed to parse Excel file: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'success': False, 'message': 'Unsupported file format. Please upload .xlsx, .xls or .csv.'}, status=status.HTTP_400_BAD_REQUEST)

        if not rows_data:
            return Response({'success': False, 'message': 'No rows were found in the spreadsheet.'}, status=status.HTTP_400_BAD_REQUEST)

        # Existing lead emails and phones
        existing_leads = Lead.objects.values('email', 'phone')
        existing_emails = {clean_email(x['email']) for x in existing_leads if clean_email(x['email'])}
        existing_phones = {norm_phone(x['phone']) for x in existing_leads if norm_phone(x['phone'])}

        seen_emails = set()
        seen_phones = set()

        created_leads = []
        errors = []

        for i, raw_row in enumerate(rows_data):
            x = map_import_row(raw_row)
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
                current_review=x.get('current_review'),
                review_sentiment=x.get('review_sentiment'),
                website_status=x.get('website_status'),
                https=x.get('https'),
                mobile_responsive=x.get('mobile_responsive'),
                page_speed=x.get('page_speed'),
                outdated_indicators=x.get('outdated_indicators'),
                lead_score=x.get('lead_score'),
                google_rating=x.get('google_rating'),
                google_review_count=x.get('google_review_count'),
                google_reviews_url=x.get('google_reviews_url'),
                google_maps_url=x.get('google_maps_url'),
                facebook=x.get('facebook'),
                instagram=x.get('instagram'),
                linkedin=x.get('linkedin'),
                youtube=x.get('youtube'),
                social_media_found=x.get('social_media_found'),
                social_media_links=x.get('social_media_links'),
                email_count=x.get('email_count'),
                email_source=x.get('email_source'),
                email_type=x.get('email_type'),
                all_emails=x.get('all_emails'),
                source=x.get('source') or 'Excel Import',
                status='new',
                creation_method='excel_import',
                created_by=request.user,
                assigned_to=assignee,
                domain_type=domain,
                image_urls=x.get('image_urls'),
                top_comments=x.get('top_comments')
            ))

        if created_leads:
            with transaction.atomic():
                Lead.objects.bulk_create(created_leads)
                create_audit_log(
                    actor_id=request.user.id,
                    entity_type='lead',
                    entity_id=0,
                    action='leads_imported',
                    new_value={'count': len(created_leads), 'domainTypeId': domain.id}
                )

        return Response({
            'success': True,
            'imported': len(created_leads),
            'skipped': len(errors),
            'errors': errors[:50]
        })


class LeadDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _accessible_lead(self, id, user):
        qs = Lead.objects.filter(id=id)
        if user.role == 'lead_user':
            qs = qs.filter(Q(assigned_to_id=user.id) | Q(created_by_id=user.id))
        return qs.select_related('domain_type', 'assigned_to', 'created_by').prefetch_related(
            'notes__created_by', 'follow_ups__created_by', 'assignment_history__from_user', 'assignment_history__to_user'
        ).first()

    def get(self, request, id):
        lead = self._accessible_lead(id, request.user)
        if not lead:
            return Response({'success': False, 'message': 'Lead not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'success': True, 'lead': present_lead(lead)})

    def put(self, request, id):
        lead = self._accessible_lead(id, request.user)
        if not lead:
            return Response({'success': False, 'message': 'Lead not found.'}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == 'lead_user' and lead.assigned_to_id != request.user.id:
            return Response({'success': False, 'message': 'You can modify only a lead assigned to you.'}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        if 'domainTypeId' in data and request.user.role in ['admin', 'super_admin']:
            domain = DomainType.objects.filter(id=data['domainTypeId'], is_active=True).first()
            if domain:
                lead.domain_type = domain
                lead.primary_domain = domain.name

        for k, attr in [
            ('name', 'name'), ('email', 'email'), ('phone', 'phone'),
            ('company', 'company'), ('message', 'message'), ('source', 'source'),
            ('website', 'website'), ('address', 'address'), ('primaryDomain', 'primary_domain'),
            ('finalDomain', 'final_domain'), ('country', 'country'), ('state', 'state'),
            ('city', 'city'), ('pincode', 'pincode'), ('currentReview', 'current_review'),
            ('reviewSentiment', 'review_sentiment'), ('websiteStatus', 'website_status'),
            ('https', 'https'), ('mobileResponsive', 'mobile_responsive'), ('pageSpeed', 'page_speed'),
            ('outdatedIndicators', 'outdated_indicators'), ('googleReviewsUrl', 'google_reviews_url'),
            ('googleMapsUrl', 'google_maps_url'), ('facebook', 'facebook'), ('instagram', 'instagram'),
            ('linkedin', 'linkedin'), ('youtube', 'youtube'), ('socialMediaFound', 'social_media_found'),
            ('socialMediaLinks', 'social_media_links'), ('emailSource', 'email_source'),
            ('emailType', 'email_type'), ('allEmails', 'all_emails'), ('topComments', 'top_comments'),
        ]:
            if k in data:
                setattr(lead, attr, data[k] or None)

        for num_k, attr in [
            ('leadScore', 'lead_score'), ('googleRating', 'google_rating'),
            ('googleReviewCount', 'google_review_count'), ('emailCount', 'email_count')
        ]:
            if num_k in data:
                val = data[num_k]
                setattr(lead, attr, None if val in (None, '') else val)

        if 'imageUrls' in data:
            lead.image_urls = data['imageUrls'] if isinstance(data['imageUrls'], list) and data['imageUrls'] else None

        lead.save()
        return Response({'success': True, 'message': 'Lead updated successfully.', 'lead': present_lead(lead)})

    def delete(self, request, id):
        if request.user.role not in ['admin', 'super_admin']:
            return Response({'success': False, 'message': 'Only administrators can delete leads.'}, status=status.HTTP_403_FORBIDDEN)

        lead = Lead.objects.filter(id=id).first()
        if not lead:
            return Response({'success': False, 'message': 'Lead not found.'}, status=status.HTTP_404_NOT_FOUND)

        if lead.status == 'won' or Customer.objects.filter(lead_id=id).exists():
            return Response({'success': False, 'message': 'Converted customer leads cannot be deleted.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            create_audit_log(
                request.user.id, 'lead', id, 'lead_deleted',
                old_value={'name': lead.name, 'status': lead.status, 'assignedToId': lead.assigned_to_id, 'domainTypeId': lead.domain_type_id}
            )
            lead.delete()

        return Response({'success': True, 'message': 'Lead deleted successfully.'})


class LeadEligibleAssigneesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        lead = Lead.objects.filter(id=id).first()
        if not lead:
            return Response({'success': False, 'message': 'Lead not found.'}, status=status.HTTP_404_NOT_FOUND)

        view = DomainEligibleAssigneesView()
        return view.get(request, lead.domain_type_id)


class LeadAssignUnassignedView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, id, userId):
        lead = Lead.objects.filter(id=id).first()
        if not lead:
            return Response({'success': False, 'message': 'Lead not found.'}, status=status.HTTP_404_NOT_FOUND)

        if lead.status == 'won' or Customer.objects.filter(lead_id=id).exists():
            return Response({'success': False, 'message': 'Converted customer leads cannot be assigned.'}, status=status.HTTP_400_BAD_REQUEST)

        if lead.assigned_to_id:
            return Response({'success': False, 'message': 'Lead is already assigned. Use Transfer instead.'}, status=status.HTTP_400_BAD_REQUEST)

        target = User.objects.filter(id=userId, is_active=True, role__in=['admin', 'lead_user']).first()
        if not target:
            return Response({'success': False, 'message': 'Target user is not available.'}, status=status.HTTP_400_BAD_REQUEST)

        eligible = TeamMember.objects.filter(
            user_id=target.id,
            team__domain_type_id=lead.domain_type_id,
            team__is_active=True
        ).exists()
        if not eligible:
            return Response({'success': False, 'message': 'Target user must be an active member of this Domain Type team.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            lead.assigned_to = target
            lead.save(update_fields=['assigned_to'])

            LeadAssignmentHistory.objects.create(
                lead=lead,
                to_user=target,
                performed_by=request.user,
                action='assigned'
            )
            create_audit_log(
                request.user.id, 'lead', id, 'lead_assigned',
                new_value={'assignedToId': target.id, 'source': 'direct_admin_assignment'}
            )

        return Response({'success': True, 'message': 'Lead assigned successfully.'})


class LeadTransferView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, id, userId):
        lead = Lead.objects.filter(id=id).first()
        if not lead:
            return Response({'success': False, 'message': 'Lead not found.'}, status=status.HTTP_404_NOT_FOUND)

        if lead.status == 'won' or Customer.objects.filter(lead_id=id).exists():
            return Response({'success': False, 'message': 'Converted customer leads cannot be transferred.'}, status=status.HTTP_400_BAD_REQUEST)

        if not lead.assigned_to_id:
            return Response({'success': False, 'message': 'Lead is currently unassigned.'}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.role == 'lead_user' and lead.assigned_to_id != request.user.id:
            return Response({'success': False, 'message': 'You can transfer only your assigned lead.'}, status=status.HTTP_403_FORBIDDEN)

        target = User.objects.filter(id=userId, is_active=True, role__in=['admin', 'lead_user']).first()
        if not target:
            return Response({'success': False, 'message': 'Target user is not available.'}, status=status.HTTP_400_BAD_REQUEST)

        ok = TeamMember.objects.filter(
            user_id=userId,
            team__domain_type_id=lead.domain_type_id,
            team__is_active=True
        ).exists()
        if not ok:
            return Response({'success': False, 'message': 'Transfer is allowed only to an active member of the same Domain Type team.'}, status=status.HTTP_400_BAD_REQUEST)

        old_assignee_id = lead.assigned_to_id

        with transaction.atomic():
            lead.assigned_to = target
            lead.save(update_fields=['assigned_to'])

            LeadAssignmentHistory.objects.create(
                lead=lead,
                from_user_id=old_assignee_id,
                to_user=target,
                performed_by=request.user,
                action='transferred'
            )
            create_audit_log(
                request.user.id, 'lead', id, 'lead_transferred',
                old_value={'assignedToId': old_assignee_id},
                new_value={'assignedToId': target.id}
            )

        return Response({'success': True, 'message': 'Lead transferred successfully.'})


class LeadUnassignView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, id):
        lead = Lead.objects.filter(id=id).first()
        if not lead:
            return Response({'success': False, 'message': 'Lead not found.'}, status=status.HTTP_404_NOT_FOUND)

        if lead.status == 'won' or Customer.objects.filter(lead_id=id).exists():
            return Response({'success': False, 'message': 'Converted customer leads cannot be unassigned.'}, status=status.HTTP_400_BAD_REQUEST)

        if not lead.assigned_to_id:
            return Response({'success': True, 'message': 'Lead is already unassigned.'})

        old_assignee_id = lead.assigned_to_id

        with transaction.atomic():
            lead.assigned_to = None
            lead.save(update_fields=['assigned_to'])

            LeadAssignmentHistory.objects.create(
                lead=lead,
                from_user_id=old_assignee_id,
                performed_by=request.user,
                action='unassigned'
            )
            create_audit_log(
                request.user.id, 'lead', id, 'lead_unassigned',
                old_value={'assignedToId': old_assignee_id},
                new_value={'assignedToId': None}
            )

        return Response({'success': True, 'message': 'Lead unassigned successfully.'})


class LeadStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, id):
        new_status = request.data.get('status')
        if new_status == 'won':
            return Response({'success': False, 'message': 'Use Convert to Customer to mark a lead as won.'}, status=status.HTTP_400_BAD_REQUEST)

        lead = Lead.objects.filter(id=id).first()
        if not lead:
            return Response({'success': False, 'message': 'Lead not found.'}, status=status.HTTP_404_NOT_FOUND)

        if lead.status == 'won' or Customer.objects.filter(lead_id=id).exists():
            return Response({'success': False, 'message': 'A converted customer lead cannot return to the lead pipeline.'}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.role == 'lead_user' and lead.assigned_to_id != request.user.id:
            return Response({'success': False, 'message': 'You can modify only a lead assigned to you.'}, status=status.HTTP_403_FORBIDDEN)

        old_status = lead.status
        old_lost_reason = lead.lost_reason

        now = datetime.now(timezone.utc)
        lead.status = new_status

        if new_status == 'contacted':
            lead.last_contacted_at = now

        if new_status == 'lost':
            lost_reason = request.data.get('lostReason')
            if not lost_reason:
                return Response({'success': False, 'message': 'Lost reason is required.'}, status=status.HTTP_400_BAD_REQUEST)
            lead.lost_reason = lost_reason
            lead.lost_at = now
            lead.won_at = None
        else:
            lead.lost_reason = None
            lead.lost_at = None

        lead.save()

        create_audit_log(
            request.user.id, 'lead', id,
            'lead_marked_lost' if new_status == 'lost' else ('lead_reopened' if old_status == 'lost' else 'lead_status_changed'),
            old_value={'status': old_status, 'lostReason': old_lost_reason},
            new_value={'status': lead.status, 'lostReason': lead.lost_reason}
        )

        return Response({'success': True, 'message': 'Lead status updated.', 'lead': present_lead(lead)})


class LeadLegacyFollowUpView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, id):
        lead = Lead.objects.filter(id=id).first()
        if not lead:
            return Response({'success': False, 'message': 'Lead not found.'}, status=status.HTTP_404_NOT_FOUND)

        date_val = request.data.get('followUpDate')
        parsed = None
        if date_val:
            try:
                parsed = datetime.fromisoformat(str(date_val).replace('Z', '+00:00'))
            except Exception:
                return Response({'success': False, 'message': 'Invalid follow-up date.'}, status=status.HTTP_400_BAD_REQUEST)

        lead.follow_up_date = parsed
        lead.save(update_fields=['follow_up_date'])

        return Response({
            'success': True,
            'message': 'Follow-up saved successfully.' if parsed else 'Follow-up deleted successfully.',
            'lead': present_lead(lead)
        })

    def delete(self, request, id):
        return self.patch(request, id)


class LeadFollowUpCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        lead = Lead.objects.filter(id=id).first()
        if not lead:
            return Response({'success': False, 'message': 'Lead not found.'}, status=status.HTTP_404_NOT_FOUND)

        due_date_str = request.data.get('dueDate')
        if not due_date_str:
            return Response({'success': False, 'message': 'dueDate is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            due_date = datetime.fromisoformat(str(due_date_str).replace('Z', '+00:00'))
        except Exception:
            return Response({'success': False, 'message': 'Invalid due date format.'}, status=status.HTTP_400_BAD_REQUEST)

        note = request.data.get('note', '').strip()

        LeadFollowUp.objects.create(
            lead=lead,
            due_date=due_date,
            note=note or None,
            created_by=request.user
        )

        # Sync nearest pending follow-up date to lead
        earliest = LeadFollowUp.objects.filter(lead=lead, status='pending').order_by('due_date').first()
        lead.follow_up_date = earliest.due_date if earliest else None
        lead.save(update_fields=['follow_up_date'])

        return Response({
            'success': True,
            'message': 'Follow-up scheduled successfully.',
            'lead': present_lead(lead)
        })


class LeadFollowUpStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, id, fid):
        follow_up = LeadFollowUp.objects.filter(id=fid, lead_id=id).first()
        if not follow_up:
            return Response({'success': False, 'message': 'Follow-up not found.'}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('status')
        if new_status:
            follow_up.status = new_status
            follow_up.save(update_fields=['status'])

        lead = Lead.objects.get(id=id)
        earliest = LeadFollowUp.objects.filter(lead=lead, status='pending').order_by('due_date').first()
        lead.follow_up_date = earliest.due_date if earliest else None
        lead.save(update_fields=['follow_up_date'])

        return Response({
            'success': True,
            'message': 'Follow-up updated successfully.',
            'lead': present_lead(lead)
        })

    def delete(self, request, id, fid):
        deleted, _ = LeadFollowUp.objects.filter(id=fid, lead_id=id).delete()
        if not deleted:
            return Response({'success': False, 'message': 'Follow-up not found.'}, status=status.HTTP_404_NOT_FOUND)

        lead = Lead.objects.get(id=id)
        earliest = LeadFollowUp.objects.filter(lead=lead, status='pending').order_by('due_date').first()
        lead.follow_up_date = earliest.due_date if earliest else None
        lead.save(update_fields=['follow_up_date'])

        return Response({
            'success': True,
            'message': 'Follow-up deleted successfully.',
            'lead': present_lead(lead)
        })


class LeadNoteCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        lead = Lead.objects.filter(id=id).first()
        if not lead:
            return Response({'success': False, 'message': 'Lead not found.'}, status=status.HTTP_404_NOT_FOUND)

        text = request.data.get('text', '').strip()
        if not text:
            return Response({'success': False, 'message': 'Note cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)

        LeadNote.objects.create(
            lead=lead,
            text=text,
            created_by=request.user
        )

        return Response({
            'success': True,
            'message': 'Note added successfully.',
            'lead': present_lead(lead)
        })

    def delete(self, request, id, nid):
        deleted, _ = LeadNote.objects.filter(id=nid, lead_id=id).delete()
        if not deleted:
            return Response({'success': False, 'message': 'Note not found.'}, status=status.HTTP_404_NOT_FOUND)

        lead = Lead.objects.get(id=id)
        return Response({
            'success': True,
            'message': 'Note deleted successfully.',
            'lead': present_lead(lead)
        })
