from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.db.models import Count

from api.models import DomainType, Lead, TeamMember, User
from api.permissions import IsAuthenticated, IsAdminUser
from api.helpers import safe_user, create_audit_log


class DomainListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        domains = DomainType.objects.annotate(
            leads_count=Count('leads', distinct=True),
            teams_count=Count('team', distinct=True)
        ).order_by('name')

        results = []
        for d in domains:
            results.append({
                'id': d.id,
                'name': d.name,
                'description': d.description,
                'isActive': bool(d.is_active),
                'createdById': d.created_by_id,
                'createdAt': d.created_at.isoformat() if d.created_at else None,
                'updatedAt': d.updated_at.isoformat() if d.updated_at else None,
                '_count': {
                    'leads': d.leads_count,
                    'teams': d.teams_count,
                }
            })

        return Response({'success': True, 'domains': results})

    def post(self, request):
        if request.user.role not in ['super_admin', 'admin']:
            return Response({'success': False, 'message': 'Only administrators can manage domain types.'}, status=status.HTTP_403_FORBIDDEN)

        name = request.data.get('name', '').strip()
        description = request.data.get('description', '')

        if not name:
            return Response({'success': False, 'message': 'Name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if DomainType.objects.filter(name=name).exists():
            return Response({'success': False, 'message': 'Domain type already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        domain = DomainType.objects.create(
            name=name,
            description=description or None,
            created_by=request.user
        )

        create_audit_log(
            actor_id=request.user.id,
            entity_type='domain_type',
            entity_id=domain.id,
            action='domain_created',
            new_value={'name': domain.name}
        )

        return Response({
            'success': True,
            'domain': {
                'id': domain.id,
                'name': domain.name,
                'description': domain.description,
                'isActive': bool(domain.is_active),
                'createdAt': domain.created_at.isoformat() if domain.created_at else None,
                'updatedAt': domain.updated_at.isoformat() if domain.updated_at else None,
            }
        }, status=status.HTTP_201_CREATED)


class DomainEligibleAssigneesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        domain = DomainType.objects.filter(id=id, is_active=True).first()
        if not domain:
            return Response({'success': False, 'message': 'Active domain type not found.'}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role in ['super_admin', 'admin']:
            memberships = TeamMember.objects.filter(
                team__domain_type_id=id,
                team__is_active=True,
                user__is_active=True,
                user__role__in=['admin', 'lead_user']
            ).select_related('user').order_by('user__name')
            users = [m.user for m in memberships]
        else:
            user_teams = TeamMember.objects.filter(
                user_id=request.user.id,
                team__domain_type_id=id,
                team__is_active=True
            ).values_list('team_id', flat=True)

            if not user_teams:
                users = []
            else:
                memberships = TeamMember.objects.filter(
                    team_id__in=user_teams,
                    user__is_active=True,
                    user__role__in=['admin', 'lead_user']
                ).select_related('user').order_by('user__name')
                users = [m.user for m in memberships]

        seen = set()
        unique_users = []
        for u in users:
            if u.id not in seen:
                seen.add(u.id)
                unique_users.append({
                    'id': u.id,
                    'name': u.name,
                    'email': u.email,
                    'role': u.role
                })

        return Response({'success': True, 'users': unique_users})


class DomainDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, id):
        domain = DomainType.objects.filter(id=id).first()
        if not domain:
            return Response({'success': False, 'message': 'Domain type not found.'}, status=status.HTTP_404_NOT_FOUND)

        name = request.data.get('name', '').strip()
        description = request.data.get('description', '')

        if not name:
            return Response({'success': False, 'message': 'Name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        duplicate = DomainType.objects.filter(name=name).exclude(id=id).first()
        if duplicate:
            return Response({'success': False, 'message': 'Domain type already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        old_name = domain.name
        old_desc = domain.description

        with transaction.atomic():
            domain.name = name
            domain.description = description or None
            domain.save(update_fields=['name', 'description'])

            if old_name != name:
                Lead.objects.filter(domain_type_id=id).update(primary_domain=name)

            create_audit_log(
                actor_id=request.user.id,
                entity_type='domain_type',
                entity_id=id,
                action='domain_updated',
                old_value={'name': old_name, 'description': old_desc},
                new_value={'name': domain.name, 'description': domain.description}
            )

        return Response({
            'success': True,
            'domain': {
                'id': domain.id,
                'name': domain.name,
                'description': domain.description,
                'isActive': bool(domain.is_active),
            }
        })


class DomainActiveToggleView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, id):
        domain = DomainType.objects.filter(id=id).first()
        if not domain:
            return Response({'success': False, 'message': 'Domain type not found.'}, status=status.HTTP_404_NOT_FOUND)

        is_active = bool(request.data.get('isActive', False))
        domain.is_active = is_active
        domain.save(update_fields=['is_active'])

        create_audit_log(
            actor_id=request.user.id,
            entity_type='domain_type',
            entity_id=id,
            action='domain_activated' if is_active else 'domain_deactivated',
            new_value={'isActive': is_active}
        )

        return Response({
            'success': True,
            'domain': {
                'id': domain.id,
                'name': domain.name,
                'description': domain.description,
                'isActive': bool(domain.is_active),
            }
        })
