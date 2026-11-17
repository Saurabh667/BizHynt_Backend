import getpass
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from api.models import User
from api.helpers import hash_password


class Command(BaseCommand):
    help = 'Create, promote, or sync a super admin user for SalesGenerator'

    def add_arguments(self, parser):
        parser.add_argument('--from-env', action='store_true', help='Sync Super Admin credentials directly from .env')
        parser.add_argument('--name', type=str, help='Full Name of Super Admin')
        parser.add_argument('--email', type=str, help='Email address')
        parser.add_argument('--password', type=str, help='Password')
        parser.add_argument('--company', type=str, default='TechSolutions', help='Company name')
        parser.add_argument('--force', action='store_true', help='Overwrite password without prompting if user exists')

    def handle(self, *args, **options):
        from_env = options.get('from_env')
        name = options.get('name')
        email = options.get('email')
        password = options.get('password')
        company = options.get('company') or 'TechSolutions'
        force = options.get('force')

        if from_env:
            email = getattr(settings, 'SUPER_ADMIN_EMAIL', None)
            password = getattr(settings, 'SUPER_ADMIN_PASSWORD', None)
            name = getattr(settings, 'SUPER_ADMIN_NAME', 'Super Admin')

            if not email or not password:
                raise CommandError('SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD must be defined in .env')
            
            self.stdout.write(f"Syncing Super Admin from .env: {email}")
            force = True

        elif not email or not password:
            if not name:
                name = input('Name: ').strip()
            if not email:
                email = input('Email: ').strip().lower()
            if not password:
                password = getpass.getpass('Password: ').strip()
                confirm = getpass.getpass('Confirm Password: ').strip()
                if password != confirm:
                    raise CommandError('Passwords do not match.')

        if not name or not email or not password:
            raise CommandError('Name, email, and password cannot be empty.')

        email = email.strip().lower()
        existing_user = User.objects.filter(email=email).first()

        if existing_user:
            if not force:
                self.stdout.write(self.style.WARNING(f"User with email '{email}' already exists."))
                confirm = input("Do you want to promote this user to super_admin and update their password? (y/N): ")
                if confirm.lower() != 'y':
                    self.stdout.write("Operation cancelled.")
                    return

            existing_user.role = 'super_admin'
            existing_user.name = name or existing_user.name
            existing_user.password = hash_password(password)
            existing_user.is_active = True
            existing_user.save()
            self.stdout.write(self.style.SUCCESS(f"Successfully updated/synced super_admin '{email}' (ID: {existing_user.id})!"))
            return

        user = User.objects.create(
            name=name,
            email=email,
            password=hash_password(password),
            company_name=company,
            role='super_admin',
            is_active=True
        )
        self.stdout.write(self.style.SUCCESS(f"Super admin user '{user.email}' created successfully! (ID: {user.id})"))
