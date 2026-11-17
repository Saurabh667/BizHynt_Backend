from django.db import models


class User(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    email = models.CharField(unique=True, max_length=255)
    password = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, default='TechSolutions', db_column='company_name')
    company_description = models.TextField(blank=True, null=True, db_column='company_description')
    role = models.CharField(max_length=50, default='lead_user')  # super_admin, admin, lead_user
    is_active = models.BooleanField(default=True, db_column='is_active')
    created_by = models.ForeignKey(
        'self', models.SET_NULL, blank=True, null=True, db_column='created_by_id', related_name='created_users'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')

    class Meta:
        managed = False
        db_table = 'users'

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def __str__(self):
        return f"{self.name} ({self.email})"


class DomainType(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(unique=True, max_length=150)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True, db_column='is_active')
    created_by = models.ForeignKey(
        User, models.DO_NOTHING, db_column='created_by_id', related_name='domains_created'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')

    class Meta:
        managed = False
        db_table = 'domain_types'

    def __str__(self):
        return self.name


class Team(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=150)
    domain_type = models.OneToOneField(
        DomainType, models.DO_NOTHING, db_column='domain_type_id', related_name='team'
    )
    is_active = models.BooleanField(default=True, db_column='is_active')
    created_by = models.ForeignKey(
        User, models.DO_NOTHING, db_column='created_by_id', related_name='teams_created'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')

    class Meta:
        managed = False
        db_table = 'teams'

    def __str__(self):
        return self.name


class TeamMember(models.Model):
    pk = models.CompositePrimaryKey('team', 'user')
    team = models.ForeignKey(Team, models.DO_NOTHING, db_column='team_id', related_name='members')
    user = models.ForeignKey(User, models.DO_NOTHING, db_column='user_id', related_name='team_memberships')
    added_at = models.DateTimeField(auto_now_add=True, db_column='added_at')

    class Meta:
        managed = False
        db_table = 'team_members'
        unique_together = (('team', 'user'),)


class Lead(models.Model):
    id = models.AutoField(primary_key=True)
    created_by = models.ForeignKey(
        User, models.SET_NULL, blank=True, null=True, db_column='created_by', related_name='created_leads'
    )
    assigned_to = models.ForeignKey(
        User, models.SET_NULL, blank=True, null=True, db_column='assigned_to_id', related_name='assigned_leads'
    )
    domain_type = models.ForeignKey(
        DomainType, models.DO_NOTHING, db_column='domain_type_id', related_name='leads'
    )
    creation_method = models.CharField(max_length=50, default='manual', db_column='creation_method')
    name = models.CharField(max_length=255)
    email = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=100, blank=True, null=True)
    company = models.CharField(max_length=255, blank=True, null=True)
    message = models.TextField(blank=True, null=True)
    website = models.TextField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    primary_domain = models.CharField(max_length=150, blank=True, null=True, db_column='primary_domain')
    final_domain = models.CharField(max_length=150, blank=True, null=True, db_column='final_domain')
    country = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    pincode = models.CharField(max_length=20, blank=True, null=True)
    current_review = models.TextField(blank=True, null=True, db_column='current_review')
    review_sentiment = models.CharField(max_length=20, blank=True, null=True, db_column='review_sentiment')
    website_status = models.CharField(max_length=100, blank=True, null=True, db_column='website_status')
    https = models.CharField(max_length=50, blank=True, null=True)
    mobile_responsive = models.CharField(max_length=50, blank=True, null=True, db_column='mobile_responsive')
    page_speed = models.CharField(max_length=100, blank=True, null=True, db_column='page_speed')
    outdated_indicators = models.TextField(blank=True, null=True, db_column='outdated_indicators')
    lead_score = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, db_column='lead_score')
    google_rating = models.DecimalField(max_digits=3, decimal_places=2, blank=True, null=True, db_column='google_rating')
    google_review_count = models.IntegerField(blank=True, null=True, db_column='google_review_count')
    google_reviews_url = models.TextField(blank=True, null=True, db_column='google_reviews_url')
    google_maps_url = models.TextField(blank=True, null=True, db_column='google_maps_url')
    facebook = models.TextField(blank=True, null=True)
    instagram = models.TextField(blank=True, null=True)
    linkedin = models.TextField(blank=True, null=True)
    youtube = models.TextField(blank=True, null=True)
    social_media_found = models.CharField(max_length=100, blank=True, null=True, db_column='social_media_found')
    social_media_links = models.TextField(blank=True, null=True, db_column='social_media_links')
    email_count = models.IntegerField(blank=True, null=True, db_column='email_count')
    email_source = models.TextField(blank=True, null=True, db_column='email_source')
    email_type = models.CharField(max_length=100, blank=True, null=True, db_column='email_type')
    all_emails = models.TextField(blank=True, null=True, db_column='all_emails')
    source = models.CharField(max_length=100, default='Website', blank=True, null=True)
    status = models.CharField(max_length=50, default='new')
    follow_up_date = models.DateTimeField(blank=True, null=True, db_column='follow_up_date')
    last_contacted_at = models.DateTimeField(blank=True, null=True, db_column='last_contacted_at')
    won_at = models.DateTimeField(blank=True, null=True, db_column='won_at')
    lost_at = models.DateTimeField(blank=True, null=True, db_column='lost_at')
    lost_reason = models.CharField(max_length=50, blank=True, null=True, db_column='lost_reason')
    imported_from = models.CharField(max_length=255, blank=True, null=True, db_column='imported_from')
    image_url = models.TextField(blank=True, null=True, db_column='image_url')
    image_urls = models.JSONField(blank=True, null=True, db_column='image_urls')
    top_comments = models.TextField(blank=True, null=True, db_column='top_comments')
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')

    class Meta:
        managed = False
        db_table = 'leads'

    def __str__(self):
        return f"{self.name} ({self.status})"


class LeadAssignmentHistory(models.Model):
    id = models.AutoField(primary_key=True)
    lead = models.ForeignKey(Lead, models.CASCADE, db_column='lead_id', related_name='assignment_history')
    from_user = models.ForeignKey(
        User, models.SET_NULL, blank=True, null=True, db_column='from_user_id', related_name='assignments_from'
    )
    to_user = models.ForeignKey(
        User, models.SET_NULL, blank=True, null=True, db_column='to_user_id', related_name='assignments_to'
    )
    action = models.CharField(max_length=50)  # assigned, transferred, unassigned, reassigned
    performed_by = models.ForeignKey(
        User, models.DO_NOTHING, db_column='performed_by_id', related_name='assignments_performed'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')

    class Meta:
        managed = False
        db_table = 'lead_assignment_history'


class Customer(models.Model):
    id = models.AutoField(primary_key=True)
    lead = models.OneToOneField(Lead, models.DO_NOTHING, db_column='lead_id', related_name='customer')
    owner = models.ForeignKey(
        User, models.SET_NULL, blank=True, null=True, db_column='owner_id', related_name='customers_owned'
    )
    converted_by = models.ForeignKey(
        User, models.DO_NOTHING, db_column='converted_by_id', related_name='customers_converted'
    )
    requirement = models.TextField(blank=True, null=True)
    service = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    contact_person = models.CharField(max_length=255, blank=True, null=True, db_column='contact_person')
    alternate_phone = models.CharField(max_length=100, blank=True, null=True, db_column='alternate_phone')
    converted_at = models.DateTimeField(auto_now_add=True, db_column='converted_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')

    class Meta:
        managed = False
        db_table = 'customers'


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    actor = models.ForeignKey(
        User, models.SET_NULL, blank=True, null=True, db_column='actor_id', related_name='audit_logs'
    )
    entity_type = models.CharField(max_length=50, db_column='entity_type')
    entity_id = models.IntegerField(db_column='entity_id')
    action = models.CharField(max_length=100)
    old_value = models.JSONField(blank=True, null=True, db_column='old_value')
    new_value = models.JSONField(blank=True, null=True, db_column='new_value')
    metadata = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')

    class Meta:
        managed = False
        db_table = 'audit_logs'


class LeadNote(models.Model):
    id = models.AutoField(primary_key=True)
    lead = models.ForeignKey(Lead, models.CASCADE, db_column='lead_id', related_name='notes')
    text = models.TextField()
    created_by = models.ForeignKey(
        User, models.SET_NULL, blank=True, null=True, db_column='created_by', related_name='lead_notes'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')

    class Meta:
        managed = False
        db_table = 'lead_notes'


class LeadFollowUp(models.Model):
    id = models.AutoField(primary_key=True)
    lead = models.ForeignKey(Lead, models.CASCADE, db_column='lead_id', related_name='follow_ups')
    due_date = models.DateTimeField(db_column='due_date')
    note = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, default='pending')  # pending, done
    created_by = models.ForeignKey(
        User, models.SET_NULL, blank=True, null=True, db_column='created_by', related_name='lead_follow_ups'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')

    class Meta:
        managed = False
        db_table = 'lead_follow_ups'


class File(models.Model):
    id = models.AutoField(primary_key=True)
    original_name = models.CharField(max_length=255, db_column='original_name')
    s3_key = models.CharField(unique=True, max_length=500, db_column='s3_key')
    mime_type = models.CharField(max_length=255, blank=True, null=True, db_column='mime_type')
    size = models.BigIntegerField()
    uploaded_by = models.ForeignKey(
        User, models.DO_NOTHING, db_column='uploaded_by_id', related_name='uploaded_files'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, db_column='uploaded_at')

    class Meta:
        managed = False
        db_table = 'files'


class FileFolder(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        User, models.CASCADE, db_column='owner_id', related_name='file_folders'
    )
    parent = models.ForeignKey(
        'self', models.CASCADE, blank=True, null=True, db_column='parent_id', related_name='children'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')

    class Meta:
        managed = False
        db_table = 'file_folders'
        unique_together = (('owner', 'parent', 'name'),)


class FileFolderAssignment(models.Model):
    id = models.AutoField(primary_key=True)
    file = models.ForeignKey(File, models.CASCADE, db_column='file_id', related_name='folder_assignments')
    folder = models.ForeignKey(FileFolder, models.CASCADE, db_column='folder_id', related_name='assignments')
    owner = models.ForeignKey(User, models.CASCADE, db_column='owner_id', related_name='folder_assignments')
    assigned_by = models.ForeignKey(
        User, models.SET_NULL, blank=True, null=True, db_column='assigned_by_id', related_name='folder_assignment_logs'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')

    class Meta:
        managed = False
        db_table = 'file_folder_assignments'
        unique_together = (('file', 'owner'),)


class SmBusinessCategory(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(unique=True, max_length=150)
    created_by_id = models.IntegerField(db_column='created_by_id')
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')

    class Meta:
        managed = False
        db_table = 'sm_business_categories'


class SmPlatform(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    code = models.CharField(unique=True, max_length=110)
    icon_key = models.CharField(max_length=40, blank=True, null=True, db_column='icon_key')
    logo_data = models.TextField(blank=True, null=True, db_column='logo_data')
    is_active = models.BooleanField(default=True, db_column='is_active')
    created_by_id = models.IntegerField(blank=True, null=True, db_column='created_by_id')
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')

    class Meta:
        managed = False
        db_table = 'sm_platforms'


class SmTermsVersion(models.Model):
    id = models.AutoField(primary_key=True)
    version = models.IntegerField(unique=True)
    title = models.CharField(max_length=200)
    body = models.TextField()
    created_by_id = models.IntegerField(db_column='created_by_id')
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')

    class Meta:
        managed = False
        db_table = 'sm_terms_versions'


class SmCustomer(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200)
    business_category = models.CharField(max_length=150, blank=True, null=True, db_column='businessCategory')
    status = models.CharField(max_length=24, default='active')
    handled_by = models.CharField(max_length=200, blank=True, null=True, db_column='handledBy')
    plan_details = models.TextField(blank=True, null=True, db_column='planDetails')
    notes = models.TextField(blank=True, null=True)
    created_by_id = models.IntegerField(db_column='created_by_id')
    updated_by_id = models.IntegerField(blank=True, null=True, db_column='updated_by_id')
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')
    archived_at = models.DateTimeField(blank=True, null=True, db_column='archived_at')

    class Meta:
        managed = False
        db_table = 'sm_customers'


class SmContact(models.Model):
    id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(SmCustomer, models.DO_NOTHING, db_column='customer_id', related_name='contacts')
    name = models.CharField(max_length=160, blank=True, null=True)
    designation = models.CharField(max_length=120, blank=True, null=True)
    kind = models.CharField(max_length=12)  # email, phone
    value = models.CharField(max_length=255)
    is_primary = models.BooleanField(default=False, db_column='is_primary')

    class Meta:
        managed = False
        db_table = 'sm_contacts'


class SmAddress(models.Model):
    id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(SmCustomer, models.DO_NOTHING, db_column='customer_id', related_name='addresses')
    label = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField()

    class Meta:
        managed = False
        db_table = 'sm_addresses'


class SmAccount(models.Model):
    id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(SmCustomer, models.DO_NOTHING, db_column='customer_id', related_name='accounts')
    platform = models.CharField(max_length=100)
    platform_record = models.ForeignKey(
        SmPlatform, models.DO_NOTHING, blank=True, null=True, db_column='platform_id', related_name='accounts'
    )
    label = models.CharField(max_length=160, blank=True, null=True)
    handle = models.CharField(max_length=200, blank=True, null=True)
    profile_url = models.CharField(max_length=1000, blank=True, null=True, db_column='profile_url')
    login_email = models.CharField(max_length=255, blank=True, null=True, db_column='login_email')
    login_phone = models.CharField(max_length=40, blank=True, null=True, db_column='login_phone')
    account_user_id = models.CharField(max_length=255, blank=True, null=True, db_column='account_user_id')
    access_type = models.CharField(max_length=30, default='password', db_column='access_type')
    access_status = models.CharField(max_length=30, default='available', db_column='access_status')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')
    archived_at = models.DateTimeField(blank=True, null=True, db_column='archived_at')

    class Meta:
        managed = False
        db_table = 'sm_accounts'


class SmAccountManager(models.Model):
    id = models.AutoField(primary_key=True)
    account = models.ForeignKey(SmAccount, models.DO_NOTHING, db_column='account_id', related_name='managers')
    name = models.CharField(max_length=160, blank=True, null=True)
    email = models.CharField(max_length=255)
    contact = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'sm_account_managers'


class SmCredentialVersion(models.Model):
    id = models.AutoField(primary_key=True)
    account = models.ForeignKey(SmAccount, models.DO_NOTHING, db_column='account_id', related_name='versions')
    version = models.IntegerField()
    encrypted_value = models.TextField(db_column='encrypted_value')
    iv = models.CharField(max_length=40)
    tag = models.CharField(max_length=40)
    key_version = models.CharField(max_length=30, default='v1', db_column='key_version')
    created_by_id = models.IntegerField(db_column='created_by_id')
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')

    class Meta:
        managed = False
        db_table = 'sm_credential_versions'
        unique_together = (('account', 'version'),)


class SmAuditEvent(models.Model):
    id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(SmCustomer, models.DO_NOTHING, db_column='customer_id', related_name='events')
    actor_id = models.IntegerField(db_column='actor_id')
    action = models.CharField(max_length=80)
    subject = models.CharField(max_length=120)
    changes = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')

    class Meta:
        managed = False
        db_table = 'sm_audit_events'


class SmContract(models.Model):
    id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(SmCustomer, models.DO_NOTHING, db_column='customer_id', related_name='contracts')
    terms_version = models.ForeignKey(
        SmTermsVersion, models.DO_NOTHING, db_column='terms_version_id', related_name='contracts'
    )
    starts_at = models.DateTimeField(db_column='starts_at')
    ends_at = models.DateTimeField(db_column='ends_at')
    amount = models.DecimalField(max_digits=13, decimal_places=2)
    frequency = models.CharField(max_length=20)
    s3_key = models.CharField(unique=True, max_length=512, db_column='s3_key')
    status = models.CharField(max_length=20, default='ready')
    snapshot = models.JSONField()
    created_by_id = models.IntegerField(db_column='created_by_id')
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')

    class Meta:
        managed = False
        db_table = 'sm_contracts'
