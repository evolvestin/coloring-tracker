from django.core.exceptions import ValidationError
from django.db import models

FLOWER_ICONS = (
    '🌸',
    '🌷',
    '🌹',
    '🌺',
    '🌻',
    '🌼',
    '💐',
    '🏵️',
    '🪻',
    '🪷',
    '🥀',
    '🌾',
    '💮',
    '🪴',
    '☘️',
    '🍀',
    '🪺',
    '🌿',
    '🍃',
    '🦋',
)
FLOWER_ICON_CHOICES = [(icon, icon) for icon in FLOWER_ICONS]


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TrackerUser(TimestampedModel):
    telegram_id = models.BigIntegerField('Telegram ID', unique=True, null=True, blank=True)
    session_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    username = models.CharField('Username', max_length=255, blank=True)
    display_name = models.CharField('Имя', max_length=255, blank=True)
    photo_url = models.URLField('Аватар', max_length=500, blank=True)
    webapp_viewport_width = models.PositiveIntegerField('Ширина WebApp', null=True, blank=True)
    webapp_viewport_height = models.PositiveIntegerField('Высота WebApp', null=True, blank=True)

    class Meta:
        verbose_name = 'Пользователь трекера'
        verbose_name_plural = 'Пользователи трекера'

    def __str__(self):
        return self.display_name or self.username or str(self.telegram_id or self.pk)


class ColoringBook(TimestampedModel):
    """A book maintained exclusively through the Django admin catalogue."""

    title = models.CharField('Название', max_length=255)
    author = models.CharField('Автор', max_length=255, blank=True)
    publisher = models.CharField('Издательство', max_length=255, blank=True)
    cover = models.ImageField('Обложка', upload_to='books/covers/', blank=True)
    description = models.TextField('Описание', blank=True)
    is_published = models.BooleanField('Опубликована', default=True)
    report_icon = models.CharField(
        'Значок в отчёте', max_length=8, choices=FLOWER_ICON_CHOICES, blank=True
    )

    class Meta:
        verbose_name = 'Раскраска'
        verbose_name_plural = 'Раскраски'
        ordering = ('title',)

    def __str__(self):
        return self.title


class ColoringPage(TimestampedModel):
    """One work; a spread is represented by one record with spread_end set."""

    book = models.ForeignKey(ColoringBook, on_delete=models.CASCADE, related_name='pages')
    number = models.PositiveIntegerField('Первая страница')
    spread_end = models.PositiveIntegerField('Последняя страница разворота', null=True, blank=True)
    title = models.CharField('Подпись', max_length=255, blank=True)

    class Meta:
        verbose_name = 'Страница / разворот'
        verbose_name_plural = 'Страницы / развороты'
        ordering = ('number',)
        constraints = [
            models.UniqueConstraint(fields=('book', 'number'), name='unique_coloring_page')
        ]

    @property
    def label(self):
        return f'{self.number}–{self.spread_end}' if self.spread_end else str(self.number)

    def __str__(self):
        return f'{self.book}: {self.label}'

    def clean(self):
        super().clean()
        if self.spread_end and self.spread_end <= self.number:
            raise ValidationError({'spread_end': 'Последняя страница должна быть больше первой.'})
        if not self.book_id:
            return
        last_page = self.spread_end or self.number
        for page in ColoringPage.objects.filter(book_id=self.book_id).exclude(pk=self.pk):
            existing_last = page.spread_end or page.number
            if self.number <= existing_last and page.number <= last_page:
                raise ValidationError(
                    'Страницы и развороты в одной раскраске не должны пересекаться.'
                )


class UserBook(TimestampedModel):
    book = models.ForeignKey(ColoringBook, on_delete=models.CASCADE, related_name='user_books')
    user = models.ForeignKey(TrackerUser, on_delete=models.CASCADE, related_name='books')

    class Meta:
        verbose_name = 'Раскраска пользователя'
        verbose_name_plural = 'Раскраски пользователей'
        constraints = [
            models.UniqueConstraint(fields=('book', 'user'), name='unique_user_coloring_book')
        ]

    def __str__(self):
        return str(self.book)


class ColoringWork(TimestampedModel):
    user_book = models.ForeignKey(UserBook, on_delete=models.CASCADE, related_name='works')
    page = models.ForeignKey(ColoringPage, on_delete=models.CASCADE, related_name='works')
    completed_at = models.DateField('Дата завершения', auto_now_add=True)
    note = models.CharField('Заметка', max_length=500, blank=True)
    hide_in_report = models.BooleanField('Не отображать в статистике', default=False)

    class Meta:
        verbose_name = 'Раскрашенная работа'
        verbose_name_plural = 'Раскрашенные работы'
        constraints = [
            models.UniqueConstraint(fields=('user_book', 'page'), name='unique_coloring_work')
        ]


class ColoringPagePhoto(TimestampedModel):
    """A user's photo of a page, kept even if its completion mark is removed."""

    user_book = models.ForeignKey(UserBook, on_delete=models.CASCADE, related_name='page_photos')
    page = models.ForeignKey(ColoringPage, on_delete=models.CASCADE, related_name='page_photos')
    image = models.ImageField('Фото работы', upload_to='works/%Y/%m/')

    class Meta:
        verbose_name = 'Фото работы'
        verbose_name_plural = 'Фотографии работ'
        constraints = [
            models.UniqueConstraint(fields=('user_book', 'page'), name='unique_coloring_page_photo')
        ]

    def __str__(self):
        return f'{self.user_book}: стр. {self.page.label}'


class ColoringColorCode(TimestampedModel):
    """A user's palette reference for a page, independent from its completion."""

    user_book = models.ForeignKey(UserBook, on_delete=models.CASCADE, related_name='color_codes')
    page = models.ForeignKey(ColoringPage, on_delete=models.CASCADE, related_name='color_codes')
    image = models.ImageField('Цветовой код', upload_to='color-codes/%Y/%m/')

    class Meta:
        verbose_name = 'Цветовой код'
        verbose_name_plural = 'Цветовые коды'
        constraints = [
            models.UniqueConstraint(fields=('user_book', 'page'), name='unique_coloring_color_code')
        ]

    def __str__(self):
        return f'{self.user_book}: стр. {self.page.label}'
