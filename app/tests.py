import asyncio
import os
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app.models import ColoringBook, ColoringPage, ColoringSuggestion, TrackerUser, UserBook
from app.page_import import parse_pages_json, sync_book_pages
from app.tasks import send_suggestion_notification, suggestion_notification_text
from app.views import suggestion_fingerprint, validate_image_upload
from tracker_bot.main import copy_moderator_reply


class SuggestionTests(TransactionTestCase):
    @override_settings(DEBUG=True)
    @patch('app.views.send_suggestion_notification.delay')
    def test_suggestion_is_saved_and_rate_limited(self, enqueue):
        payload = {'title': 'Secret Garden', 'source_text': 'любой источник'}
        response = self.client.post(
            '/api/tracker/suggestions/?dev=true', payload, content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ColoringSuggestion.objects.count(), 1)
        enqueue.assert_called_once()

        limited = self.client.post(
            '/api/tracker/suggestions/?dev=true', payload, content_type='application/json'
        )
        self.assertEqual(limited.status_code, 429)

        suggestion = ColoringSuggestion.objects.get()
        suggestion.created_at = timezone.now() - timedelta(seconds=31)
        suggestion.save(update_fields=('created_at',))
        duplicate = self.client.post(
            '/api/tracker/suggestions/?dev=true', payload, content_type='application/json'
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_notification_escapes_user_text_and_has_links(self):
        user = TrackerUser.objects.create(
            telegram_id=123456,
            display_name='Имя <Фамилия>',
            username='name&tag',
        )
        suggestion = ColoringSuggestion.objects.create(
            user=user,
            title='<script>alert(1)</script>',
            source_text='https://example.test/?a=1&b=2',
            fingerprint=suggestion_fingerprint('title', 'source'),
        )
        with patch.dict(
            os.environ,
            {'TELEGRAM_WEBAPP_URL': 'https://tracker.example/'},
        ):
            message = suggestion_notification_text(suggestion)
        self.assertIn('&lt;script&gt;', message)
        self.assertIn('&amp;', message)
        self.assertIn(f'admin/app/coloringsuggestion/{suggestion.pk}/change/', message)
        self.assertIn('tg://user?id=123456', message)
        self.assertIn('Ответьте на это сообщение', message)

    @patch('app.tasks._send_telegram_message', new_callable=AsyncMock)
    def test_notification_stores_group_message_reference(self, send_message):
        user = TrackerUser.objects.create(telegram_id=123456)
        suggestion = ColoringSuggestion.objects.create(
            user=user,
            title='Secret Garden',
            fingerprint=suggestion_fingerprint('title', 'source'),
        )
        send_message.return_value = SimpleNamespace(chat=SimpleNamespace(id=-10042), message_id=77)

        with patch.dict(
            os.environ,
            {
                'TELEGRAM_BOT_TOKEN': 'token',
                'TELEGRAM_SUGGESTIONS_CHAT_ID': '-10042',
                'TELEGRAM_WEBAPP_URL': 'https://tracker.example/',
            },
        ):
            self.assertTrue(send_suggestion_notification(suggestion.pk))

        suggestion.refresh_from_db()
        self.assertEqual(suggestion.moderation_chat_id, -10042)
        self.assertEqual(suggestion.moderation_message_id, 77)

    def test_group_reply_is_copied_to_the_requesting_user(self):
        user = TrackerUser.objects.create(telegram_id=123456)
        suggestion = ColoringSuggestion.objects.create(
            user=user,
            title='Secret Garden',
            fingerprint=suggestion_fingerprint('title', 'source'),
            moderation_chat_id=-10042,
            moderation_message_id=77,
        )
        message = SimpleNamespace(
            chat=SimpleNamespace(id=-10042),
            reply_to_message=SimpleNamespace(message_id=77),
            copy_to=AsyncMock(),
        )

        with patch.dict(os.environ, {'TELEGRAM_SUGGESTIONS_CHAT_ID': '-10042'}):
            asyncio.run(copy_moderator_reply(message))

        message.copy_to.assert_awaited_once_with(chat_id=123456)
        suggestion.refresh_from_db()
        self.assertIsNotNone(suggestion.reply_sent_at)
        self.assertEqual(suggestion.reply_error, '')

    def test_invalid_image_is_rejected(self):
        error = validate_image_upload(SimpleUploadedFile('bad.jpg', b'not an image'))
        self.assertIn('Не удалось распознать изображение', error)


class PersonalBookTests(TestCase):
    @override_settings(DEBUG=True)
    def test_personal_book_is_created_with_pages_and_hidden_from_catalog(self):
        response = self.client.post(
            '/api/tracker/personal-books/?dev=true',
            {
                'title': 'Мой сад',
                'emoji': '🌷',
                'pages': [
                    {'number': 1, 'title': 'Начало'},
                    {'number': 2, 'spread_end': 3},
                ],
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        user_book = UserBook.objects.get()
        self.assertTrue(user_book.book.is_personal)
        self.assertEqual(user_book.book.owner_id, user_book.user_id)
        self.assertEqual(user_book.book.report_icon, '🌷')
        self.assertEqual(user_book.book.pages.count(), 2)
        self.assertEqual(user_book.book.pages.get(number=2).page_count, 2)

        catalog = self.client.get('/api/tracker/catalog/?dev=true')
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.json()['books'], [])

    @override_settings(DEBUG=True)
    def test_personal_pages_reject_overlaps_and_allow_spreads(self):
        created = self.client.post(
            '/api/tracker/personal-books/?dev=true',
            {'title': 'Черновик', 'emoji': '🌸', 'pages': [{'number': 1}]},
            content_type='application/json',
        )
        user_book_id = created.json()['book']['id']
        overlap = self.client.post(
            f'/api/tracker/personal-books/{user_book_id}/pages/?dev=true',
            {'number': 1, 'spread_end': 2},
            content_type='application/json',
        )
        self.assertEqual(overlap.status_code, 400)
        added = self.client.post(
            f'/api/tracker/personal-books/{user_book_id}/pages/?dev=true',
            {'number': 2, 'spread_end': 3, 'title': 'Разворот'},
            content_type='application/json',
        )
        self.assertEqual(added.status_code, 201)
        self.assertEqual(added.json()['page']['label'], '2–3')

    @override_settings(DEBUG=True)
    def test_personal_book_allows_zero_pages_but_rejects_three_page_spread_and_over_limit(self):
        empty = self.client.post(
            '/api/tracker/personal-books/?dev=true',
            {'title': 'Пустая', 'emoji': '🌸', 'pages': []},
            content_type='application/json',
        )
        self.assertEqual(empty.status_code, 201)
        user_book_id = empty.json()['book']['id']
        profile = self.client.get('/api/tracker/profile/?dev=true')
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()['stats']['progress'], 0)

        invalid_spread = self.client.patch(
            f'/api/tracker/personal-books/{user_book_id}/?dev=true',
            {'pages': [{'id': None, 'number': 1, 'spread_end': 3}]},
            content_type='application/json',
        )
        self.assertEqual(invalid_spread.status_code, 400)
        self.assertIn('ровно из двух', invalid_spread.json()['error'])

        too_many = self.client.patch(
            f'/api/tracker/personal-books/{user_book_id}/?dev=true',
            {'pages': [{'id': None, 'number': number} for number in range(1, 302)]},
            content_type='application/json',
        )
        self.assertEqual(too_many.status_code, 400)
        self.assertIn('не больше 300', too_many.json()['error'])

        cleared = self.client.patch(
            f'/api/tracker/personal-books/{user_book_id}/?dev=true',
            {'pages': []},
            content_type='application/json',
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()['book']['total'], 0)

    @override_settings(DEBUG=True)
    def test_personal_book_is_not_visible_to_another_user(self):
        created = self.client.post(
            '/api/tracker/personal-books/?dev=true',
            {'title': 'Только моя', 'emoji': '🦋', 'pages': [{'number': 1}]},
            content_type='application/json',
        )
        user_book_id = created.json()['book']['id']
        other_user = TrackerUser.objects.create(session_key='other-session')
        with patch('app.views.tracker_identity', return_value=other_user):
            response = self.client.get(f'/api/tracker/books/{user_book_id}/?dev=true')
            update = self.client.patch(
                f'/api/tracker/personal-books/{user_book_id}/?dev=true',
                {'title': 'Украденное имя', 'emoji': '🌹'},
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(update.status_code, 404)


class PageJsonImportTests(TestCase):
    def test_parser_accepts_pages_and_spreads(self):
        pages = parse_pages_json('{"1": "stitch", "2-3": "bebra"}')

        self.assertEqual(pages, [(1, None, 'stitch'), (2, 3, 'bebra')])

    def test_parser_rejects_overlapping_ranges(self):
        with self.assertRaisesMessage(ValidationError, 'пересекаются'):
            parse_pages_json('{"1-3": "one", "3": "three"}')

    def test_sync_replaces_pages_and_keeps_matching_page(self):
        book = ColoringBook.objects.create(title='Книга')
        first = ColoringPage.objects.create(book=book, number=1, title='old')
        ColoringPage.objects.create(book=book, number=2, title='to delete')
        ColoringPage.objects.create(book=book, number=4, title='to merge')

        result = sync_book_pages(book, parse_pages_json('{"1": "new", "3-4": "spread"}'))

        self.assertEqual(result, {'created': 1, 'updated': 1, 'deleted': 2, 'total': 2})
        first.refresh_from_db()
        self.assertEqual(first.title, 'new')
        self.assertEqual(first.spread_end, None)
        self.assertEqual(
            list(book.pages.values_list('number', 'spread_end', 'title')),
            [(1, None, 'new'), (3, 4, 'spread')],
        )

    def test_admin_import_page_synchronises_book(self):
        admin_user = get_user_model().objects.create_superuser(
            username='admin', email='admin@example.com', password='password'
        )
        self.client.force_login(admin_user)
        book = ColoringBook.objects.create(title='Книга')

        response = self.client.post(
            reverse('admin:app_coloringbook_pages_json', args=(book.pk,)),
            {'pages_json': '{"1": "stitch", "2-3": "bebra"}'},
        )

        self.assertRedirects(response, reverse('admin:app_coloringbook_change', args=(book.pk,)))
        self.assertEqual(book.pages.count(), 2)
        self.assertEqual(book.pages.get(number=2).spread_end, 3)
