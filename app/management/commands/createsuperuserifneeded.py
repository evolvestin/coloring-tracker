import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Creates the local Django administrator when it does not exist yet.'

    def handle(self, *args, **options):
        username = os.getenv('DJANGO_SUPERUSER_USERNAME')
        password = os.getenv('DJANGO_SUPERUSER_PASSWORD')
        email = os.getenv('DJANGO_SUPERUSER_EMAIL', '')
        if not username or not password:
            self.stdout.write('Administrator creation skipped: credentials are not configured.')
            return
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            self.stdout.write('Administrator already exists.')
            return
        user_model.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS('Administrator created.'))
