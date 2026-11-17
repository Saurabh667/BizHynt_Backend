from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Sync Super Admin credentials from .env to the database'

    def handle(self, *args, **options):
        call_command('createsuperadmin', from_env=True)
