from django.core.management import BaseCommand, CommandError

from app.image_previews import build_cover_preview
from app.models import ColoringBook


class Command(BaseCommand):
    help = 'Rebuild WebP previews for every coloring book cover.'

    def handle(self, *args, **options):
        rebuilt = 0
        cleared = 0
        failed = 0

        for book in ColoringBook.objects.all().iterator():
            old_name = book.cover_preview.name if book.cover_preview else ''
            try:
                if book.cover:
                    preview_name, preview_file = build_cover_preview(book.cover)
                    if old_name:
                        book.cover_preview.delete(save=False)
                    book.cover_preview.save(preview_name, preview_file, save=False)
                    ColoringBook.objects.filter(pk=book.pk).update(
                        cover_preview=book.cover_preview.name
                    )
                    if old_name and old_name != book.cover_preview.name:
                        book.cover_preview.storage.delete(old_name)
                    rebuilt += 1
                elif old_name:
                    book.cover_preview.delete(save=False)
                    ColoringBook.objects.filter(pk=book.pk).update(cover_preview='')
                    cleared += 1
            except (OSError, ValueError) as error:
                failed += 1
                self.stderr.write(f'Не удалось обработать #{book.pk} «{book.title}»: {error}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Готово: пересобрано {rebuilt}, очищено {cleared}, ошибок {failed}.'
            )
        )
        if failed:
            raise CommandError('Часть обложек не удалось обработать; см. список ошибок выше.')
