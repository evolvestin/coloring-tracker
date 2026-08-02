from io import StringIO

from celery import shared_task
from django.core.management import call_command


@shared_task
def backup_tracker_database():
    """Run the database backup command in a Celery worker."""
    output = StringIO()
    call_command('backup_tracker_database', stdout=output)
    return output.getvalue().strip()
