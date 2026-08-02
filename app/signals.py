from django.db.models.signals import post_delete
from django.dispatch import receiver

from app.models import ColoringColorCode, ColoringPagePhoto


@receiver(post_delete, sender=ColoringPagePhoto)
def delete_page_photo(sender, instance, **kwargs):
    """Remove a page photo only when the independent photo record is removed."""
    if instance.image:
        instance.image.delete(save=False)


@receiver(post_delete, sender=ColoringColorCode)
def delete_color_code_image(sender, instance, **kwargs):
    """Remove the uploaded palette image with its database record."""
    if instance.image:
        instance.image.delete(save=False)
