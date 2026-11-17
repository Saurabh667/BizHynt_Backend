import re
from urllib.parse import urlparse

NOT_FOUND_VALUES = {
    'none', 'null', 'nil', 'undefined', 'not found', 'mail not found',
    'email not found', 'e-mail not found', 'phone not found', 'number not found',
    'phone number not found', 'website not found', 'no email', 'no phone',
    'no website', 'not available', 'not applicable', 'n/a', 'n.a.', 'n.a',
    'na', 'nan', '-', '--', '---', '—'
}

FIELD_MAP = {
    'name': 'name',
    'business_name': 'name',
    'company_name': 'name',
    'company': 'company',
    'organization': 'company',
    'message': 'message',
    'requirement': 'message',
    'source': 'source',
    'phone': 'phone',
    'phone_number': 'phone',
    'website': 'website',
    'address': 'address',
    'primary_domain': 'primary_domain',
    'sector': 'primary_domain',
    'category': 'primary_domain',
    'business_category': 'primary_domain',
    'final_domain': 'final_domain',
    'sub_sector': 'final_domain',
    'sub_category': 'final_domain',
    'country': 'country',
    'state': 'state',
    'city': 'city',
    'pincode': 'pincode',
    'pin_code': 'pincode',
    'postal_code': 'pincode',
    'zipcode': 'pincode',
    'zip_code': 'pincode',
    'current_review': 'current_review',
    'latest_review': 'current_review',
    'bad_review': 'current_review',
    'negative_review': 'current_review',
    'good_review': 'current_review',
    'review_sentiment': 'review_sentiment',
    'current_review_sentiment': 'review_sentiment',
    'sentiment': 'review_sentiment',
    'website_status': 'website_status',
    'https': 'https',
    'mobile_responsive': 'mobile_responsive',
    'page_speed': 'page_speed',
    'outdated_indicators': 'outdated_indicators',
    'lead_score': 'lead_score',
    'google_rating': 'google_rating',
    'google_review_count': 'google_review_count',
    'google_reviews_url': 'google_reviews_url',
    'google_maps_url': 'google_maps_url',
    'facebook': 'facebook',
    'instagram': 'instagram',
    'linkedin': 'linkedin',
    'youtube': 'youtube',
    'social_media_found': 'social_media_found',
    'social_media_links': 'social_media_links',
    'email': 'email',
    'email_count': 'email_count',
    'email_source': 'email_source',
    'email_type': 'email_type',
    'all_emails': 'all_emails',
    'image': 'image_urls',
    'image_url': 'image_urls',
    'image_urls': 'image_urls',
    'images': 'image_urls',
    'photo': 'image_urls',
    'photos': 'image_urls',
    'logo': 'image_urls',
    'top_5_comments': 'top_comments',
    'top_comments': 'top_comments',
    'top_5_reviews': 'top_comments',
    'comments': 'top_comments',
    'reviews': 'top_comments',
    'websitestatus': 'website_status',
    'mobileresponsive': 'mobile_responsive',
    'pagespeed': 'page_speed',
    'outdatedindicators': 'outdated_indicators',
    'leadscore': 'lead_score',
    'googlerating': 'google_rating',
    'googlereviewcount': 'google_review_count',
    'googlereviewsurl': 'google_reviews_url',
    'googlemapsurl': 'google_maps_url',
    'socialmediafound': 'social_media_found',
    'socialmedialinks': 'social_media_links',
    'emailcount': 'email_count',
    'emailsource': 'email_source',
    'emailtype': 'email_type',
    'allemails': 'all_emails',
    'primarydomain': 'primary_domain',
    'finaldomain': 'final_domain',
    'currentreview': 'current_review',
    'reviewsentiment': 'review_sentiment',
    'topcomments': 'top_comments',
}

NUMERIC_FIELDS = {'lead_score', 'google_rating', 'google_review_count', 'email_count'}


def is_not_found(val):
    if val is None:
        return True
    s = str(val).strip().lower()
    return not s or s in NOT_FOUND_VALUES


def clean_email(val):
    if is_not_found(val):
        return None
    return str(val).strip().lower()


def norm_phone(val):
    if is_not_found(val):
        return ''
    digits = re.sub(r'\D', '', str(val))
    return digits[-10:] if len(digits) >= 7 else ''


def norm_website(val):
    if is_not_found(val):
        return ''
    raw = str(val).strip().lower()
    if not re.match(r'^https?://', raw):
        raw = f'https://{raw}'
    try:
        parsed = urlparse(raw)
        host = parsed.netloc or parsed.path.split('/')[0]
        return re.sub(r'^www\.', '', host)
    except Exception:
        return raw.split('/')[0]


def map_import_row(row):
    out = {}
    for header, value in row.items():
        k = re.sub(r'[^a-z0-9]+', '_', str(header).strip().lower()).strip('_')
        f = FIELD_MAP.get(k)
        if not f:
            continue

        if k in ['bad_review', 'negative_review'] and str(value or '').strip():
            out['review_sentiment'] = 'bad'
        if k == 'good_review' and str(value or '').strip():
            out['review_sentiment'] = 'good'

        if f == 'image_urls':
            values = value if isinstance(value, list) else re.split(r'[,|\n]+', str(value or ''))
            urls = [str(item).strip() for item in values if str(item).strip()]
            if urls:
                current = out.get('image_urls') or []
                out['image_urls'] = list(dict.fromkeys(current + urls))
        elif f in NUMERIC_FIELDS:
            try:
                num_str = re.sub(r'[^0-9.-]', '', str(value or ''))
                if num_str:
                    n = float(num_str) if '.' in num_str else int(num_str)
                    out[f] = n
            except Exception:
                pass
        else:
            s = str(value or '').strip()
            if s and not is_not_found(s):
                out[f] = s
            elif is_not_found(s):
                out[f] = None

    return out


def validate_import_row(x):
    limits = {
        'name': 255, 'phone': 100, 'company': 255, 'website_status': 100,
        'https': 50, 'mobile_responsive': 50, 'page_speed': 100,
        'social_media_found': 100, 'email': 255, 'email_type': 100,
        'primary_domain': 150, 'final_domain': 150, 'country': 100,
        'state': 100, 'city': 100, 'pincode': 20, 'review_sentiment': 20,
    }

    for k, max_len in limits.items():
        val = x.get(k)
        if val is not None and len(str(val)) > max_len:
            return f"{k} exceeds the {max_len} character limit."

    email = x.get('email')
    if email and not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        return 'Invalid email address.'

    rating = x.get('google_rating')
    if rating is not None and (rating < 0 or rating > 9.99):
        return 'Google rating must be between 0 and 9.99.'

    return None
