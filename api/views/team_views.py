from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.db.models import Count

from api.models import Team, TeamMember, DomainType, User, Lead, LeadAssignmentHistory
from api.permissions import IsAdminUser
from api.helpers import safe_user, create_audit_log, present_lead


class TeamListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        teams = Team.objects.select_related('domain_type').prefetch_related('members__user').order_by('name')

        results = []
        for t in teams:
            members_data = []
            for m in t.members.all():
                u = m.user
                members_data.append({
                    'teamId': m.team_id,
                    'userId': m.user_id,
                    'addedAt': m.added_at.isoformat() if m.added_at else None,
                    'user': {
                        'id': u.id,
                        'name': u.name,
                        'email': u.email,
                        'role': u.role,
                        'isActive': bool(u.is_active)
                    }
                })

            results.append({
                'id': t.id,
                'name': t.name,
                'domainTypeId': t.domain_type_id,
                'isActive': bool(t.is_active),
                'createdById': t.created_by_id,
                'createdAt': t.created_at.isoformat() if t.created_at else None,
                'updatedAt': t.updated_at.isoformat() if t.updated_at else None,
                'domainType': {
                    'id': t.domain_type.id,
                    'name': t.domain_type.name,
                    'description': t.domain_type.description,
                    'isActive': bool(t.domain_type.is_active),
                },
                'members': members_data,
                '_count': {
                    'members': len(members_data)
                }
            })

        return Response({'success': True, 'teams': results})

    def post(self, request):
        return self._save(request, None)

    def _save(self, request, id):
        name = request.data.get('name', '').strip()
        domain_type_id = request.data.get('domainTypeId')
        member_ids = request.data.get('memberIds', [])

        if not name or not domain_type_id:
            return Response({'success': False, 'message': 'Name and Domain Type are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            domain_type_id = int(domain_type_id)
            member_ids = [int(mid) for mid in member_ids]
        except (ValueError, TypeError):
            return Response({'success': False, 'message': 'Invalid IDs provided.'}, status=status.HTTP_400_BAD_REQUEST)

        if id:
            current = Team.objects.filter(id=id).first()
            if not current:
                return Response({'success': False, 'message': 'Team not found.'}, status=status.HTTP_404_NOT_FOUND)
            if current.domain_type_id != domain_type_id:
                return Response({
                    'success': False,
                    'message': 'A team Domain Type cannot be changed after creation. Create/edit membership within the existing Domain Type instead.'
                }, status=status.HTTP_400_BAD_REQUEST)

        domain = DomainType.objects.filter(id=domain_type_id, is_active=True).first()
        if not domain:
            return Response({'success': False, 'message': 'Active domain type not found.'}, status=status.HTTP_400_BAD_REQUEST)

        existing = Team.objects.filter(domain_type_id=domain_type_id)
        if id:
            existing = existing.exclude(id=id)
        if existing.exists():
            return Response({
                'success': False,
                'message': f'A team already exists for {domain.name}. One Domain Type can have only one Team.'
            }, status=status.HTTP_400_BAD_REQUEST)

        valid_users = list(User.objects.filter(id__in=member_ids, role__in=['admin', 'lead_user'], is_active=True))
        if len(valid_users) != len(set(member_ids)):
            return Response({'success': False, 'message': 'One or more selected users are invalid.'}, status=status.HTTP_400_BAD_REQUEST)

        before_ids = list(TeamMember.objects.filter(team_id=id).values_list('user_id', flat=True)) if id else []
        removed = [uid for uid in before_ids if uid not in member_ids]

        with transaction.atomic():
            if id:
                team = Team.objects.get(id=id)
                team.name = name
                team.domain_type_id = domain_type_id
                team.save()
            else:
                team = Team.objects.create(
                    name=name,
                    domain_type_id=domain_type_id,
                    created_by=request.user
                )

            TeamMember.objects.filter(team_id=team.id).delete()
            for uid in member_ids:
                TeamMember.objects.create(team_id=team.id, user_id=uid)

            create_audit_log(
                actor_id=request.user.id,
                entity_type='team',
                entity_id=team.id,
                action='team_updated' if id else 'team_created',
                new_value={
                    'name': team.name,
                    'domainTypeId': team.domain_type_id,
                    'memberIds': member_ids,
                    'removedMembers': removed,
                    'existingAssignmentsPreserved': True
                }
            )

        impacted = []
        if removed:
            impact_counts = Lead.objects.filter(
                assigned_to_id__in=removed,
                domain_type_id=domain_type_id
            ).exclude(status__in=['won', 'lost']).values('assigned_to_id').annotate(c=Count('id'))
            impacted = [{'userId': ic['assigned_to_id'], 'count': ic['c']} for ic in impact_counts]

        return Response({
            'success': True,
            'team': {
                'id': team.id,
                'name': team.name,
                'domainTypeId': team.domain_type_id,
                'isActive': bool(team.is_active),
            },
            'removedMembers': removed,
            'impactedAssignments': impacted,
            'message': 'Team updated. Existing lead assignments for removed members were preserved; reassign them separately if needed.' if removed else 'Team saved successfully.'
        })


class TeamDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, id):
        team = Team.objects.filter(id=id).select_related('domain_type').prefetch_related('members__user').first()
        if not team:
            return Response({'success': False, 'message': 'Team not found.'}, status=status.HTTP_404_NOT_FOUND)

        member_ids = [m.user_id for m in team.members.all()]
        active_counts = {
            item['assigned_to_id']: item['c']
            for item in Lead.objects.filter(
                assigned_to_id__in=member_ids,
                domain_type_id=team.domain_type_id
            ).exclude(status__in=['won', 'lost']).values('assigned_to_id').annotate(c=Count('id'))
        }

        members_list = []
        for m in team.members.all():
            u = m.user
            members_list.append({
                'teamId': m.team_id,
                'userId': m.user_id,
                'addedAt': m.added_at.isoformat() if m.added_at else None,
                'activeLeadCount': active_counts.get(m.user_id, 0),
                'user': {
                    'id': u.id,
                    'name': u.name,
                    'email': u.email,
                    'role': u.role,
                    'isActive': bool(u.is_active)
                }
            })

        unassigned_leads = Lead.objects.filter(
            domain_type_id=team.domain_type_id,
            assigned_to__isnull=True,
            creation_method__in=['excel_import', 'api_import']
        ).exclude(status__in=['won', 'lost']).order_by('-created_at')

        return Response({
            'success': True,
            'team': {
                'id': team.id,
                'name': team.name,
                'domainTypeId': team.domain_type_id,
                'isActive': bool(team.is_active),
                'domainType': {
                    'id': team.domain_type.id,
                    'name': team.domain_type.name,
                    'description': team.domain_type.description,
                    'isActive': bool(team.domain_type.is_active),
                },
                'members': members_list
            },
            'unassignedLeads': [present_lead(l) for l in unassigned_leads]
        })

    def put(self, request, id):
        view = TeamListView()
        return view._save(request, id)


class TeamAssignView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, id):
        team = Team.objects.filter(id=id).first()
        if not team:
            return Response({'success': False, 'message': 'Team not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not team.is_active:
            return Response({'success': False, 'message': 'This team is inactive.'}, status=status.HTTP_400_BAD_REQUEST)

        user_id = request.data.get('userId')
        lead_ids = request.data.get('leadIds', [])

        if not user_id or not lead_ids:
            return Response({'success': False, 'message': 'User and lead IDs are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_id = int(user_id)
            lead_ids = [int(lid) for lid in lead_ids]
        except (ValueError, TypeError):
            return Response({'success': False, 'message': 'Invalid IDs provided.'}, status=status.HTTP_400_BAD_REQUEST)

        target = User.objects.filter(id=user_id, is_active=True, role__in=['admin', 'lead_user']).first()
        if not target or not TeamMember.objects.filter(team_id=id, user_id=user_id).exists():
            return Response({'success': False, 'message': 'User is not an active member of this team.'}, status=status.HTTP_400_BAD_REQUEST)

        assigned = 0
        skipped = 0

        for lead_id in lead_ids:
            with transaction.atomic():
                updated = Lead.objects.filter(
                    id=lead_id,
                    domain_type_id=team.domain_type_id,
                    assigned_to__isnull=True,
                    creation_method__in=['excel_import', 'api_import']
                ).update(assigned_to_id=user_id)

                if updated:
                    LeadAssignmentHistory.objects.create(
                        lead_id=lead_id,
                        to_user_id=user_id,
                        performed_by=request.user,
                        action='assigned'
                    )
                    create_audit_log(
                        request.user.id, 'lead', lead_id, 'lead_assigned',
                        new_value={'assignedToId': user_id, 'teamId': id}
                    )
                    assigned += 1
                else:
                    skipped += 1

        return Response({
            'success': True,
            'selected': len(lead_ids),
            'assigned': assigned,
            'skipped': skipped
        })
