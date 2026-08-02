from django.db.models.signals import post_delete
from django.dispatch import receiver

from app.models import ColoringWork


@receiver(post_delete, sender=ColoringWork)
def delete_work_photo(sender, instance, **kwargs):
    """Keep media storage in sync when a work is removed from the tracker."""
    if instance.photo:
        instance.photo.delete(save=False)
