import pytest
from rest_framework.test import APIClient
from api.models import User
from api.authentication import generate_token

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def super_admin_auth():
    admin = User.objects.filter(role='super_admin').first()
    if not admin:
        admin = User.objects.get(id=1)
    token = generate_token(admin.id)
    return {'client': APIClient(), 'token': token, 'user': admin}

@pytest.fixture
def lead_user_auth():
    user = User.objects.filter(role='lead_user').first()
    if not user:
        user = User.objects.create(
            name='Test Lead User',
            email='test_lead_user_fixture@example.com',
            password='Password@123',
            role='lead_user',
            is_active=True
        )
    token = generate_token(user.id)
    return {'client': APIClient(), 'token': token, 'user': user}

@pytest.mark.django_db(transaction=True)
def test_health_check(api_client):
    res = api_client.get('/api/health')
    assert res.status_code == 200
    data = res.json()
    assert data.get('status') == 'ok'
    assert data.get('success') is True

@pytest.mark.django_db(transaction=True)
def test_unauthenticated_me_rejected(api_client):
    res = api_client.get('/api/auth/me')
    assert res.status_code in [401, 403]

@pytest.mark.django_db(transaction=True)
def test_super_admin_me(super_admin_auth):
    client = super_admin_auth['client']
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {super_admin_auth['token']}")
    res = client.get('/api/auth/me')
    assert res.status_code == 200
    data = res.json()
    assert data.get('user', {}).get('role') == 'super_admin'

@pytest.mark.django_db(transaction=True)
def test_lead_user_cannot_access_admin_overview(lead_user_auth):
    client = lead_user_auth['client']
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {lead_user_auth['token']}")
    res = client.get('/api/admin/overview')
    assert res.status_code == 403

@pytest.mark.django_db(transaction=True)
def test_super_admin_can_access_admin_overview(super_admin_auth):
    client = super_admin_auth['client']
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {super_admin_auth['token']}")
    res = client.get('/api/admin/overview')
    assert res.status_code == 200
    data = res.json()
    assert 'overview' in data

@pytest.mark.django_db(transaction=True)
def test_lead_user_cannot_access_teams(lead_user_auth):
    client = lead_user_auth['client']
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {lead_user_auth['token']}")
    res = client.get('/api/teams')
    assert res.status_code == 403

@pytest.mark.django_db(transaction=True)
def test_super_admin_can_list_teams(super_admin_auth):
    client = super_admin_auth['client']
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {super_admin_auth['token']}")
    res = client.get('/api/teams')
    assert res.status_code == 200
    assert 'teams' in res.json()

@pytest.mark.django_db(transaction=True)
def test_leads_endpoints_accessible(super_admin_auth):
    client = super_admin_auth['client']
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {super_admin_auth['token']}")
    
    res = client.get('/api/leads')
    assert res.status_code == 200
    assert 'leads' in res.json()

    res_stats = client.get('/api/leads/stats')
    assert res_stats.status_code == 200

    res_dash = client.get('/api/leads/dashboard')
    assert res_dash.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_social_media_platforms_and_categories(super_admin_auth):
    client = super_admin_auth['client']
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {super_admin_auth['token']}")

    res_p = client.get('/api/social-media-customers/platforms')
    assert res_p.status_code == 200

    res_c = client.get('/api/social-media-customers/business-categories')
    assert res_c.status_code == 200
