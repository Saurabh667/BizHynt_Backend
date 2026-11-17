from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Max, Q

from api.models import User, Lead, Customer, DomainType, Team, AuditLog
from api.permissions import IsAdminUser
from api.helpers import safe_user, present_lead


class AdminOverviewView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        total_users = User.objects.filter(role__in=['admin', 'lead_user'], is_active=True).count()
        total_leads = Lead.objects.count()
        unassigned_leads = Lead.objects.filter(assigned_to__isnull=True).count()
        total_customers = Customer.objects.count()
        total_domains = DomainType.objects.filter(is_active=True).count()
        total_teams = Team.objects.filter(is_active=True).count()

        statuses = [
            'new', 'contacted', 'replied', 'interested',
            'meeting_scheduled', 'proposal_sent', 'negotiation', 'won', 'lost'
        ]
        status_counts = Lead.objects.values('status').annotate(c=Count('id'))
        status_map = {item['status']: item['c'] for item in status_counts}
        status_breakdown = {s: status_map.get(s, 0) for s in statuses}

        won_count = status_breakdown.get('won', 0)
        conversion_rate = round((won_count / total_leads * 100), 1) if total_leads > 0 else 0

        return Response({
            'success': True,
            'overview': {
                'totalUsers': total_users,
                'totalLeads': total_leads,
                'unassignedLeads': unassigned_leads,
                'totalCustomers': total_customers,
                'totalDomains': total_domains,
                'totalTeams': total_teams,
                'statusBreakdown': status_breakdown,
                'conversionRate': conversion_rate,
            }
        })


class AdminCompaniesView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        search = request.query_params.get('search', '').strip()
        qs = User.objects.filter(role__in=['admin', 'lead_user'])
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(email__icontains=search))

        qs = qs.order_by('-created_at')

        results = []
        for u in qs:
            assigned_count = Lead.objects.filter(assigned_to_id=u.id).count()
            uploaded_count = Lead.objects.filter(created_by_id=u.id).count()
            customers_count = Customer.objects.filter(owner_id=u.id).count()
            won_count = Lead.objects.filter(assigned_to_id=u.id, status='won').count()
            lost_count = Lead.objects.filter(assigned_to_id=u.id, status='lost').count()
            last_activity = Lead.objects.filter(assigned_to_id=u.id).aggregate(m=Max('updated_at'))['m']

            results.append({
                'id': u.id,
                '_id': u.id,
                'name': u.name,
                'email': u.email,
                'role': u.role,
                'companyName': u.name,
                'isActive': bool(u.is_active),
                'createdAt': u.created_at.isoformat() if u.created_at else None,
                'totalLeads': assigned_count,
                'uploadedLeads': uploaded_count,
                'customers': customers_count,
                'wonLeads': won_count,
                'lostLeads': lost_count,
                'lastActivityAt': last_activity.isoformat() if last_activity else None,
            })

        return Response({
            'success': True,
            'count': len(results),
            'companies': results
        })


class AdminCompanyDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, id):
        u = User.objects.filter(id=id, role__in=['admin', 'lead_user']).first()
        if not u:
            return Response({'success': False, 'message': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        assigned = Lead.objects.filter(assigned_to_id=id).count()
        uploaded = Lead.objects.filter(created_by_id=id).count()
        won = Lead.objects.filter(assigned_to_id=id, status='won').count()
        lost = Lead.objects.filter(assigned_to_id=id, status='lost').count()

        return Response({
            'success': True,
            'company': {
                'id': u.id,
                '_id': u.id,
                'name': u.name,
                'email': u.email,
                'role': u.role,
                'companyName': u.name,
                'isActive': bool(u.is_active),
                'createdAt': u.created_at.isoformat() if u.created_at else None,
            },
            'stats': {
                'total': assigned,
                'uploaded': uploaded,
                'won': won,
                'lost': lost,
            }
        })


class AdminCompanyLeadsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, id):
        u = User.objects.filter(id=id, role__in=['admin', 'lead_user']).first()
        if not u:
            return Response({'success': False, 'message': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        qs = Lead.objects.filter(assigned_to_id=id)
        stat = request.query_params.get('status')
        if stat and stat != 'all':
            qs = qs.filter(status=stat)

        qs = qs.select_related('domain_type', 'assigned_to', 'created_by').order_by('-created_at')
        leads_list = [present_lead(lead) for lead in qs]

        return Response({
            'success': True,
            'count': len(leads_list),
            'leads': leads_list
        })


class AdminCompanyLeadDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, id, lid):
        lead = Lead.objects.filter(
            id=lid
        ).filter(
            Q(assigned_to_id=id) | Q(created_by_id=id)
        ).select_related('domain_type', 'assigned_to', 'created_by').first()

        if not lead:
            return Response({'success': False, 'message': 'Lead not found.'}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            'success': True,
            'lead': present_lead(lead)
        })


class AdminAllLeadsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = Lead.objects.all()

        stat = request.query_params.get('status')
        if stat and stat != 'all':
            qs = qs.filter(status=stat)

        domain_type_id = request.query_params.get('domainTypeId')
        if domain_type_id:
            qs = qs.filter(domain_type_id=domain_type_id)

        assigned = request.query_params.get('assigned')
        if assigned == 'no':
            qs = qs.filter(assigned_to__isnull=True)
        elif assigned == 'yes':
            qs = qs.filter(assigned_to__isnull=False)

        qs = qs.select_related('domain_type', 'assigned_to', 'created_by').order_by('-created_at')
        leads_list = [present_lead(lead) for lead in qs]

        return Response({
            'success': True,
            'count': len(leads_list),
            'leads': leads_list
        })


class AdminAuditLogsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = AuditLog.objects.all().select_related('actor').order_by('-created_at')

        entity_type = request.query_params.get('entityType')
        if entity_type:
            qs = qs.filter(entity_type=entity_type)

        actor_id = request.query_params.get('actorId')
        if actor_id:
            qs = qs.filter(actor_id=actor_id)

        action = request.query_params.get('action')
        if action:
            qs = qs.filter(action__icontains=action)

        limit = min(int(request.query_params.get('limit', 200)), 500)
        logs = qs[:limit]

        results = []
        for log in logs:
            results.append({
                'id': str(log.id),
                'actorId': log.actor_id,
                'entityType': log.entity_type,
                'entityId': log.entity_id,
                'action': log.action,
                'oldValue': log.old_value,
                'newValue': log.new_value,
                'metadata': log.metadata,
                'createdAt': log.created_at.isoformat() if log.created_at else None,
                'actor': safe_user(log.actor) if log.actor else None
            })

        return Response({
            'success': True,
            'logs': results
        })
