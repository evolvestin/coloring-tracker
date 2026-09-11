from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from app.image_previews import build_cover_preview
from app.models import ColoringBook, ColoringColorCode, ColoringPagePhoto


@receiver(pre_save, sender=ColoringBook)
def remember_cover_change(sender, instance, **kwargs):
    if not instance.pk:
        instance._cover_changed = bool(instance.cover)
        instance._old_cover_preview_name = ''
        return

    old = sender.objects.filter(pk=instance.pk).only('cover', 'cover_preview').first()
    instance._cover_changed = bool(old and old.cover.name != instance.cover.name)
    instance._old_cover_preview_name = old.cover_preview.name if old else ''


@receiver(post_save, sender=ColoringBook)
def create_cover_preview(sender, instance, **kwargs):
    old_preview_name = getattr(instance, '_old_cover_preview_name', '')
    changed = getattr(instance, '_cover_changed', False)

    has_duplicate_path = instance.cover_preview.name.startswith(
        'books/cover-previews/books/cover-previews/'
    ) if instance.cover_preview else False
    if instance.cover and (changed or not instance.cover_preview or has_duplicate_path):
        preview_name, preview_file = build_cover_preview(instance.cover)
        if instance.cover_preview:
            instance.cover_preview.delete(save=False)
        instance.cover_preview.save(preview_name, preview_file, save=False)
        sender.objects.filter(pk=instance.pk).update(cover_preview=instance.cover_preview.name)
        if old_preview_name and old_preview_name != instance.cover_preview.name:
            instance.cover_preview.storage.delete(old_preview_name)
    elif not instance.cover and instance.cover_preview:
        preview = instance.cover_preview
        instance.cover_preview = ''
        sender.objects.filter(pk=instance.pk).update(cover_preview='')
        preview.delete(save=False)


@receiver(post_delete, sender=ColoringPagePhoto)
def delete_page_photo(sender, instance, **kwargs):
    """Remove a page photo only when the independent photo record is removed."""
    if instance.image:
        instance.image.delete(save=False)
    if instance.original_image:
        instance.original_image.delete(save=False)


@receiver(post_delete, sender=ColoringColorCode)
def delete_color_code_image(sender, instance, **kwargs):
    """Remove the uploaded palette image with its database record."""
    if instance.image:
        instance.image.delete(save=False)
    if instance.original_image:
        instance.original_image.delete(save=False)
