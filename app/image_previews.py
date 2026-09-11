from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageOps


COVER_PREVIEW_SIZE = (480, 640)


def build_cover_preview(cover):
    """Return a small, browser-friendly preview for a book cover."""
    cover.open('rb')
    with Image.open(cover) as source:
        image = ImageOps.exif_transpose(source)
        image.thumbnail(COVER_PREVIEW_SIZE, Image.Resampling.LANCZOS)
        if image.mode not in ('RGB', 'RGBA'):
            image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')

        output = BytesIO()
        if image.mode == 'RGBA':
            image.save(output, format='WEBP', quality=82, method=6)
        else:
            image.convert('RGB').save(output, format='WEBP', quality=82, method=6)

    stem = Path(cover.name).stem or 'cover'
    # ImageField.upload_to adds the directory itself when saving the file.
    return f'{stem}.webp', ContentFile(output.getvalue())
