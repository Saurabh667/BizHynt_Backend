from api.management.commands.createsuperadmin import Command as CreateSuperAdminCommand

class Command(CreateSuperAdminCommand):
    help = 'Create or promote a super admin user for SalesGenerator (alias for createsuperadmin)'
