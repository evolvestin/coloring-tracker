import uuid

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
    '🌱',
    '🌲',
    '🌳',
    '🌴',
    '🌵',
    '🎋',
    '🎍',
    '🍁',
    '🍂',
    '🍄',
    '🌰',
    '🐶',
    '🐱',
    '🐭',
    '🐹',
    '🐰',
    '🦊',
    '🐻',
    '🐼',
    '🐨',
    '🐯',
    '🦁',
    '🐮',
    '🐷',
    '🐸',
    '🐵',
    '🙈',
    '🙉',
    '🙊',
    '🐔',
    '🐧',
    '🐦',
    '🦄',
    '🐝',
    '🐞',
    '🐢',
    '🐍',
    '🦎',
    '🐙',
    '🦀',
    '🐳',
    '🐬',
    '🐠',
    '🐟',
    '🦈',
    '🐊',
    '🦖',
    '🦕',
    '🌈',
    '☀️',
    '🌙',
    '⭐',
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
    """A catalogue book or a private book created by one tracker user."""

    title = models.CharField('Название', max_length=255)
    owner = models.ForeignKey(
        TrackerUser,
        on_delete=models.CASCADE,
        related_name='personal_coloring_books',
        null=True,
        blank=True,
        verbose_name='Владелец личной раскраски',
    )
    author = models.CharField('Автор', max_length=255, blank=True)
    publisher = models.CharField('Издательство', max_length=255, blank=True)
    cover = models.ImageField('Обложка', upload_to='books/covers/', blank=True)
    cover_original = models.ImageField(
        'Исходник обложки', upload_to='books/cover-originals/', blank=True
    )
    cover_preview = models.ImageField(
        'Превью обложки', upload_to='books/cover-previews/', blank=True, editable=False
    )
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

    @property
    def is_personal(self):
        return self.owner_id is not None

    @property
    def total_pages_count(self):
        return sum(p.page_count for p in self.pages.all())

    @property
    def total_works_count(self):
        """Number of trackable works; a spread is one work."""
        return self.pages.count()

    @property
    def spreads_count(self):
        return sum(1 for p in self.pages.all() if p.spread_end)


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
    def page_count(self):
        return (self.spread_end - self.number + 1) if self.spread_end else 1

    @property
    def label(self):
        return f'{self.number}–{self.spread_end}' if self.spread_end else str(self.number)

    def __str__(self):
        return f'{self.book}: {self.label}'

    def clean(self):
        super().clean()
        if self.spread_end and self.spread_end <= self.number:
            raise ValidationError({'spread_end': 'Последняя страница должна быть больше первой.'})


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


class RandomizerRun(TimestampedModel):
    """A server-side randomizer launch and the page it selected."""

    user = models.ForeignKey(TrackerUser, on_delete=models.CASCADE, related_name='randomizer_runs')
    user_book = models.ForeignKey(
        UserBook,
        on_delete=models.CASCADE,
        related_name='randomizer_runs',
        null=True,
        blank=True,
    )
    page = models.ForeignKey(ColoringPage, on_delete=models.CASCADE, related_name='randomizer_runs')

    class Meta:
        verbose_name = 'Запуск рандомизатора'
        verbose_name_plural = 'Запуски рандомизатора'
        ordering = ('-created_at',)


class ColoringPagePhoto(TimestampedModel):
    """A user's photo of a page, kept even if its completion mark is removed."""

    user_book = models.ForeignKey(UserBook, on_delete=models.CASCADE, related_name='page_photos')
    page = models.ForeignKey(ColoringPage, on_delete=models.CASCADE, related_name='page_photos')
    image = models.ImageField('Фото работы', upload_to='works/%Y/%m/')
    original_image = models.ImageField(
        'Исходник фото работы', upload_to='works/originals/%Y/%m/', blank=True
    )

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
    original_image = models.ImageField(
        'Исходник цветового кода', upload_to='color-codes/originals/%Y/%m/', blank=True
    )

    class Meta:
        verbose_name = 'Цветовой код'
        verbose_name_plural = 'Цветовые коды'
        constraints = [
            models.UniqueConstraint(fields=('user_book', 'page'), name='unique_coloring_color_code')
        ]

    def __str__(self):
        return f'{self.user_book}: стр. {self.page.label}'


class ColoringSuggestion(TimestampedModel):
    """A catalogue suggestion submitted by a Telegram user."""

    user = models.ForeignKey(TrackerUser, on_delete=models.PROTECT, related_name='suggestions')
    title = models.CharField('Название раскраски', max_length=500)
    source_text = models.TextField('Ссылка или источник', blank=True)
    fingerprint = models.CharField('Отпечаток', max_length=64)
    notification_sent_at = models.DateTimeField('Уведомление отправлено', null=True, blank=True)
    notification_error = models.TextField('Ошибка уведомления', blank=True)
    moderation_chat_id = models.BigIntegerField(
        'ID группы модераторов', null=True, blank=True, db_index=True
    )
    moderation_message_id = models.PositiveBigIntegerField(
        'ID сообщения в группе модераторов', null=True, blank=True
    )
    admin_reply = models.TextField('Ответ пользователю', blank=True)
    reply_sent_at = models.DateTimeField('Ответ отправлен', null=True, blank=True)
    reply_error = models.TextField('Ошибка ответа', blank=True)

    class Meta:
        verbose_name = 'Предложение раскраски'
        verbose_name_plural = 'Предложения раскрасок'
        ordering = ('-created_at',)
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'fingerprint'), name='unique_user_coloring_suggestion'
            )
        ]

    def __str__(self):
        return f'{self.title} — {self.user}'


class StarDonation(TimestampedModel):
    """A Telegram Stars donation invoice and its server-side receipt."""

    STATUS_PENDING = 'pending'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Ожидает оплаты'),
        (STATUS_SUCCEEDED, 'Оплачен'),
        (STATUS_FAILED, 'Ошибка'),
    )

    user = models.ForeignKey(TrackerUser, on_delete=models.PROTECT, related_name='star_donations')
    amount = models.PositiveIntegerField('Сумма, Stars')
    payload = models.CharField(
        'Платёжный payload',
        max_length=128,
        unique=True,
        default=uuid.uuid4,
        editable=False,
    )
    status = models.CharField(
        'Статус', max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    is_test = models.BooleanField('Тестовый платёж', default=False)
    invoice_url = models.URLField('Ссылка на invoice', max_length=1000, blank=True)
    telegram_payment_charge_id = models.CharField(
        'Telegram payment charge ID', max_length=255, unique=True, null=True, blank=True
    )
    provider_payment_charge_id = models.CharField(
        'Provider payment charge ID', max_length=255, blank=True
    )
    paid_at = models.DateTimeField('Дата оплаты', null=True, blank=True)
    error = models.TextField('Ошибка', blank=True)
    notification_sent_at = models.DateTimeField('Уведомление отправлено', null=True, blank=True)
    notification_error = models.TextField('Ошибка уведомления', blank=True)
    notification_chat_id = models.BigIntegerField(
        'ID чата уведомлений', null=True, blank=True, db_index=True
    )
    notification_message_id = models.PositiveBigIntegerField(
        'ID сообщения уведомления', null=True, blank=True
    )

    class Meta:
        verbose_name = 'Донат Stars'
        verbose_name_plural = 'Донаты Stars'
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.amount} Stars — {self.user}'


class TelegramBackup(models.Model):
    class Status(models.TextChoices):
        UPLOADING = 'uploading', 'Загружается'
        UPLOADED = 'uploaded', 'Загружен'
        FAILED = 'failed', 'Ошибка'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_filename = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    part_count = models.PositiveIntegerField(default=0)
    manifest_message_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    manifest_file_id = models.CharField(max_length=512, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UPLOADING)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.source_filename} · {self.created_at:%Y-%m-%d %H:%M:%S}'


class TelegramBackupPart(models.Model):
    backup = models.ForeignKey(
        TelegramBackup,
        on_delete=models.CASCADE,
        related_name='parts',
    )
    part_number = models.PositiveIntegerField()
    filename = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    message_id = models.BigIntegerField(db_index=True)
    file_id = models.CharField(max_length=512)
    file_unique_id = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ('part_number',)
        constraints = [
            models.UniqueConstraint(
                fields=('backup', 'part_number'),
                name='unique_telegram_backup_part',
            )
        ]

    def __str__(self):
        return f'{self.backup_id} · часть {self.part_number}'
