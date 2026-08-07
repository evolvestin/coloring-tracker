import os
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from app.models import ColoringSuggestion, TrackerUser
from app.tasks import suggestion_notification_text
from app.views import suggestion_fingerprint, validate_image_upload


class SuggestionTests(TestCase):
    @override_settings(DEBUG=True)
    @patch('app.views.send_suggestion_notification.delay')
    def test_suggestion_is_saved_and_rate_limited(self, enqueue):
        payload = {'title': 'Secret Garden', 'source_text': 'любой источник'}
        with self.captureOnCommitCallbacks(execute=True):
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

    def test_invalid_image_is_rejected(self):
        error = validate_image_upload(SimpleUploadedFile('bad.jpg', b'not an image'))
        self.assertIn('Не удалось распознать изображение', error)
