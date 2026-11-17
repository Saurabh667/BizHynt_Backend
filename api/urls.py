from django.urls import path, re_path

from api.views.health_views import HealthCheckView
from api.views.auth_views import (
    LoginView, RegisterView, MeView, UserListView,
    DeactivationImpactView, UserActiveToggleView
)
from api.views.admin_views import (
    AdminOverviewView, AdminCompaniesView, AdminCompanyDetailView,
    AdminCompanyLeadsView, AdminCompanyLeadDetailView, AdminAllLeadsView,
    AdminAuditLogsView
)
from api.views.domain_views import (
    DomainListView, DomainEligibleAssigneesView, DomainDetailView,
    DomainActiveToggleView
)
from api.views.team_views import (
    TeamListView, TeamDetailView, TeamAssignView
)
from api.views.lead_views import (
    LeadListView, LeadStatsView, LeadDashboardView, LeadAdvancedView,
    LeadFollowUpsView, LeadImportView, LeadDetailView,
    LeadEligibleAssigneesView, LeadAssignUnassignedView, LeadTransferView,
    LeadUnassignView, LeadStatusView, LeadLegacyFollowUpView,
    LeadFollowUpCreateView, LeadFollowUpStatusView, LeadNoteCreateView
)
from api.views.customer_views import (
    CustomerListView, CustomerDetailView, CustomerConvertFromLeadView
)
from api.views.integration_views import (
    IntegrationImportLeadsView, IntegrationImportLeadsFileView
)
from api.views.social_media_views import (
    SmCustomerListView, SmCustomerDetailView, SmCustomerHistoryView,
    SmPlatformsView, SmPlatformDetailView, SmBusinessCategoriesView,
    SmBusinessCategoryDetailView, SmTermsView, SmTermsHistoryView,
    SmContractListView, SmContractPdfDownloadView, SmAccountActionView,
    SmAccountVersionsView, SmAccountRevealView
)

urlpatterns = [
    # Health
    path('health', HealthCheckView.as_view(), name='health'),

    # Auth
    path('auth/login', LoginView.as_view(), name='auth_login'),
    path('auth/register', RegisterView.as_view(), name='auth_register'),
    path('auth/me', MeView.as_view(), name='auth_me'),
    path('auth/users', UserListView.as_view(), name='auth_users'),
    path('auth/users/<int:id>/deactivation-impact', DeactivationImpactView.as_view(), name='auth_deactivation_impact'),
    path('auth/users/<int:id>/active', UserActiveToggleView.as_view(), name='auth_active'),

    # Admin
    path('admin/overview', AdminOverviewView.as_view(), name='admin_overview'),
    path('admin/companies', AdminCompaniesView.as_view(), name='admin_companies'),
    path('admin/companies/<int:id>', AdminCompanyDetailView.as_view(), name='admin_company_detail'),
    path('admin/companies/<int:id>/leads', AdminCompanyLeadsView.as_view(), name='admin_company_leads'),
    path('admin/companies/<int:id>/leads/<int:lid>', AdminCompanyLeadDetailView.as_view(), name='admin_company_lead_detail'),
    path('admin/leads', AdminAllLeadsView.as_view(), name='admin_leads'),
    path('admin/audit-logs', AdminAuditLogsView.as_view(), name='admin_audit_logs'),

    # Domains
    path('domains', DomainListView.as_view(), name='domains_list'),
    path('domains/<int:id>/eligible-assignees', DomainEligibleAssigneesView.as_view(), name='domain_eligible_assignees'),
    path('domains/<int:id>', DomainDetailView.as_view(), name='domain_detail'),
    path('domains/<int:id>/active', DomainActiveToggleView.as_view(), name='domain_active'),

    # Teams
    path('teams', TeamListView.as_view(), name='teams_list'),
    path('teams/<int:id>', TeamDetailView.as_view(), name='team_detail'),
    path('teams/<int:id>/assign', TeamAssignView.as_view(), name='team_assign'),

    # Leads
    path('leads/follow-ups', LeadFollowUpsView.as_view(), name='lead_follow_ups'),
    path('leads/stats', LeadStatsView.as_view(), name='lead_stats'),
    path('leads/dashboard', LeadDashboardView.as_view(), name='lead_dashboard'),
    path('leads/advanced', LeadAdvancedView.as_view(), name='lead_advanced'),
    path('leads/import', LeadImportView.as_view(), name='lead_import'),
    path('leads', LeadListView.as_view(), name='leads_list'),
    path('leads/<int:id>', LeadDetailView.as_view(), name='lead_detail'),
    path('leads/<int:id>/eligible-assignees', LeadEligibleAssigneesView.as_view(), name='lead_eligible_assignees'),
    path('leads/<int:id>/assign/<int:userId>', LeadAssignUnassignedView.as_view(), name='lead_assign_unassigned'),
    path('leads/<int:id>/transfer/<int:userId>', LeadTransferView.as_view(), name='lead_transfer'),
    path('leads/<int:id>/unassign', LeadUnassignView.as_view(), name='lead_unassign'),
    path('leads/<int:id>/status', LeadStatusView.as_view(), name='lead_status'),
    path('leads/<int:id>/follow-up', LeadLegacyFollowUpView.as_view(), name='lead_legacy_follow_up'),
    path('leads/<int:id>/follow-ups', LeadFollowUpCreateView.as_view(), name='lead_follow_up_create'),
    path('leads/<int:id>/follow-ups/<int:fid>', LeadFollowUpStatusView.as_view(), name='lead_follow_up_status'),
    path('leads/<int:id>/notes', LeadNoteCreateView.as_view(), name='lead_notes'),
    path('leads/<int:id>/notes/<int:nid>', LeadNoteCreateView.as_view(), name='lead_note_delete'),

    # Customers
    path('customers', CustomerListView.as_view(), name='customer_list'),
    path('customers/<int:id>', CustomerDetailView.as_view(), name='customer_detail'),
    path('customers/from-lead/<int:leadId>', CustomerConvertFromLeadView.as_view(), name='customer_convert'),

    # Integrations
    path('integrations/leads/import', IntegrationImportLeadsView.as_view(), name='integration_import_leads'),
    path('integrations/leads/import-file', IntegrationImportLeadsFileView.as_view(), name='integration_import_leads_file'),

    # Social Media Customers
    path('social-media-customers', SmCustomerListView.as_view(), name='sm_customer_list'),
    path('social-media-customers/platforms', SmPlatformsView.as_view(), name='sm_platforms'),
    path('social-media-customers/platforms/manage', SmPlatformsView.as_view(), name='sm_platforms_manage'),
    path('social-media-customers/platforms/<int:platformId>', SmPlatformDetailView.as_view(), name='sm_platform_detail'),
    path('social-media-customers/business-categories', SmBusinessCategoriesView.as_view(), name='sm_categories'),
    path('social-media-customers/business-categories/<int:categoryId>', SmBusinessCategoryDetailView.as_view(), name='sm_category_detail'),
    path('social-media-customers/<int:id>', SmCustomerDetailView.as_view(), name='sm_customer_detail'),
    path('social-media-customers/<int:id>/history', SmCustomerHistoryView.as_view(), name='sm_customer_history'),
    path('social-media-customers/<int:id>/accounts', SmAccountActionView.as_view(), name='sm_account_add'),
    path('social-media-customers/<int:id>/accounts/<int:aid>', SmAccountActionView.as_view(), name='sm_account_action'),
    path('social-media-customers/<int:id>/accounts/<int:aid>/versions', SmAccountVersionsView.as_view(), name='sm_account_versions'),
    path('social-media-customers/<int:id>/accounts/<int:aid>/versions/<int:vid>/reveal', SmAccountRevealView.as_view(), name='sm_account_reveal'),

    # Social Media Terms & Contracts
    path('social-media/terms', SmTermsView.as_view(), name='sm_terms'),
    path('social-media/terms/history', SmTermsHistoryView.as_view(), name='sm_terms_history'),
    path('social-media/customers/<int:id>/contracts', SmContractListView.as_view(), name='sm_contracts'),
    path('social-media/customers/<int:id>/contracts/<int:contractId>/pdf', SmContractPdfDownloadView.as_view(), name='sm_contract_pdf'),
]
