from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.db import transaction
from django.db.models import Count, Q

from api.models import User, Lead, TeamMember, LeadAssignmentHistory, AuditLog
from api.authentication import generate_token
from api.permissions import IsAuthenticated, IsAdminUser
from api.helpers import safe_user, verify_password, hash_password, create_audit_log


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')

        if not email or not password:
            return Response(
                {'success': False, 'message': 'Email and password are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.filter(email=email).first()
        if not user or not user.is_active or not verify_password(password, user.password):
            return Response(
                {'success': False, 'message': 'Invalid email or password.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        token = generate_token(user.id)
        return Response({
            'success': True,
            'message': 'Login successful.',
            'token': token,
            'user': safe_user(user)
        })


class RegisterView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        actor = request.user
        name = request.data.get('name', '').strip()
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')
        user_type = request.data.get('userType', 'lead_user')

        if not name or not email or not password:
            return Response(
                {'success': False, 'message': 'Name, email, and password are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if user_type == 'super_admin':
            return Response(
                {'success': False, 'message': 'Super admin cannot be created from the portal.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if user_type == 'admin' and actor.role != 'super_admin':
            return Response(
                {'success': False, 'message': 'Only the super admin can create an admin.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if User.objects.filter(email=email).exists():
            return Response(
                {'success': False, 'message': 'Email already exists.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        hashed = hash_password(password)
        user = User.objects.create(
            name=name,
            email=email,
            password=hashed,
            role=user_type,
            company_name='TechSolutions',
            company_description='',
            created_by=actor
        )

        create_audit_log(
            actor_id=actor.id,
            entity_type='user',
            entity_id=user.id,
            action='user_created',
            new_value={'role': user.role, 'email': user.email}
        )

        return Response({
            'success': True,
            'message': 'User created successfully.',
            'user': safe_user(user)
        }, status=status.HTTP_201_CREATED)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'success': True,
            'user': safe_user(request.user)
        })


class UserListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        users = User.objects.filter(role__in=['admin', 'lead_user']).order_by('name')
        result = []
        for u in users:
            data = safe_user(u)
            data['_count'] = {
                'assignedLeads': u.assigned_leads.count(),
                'createdLeads': u.created_leads.count()
            }
            result.append(data)

        return Response({'success': True, 'users': result})


class DeactivationImpactView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, id):
        actor = request.user
        target = User.objects.filter(id=id).first()
        if not target or target.role == 'super_admin':
            return Response({'success': False, 'message': 'User cannot be managed.'}, status=status.HTTP_400_BAD_REQUEST)
        if target.role == 'admin' and actor.role != 'super_admin':
            return Response({'success': False, 'message': 'Only Super Admin can manage an Admin.'}, status=status.HTTP_403_FORBIDDEN)

        active_leads = Lead.objects.filter(assigned_to_id=id).exclude(status__in=['won', 'lost'])
        domain_ids = list(set(active_leads.values_list('domain_type_id', flat=True)))

        memberships = TeamMember.objects.filter(
            user_id=id,
            team__domain_type_id__in=domain_ids
        ).select_related('team')

        team_ids = [m.team_id for m in memberships]
        peer_memberships = TeamMember.objects.filter(
            team_id__in=team_ids
        ).exclude(user_id=id).select_related('user', 'team')

        counts = {}
        for pm in peer_memberships:
            u = pm.user
            if u.is_active and u.role in ['admin', 'lead_user']:
                if u.id not in counts:
                    counts[u.id] = {'user': safe_user(u), 'domain_ids': set()}
                counts[u.id]['domain_ids'].add(pm.team.domain_type_id)

        eligible = [
            v['user'] for v in counts.values()
            if len(v['domain_ids']) == len(domain_ids)
        ]

        return Response({
            'success': True,
            'activeLeadCount': active_leads.count(),
            'activeDomainCount': len(domain_ids),
            'eligibleReplacements': eligible
        })


class UserActiveToggleView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, id):
        actor = request.user
        target = User.objects.filter(id=id).first()
        if not target or target.role == 'super_admin':
            return Response({'success': False, 'message': 'User cannot be managed.'}, status=status.HTTP_400_BAD_REQUEST)
        if target.role == 'admin' and actor.role != 'super_admin':
            return Response({'success': False, 'message': 'Only Super Admin can manage an Admin.'}, status=status.HTTP_403_FORBIDDEN)
        if target.id == actor.id:
            return Response({'success': False, 'message': 'You cannot change your own active status.'}, status=status.HTTP_400_BAD_REQUEST)

        is_active = bool(request.data.get('isActive', False))

        if is_active:
            target.is_active = True
            target.save(update_fields=['is_active'])
            create_audit_log(actor.id, 'user', id, 'user_activated', new_value={'isActive': True})
            return Response({'success': True, 'user': safe_user(target)})

        # Deactivation logic
        active_leads = list(Lead.objects.filter(assigned_to_id=id).exclude(status__in=['won', 'lost']))
        strategy = request.data.get('strategy', 'keep')
        if strategy not in ['keep', 'unassign', 'reassign']:
            return Response({'success': False, 'message': 'Invalid deactivation strategy.'}, status=status.HTTP_400_BAD_REQUEST)

        reassign_to_id = request.data.get('reassignToId')
        if reassign_to_id:
            try:
                reassign_to_id = int(reassign_to_id)
            except ValueError:
                reassign_to_id = None

        if len(active_leads) > 0 and strategy == 'keep':
            return Response({
                'success': False,
                'message': f'This user has {len(active_leads)} active assigned lead(s). Choose Reassign or Move to Unassigned before deactivation.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if strategy == 'reassign':
            if not reassign_to_id:
                return Response({'success': False, 'message': 'Replacement user is required.'}, status=status.HTTP_400_BAD_REQUEST)
            replacement = User.objects.filter(id=reassign_to_id, is_active=True, role__in=['admin', 'lead_user']).first()
            if not replacement:
                return Response({'success': False, 'message': 'Replacement user is not available.'}, status=status.HTTP_400_BAD_REQUEST)

            for lead in active_leads:
                same_team = TeamMember.objects.filter(
                    user_id=reassign_to_id,
                    team__domain_type_id=lead.domain_type_id
                ).exists()
                if not same_team:
                    return Response({
                        'success': False,
                        'message': 'Replacement user must belong to the same Domain Type team for every active lead.'
                    }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for lead in active_leads:
                to_id = reassign_to_id if strategy == 'reassign' else None
                lead.assigned_to_id = to_id
                lead.save(update_fields=['assigned_to_id'])

                LeadAssignmentHistory.objects.create(
                    lead=lead,
                    from_user_id=id,
                    to_user_id=to_id,
                    performed_by=actor,
                    action='reassigned' if to_id else 'unassigned'
                )
                create_audit_log(
                    actor.id, 'lead', lead.id,
                    'lead_reassigned_on_user_deactivation' if to_id else 'lead_unassigned_on_user_deactivation',
                    old_value={'assignedToId': id},
                    new_value={'assignedToId': to_id}
                )

            target.is_active = False
            target.save(update_fields=['is_active'])

            create_audit_log(
                actor.id, 'user', id, 'user_deactivated',
                new_value={'isActive': False, 'strategy': strategy, 'reassignToId': reassign_to_id, 'affectedLeads': len(active_leads)}
            )

        msg_action = 'reassigned' if strategy == 'reassign' else 'moved to the unassigned pool'
        return Response({
            'success': True,
            'message': f'User deactivated. {len(active_leads)} active lead(s) {msg_action}.'
        })
