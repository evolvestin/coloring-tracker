"""Parse and synchronise the compact JSON format used for coloring pages."""

import json
import re

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from app.models import ColoringBook, ColoringPage

PAGE_KEY_RE = re.compile(r'^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$')
MAX_IMPORTED_PAGES = 500


class ColoringBookPagesImportForm(forms.Form):
    pages_json = forms.CharField(
        label='JSON страниц',
        widget=forms.Textarea(attrs={'rows': 24, 'cols': 100, 'spellcheck': 'false'}),
    )

    def clean_pages_json(self):
        raw_json = self.cleaned_data['pages_json']
        return parse_pages_json(raw_json)


def parse_pages_json(raw_json):
    """Return a sorted list of ``(number, spread_end, title)`` tuples."""
    try:
        payload = json.loads(raw_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValidationError('Введите корректный JSON с двойными кавычками.') from exc

    if not isinstance(payload, dict):
        raise ValidationError('JSON должен быть объектом: {"1": "Подпись"}.')
    if len(payload) > MAX_IMPORTED_PAGES:
        raise ValidationError(f'В JSON может быть не больше {MAX_IMPORTED_PAGES} записей.')

    pages = []
    for raw_key, title in payload.items():
        if not isinstance(raw_key, str):
            raise ValidationError('Ключи JSON должны быть строками с номерами страниц.')
        match = PAGE_KEY_RE.fullmatch(raw_key)
        if not match:
            raise ValidationError(
                f'Неверный ключ «{raw_key}». Используйте номер или диапазон, например «2-3». '
            )

        number = int(match.group(1))
        spread_end = int(match.group(2)) if match.group(2) else None
        if number < 1 or (spread_end is not None and spread_end <= number):
            raise ValidationError(
                f'Неверный диапазон «{raw_key}»: номера должны быть положительными, '
                'а конец разворота — больше начала.'
            )
        if not isinstance(title, str):
            raise ValidationError(f'Подпись для «{raw_key}» должна быть строкой.')

        title = title.strip()
        if len(title) > 255:
            raise ValidationError(f'Подпись для «{raw_key}» длиннее 255 символов.')
        pages.append((number, spread_end, title))

    pages.sort(key=lambda page: page[0])
    for previous, current in zip(pages, pages[1:], strict=True):
        previous_end = previous[1] or previous[0]
        if current[0] <= previous_end:
            raise ValidationError(
                f'Страницы «{previous[0]}» и «{current[0]}» пересекаются. Проверьте развороты.'
            )
    return pages


@transaction.atomic
def sync_book_pages(book, pages):
    """Make the book's pages exactly match parsed JSON data."""
    locked_book = ColoringBook.objects.select_for_update().get(pk=book.pk)
    existing = {
        page.number: page
        for page in ColoringPage.objects.select_for_update().filter(book=locked_book)
    }
    desired_numbers = {number for number, _spread_end, _title in pages}

    deleted = 0
    for number, page in existing.items():
        if number not in desired_numbers:
            page.delete()
            deleted += 1

    created = 0
    updated = 0
    for number, spread_end, title in pages:
        page = existing.get(number)
        if page is None:
            ColoringPage.objects.create(
                book=locked_book,
                number=number,
                spread_end=spread_end,
                title=title,
            )
            created += 1
            continue

        if page.spread_end != spread_end or page.title != title:
            page.spread_end = spread_end
            page.title = title
            page.save(update_fields=('spread_end', 'title', 'updated_at'))
            updated += 1

    return {
        'created': created,
        'updated': updated,
        'deleted': deleted,
        'total': len(pages),
    }
