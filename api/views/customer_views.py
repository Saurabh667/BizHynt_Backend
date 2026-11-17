from datetime import datetime, timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.db.models import Q

from api.models import Customer, Lead, User
from api.permissions import IsAuthenticated
from api.helpers import safe_user, present_lead, create_audit_log


def present_customer(c):
    if not c:
        return None

    lead_data = present_lead(c.lead) if c.lead else None
    owner_data = safe_user(c.owner) if c.owner else None
    converted_by_data = safe_user(c.converted_by) if c.converted_by else None

    return {
        'id': c.id,
        '_id': c.id,
        'leadId': c.lead_id,
        'ownerId': c.owner_id,
        'convertedById': c.converted_by_id,
        'requirement': c.requirement,
        'service': c.service,
        'notes': c.notes,
        'contactPerson': c.contact_person,
        'alternatePhone': c.alternate_phone,
        'convertedAt': c.converted_at.isoformat() if c.converted_at else None,
        'updatedAt': c.updated_at.isoformat() if c.updated_at else None,
        'lead': lead_data,
        'owner': owner_data,
        'convertedBy': converted_by_data,
    }


class CustomerListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        qs = Customer.objects.select_related(
            'lead__domain_type', 'lead__assigned_to', 'lead__created_by', 'owner', 'converted_by'
        )
        if user.role not in ['super_admin', 'admin']:
            qs = qs.filter(owner_id=user.id)

        qs = qs.order_by('-converted_at')
        customers = [present_customer(c) for c in qs]
        return Response({'success': True, 'customers': customers})


class CustomerDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        user = request.user
        qs = Customer.objects.filter(id=id).select_related(
            'lead__domain_type', 'lead__assigned_to', 'lead__created_by', 'owner', 'converted_by'
        ).prefetch_related(
            'lead__assignment_history__from_user', 'lead__assignment_history__to_user', 'lead__assignment_history__performed_by'
        )
        if user.role not in ['super_admin', 'admin']:
            qs = qs.filter(owner_id=user.id)

        customer = qs.first()
        if not customer:
            return Response({'success': False, 'message': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)

        return Response({'success': True, 'customer': present_customer(customer)})

    def patch(self, request, id):
        user = request.user
        qs = Customer.objects.filter(id=id)
        if user.role not in ['super_admin', 'admin']:
            qs = qs.filter(owner_id=user.id)

        customer = qs.first()
        if not customer:
            return Response({'success': False, 'message': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        updated_data = {}
        for k, attr in [
            ('requirement', 'requirement'), ('service', 'service'), ('notes', 'notes'),
            ('contactPerson', 'contact_person'), ('alternatePhone', 'alternate_phone')
        ]:
            if k in data:
                val = data[k]
                val_clean = str(val).strip() if val else None
                setattr(customer, attr, val_clean)
                updated_data[k] = val_clean

        customer.save()
        create_audit_log(
            user.id, 'customer', id, 'customer_updated', new_value=updated_data
        )

        return Response({
            'success': True,
            'message': 'Customer updated successfully.',
            'customer': present_customer(customer)
        })


class CustomerConvertFromLeadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, leadId):
        user = request.user
        lead = Lead.objects.filter(id=leadId).first()
        if not lead:
            return Response({'success': False, 'message': 'Lead not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not lead.assigned_to_id:
            return Response({'success': False, 'message': 'Assign the lead to an active user before converting it to a customer.'}, status=status.HTTP_400_BAD_REQUEST)

        owner = User.objects.filter(id=lead.assigned_to_id, is_active=True, role__in=['admin', 'lead_user']).first()
        if not owner:
            return Response({'success': False, 'message': 'The assigned user is inactive or unavailable. Reassign the lead before conversion.'}, status=status.HTTP_400_BAD_REQUEST)

        if user.role == 'lead_user' and lead.assigned_to_id != user.id:
            return Response({'success': False, 'message': 'You can only convert your assigned lead.'}, status=status.HTTP_403_FORBIDDEN)

        if Customer.objects.filter(lead_id=leadId).exists():
            return Response({'success': False, 'message': 'Customer already exists for this lead.'}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        with transaction.atomic():
            customer = Customer.objects.create(
                lead=lead,
                owner=owner,
                converted_by=user,
                requirement=data.get('requirement') or None,
                service=data.get('service') or None,
                notes=data.get('notes') or None,
                contact_person=data.get('contactPerson') or None,
                alternate_phone=data.get('alternatePhone') or None,
            )

            now = datetime.now(timezone.utc)
            lead.status = 'won'
            lead.won_at = now
            lead.lost_at = None
            lead.lost_reason = None
            lead.save()

            create_audit_log(
                user.id, 'customer', customer.id, 'lead_converted_to_customer', new_value={'leadId': leadId}
            )

        customer.refresh_from_db()
        return Response({
            'success': True,
            'message': 'Lead won and customer created successfully.',
            'customer': present_customer(customer)
        }, status=status.HTTP_201_CREATED)
