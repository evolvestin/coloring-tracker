import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'coloring_tracker.settings')
celery_app = Celery('coloring_tracker')
celery_app.config_from_object('django.conf:settings', namespace='CELERY')
celery_app.autodiscover_tasks()
