import bcrypt
from datetime import datetime
from django.conf import settings
from .models import AuditLog


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False


def safe_user(u):
    if not u:
        return None
    return {
        'id': u.id,
        '_id': u.id,
        'name': u.name,
        'email': u.email,
        'role': u.role,
        'companyName': u.company_name,
        'companyDescription': u.company_description or '',
        'isActive': bool(u.is_active),
        'createdById': u.created_by_id if hasattr(u, 'created_by_id') else (u.created_by.id if u.created_by else None),
        'createdAt': u.created_at.isoformat() if u.created_at else None,
        'updatedAt': u.updated_at.isoformat() if u.updated_at else None,
    }


def create_audit_log(actor_id, entity_type, entity_id, action, old_value=None, new_value=None, metadata=None):
    try:
        AuditLog.objects.create(
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_value=old_value,
            new_value=new_value,
            metadata=metadata
        )
    except Exception as e:
        print(f"Error creating audit log: {e}")


def present_note(n):
    if not n:
        return None
    return {
        'id': n.id,
        '_id': n.id,
        'leadId': n.lead_id if hasattr(n, 'lead_id') else n.lead.id,
        'text': n.text,
        'createdBy': n.created_by_id if hasattr(n, 'created_by_id') else (n.created_by.id if n.created_by else None),
        'createdAt': n.created_at.isoformat() if n.created_at else None,
        'updatedAt': n.updated_at.isoformat() if n.updated_at else None,
        'creator': safe_user(n.created_by) if getattr(n, 'created_by', None) else None,
    }


def present_follow_up(f):
    if not f:
        return None
    return {
        'id': f.id,
        '_id': f.id,
        'leadId': f.lead_id if hasattr(f, 'lead_id') else f.lead.id,
        'dueDate': f.due_date.isoformat() if f.due_date else None,
        'note': f.note,
        'status': f.status,
        'createdBy': f.created_by_id if hasattr(f, 'created_by_id') else (f.created_by.id if f.created_by else None),
        'createdAt': f.created_at.isoformat() if f.created_at else None,
        'updatedAt': f.updated_at.isoformat() if f.updated_at else None,
        'creator': safe_user(f.created_by) if getattr(f, 'created_by', None) else None,
    }


def present_assignment_history(h):
    if not h:
        return None
    return {
        'id': h.id,
        'leadId': h.lead_id if hasattr(h, 'lead_id') else h.lead.id,
        'fromUserId': h.from_user_id if hasattr(h, 'from_user_id') else (h.from_user.id if h.from_user else None),
        'toUserId': h.to_user_id if hasattr(h, 'to_user_id') else (h.to_user.id if h.to_user else None),
        'action': h.action,
        'performedById': h.performed_by_id if hasattr(h, 'performed_by_id') else (h.performed_by.id if h.performed_by else None),
        'createdAt': h.created_at.isoformat() if h.created_at else None,
        'fromUser': safe_user(h.from_user) if getattr(h, 'from_user', None) else None,
        'toUser': safe_user(h.to_user) if getattr(h, 'to_user', None) else None,
        'performedBy': safe_user(h.performed_by) if getattr(h, 'performed_by', None) else None,
    }


def present_lead(x):
    if not x:
        return None

    notes_qs = getattr(x, 'notes', None)
    notes_list = [present_note(n) for n in notes_qs.all()] if hasattr(notes_qs, 'all') else []

    follow_ups_qs = getattr(x, 'follow_ups', None)
    follow_ups_list = [present_follow_up(f) for f in follow_ups_qs.all()] if hasattr(follow_ups_qs, 'all') else []

    history_qs = getattr(x, 'assignment_history', None)
    history_list = [present_assignment_history(h) for h in history_qs.all().order_by('-created_at')] if hasattr(history_qs, 'all') else []

    domain_type = None
    if getattr(x, 'domain_type', None):
        domain_type = {
            'id': x.domain_type.id,
            'name': x.domain_type.name,
            'description': x.domain_type.description,
            'isActive': bool(x.domain_type.is_active),
        }

    creator = safe_user(x.created_by) if getattr(x, 'created_by', None) else None
    assignee = safe_user(x.assigned_to) if getattr(x, 'assigned_to', None) else None

    customer_dict = None
    if hasattr(x, 'customer') and x.customer:
        customer_dict = {
            'id': x.customer.id,
            'leadId': x.id,
            'ownerId': x.customer.owner_id,
            'convertedById': x.customer.converted_by_id,
            'requirement': x.customer.requirement,
            'service': x.customer.service,
            'notes': x.customer.notes,
            'contactPerson': x.customer.contact_person,
            'alternatePhone': x.customer.alternate_phone,
            'convertedAt': x.customer.converted_at.isoformat() if x.customer.converted_at else None,
        }

    return {
        'id': x.id,
        '_id': x.id,
        'name': x.name,
        'email': x.email,
        'phone': x.phone,
        'company': x.company,
        'message': x.message,
        'website': x.website,
        'address': x.address,
        'primaryDomain': x.primary_domain,
        'finalDomain': x.final_domain,
        'country': x.country,
        'state': x.state,
        'city': x.city,
        'pincode': x.pincode,
        'currentReview': x.current_review,
        'reviewSentiment': x.review_sentiment,
        'websiteStatus': x.website_status,
        'https': x.https,
        'mobileResponsive': x.mobile_responsive,
        'pageSpeed': x.page_speed,
        'outdatedIndicators': x.outdated_indicators,
        'leadScore': float(x.lead_score) if x.lead_score is not None else None,
        'googleRating': float(x.google_rating) if x.google_rating is not None else None,
        'googleReviewCount': x.google_review_count,
        'googleReviewsUrl': x.google_reviews_url,
        'googleMapsUrl': x.google_maps_url,
        'facebook': x.facebook,
        'instagram': x.instagram,
        'linkedin': x.linkedin,
        'youtube': x.youtube,
        'socialMediaFound': x.social_media_found,
        'socialMediaLinks': x.social_media_links,
        'emailCount': x.email_count,
        'emailSource': x.email_source,
        'emailType': x.email_type,
        'allEmails': x.all_emails,
        'source': x.source,
        'status': x.status,
        'followUpDate': x.follow_up_date.isoformat() if x.follow_up_date else None,
        'lastContactedAt': x.last_contacted_at.isoformat() if x.last_contacted_at else None,
        'wonAt': x.won_at.isoformat() if x.won_at else None,
        'lostAt': x.lost_at.isoformat() if x.lost_at else None,
        'lostReason': x.lost_reason,
        'importedFrom': x.imported_from,
        'imageUrl': x.image_url,
        'imageUrls': x.image_urls,
        'topComments': x.top_comments,
        'creationMethod': x.creation_method,
        'createdBy': x.created_by_id,
        'assignedToId': x.assigned_to_id,
        'domainTypeId': x.domain_type_id,
        'createdAt': x.created_at.isoformat() if x.created_at else None,
        'updatedAt': x.updated_at.isoformat() if x.updated_at else None,

        # Nested associations
        'domainType': domain_type,
        'creator': creator,
        'assignee': assignee,
        'notes': notes_list,
        'followUps': follow_ups_list,
        'assignmentHistory': history_list,
        'customer': customer_dict,
    }
