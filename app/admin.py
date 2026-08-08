import json

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.forms.utils import flatatt
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, mark_safe

from app.models import (
    FLOWER_ICONS,
    ColoringBook,
    ColoringColorCode,
    ColoringPage,
    ColoringPagePhoto,
    ColoringSuggestion,
    ColoringWork,
    TrackerUser,
    UserBook,
)
from app.page_import import ColoringBookPagesImportForm, sync_book_pages
from app.tasks import send_suggestion_reply


class FlowerIconSelect(forms.Select):
    class Media:
        css = {'all': ('app/admin/flower-icon-picker.css',)}
        js = ('app/admin/flower-icon-picker.js',)

    def render(self, name, value, attrs=None, renderer=None):
        final_attrs = self.build_attrs(self.attrs, attrs)
        input_id = final_attrs.get('id', name)
        current_value = '' if value is None else str(value)
        unused_icons = set(self.attrs.get('data-unused-icons', []))
        options = []

        for option_value, option_label in self.choices:
            option_value = '' if option_value is None else str(option_value)
            selected = option_value == current_value
            is_unused = bool(option_value and option_value in unused_icons)
            state = 'свободен' if is_unused else 'уже используется'
            classes = 'flower-icon-option'
            if selected:
                classes += ' is-selected'
            if is_unused:
                classes += ' is-unused'
            label = 'Без значка' if not option_value else option_label
            aria_label = label if not option_value else f'{label} — {state}'
            options.append(
                format_html(
                    '<button type="button" class="{}" data-value="{}" '
                    'aria-label="{}" aria-pressed="{}" title="{}">'
                    '<span class="flower-icon-glyph">{}</span><small>{}</small></button>',
                    classes,
                    option_value,
                    aria_label,
                    'true' if selected else 'false',
                    aria_label,
                    label,
                    'свободен' if is_unused else ('выбран' if selected else ''),
                )
            )

        hidden_attrs = {
            'type': 'hidden',
            'name': name,
            'id': input_id,
            'value': current_value,
        }
        hidden = format_html('<input{}>', flatatt(hidden_attrs))
        return format_html(
            '<div class="flower-icon-picker" data-flower-icon-picker>{}<div '
            'class="flower-icon-options">{}</div><p class="flower-icon-help">'
            'Зелёные варианты ещё не выбраны ни у одной раскраски.</p></div>',
            hidden,
            mark_safe(''.join(str(option) for option in options)),
        )


class ColoringBookAdminForm(forms.ModelForm):
    class Meta:
        model = ColoringBook
        fields = '__all__'
        widgets = {'report_icon': FlowerIconSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        used_icons = set(
            ColoringBook.objects.filter(owner__isnull=True)
            .exclude(pk=self.instance.pk)
            .exclude(report_icon='')
            .values_list('report_icon', flat=True)
        )
        self.fields['report_icon'].widget.attrs['data-unused-icons'] = [
            icon for icon in FLOWER_ICONS if icon not in used_icons
        ]


class ColoringPageFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        pages = []
        for form in self.forms:
            if not form.is_valid():
                continue
            if self._should_delete_form(form):
                continue
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            number = form.cleaned_data.get('number')
            if number is None:
                continue
            spread_end = form.cleaned_data.get('spread_end')
            last_page = spread_end or number
            pages.append((number, last_page, form))

        pages.sort(key=lambda item: item[0])
        for i in range(len(pages) - 1):
            num1, last1, form1 = pages[i]
            num2, last2, form2 = pages[i + 1]
            if num1 <= last2 and num2 <= last1:
                msg = 'Страницы и развороты в одной раскраске не должны пересекаться.'
                form1.add_error('number', msg)
                form2.add_error('number', msg)


class ColoringPageInline(admin.TabularInline):
    model = ColoringPage
    formset = ColoringPageFormSet
    extra = 1
    fields = ('number', 'spread_end', 'title')
    template = 'admin/app/coloringpage/tabular.html'


def pluralize_ru(count, one, two, many):
    n = abs(count) % 100
    n1 = n % 10
    if 11 <= n <= 19:
        return f'{count} {many}'
    if 2 <= n1 <= 4:
        return f'{count} {two}'
    if n1 == 1:
        return f'{count} {one}'
    return f'{count} {many}'


@admin.register(ColoringBook)
class ColoringBookAdmin(admin.ModelAdmin):
    form = ColoringBookAdminForm
    change_form_template = 'admin/app/coloringbook/change_form.html'
    list_display = (
        'title',
        'owner',
        'report_icon',
        'author',
        'publisher',
        'is_published',
        'page_count',
    )
    list_filter = ('is_published',)
    search_fields = ('title', 'author', 'publisher', 'owner__display_name', 'owner__username')
    inlines = (ColoringPageInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('pages')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/pages-json/',
                self.admin_site.admin_view(self.pages_json_view),
                name='app_coloringbook_pages_json',
            ),
        ]
        return custom_urls + urls

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['pages_json_url'] = reverse(
            'admin:app_coloringbook_pages_json', args=(object_id,)
        )
        return super().change_view(request, object_id, form_url, extra_context)

    def pages_json_view(self, request, object_id):
        book = get_object_or_404(ColoringBook, pk=object_id)
        if not self.has_change_permission(request, book):
            raise PermissionDenied

        initial = {
            (
                f'{page.number}-{page.spread_end}' if page.spread_end else str(page.number)
            ): page.title
            for page in book.pages.all().order_by('number')
        }
        form = ColoringBookPagesImportForm(
            request.POST if request.method == 'POST' else None,
            initial={'pages_json': json.dumps(initial, ensure_ascii=False, indent=2)},
        )
        if request.method == 'POST' and form.is_valid():
            result = sync_book_pages(book, form.cleaned_data['pages_json'])
            self.message_user(
                request,
                'Страницы синхронизированы: '
                f'создано {result["created"]}, изменено {result["updated"]}, '
                f'удалено {result["deleted"]}.',
                messages.SUCCESS,
            )
            return redirect('admin:app_coloringbook_change', object_id=book.pk)

        context = {
            **self.admin_site.each_context(request),
            'title': 'Импорт страниц из JSON',
            'book': book,
            'form': form,
            'change_url': reverse('admin:app_coloringbook_change', args=(book.pk,)),
            'opts': self.model._meta,
        }
        return TemplateResponse(request, 'admin/app/coloringbook/pages_json.html', context)

    @admin.display(description='Страниц')
    def page_count(self, book):
        total = book.total_pages_count
        spreads = book.spreads_count
        if spreads:
            return f'{total} ({pluralize_ru(spreads, "разворот", "разворота", "разворотов")})'
        return str(total)


@admin.register(UserBook)
class UserBookAdmin(admin.ModelAdmin):
    list_display = ('book', 'user', 'created_at')
    search_fields = ('book__title', 'user__username')


@admin.register(ColoringWork)
class ColoringWorkAdmin(admin.ModelAdmin):
    list_display = ('user_book', 'page', 'completed_at', 'hide_in_report')
    list_filter = ('completed_at', 'user_book__book', 'hide_in_report')
    fields = ('user_book', 'page', 'completed_at', 'note', 'hide_in_report')


@admin.register(ColoringPagePhoto)
class ColoringPagePhotoAdmin(admin.ModelAdmin):
    list_display = ('user_book', 'page', 'created_at')
    list_filter = ('user_book__book',)
    fields = ('user_book', 'page', 'image')


@admin.register(ColoringColorCode)
class ColoringColorCodeAdmin(admin.ModelAdmin):
    list_display = ('user_book', 'page', 'created_at')
    list_filter = ('user_book__book',)
    fields = ('user_book', 'page', 'image')


class TelegramReplyTextarea(forms.Textarea):
    class Media:
        css = {'all': ('app/admin/telegram-reply-editor.css',)}
        js = ('app/admin/telegram-reply-editor.js',)


class ColoringSuggestionAdminForm(forms.ModelForm):
    send_reply = forms.BooleanField(
        required=False,
        label='Отправить ответ пользователю сейчас',
        help_text=(
            'После сохранения ответ уйдёт в Telegram. Поддерживаются HTML-теги Telegram: '
            '&lt;b&gt;, &lt;i&gt;, &lt;u&gt;, &lt;s&gt;, &lt;code&gt;, &lt;pre&gt; и '
            '&lt;a href="..."&gt;ссылка&lt;/a&gt;.'
        ),
    )

    class Meta:
        model = ColoringSuggestion
        fields = '__all__'
        widgets = {
            'admin_reply': TelegramReplyTextarea(attrs={'rows': 10}),
        }

    def clean_admin_reply(self):
        reply = self.cleaned_data['admin_reply']
        if len(reply) > 4096:
            raise forms.ValidationError(
                'Telegram принимает сообщения длиной не более 4096 символов.'
            )
        return reply

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('send_reply') and not cleaned.get('admin_reply', '').strip():
            self.add_error('admin_reply', 'Введите текст ответа перед отправкой.')
        return cleaned


@admin.register(ColoringSuggestion)
class ColoringSuggestionAdmin(admin.ModelAdmin):
    form = ColoringSuggestionAdminForm
    list_display = (
        'title',
        'user_link',
        'created_at',
        'notification_status',
        'reply_status',
    )
    list_filter = ('notification_sent_at', 'reply_sent_at', 'created_at')
    search_fields = ('title', 'source_text', 'user__display_name', 'user__username')
    readonly_fields = (
        'user_link',
        'fingerprint',
        'notification_sent_at',
        'notification_error',
        'reply_sent_at',
        'reply_error',
        'created_at',
        'updated_at',
    )
    fieldsets = (
        (
            'Предложение',
            {'fields': ('user_link', 'title', 'source_text', 'created_at', 'updated_at')},
        ),
        (
            'Техническая проверка',
            {'fields': ('fingerprint', 'notification_sent_at', 'notification_error')},
        ),
        (
            'Ответ пользователю',
            {
                'fields': (
                    'admin_reply',
                    'send_reply',
                    'reply_sent_at',
                    'reply_error',
                ),
                'description': (
                    'Текст отправляется с HTML-разметкой Telegram. Если нужно отправить тот же '
                    'текст ещё раз, сохраните его с включённым флажком.'
                ),
            },
        ),
    )

    @admin.display(description='Пользователь')
    def user_link(self, suggestion):
        url = reverse('admin:app_trackeruser_change', args=(suggestion.user_id,))
        return format_html('<a href="{}">{}</a>', url, suggestion.user)

    @admin.display(description='Уведомление')
    def notification_status(self, suggestion):
        if suggestion.notification_sent_at:
            return 'Отправлено'
        return (
            'Ошибка: ' + suggestion.notification_error[:80]
            if suggestion.notification_error
            else 'В очереди'
        )

    @admin.display(description='Ответ')
    def reply_status(self, suggestion):
        if suggestion.reply_sent_at:
            return 'Отправлен'
        return (
            'Ошибка: ' + suggestion.reply_error[:80] if suggestion.reply_error else 'Не отправлен'
        )

    def save_model(self, request, obj, form, change):
        send_reply = form.cleaned_data.get('send_reply', False)
        super().save_model(request, obj, form, change)
        if send_reply:
            obj.reply_sent_at = None
            obj.reply_error = ''
            obj.save(update_fields=('reply_sent_at', 'reply_error', 'updated_at'))

            def queue_reply(suggestion_id=obj.pk):
                try:
                    send_suggestion_reply.delay(suggestion_id)
                except Exception as exc:
                    ColoringSuggestion.objects.filter(pk=suggestion_id).update(
                        reply_error=str(exc)[:4000], updated_at=timezone.now()
                    )

            transaction.on_commit(queue_reply)


@admin.register(TrackerUser)
class TrackerUserAdmin(admin.ModelAdmin):
    list_display = (
        'display_name',
        'username',
        'telegram_id',
        'tracker_preview_link',
        'webapp_viewport',
        'created_at',
    )
    search_fields = ('display_name', 'username', 'telegram_id')
    readonly_fields = ('tracker_preview_link',)

    @admin.display(description='Предпросмотр')
    def tracker_preview_link(self, user):
        if not user.telegram_id:
            return '—'
        url = reverse('tracker-preview', args=(user.telegram_id,))
        return format_html('<a href="{}" target="_blank" rel="noopener">Открыть iframe</a>', url)

    @admin.display(description='Размер WebApp')
    def webapp_viewport(self, user):
        if not user.webapp_viewport_width or not user.webapp_viewport_height:
            return '—'
        return f'{user.webapp_viewport_width} × {user.webapp_viewport_height}'
