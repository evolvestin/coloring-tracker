import hashlib

from django.core.management.base import BaseCommand

from app.models import ColoringBook, ColoringPage, Marker, MarkerPalette, MarkerPaletteItem, TrackerUser, UserBook


class Command(BaseCommand):
    help = 'Создаёт локальные демонстрационные палитры маркеров для проверки WebApp.'

    def handle(self, *args, **options):
        book, _ = ColoringBook.objects.get_or_create(
            title='Демо-палитры · Сад цветов',
            defaults={'author': 'Демонстрация', 'is_published': True},
        )
        pages = [ColoringPage.objects.get_or_create(book=book, number=number)[0] for number in range(1, 5)]
        users = []
        for index in range(1, 4):
            user, _ = TrackerUser.objects.get_or_create(
                telegram_id=990000000 + index,
                defaults={'display_name': f'Демо-пользователь {index}'},
            )
            users.append(user)
        user_books = [UserBook.objects.get_or_create(user=user, book=book)[0] for user in users]
        sets = [
            [('✦', '599', 'medium'), ('❀', 'Y34', 'little'), ('◈', 'BG3', 'much'), ('☾', '120', '')],
            [('✧', '599', 'little'), ('❁', 'Y34', 'medium'), ('◇', 'BG3', 'medium'), ('☽', '120', 'little'), ('⚘', '407', 'much')],
            [('✦', '599', 'medium'), ('❀', 'Y34', 'little'), ('◈', 'BG3', 'much'), ('☾', '120', '')],
        ]
        palettes = []
        for index, items in enumerate(sets):
            palette_items = []
            for symbol, number, usage in items:
                marker, _ = Marker.objects.get_or_create(
                    manufacturer='unknown',
                    number=number,
                    defaults={'symbol': symbol, 'created_by': users[index]},
                )
                palette_items.append({'marker_id': marker.id, 'symbol': symbol, 'usage_level': usage})
            fingerprint = hashlib.sha256('|'.join(sorted(f"{item['marker_id']}:{item['symbol']}:{item['usage_level']}" for item in palette_items)).encode()).hexdigest()
            palette, _ = MarkerPalette.objects.update_or_create(
                user_book=user_books[index],
                page=pages[0],
                defaults={'allow_import': True, 'fingerprint': fingerprint},
            )
            palette.items.all().delete()
            MarkerPaletteItem.objects.bulk_create([
                MarkerPaletteItem(palette=palette, position=position, **item)
                for position, item in enumerate(palette_items)
            ])
            palettes.append(palette)
        palettes[2].imported_from = palettes[0]
        palettes[2].save(update_fields=('imported_from', 'updated_at'))
        self.stdout.write(self.style.SUCCESS(
            'Демо-палитры готовы. Откройте iframe для Telegram ID 990000003.'
        ))
