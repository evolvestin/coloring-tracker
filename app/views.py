import hashlib
import hmac
import json
import math
import os
import random
import re
from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import parse_qsl, urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from PIL import Image, UnidentifiedImageError

from app.marker_constants import (
    MARKER_MANUFACTURER_CODES,
    MARKER_MANUFACTURER_LABELS,
    MARKER_MANUFACTURERS,
    MARKER_TYPE_CODES,
    MARKER_TYPE_LABELS,
    MARKER_TYPES,
)
from app.models import (
    FLOWER_ICONS,
    ColoringBook,
    ColoringColorCode,
    ColoringPage,
    ColoringPagePhoto,
    ColoringSuggestion,
    ColoringWork,
    Marker,
    MarkerPalette,
    MarkerPaletteItem,
    RandomizerRun,
    StarDonation,
    TrackerUser,
    UserBook,
)
from app.tasks import send_donation_notification, send_suggestion_notification

REPORT_LAUNCH_DATE = date(2026, 8, 1)
SUGGESTION_COOLDOWN_SECONDS = 30
RANDOMIZER_COOLDOWN_SECONDS = 60 * 60
SUGGESTION_TITLE_LIMIT = 500
SUGGESTION_SOURCE_LIMIT = 100_000
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
PERSONAL_BOOK_TITLE_LIMIT = 255
PERSONAL_PAGE_LIMIT = 300
MARKER_SYMBOL_LIMIT = 32
MARKER_NUMBER_LIMIT = 64
MARKER_NUMBER_RE = re.compile(r'^[A-Z0-9 -]+$')
MARKER_PALETTE_LIMIT = 30
MARKER_SUGGESTION_LIMIT = 12
MARKER_USAGE_WEIGHTS = {
    '': 1,
    MarkerPaletteItem.USAGE_LITTLE: 1,
    MarkerPaletteItem.USAGE_MEDIUM: 2,
    MarkerPaletteItem.USAGE_MUCH: 3,
}
MARKER_USAGE_LABELS = {
    MarkerPaletteItem.USAGE_MUCH: 'Много',
    MarkerPaletteItem.USAGE_MEDIUM: 'Средне',
    MarkerPaletteItem.USAGE_LITTLE: 'Немного',
    '': 'Не указали',
}
MARKER_STATS_PERIOD_DAYS = {
    '1m': 30,
    '3m': 90,
    '6m': 180,
    '1y': 365,
    'all': None,
}
DONATION_TITLE = 'Поддержка трекера'
DONATION_DESCRIPTION = 'Спасибо, что помогаете развивать трекер раскрасок.'
DONATION_PRESETS = (10, 50, 100, 250)
DONATION_MIN_STARS = 1
DONATION_MAX_STARS = 10_000


def stars_test_mode_enabled():
    return (
        settings.DEBUG
        or os.getenv('VITE_DEV_MODE', 'False').lower() == 'true'
        or os.getenv('TELEGRAM_STARS_TEST_MODE', 'false').lower() == 'true'
    )


def stars_enabled():
    return os.getenv('TELEGRAM_STARS_ENABLED', 'false').lower() == 'true'


def donation_amounts():
    return list(DONATION_PRESETS)


def telegram_bot_api(method, data):
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    if not token:
        raise RuntimeError('TELEGRAM_BOT_TOKEN не настроен.')
    encoded_data = {
        key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
        for key, value in data.items()
    }
    request = Request(
        f'https://api.telegram.org/bot{token}/{method}',
        data=urlencode(encoded_data).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    try:
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode())
    except Exception as exc:
        raise RuntimeError(f'Не удалось связаться с Telegram: {exc}') from exc
    if not result.get('ok'):
        raise RuntimeError(result.get('description', 'Telegram отклонил запрос.'))
    return result.get('result')


def media_url(request, field, updated_at=None):
    """Return a same-origin, cache-busted media URL for the WebApp."""
    if not field:
        return ''
    # Keep this relative so media always use the current WebApp origin.
    url = field.url
    return f'{url}?v={int(updated_at.timestamp())}' if updated_at else url


def validate_image_upload(upload):
    if not upload or upload.size > MAX_UPLOAD_BYTES:
        return 'Изображение должно быть не больше 12 МБ.'
    try:
        image = Image.open(upload)
        image.verify()
    except (UnidentifiedImageError, OSError):
        return 'Не удалось распознать изображение. Выберите JPG, PNG или WebP.'
    finally:
        upload.seek(0)
    return ''


def webapp_index(request):
    return render(request, 'webapp/coloring.html')


def tracker_preview_telegram_id(request):
    """Return the impersonated user for an authenticated staff preview only."""
    raw_id = request.headers.get('X-Tracker-Preview-Telegram-ID', '')
    if not raw_id or not request.user.is_active or not request.user.is_staff:
        return None
    try:
        return int(raw_id)
    except ValueError:
        return None


@staff_member_required
def tracker_preview(request, telegram_id):
    """Recreate a saved Telegram WebApp viewport for an administrator."""
    user = get_object_or_404(TrackerUser, telegram_id=telegram_id)
    viewport = None
    if user.webapp_viewport_width and user.webapp_viewport_height:
        viewport = {'width': user.webapp_viewport_width, 'height': user.webapp_viewport_height}
    return render(request, 'webapp/tracker_preview.html', {'user': user, 'viewport': viewport})


@staff_member_required
@xframe_options_sameorigin
def tracker_preview_webapp(request, telegram_id):
    """Serve the WebApp inside an authenticated staff preview frame."""
    get_object_or_404(TrackerUser, telegram_id=telegram_id)
    return webapp_index(request)


def update_webapp_viewport(request, user):
    """Persist the visible WebApp viewport when Telegram opens the app."""
    try:
        width = int(request.headers.get('X-WebApp-Viewport-Width', ''))
        height = int(request.headers.get('X-WebApp-Viewport-Height', ''))
    except ValueError:
        return
    if not 100 <= width <= 10_000 or not 100 <= height <= 10_000:
        return
    if (user.webapp_viewport_width, user.webapp_viewport_height) != (width, height):
        user.webapp_viewport_width = width
        user.webapp_viewport_height = height
        user.save(update_fields=('webapp_viewport_width', 'webapp_viewport_height', 'updated_at'))


def tracker_identity(request):
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    if init_data:
        telegram_user = telegram_webapp_user(init_data)
        if telegram_user:
            defaults = {
                'username': telegram_user.get('username', ''),
                'display_name': ' '.join(
                    filter(None, [telegram_user.get('first_name'), telegram_user.get('last_name')])
                ),
                'photo_url': telegram_user.get('photo_url', ''),
            }
            tracker_user, _ = TrackerUser.objects.update_or_create(
                telegram_id=telegram_user['id'], defaults=defaults
            )
            update_webapp_viewport(request, tracker_user)
            return tracker_user

    preview_telegram_id = tracker_preview_telegram_id(request)
    if preview_telegram_id:
        return TrackerUser.objects.filter(telegram_id=preview_telegram_id).first()

    dev_mode = settings.DEBUG or os.getenv('VITE_DEV_MODE', 'False').lower() == 'true'
    dev_preview_id = request.headers.get('X-Dev-Preview-Telegram-ID') or request.GET.get('dev_telegram_id')
    if dev_mode and request.headers.get('X-Dev-Mode') == 'true' and dev_preview_id:
        try:
            return TrackerUser.objects.filter(telegram_id=int(dev_preview_id)).first()
        except (TypeError, ValueError):
            return None
    if dev_mode and (
        request.GET.get('dev') == 'true' or request.headers.get('X-Dev-Mode') == 'true'
    ):
        if not request.session.session_key:
            request.session.create()
        tracker_user, _ = TrackerUser.objects.get_or_create(session_key=request.session.session_key)
        return tracker_user

    return None


def telegram_webapp_user(init_data):
    """Validate Telegram WebApp init data before trusting its user id."""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = fields.pop('hash', '')
    if not token or not received_hash:
        return None
    check_string = '\n'.join(f'{key}={value}' for key, value in sorted(fields.items()))
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        return None
    try:
        return json.loads(fields['user'])
    except (KeyError, json.JSONDecodeError):
        return None


def user_books(request):
    user = tracker_identity(request)
    if not user:
        return UserBook.objects.none()
    return (
        UserBook.objects.filter(user=user)
        .select_related('book')
        .prefetch_related('book__pages', 'works')
    )


def book_data(user_book):
    # A spread is represented by one ColoringPage and is one trackable work,
    # even though it contains two physical pages.
    total = user_book.book.total_works_count
    completed = user_book.works.count()
    return {
        'id': user_book.id,
        'catalog_id': user_book.book_id,
        'title': user_book.book.title,
        'author': user_book.book.author,
        'cover': user_book.book.cover.url if user_book.book.cover else '',
        'cover_preview': (
            user_book.book.cover_preview.url if user_book.book.cover_preview else ''
        ),
        'cover_source': (
            user_book.book.cover_original.url
            if user_book.book.cover_original
            else (user_book.book.cover.url if user_book.book.cover else '')
        ),
        'total': total,
        'done': completed,
        'progress': round(completed * 100 / total) if total else 0,
        'is_personal': user_book.book.is_personal,
        'emoji': user_book.book.report_icon if user_book.book.is_personal else '',
    }


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def tracker_books(request):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    if request.method == 'POST':
        try:
            payload = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse(
                {'error': 'Ожидается JSON с идентификатором раскраски.'}, status=400
            )
        book = get_object_or_404(
            ColoringBook, pk=payload.get('book_id'), owner__isnull=True, is_published=True
        )
        user_book, _ = UserBook.objects.get_or_create(book=book, user=user)
        return JsonResponse({'book': book_data(user_book)}, status=201)
    return JsonResponse({'books': [book_data(item) for item in user_books(request)]})


def randomizer_result(request, run):
    page = run.page
    book = page.book
    user_book_id = (
        run.user_book_id
        or UserBook.objects.filter(user=run.user, book_id=book.pk)
        .values_list('pk', flat=True)
        .first()
    )
    return {
        'user_book_id': user_book_id,
        'book_id': book.pk,
        'book_title': book.title,
        'book_author': book.author,
        'book_cover': book.cover.url if book.cover else '',
        'book_is_personal': book.is_personal,
        'book_emoji': book.report_icon if book.is_personal else '',
        'page_id': page.pk,
        'page_label': page.label,
        'page_title': page.title,
    }


def randomizer_status(request, now=None, user=None):
    now = now or timezone.now()
    user = user or tracker_identity(request)
    runs = RandomizerRun.objects.filter(user=user)
    last_run = runs.select_related('page__book').first()
    if not last_run:
        return {
            'available': True,
            'retry_after': 0,
            'next_available_at': None,
            'last_result': None,
        }
    next_available_at = last_run.created_at + timedelta(seconds=RANDOMIZER_COOLDOWN_SECONDS)
    retry_after = max(0, math.ceil((next_available_at - now).total_seconds()))
    return {
        'available': retry_after == 0,
        'retry_after': retry_after,
        'next_available_at': next_available_at.isoformat(),
        'last_result': randomizer_result(request, last_run),
    }


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def tracker_randomizer(request):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    raw_scope = request.GET.get('user_book_id', '').strip()
    if raw_scope:
        try:
            scope_user_book_id = int(raw_scope)
        except ValueError:
            return JsonResponse({'error': 'Некорректная раскраска для рандомизации.'}, status=400)
    else:
        scope_user_book_id = None

    if request.method == 'GET':
        if (
            scope_user_book_id is not None
            and not UserBook.objects.filter(pk=scope_user_book_id, user=user).exists()
        ):
            return JsonResponse({'error': 'Раскраска не найдена.'}, status=404)
        return JsonResponse(randomizer_status(request, user=user))

    with transaction.atomic():
        locked_user = TrackerUser.objects.select_for_update().get(pk=user.pk)
        target_user_book = None
        if scope_user_book_id is not None:
            target_user_book = get_object_or_404(
                UserBook.objects.select_for_update().select_related('book'),
                pk=scope_user_book_id,
                user=locked_user,
            )
            candidate_pages = (
                ColoringPage.objects.filter(book=target_user_book.book)
                .exclude(works__user_book=target_user_book)
                .select_related('book')
            )
        else:
            target_books = list(
                UserBook.objects.filter(user=locked_user).values_list('book_id', flat=True)
            )
            candidate_pages = (
                ColoringPage.objects.filter(book_id__in=target_books)
                .exclude(works__user_book__user=locked_user)
                .select_related('book')
                .distinct()
            )

        runs = RandomizerRun.objects.filter(user=locked_user)
        last_run = runs.first()
        now = timezone.now()
        if last_run:
            next_available_at = last_run.created_at + timedelta(seconds=RANDOMIZER_COOLDOWN_SECONDS)
            retry_after = (next_available_at - now).total_seconds()
            if retry_after > 0:
                payload = randomizer_status(request, now, user=locked_user)
                payload['error'] = 'Рандомизатор станет доступен позже.'
                return JsonResponse(payload, status=429)

        page = random.choice(list(candidate_pages)) if candidate_pages.exists() else None
        if not page:
            return JsonResponse(
                {'error': 'В этой области пока нет незакрашенных работ.'}, status=409
            )
        run = RandomizerRun.objects.create(
            user=locked_user,
            user_book=target_user_book,
            page=page,
        )

    next_available_at = run.created_at + timedelta(seconds=RANDOMIZER_COOLDOWN_SECONDS)
    return JsonResponse(
        {
            'available': False,
            'retry_after': RANDOMIZER_COOLDOWN_SECONDS,
            'next_available_at': next_available_at.isoformat(),
            'last_result': randomizer_result(request, run),
            'result': randomizer_result(request, run),
        },
        status=201,
    )


@require_http_methods(['GET'])
def tracker_catalog(request):
    user = tracker_identity(request)
    collection_books = list(user_books(request)) if user else []
    owned = {item.book_id for item in collection_books}
    collection = {item.book_id: item for item in collection_books}
    query = request.GET.get('q', '').strip()
    catalogue = ColoringBook.objects.filter(owner__isnull=True, is_published=True).prefetch_related(
        'pages'
    )
    if query:
        catalogue = catalogue.filter(
            Q(title__icontains=query) | Q(author__icontains=query) | Q(publisher__icontains=query)
        )
    return JsonResponse(
        {
            'books': [
                {
                    'id': book.id,
                    'title': book.title,
                    'author': book.author,
                    'cover': book.cover.url if book.cover else '',
                    'cover_preview': book.cover_preview.url if book.cover_preview else '',
                    'pages': book.total_pages_count,
                    'spreads': book.spreads_count,
                    'owned': book.id in owned,
                    'collection_id': collection[book.id].id if book.id in collection else None,
                    'completed': collection[book.id].works.count() if book.id in collection else 0,
                }
                for book in catalogue
            ]
        }
    )


@require_http_methods(['GET'])
def tracker_catalog_book_detail(request, book_id):
    """Published catalogue entry preview, available before it is collected."""
    book = get_object_or_404(
        ColoringBook.objects.filter(owner__isnull=True).prefetch_related('pages'),
        pk=book_id,
        is_published=True,
    )
    return JsonResponse(
        {
            'book': {
                'id': book.id,
                'title': book.title,
                'author': book.author,
                'publisher': book.publisher,
                'description': book.description,
                'cover': book.cover.url if book.cover else '',
                'cover_preview': book.cover_preview.url if book.cover_preview else '',
                'pages': book.total_pages_count,
                'spreads': book.spreads_count,
            },
            'pages': [
                {
                    'id': page.id,
                    'label': page.label,
                    'spread_end': page.spread_end,
                    'title': page.title,
                }
                for page in book.pages.all()
            ],
        }
    )


def suggestion_fingerprint(title, source_text):
    normalized = ' '.join(title.split()).casefold()
    normalized_source = ' '.join(source_text.split()).casefold()
    return hashlib.sha256(f'{normalized}\n{normalized_source}'.encode()).hexdigest()


@csrf_exempt
@require_http_methods(['POST'])
def tracker_suggestion(request):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Ожидается JSON.'}, status=400)

    title = str(payload.get('title', '')).strip()
    source_text = str(payload.get('source_text', '')).strip()
    if not title:
        return JsonResponse({'error': 'Напишите название раскраски.'}, status=400)
    if len(title) > SUGGESTION_TITLE_LIMIT:
        return JsonResponse(
            {'error': f'Название слишком длинное (максимум {SUGGESTION_TITLE_LIMIT} символов).'},
            status=400,
        )
    if len(source_text) > SUGGESTION_SOURCE_LIMIT:
        return JsonResponse(
            {'error': 'Текст ссылки слишком длинный. Укажите до 100 000 символов.'}, status=400
        )

    fingerprint = suggestion_fingerprint(title, source_text)
    try:
        with transaction.atomic():
            locked_user = TrackerUser.objects.select_for_update().get(pk=user.pk)
            cooldown_from = timezone.now() - timedelta(seconds=SUGGESTION_COOLDOWN_SECONDS)
            last_suggestion = (
                ColoringSuggestion.objects.filter(user=locked_user, created_at__gte=cooldown_from)
                .order_by('-created_at')
                .first()
            )
            if last_suggestion:
                retry_after = max(
                    1,
                    SUGGESTION_COOLDOWN_SECONDS
                    - int((timezone.now() - last_suggestion.created_at).total_seconds()),
                )
                return JsonResponse(
                    {
                        'error': f'Новое предложение можно отправить через {retry_after} сек.',
                        'retry_after': retry_after,
                    },
                    status=429,
                )
            if ColoringSuggestion.objects.filter(
                user=locked_user, fingerprint=fingerprint
            ).exists():
                return JsonResponse(
                    {'error': 'Вы уже отправляли такое предложение. Спасибо, мы его проверяем.'},
                    status=409,
                )
            suggestion = ColoringSuggestion.objects.create(
                user=locked_user,
                title=title,
                source_text=source_text,
                fingerprint=fingerprint,
            )

            def queue_notification(suggestion_id=suggestion.pk):
                try:
                    send_suggestion_notification.delay(suggestion_id)
                except Exception as exc:
                    ColoringSuggestion.objects.filter(pk=suggestion_id).update(
                        notification_error=str(exc)[:4000], updated_at=timezone.now()
                    )

            transaction.on_commit(queue_notification)
    except IntegrityError:
        return JsonResponse(
            {'error': 'Вы уже отправляли такое предложение. Спасибо, мы его проверяем.'}, status=409
        )
    return JsonResponse({'ok': True, 'id': suggestion.pk}, status=201)


def donation_data(donation):
    return {
        'id': donation.pk,
        'amount': donation.amount,
        'status': donation.status,
        'is_test': donation.is_test,
    }


@csrf_exempt
@require_http_methods(['GET'])
def tracker_stars(request):
    user = tracker_identity(request)
    return JsonResponse(
        {
            'enabled': stars_enabled(),
            'test_mode': stars_test_mode_enabled(),
            'amounts': donation_amounts(),
            'can_donate': bool(user),
        }
    )


@csrf_exempt
@require_http_methods(['POST'])
def tracker_stars_invoice(request):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    test_mode = stars_test_mode_enabled()
    if not test_mode and not stars_enabled():
        return JsonResponse({'error': 'Поддержка Stars пока не включена.'}, status=503)
    if not test_mode and not user.telegram_id:
        return JsonResponse({'error': 'Реальный донат доступен только в Telegram.'}, status=403)
    try:
        payload = json.loads(request.body or '{}')
        raw_amount = payload.get('amount', 0)
        if isinstance(raw_amount, bool) or (
            isinstance(raw_amount, float) and not raw_amount.is_integer()
        ):
            raise ValueError
        amount = int(raw_amount)
    except (json.JSONDecodeError, TypeError, ValueError):
        amount = 0
    if not DONATION_MIN_STARS <= amount <= DONATION_MAX_STARS:
        return JsonResponse(
            {
                'error': (
                    f'Укажите целую сумму от {DONATION_MIN_STARS} до {DONATION_MAX_STARS} Stars.'
                )
            },
            status=400,
        )

    donation = StarDonation.objects.create(user=user, amount=amount, is_test=test_mode)
    if test_mode:
        return JsonResponse({'donation': donation_data(donation), 'test_mode': True})

    try:
        invoice_url = telegram_bot_api(
            'createInvoiceLink',
            {
                'title': DONATION_TITLE,
                'description': DONATION_DESCRIPTION,
                'payload': donation.payload,
                'currency': 'XTR',
                'prices': [{'label': 'Поддержка трекера', 'amount': amount}],
            },
        )
    except RuntimeError as exc:
        donation.status = StarDonation.STATUS_FAILED
        donation.error = str(exc)[:4000]
        donation.save(update_fields=('status', 'error', 'updated_at'))
        return JsonResponse(
            {'error': 'Не получилось открыть оплату. Попробуйте ещё раз.'}, status=502
        )

    donation.invoice_url = invoice_url
    donation.save(update_fields=('invoice_url', 'updated_at'))
    return JsonResponse(
        {'donation': donation_data(donation), 'test_mode': False, 'invoice_url': invoice_url}
    )


@csrf_exempt
@require_http_methods(['POST'])
def tracker_stars_test_complete(request, donation_id):
    user = tracker_identity(request)
    if not user or not stars_test_mode_enabled():
        return JsonResponse({'error': 'Тестовый режим доступен только локально.'}, status=404)
    donation = get_object_or_404(StarDonation, pk=donation_id, user=user, is_test=True)
    if donation.status == StarDonation.STATUS_PENDING:
        donation.status = StarDonation.STATUS_SUCCEEDED
        donation.paid_at = timezone.now()
        donation.save(update_fields=('status', 'paid_at', 'updated_at'))
    return JsonResponse({'donation': donation_data(donation)})


@require_http_methods(['GET'])
def tracker_stars_status(request, donation_id):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    donation = get_object_or_404(StarDonation, pk=donation_id, user=user)
    return JsonResponse({'donation': donation_data(donation)})


def validate_donation_pre_checkout(payload, telegram_id, currency, total_amount):
    donation = StarDonation.objects.filter(payload=payload).select_related('user').first()
    if not donation:
        return False, 'Этот счёт больше недействителен.'
    if donation.status != StarDonation.STATUS_PENDING:
        return False, 'Этот счёт уже обработан.'
    if donation.user.telegram_id != telegram_id:
        return False, 'Счёт создан для другого пользователя.'
    if currency != 'XTR' or total_amount != donation.amount:
        return False, 'Сумма счёта не совпадает.'
    return True, ''


def record_successful_donation(payload, telegram_id, payment):
    with transaction.atomic():
        donation = (
            StarDonation.objects.select_for_update()
            .select_related('user')
            .filter(payload=payload)
            .first()
        )
        if not donation or donation.user.telegram_id != telegram_id:
            return False
        if payment.currency != 'XTR' or payment.total_amount != donation.amount:
            donation.status = StarDonation.STATUS_FAILED
            donation.error = 'Telegram прислал платёж с неожиданной суммой или валютой.'
            donation.save(update_fields=('status', 'error', 'updated_at'))
            return False
        if donation.status == StarDonation.STATUS_SUCCEEDED:
            return True
        donation.status = StarDonation.STATUS_SUCCEEDED
        donation.telegram_payment_charge_id = payment.telegram_payment_charge_id
        donation.provider_payment_charge_id = payment.provider_payment_charge_id or ''
        donation.paid_at = timezone.now()
        donation.error = ''
        donation.save(
            update_fields=(
                'status',
                'telegram_payment_charge_id',
                'provider_payment_charge_id',
                'paid_at',
                'error',
                'updated_at',
            )
        )

        def queue_notification(donation_id=donation.pk):
            try:
                send_donation_notification.delay(donation_id)
            except Exception as exc:
                StarDonation.objects.filter(pk=donation_id).update(
                    notification_error=str(exc)[:4000], updated_at=timezone.now()
                )

        transaction.on_commit(queue_notification)
    return True


@csrf_exempt
@require_http_methods(['DELETE'])
def tracker_collection_book(request, book_id):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    user_book = get_object_or_404(UserBook, user=user, book_id=book_id, book__owner__isnull=True)
    deleted_works = user_book.works.count()
    user_book.delete()
    return JsonResponse({'ok': True, 'deleted_works': deleted_works})


def personal_user_book(request, user_book_id):
    user = tracker_identity(request)
    if not user:
        return None
    return get_object_or_404(
        UserBook.objects.select_related('book'),
        pk=user_book_id,
        user=user,
        book__owner=user,
    )


def personal_page_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError('Страница должна быть объектом.')
    raw_number = payload.get('number')
    if isinstance(raw_number, bool) or (
        isinstance(raw_number, float) and not raw_number.is_integer()
    ):
        raise ValueError('Укажите целый номер страницы.')
    try:
        number = int(raw_number)
    except (TypeError, ValueError):
        raise ValueError('Укажите номер страницы.') from None
    if number < 1:
        raise ValueError('Номер страницы должен быть положительным.')
    spread_end = payload.get('spread_end')
    if spread_end in ('', None):
        spread_end = None
    else:
        if isinstance(spread_end, bool) or (
            isinstance(spread_end, float) and not spread_end.is_integer()
        ):
            raise ValueError('Последняя страница разворота должна быть целым числом.')
        try:
            spread_end = int(spread_end)
        except (TypeError, ValueError):
            raise ValueError('Последняя страница разворота должна быть числом.') from None
        if spread_end != number + 1:
            raise ValueError('Разворот должен состоять ровно из двух соседних страниц.')
    title = str(payload.get('title', '')).strip()
    if len(title) > 255:
        raise ValueError('Подпись страницы слишком длинная.')
    return {'number': number, 'spread_end': spread_end, 'title': title}


def order_personal_pages(page_payloads):
    """Use the submitted row order as truth and assign page numbers server-side."""
    if not isinstance(page_payloads, list):
        raise ValueError('Список страниц должен быть массивом.')
    ordered = []
    next_number = 1
    for item in page_payloads:
        if not isinstance(item, dict):
            raise ValueError('Страница должна быть объектом.')
        raw_spread_end = item.get('spread_end')
        if raw_spread_end not in ('', None, False):
            raw_number = item.get('number')
            try:
                if int(raw_spread_end) != int(raw_number) + 1:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError(
                    'Разворот должен состоять ровно из двух соседних страниц.'
                ) from None
            spread_end = next_number + 1
        else:
            spread_end = None
        ordered.append({**item, 'number': next_number, 'spread_end': spread_end})
        next_number += 2 if spread_end else 1
    return ordered


def validate_personal_pages(book, page_payloads, *, include_existing=True, allow_empty=False):
    if not isinstance(page_payloads, list):
        raise ValueError('Список страниц должен быть массивом.')
    if not page_payloads and not allow_empty:
        raise ValueError('Добавьте хотя бы одну страницу.')
    pages = [personal_page_payload(item) for item in page_payloads]
    intervals = []
    total_pages = 0
    if include_existing:
        existing_pages = list(book.pages.all())
        intervals.extend((page.number, page.spread_end or page.number) for page in existing_pages)
        total_pages += sum(page.page_count for page in existing_pages)
    intervals.extend((item['number'], item['spread_end'] or item['number']) for item in pages)
    total_pages += sum(2 if item['spread_end'] else 1 for item in pages)
    if total_pages > PERSONAL_PAGE_LIMIT:
        raise ValueError(f'В личной раскраске может быть не больше {PERSONAL_PAGE_LIMIT} страниц.')
    intervals.sort()
    for previous, current in zip(intervals, intervals[1:], strict=False):
        if current[0] <= previous[1]:
            raise ValueError('Страницы и развороты не должны пересекаться.')
    return pages


def replace_personal_pages(book, page_payloads):
    """Replace the complete page list while keeping data for unchanged rows."""
    if not isinstance(page_payloads, list):
        raise ValueError('Список страниц должен быть массивом.')

    page_ids = [
        item.get('id') for item in page_payloads if isinstance(item, dict) and item.get('id')
    ]
    if len(page_ids) != len(set(page_ids)):
        raise ValueError('Строки страниц должны быть уникальными.')
    existing = {page.id: page for page in book.pages.all()}
    unknown_ids = set(page_ids) - set(existing)
    if unknown_ids:
        raise ValueError('Некоторые страницы не принадлежат этой раскраске.')

    page_payloads = order_personal_pages(page_payloads)
    pages = validate_personal_pages(book, page_payloads, include_existing=False, allow_empty=True)
    kept_ids = set(page_ids)
    removed = [page for page_id, page in existing.items() if page_id not in kept_ids]
    for page in removed:
        page.delete()

    # UniqueConstraint(book, number) makes swapping numbers unsafe when rows are
    # updated one by one. Move retained rows out of the way first.
    temporary_number = (
        max(
            [1_000_000]
            + [page.number for page in existing.values()]
            + [page.spread_end or page.number for page in existing.values()]
            + [item['number'] for item in pages]
            + [item['spread_end'] or item['number'] for item in pages]
        )
        + len(existing)
        + 1
    )
    retained = [existing[page_id] for page_id in page_ids]
    for offset, page in enumerate(retained):
        page.number = temporary_number + offset
        page.spread_end = None
        page.save(update_fields=('number', 'spread_end', 'updated_at'))

    for payload, page_data in zip(page_payloads, pages, strict=True):
        page = existing.get(payload.get('id'))
        if page is None:
            ColoringPage.objects.create(book=book, **page_data)
            continue
        page.number = page_data['number']
        page.spread_end = page_data['spread_end']
        page.title = page_data['title']
        page.save(update_fields=('number', 'spread_end', 'title', 'updated_at'))


@csrf_exempt
@require_http_methods(['POST'])
def tracker_personal_book_create(request):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    if request.content_type.startswith('multipart/form-data'):
        try:
            pages = json.loads(request.POST.get('pages', '[]'))
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Не удалось прочитать список страниц.'}, status=400)
        payload = {
            'title': request.POST.get('title', ''),
            'emoji': request.POST.get('emoji', ''),
            'pages': pages,
        }
        cover = request.FILES.get('cover')
        cover_original = request.FILES.get('cover_original')
    else:
        try:
            payload = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Ожидается JSON.'}, status=400)
        cover = None
        cover_original = None
    title = str(payload.get('title', '')).strip()
    emoji = str(payload.get('emoji', '')).strip()
    if not title:
        return JsonResponse({'error': 'Введите название раскраски.'}, status=400)
    if len(title) > PERSONAL_BOOK_TITLE_LIMIT:
        return JsonResponse({'error': 'Название раскраски слишком длинное.'}, status=400)
    if emoji not in FLOWER_ICONS:
        return JsonResponse({'error': 'Выберите эмодзи раскраски.'}, status=400)
    if cover and (error := validate_image_upload(cover)):
        return JsonResponse({'error': error}, status=400)
    if cover_original and (error := validate_image_upload(cover_original)):
        return JsonResponse({'error': error}, status=400)
    try:
        payload['pages'] = order_personal_pages(payload.get('pages', []))
        pages = validate_personal_pages(
            ColoringBook(), payload.get('pages', []), include_existing=False, allow_empty=True
        )
        with transaction.atomic():
            book = ColoringBook.objects.create(
                owner=user,
                title=title,
                report_icon=emoji,
                cover=cover,
                cover_original=cover_original or cover,
                is_published=False,
            )
            ColoringPage.objects.bulk_create([ColoringPage(book=book, **page) for page in pages])
            user_book = UserBook.objects.create(user=user, book=book)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    return JsonResponse({'book': book_data(user_book)}, status=201)


@csrf_exempt
@require_http_methods(['PATCH', 'DELETE'])
def tracker_personal_book(request, user_book_id):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    user_book = get_object_or_404(
        UserBook.objects.select_related('book'), pk=user_book_id, user=user, book__owner=user
    )
    if request.method == 'DELETE':
        user_book.book.delete()
        return JsonResponse({'ok': True})
    if request.content_type.startswith('multipart/form-data'):
        payload = {
            'title': request.POST.get('title', user_book.book.title),
            'emoji': request.POST.get('emoji', user_book.book.report_icon),
        }
        cover = request.FILES.get('cover')
        cover_original = request.FILES.get('cover_original')
        remove_cover = request.POST.get('remove_cover') in ('1', 'true', 'True')
    else:
        try:
            payload = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Ожидается JSON.'}, status=400)
        cover = None
        cover_original = None
        remove_cover = False
    title = str(payload.get('title', user_book.book.title)).strip()
    emoji = str(payload.get('emoji', user_book.book.report_icon)).strip()
    if not title or len(title) > PERSONAL_BOOK_TITLE_LIMIT:
        return JsonResponse({'error': 'Введите название до 255 символов.'}, status=400)
    if emoji not in FLOWER_ICONS:
        return JsonResponse({'error': 'Выберите эмодзи раскраски.'}, status=400)
    if cover and (error := validate_image_upload(cover)):
        return JsonResponse({'error': error}, status=400)
    if cover_original and (error := validate_image_upload(cover_original)):
        return JsonResponse({'error': error}, status=400)
    try:
        with transaction.atomic():
            book = ColoringBook.objects.select_for_update().get(pk=user_book.book_id)
            if 'pages' in payload:
                replace_personal_pages(book, payload['pages'])
            book.title = title
            book.report_icon = emoji
            update_fields = ['title', 'report_icon']
            if remove_cover:
                book.cover = ''
                book.cover_original = ''
                update_fields.extend(('cover', 'cover_original'))
            elif cover:
                book.cover = cover
                # Keep the uncropped source when a legacy client sends only
                # the processed cover. New editor uploads still replace it
                # explicitly through cover_original.
                book.cover_original = cover_original or book.cover_original or cover
                update_fields.extend(('cover', 'cover_original'))
            book.save(update_fields=(*update_fields, 'updated_at'))
            user_book.book = book
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    return JsonResponse({'book': book_data(user_book)})


@csrf_exempt
@require_http_methods(['POST'])
def tracker_personal_pages(request, user_book_id):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    user_book = get_object_or_404(
        UserBook.objects.select_related('book'), pk=user_book_id, user=user, book__owner=user
    )
    try:
        payload = json.loads(request.body or '{}')
        with transaction.atomic():
            book = ColoringBook.objects.select_for_update().get(pk=user_book.book_id)
            # Keep the old endpoint safe for cached clients: validate the
            # requested slot, then append the new row after the current list.
            validate_personal_pages(book, [payload], include_existing=True)
            last_number = max(
                (page.spread_end or page.number for page in book.pages.all()),
                default=0,
            )
            payload = {
                **payload,
                'number': last_number + 1,
                'spread_end': last_number + 2
                if payload.get('spread_end') not in ('', None, False)
                else None,
            }
            pages = validate_personal_pages(book, [payload], include_existing=True)
            page = ColoringPage.objects.create(book=book, **pages[0])
    except (json.JSONDecodeError, ValueError) as exc:
        return JsonResponse({'error': str(exc) or 'Ожидается JSON.'}, status=400)
    return JsonResponse(
        {
            'page': {
                'id': page.id,
                'number': page.number,
                'spread_end': page.spread_end,
                'label': page.label,
                'title': page.title,
            }
        },
        status=201,
    )


@csrf_exempt
@require_http_methods(['DELETE'])
def tracker_personal_page(request, user_book_id, page_id):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    user_book = get_object_or_404(
        UserBook.objects.select_related('book'), pk=user_book_id, user=user, book__owner=user
    )
    page = get_object_or_404(ColoringPage, pk=page_id, book=user_book.book)
    page.delete()
    return JsonResponse({'ok': True})


@require_http_methods(['GET'])
def tracker_profile(request):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    books = user_books(request)
    # A spread is one trackable work, even though it contains two physical pages.
    # Keep the profile aggregate consistent with book_data() and the monthly report.
    total = sum(item.book.total_works_count for item in books)
    completed = ColoringWork.objects.filter(user_book__in=books).count()
    return JsonResponse(
        {
            'user': {
                'id': user.telegram_id or user.pk,
                'username': user.username,
                'name': user.display_name or 'Мой профиль',
                'photo_url': user.photo_url,
            },
            'stats': {
                'books': books.count(),
                'completed': completed,
                'total': total,
                'progress': round(completed * 100 / total) if total else 0,
            },
        }
    )


@require_http_methods(['GET'])
def tracker_book_detail(request, user_book_id):
    user_book = get_object_or_404(user_books(request), pk=user_book_id)
    works_by_page = {work.page_id: work for work in user_book.works.all()}
    photos_by_page = {photo.page_id: photo for photo in user_book.page_photos.all()}
    color_codes_by_page = {code.page_id: code for code in user_book.color_codes.all()}
    pages = [
        {
            'id': page.id,
            'number': page.number,
            'spread_end': page.spread_end,
            'label': page.label,
            'title': page.title,
            'completed': page.id in works_by_page,
            'hide_in_report': works_by_page[page.id].hide_in_report
            if page.id in works_by_page
            else False,
            'photo': media_url(
                request, photos_by_page[page.id].image, photos_by_page[page.id].updated_at
            )
            if page.id in photos_by_page
            else '',
            'photo_source': media_url(
                request,
                photos_by_page[page.id].original_image or photos_by_page[page.id].image,
                photos_by_page[page.id].updated_at,
            )
            if page.id in photos_by_page
            else '',
            'color_code': media_url(
                request, color_codes_by_page[page.id].image, color_codes_by_page[page.id].updated_at
            )
            if page.id in color_codes_by_page
            else '',
            'color_code_source': media_url(
                request,
                color_codes_by_page[page.id].original_image or color_codes_by_page[page.id].image,
                color_codes_by_page[page.id].updated_at,
            )
            if page.id in color_codes_by_page
            else '',
        }
        for page in user_book.book.pages.all()
    ]
    return JsonResponse({'book': book_data(user_book), 'pages': pages})


@csrf_exempt
@require_http_methods(['POST', 'DELETE'])
def tracker_work(request, user_book_id, page_id):
    user_book = get_object_or_404(user_books(request), pk=user_book_id)
    page = get_object_or_404(ColoringPage, pk=page_id, book=user_book.book)
    if request.method == 'DELETE':
        ColoringWork.objects.filter(user_book=user_book, page=page).delete()
        return JsonResponse({'ok': True})
    work, _ = ColoringWork.objects.get_or_create(user_book=user_book, page=page)
    if 'hide_in_report' in request.POST:
        work.hide_in_report = request.POST.get('hide_in_report') in ('true', 'True', '1', True)
        work.save(update_fields=('hide_in_report', 'updated_at'))
    elif request.content_type == 'application/json':
        try:
            payload = json.loads(request.body or '{}')
            if 'hide_in_report' in payload:
                work.hide_in_report = bool(payload['hide_in_report'])
                work.save(update_fields=('hide_in_report', 'updated_at'))
        except json.JSONDecodeError:
            pass
    if photo := request.FILES.get('photo'):
        if error := validate_image_upload(photo):
            return JsonResponse({'error': error}, status=400)
        source_photo = request.FILES.get('source_photo')
        if source_photo and (error := validate_image_upload(source_photo)):
            return JsonResponse({'error': error}, status=400)
        page_photo, _ = ColoringPagePhoto.objects.get_or_create(user_book=user_book, page=page)
        page_photo.image = photo
        page_photo.original_image = source_photo or photo
        page_photo.save()
    page_photo = ColoringPagePhoto.objects.filter(user_book=user_book, page=page).first()
    return JsonResponse(
        {
            'id': work.id,
            'hide_in_report': work.hide_in_report,
            'photo': media_url(request, page_photo.image, page_photo.updated_at)
            if page_photo
            else '',
            'photo_source': media_url(
                request,
                page_photo.original_image or page_photo.image,
                page_photo.updated_at,
            )
            if page_photo
            else '',
        }
    )


@csrf_exempt
@require_http_methods(['POST', 'DELETE'])
def tracker_color_code(request, user_book_id, page_id):
    user_book = get_object_or_404(user_books(request), pk=user_book_id)
    page = get_object_or_404(ColoringPage, pk=page_id, book=user_book.book)
    color_code = ColoringColorCode.objects.filter(user_book=user_book, page=page).first()
    if request.method == 'DELETE':
        if color_code:
            color_code.delete()
        return JsonResponse({'ok': True})
    image = request.FILES.get('image')
    if not image:
        return JsonResponse({'error': 'Выберите изображение цветового кода.'}, status=400)
    if error := validate_image_upload(image):
        return JsonResponse({'error': error}, status=400)
    source_image = request.FILES.get('source_image')
    if source_image and (error := validate_image_upload(source_image)):
        return JsonResponse({'error': error}, status=400)
    if color_code:
        color_code.image = image
        color_code.original_image = source_image or image
        color_code.save(update_fields=('image', 'original_image', 'updated_at'))
    else:
        color_code = ColoringColorCode.objects.create(
            user_book=user_book,
            page=page,
            image=image,
            original_image=source_image or image,
        )
    return JsonResponse(
        {
            'id': color_code.id,
            'image': media_url(request, color_code.image, color_code.updated_at),
            'image_source': media_url(
                request,
                color_code.original_image or color_code.image,
                color_code.updated_at,
            ),
        }
    )


def marker_data(marker):
    return {
        'id': marker.id,
        'symbol': marker.symbol,
        'number': marker.number,
        'manufacturer': marker.manufacturer,
        'manufacturer_label': MARKER_MANUFACTURER_LABELS.get(marker.manufacturer, 'Не указан'),
        'marker_type': marker.marker_type,
        'marker_type_label': MARKER_TYPE_LABELS.get(marker.marker_type, 'Маркер'),
    }


def normalize_marker_number(raw_number):
    if not isinstance(raw_number, str):
        raise ValueError('Укажите номер расходника.')
    number = raw_number.strip().upper()
    if not number or len(number) > MARKER_NUMBER_LIMIT or not MARKER_NUMBER_RE.fullmatch(number):
        raise ValueError('Номер: только английские буквы, цифры, пробелы и дефисы.')
    return number


def palette_fingerprint(items):
    normalized = sorted(
        f"{item['marker_id']}:{item.get('symbol', '')}:{item.get('usage_level', '')}" for item in items
    )
    return hashlib.sha256('|'.join(normalized).encode()).hexdigest()


def palette_payload(request, palette):
    items = list(palette.items.select_related('marker').all())
    return {
        'id': palette.id,
        'fingerprint': palette.fingerprint,
        'allow_import': palette.user_book.user.marker_palette_import_allowed,
        'items': [
            {
                'id': item.id,
                'marker': {**marker_data(item.marker), 'symbol': item.symbol},
                'usage_level': item.usage_level,
            }
            for item in items
        ],
    }


def shared_palette_payload(palette, popularity):
    return {
        'id': palette.id,
        'fingerprint': palette.fingerprint,
        'popularity': popularity,
        'items': [
            {
                'marker': marker_data(item.marker),
                'symbol': item.symbol,
                'usage_level': item.usage_level,
            }
            for item in palette.items.select_related('marker').all()
        ],
    }


def palette_scope(request, user_book_id, page_id):
    user_book = get_object_or_404(user_books(request), pk=user_book_id)
    page = get_object_or_404(ColoringPage, pk=page_id, book=user_book.book)
    return user_book, page


@require_http_methods(['GET'])
def tracker_markers(request):
    query = request.GET.get('q', '').strip()[:MARKER_NUMBER_LIMIT]
    markers = Marker.objects.all()
    if query:
        markers = markers.filter(
            Q(symbol__icontains=query)
            | Q(number__icontains=query)
            | Q(manufacturer__icontains=query)
            | Q(palette_items__symbol__icontains=query)
        ).distinct()
    return JsonResponse({
        'markers': [marker_data(marker) for marker in markers[:MARKER_SUGGESTION_LIMIT]],
        'manufacturers': [
            {'value': value, 'label': label} for value, label in MARKER_MANUFACTURERS
        ],
        'marker_types': [{'value': value, 'label': label} for value, label in MARKER_TYPES],
    })


@csrf_exempt
@require_http_methods(['GET', 'PUT'])
def tracker_palette(request, user_book_id, page_id):
    user_book, page = palette_scope(request, user_book_id, page_id)
    own = MarkerPalette.objects.filter(user_book=user_book, page=page).first()
    if request.method == 'GET':
        candidates = (
            MarkerPalette.objects.filter(
                page=page,
                allow_import=True,
                user_book__user__marker_palette_import_allowed=True,
            )
            .exclude(user_book__user=user_book.user)
            .prefetch_related('items__marker', 'imports')
        )
        grouped = {}
        for candidate in candidates:
            popularity = 1 + candidate.imports.count()
            current = grouped.get(candidate.fingerprint)
            if current is None or popularity > current[0]:
                grouped[candidate.fingerprint] = (popularity, candidate)
            else:
                grouped[candidate.fingerprint] = (current[0] + popularity, current[1])
        shared = [
            shared_palette_payload(candidate, popularity)
            for popularity, candidate in sorted(
                grouped.values(), key=lambda pair: (-pair[0], pair[1].created_at)
            )[:8]
        ]
        return JsonResponse(
            {
                'palette': palette_payload(request, own) if own else None,
                'shared': shared,
                'limit': MARKER_PALETTE_LIMIT,
                'import_allowed': user_book.user.marker_palette_import_allowed,
                'manufacturers': [
                    {'value': value, 'label': label} for value, label in MARKER_MANUFACTURERS
                ],
                'marker_types': [{'value': value, 'label': label} for value, label in MARKER_TYPES],
            }
        )

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Ожидается JSON.'}, status=400)
    raw_items = payload.get('items', [])
    if not isinstance(raw_items, list) or len(raw_items) > MARKER_PALETTE_LIMIT:
        return JsonResponse({'error': f'В палитре может быть не больше {MARKER_PALETTE_LIMIT} позиций.'}, status=400)
    items, seen = [], set()
    try:
        for raw in raw_items:
            if not isinstance(raw, dict):
                raise ValueError('Проверьте строки палитры.')
            marker_id = raw.get('marker_id')
            if marker_id:
                marker = Marker.objects.get(pk=int(marker_id))
                symbol = str(raw.get('symbol', '')).strip() or marker.symbol
                manufacturer = str(raw.get('manufacturer', '')).strip() or marker.manufacturer
                marker_type = str(raw.get('marker_type', '')).strip() or marker.marker_type
                if manufacturer != marker.manufacturer:
                    raise ValueError('Выберите производителя для этой позиции заново.')
                if marker_type != marker.marker_type:
                    raise ValueError('Выберите тип для этой позиции заново.')
            else:
                symbol = str(raw.get('symbol', '')).strip()
                number = normalize_marker_number(raw.get('number', ''))
                manufacturer = str(raw.get('manufacturer', '')).strip() or 'unknown'
                marker_type = str(raw.get('marker_type', '')).strip()
                if not symbol or not number:
                    raise ValueError('Для каждой позиции укажите производителя, тип, значок и номер.')
                if manufacturer not in MARKER_MANUFACTURER_CODES:
                    raise ValueError('Выберите производителя из списка.')
                if marker_type not in MARKER_TYPE_CODES:
                    raise ValueError('Выберите тип: маркер или ручка.')
                if len(symbol) > MARKER_SYMBOL_LIMIT or len(number) > MARKER_NUMBER_LIMIT:
                    raise ValueError('Значок или номер расходника слишком длинный.')
                marker, created = Marker.objects.get_or_create(
                    manufacturer=manufacturer,
                    marker_type=marker_type,
                    number=number,
                    defaults={'symbol': symbol, 'created_by': user_book.user},
                )
                if not marker.symbol:
                    marker.symbol = symbol
                    marker.save(update_fields=('symbol', 'updated_at'))
            usage_level = str(raw.get('usage_level', '') or '')
            if usage_level not in MARKER_USAGE_WEIGHTS:
                raise ValueError('Неизвестная оценка расхода позиции.')
            if marker.id in seen:
                raise ValueError('Одну позицию нельзя добавить дважды.')
            seen.add(marker.id)
            if not symbol or len(symbol) > MARKER_SYMBOL_LIMIT:
                raise ValueError('Укажите значок не длиннее 32 символов.')
            items.append({'marker_id': marker.id, 'symbol': symbol, 'usage_level': usage_level})
    except (Marker.DoesNotExist, TypeError, ValueError) as exc:
        return JsonResponse({'error': str(exc) or 'Не удалось распознать позицию.'}, status=400)

    with transaction.atomic():
        palette, _ = MarkerPalette.objects.select_for_update().get_or_create(
            user_book=user_book,
            page=page,
            defaults={
                'allow_import': user_book.user.marker_palette_import_allowed,
                'fingerprint': palette_fingerprint(items),
            },
        )
        palette.allow_import = user_book.user.marker_palette_import_allowed
        palette.fingerprint = palette_fingerprint(items)
        palette.imported_from = None
        palette.save(update_fields=('allow_import', 'fingerprint', 'imported_from', 'updated_at'))
        palette.items.all().delete()
        MarkerPaletteItem.objects.bulk_create(
            [MarkerPaletteItem(palette=palette, position=index, **item) for index, item in enumerate(items)]
        )
    return JsonResponse({'palette': palette_payload(request, palette)})


@csrf_exempt
@require_http_methods(['POST'])
def tracker_palette_import(request, user_book_id, page_id):
    user_book, page = palette_scope(request, user_book_id, page_id)
    try:
        payload = json.loads(request.body or '{}')
        source_id = int(payload.get('palette_id'))
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'error': 'Выберите палитру для импорта.'}, status=400)
    source = get_object_or_404(
        MarkerPalette.objects.prefetch_related('items__marker'),
        pk=source_id,
        page=page,
        allow_import=True,
        user_book__user__marker_palette_import_allowed=True,
    )
    if source.user_book.user_id == user_book.user_id:
        return JsonResponse({'error': 'Эта палитра уже принадлежит вам.'}, status=400)
    items = [
        {'marker_id': item.marker_id, 'symbol': item.symbol, 'usage_level': item.usage_level}
        for item in source.items.all()
    ]
    with transaction.atomic():
        palette, _ = MarkerPalette.objects.select_for_update().get_or_create(
            user_book=user_book,
            page=page,
            defaults={
                'allow_import': user_book.user.marker_palette_import_allowed,
                'fingerprint': source.fingerprint,
                'imported_from': source,
            },
        )
        palette.allow_import = user_book.user.marker_palette_import_allowed
        palette.fingerprint = source.fingerprint
        palette.imported_from = source
        palette.save(update_fields=('allow_import', 'fingerprint', 'imported_from', 'updated_at'))
        palette.items.all().delete()
        MarkerPaletteItem.objects.bulk_create(
            [MarkerPaletteItem(palette=palette, position=index, **item) for index, item in enumerate(items)]
        )
    return JsonResponse({'palette': palette_payload(request, palette)})


@csrf_exempt
@require_http_methods(['GET', 'PATCH'])
def tracker_marker_settings(request):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    if request.method == 'GET':
        return JsonResponse({'import_allowed': user.marker_palette_import_allowed})
    try:
        payload = json.loads(request.body or '{}')
        allowed = payload['import_allowed']
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'error': 'Ожидается настройка импорта.'}, status=400)
    if not isinstance(allowed, bool):
        return JsonResponse({'error': 'Настройка импорта должна быть логической.'}, status=400)
    user.marker_palette_import_allowed = allowed
    user.save(update_fields=('marker_palette_import_allowed', 'updated_at'))
    return JsonResponse({'import_allowed': allowed})


def marker_stats_payload(user, period='6m', top_limit=10, top_offset=0):
    period_days = MARKER_STATS_PERIOD_DAYS.get(period, MARKER_STATS_PERIOD_DAYS['6m'])
    period_start = timezone.now() - timedelta(days=period_days) if period_days else None

    def in_period(items):
        if period_start is None:
            return items
        return [item for item in items if item.palette.created_at >= period_start]

    personal_items = in_period(list(
        MarkerPaletteItem.objects.filter(palette__user_book__user=user)
        .select_related('marker', 'palette__user_book__book')
    ))
    def aggregate(items):
        result = {}
        for item in items:
            key = item.marker_id
            row = result.setdefault(
                key,
                {
                    'marker': marker_data(item.marker),
                    'uses': 0,
                    'weighted': 0,
                    'books': set(),
                    'palettes': set(),
                    'symbols': {},
                    'usage_levels': {key: 0 for key in MARKER_USAGE_LABELS},
                },
            )
            row['uses'] += 1
            row['weighted'] += MARKER_USAGE_WEIGHTS.get(item.usage_level, 1)
            row['books'].add(item.palette.user_book.book_id)
            row['palettes'].add(item.palette_id)
            row['symbols'][item.symbol] = row['symbols'].get(item.symbol, 0) + 1
            row['usage_levels'][item.usage_level] = row['usage_levels'].get(item.usage_level, 0) + 1
        rows = []
        for row in result.values():
            symbol = max(row['symbols'], key=row['symbols'].get) if row['symbols'] else row['marker']['symbol']
            rows.append({
                'marker': {**row['marker'], 'symbol': symbol},
                'uses': row['uses'],
                'weighted': row['weighted'],
                'books': len(row['books']),
                'palettes': len(row['palettes']),
                'usage_summary': [
                    {'key': key, 'label': MARKER_USAGE_LABELS[key], 'count': count}
                    for key, count in row['usage_levels'].items()
                    if count
                ],
            })
        return sorted(rows, key=lambda row: (-row['uses'], -row['weighted'], row['marker']['number']))

    def trend(items):
        today = timezone.localdate()
        month_keys = []
        year, month = today.year, today.month
        for _ in range(6):
            month_keys.append(f'{year:04d}-{month:02d}')
            month -= 1
            if month == 0:
                year, month = year - 1, 12
        counts = {key: 0 for key in reversed(month_keys)}
        for item in items:
            key = item.palette.created_at.strftime('%Y-%m')
            if key in counts:
                counts[key] += 1
        return [{'month': key, 'value': value} for key, value in counts.items()]

    personal_top_all = aggregate(personal_items)
    personal_top = personal_top_all[top_offset:top_offset + top_limit]
    global_items = in_period(list(MarkerPaletteItem.objects.all().select_related('marker', 'palette__user_book')))
    global_top_all = aggregate(global_items)
    global_top = global_top_all[top_offset:top_offset + top_limit]
    user_totals = {}
    for item in global_items:
        user_id = item.palette.user_book.user_id
        user_totals[user_id] = user_totals.get(user_id, 0) + 1
    global_weighted_units = sum(
        MARKER_USAGE_WEIGHTS.get(item.usage_level, 1) for item in global_items
    )
    personal_weighted_units = sum(
        MARKER_USAGE_WEIGHTS.get(item.usage_level, 1) for item in personal_items
    )
    ranked_users = sorted(user_totals.values(), reverse=True)
    my_rank = ranked_users.index(user_totals[user.pk]) + 1 if user.pk in user_totals else None
    return {
        'personal': {
            'total_entries': len(personal_items),
            'weighted_units': sum(MARKER_USAGE_WEIGHTS.get(item.usage_level, 1) for item in personal_items),
            'distinct_markers': len({item.marker_id for item in personal_items}),
            'palettes': len({item.palette_id for item in personal_items}),
            'top': personal_top,
            'top_offset': top_offset,
            'top_total': len(personal_top_all),
            'top_has_more': top_offset + len(personal_top) < len(personal_top_all),
            'trend': trend(personal_items),
        },
        'global': {
            'users': len(user_totals),
            'total_entries': len(global_items),
            'weighted_units': global_weighted_units,
            'distinct_markers': len({item.marker_id for item in global_items}),
            'palettes': len({item.palette_id for item in global_items}),
            'my_weighted_units': personal_weighted_units,
            'my_share_percent': round(len(personal_items) * 100 / len(global_items), 1)
            if global_items
            else 0,
            'my_rank': my_rank,
            'top': global_top,
            'top_offset': top_offset,
            'top_total': len(global_top_all),
            'top_has_more': top_offset + len(global_top) < len(global_top_all),
            'trend': trend(global_items),
            'leaderboard': [
                {'rank': index, 'entries': value}
                for index, value in enumerate(sorted(user_totals.values(), reverse=True)[:5], 1)
            ],
        },
        'period': period if period in MARKER_STATS_PERIOD_DAYS else '6m',
    }


@require_http_methods(['GET'])
def tracker_marker_stats(request):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    period = request.GET.get('period', '6m')
    try:
        top_limit = min(max(int(request.GET.get('limit', 10)), 1), 30)
        top_offset = max(int(request.GET.get('offset', 0)), 0)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Некорректные параметры статистики.'}, status=400)
    return JsonResponse({
        'stats': marker_stats_payload(user, period=period, top_limit=top_limit, top_offset=top_offset),
        'usage_weights': MARKER_USAGE_WEIGHTS,
    })


@require_http_methods(['GET'])
def tracker_month_report(request):
    available_months = sorted(
        {
            work.completed_at.strftime('%Y-%m')
            for work in ColoringWork.objects.filter(
                user_book__in=user_books(request),
                completed_at__gte=REPORT_LAUNCH_DATE,
                hide_in_report=False,
            ).only('completed_at')
        },
        reverse=True,
    )
    requested_month = request.GET.get('month')
    if not available_months:
        return JsonResponse({'months': [], 'entries': []})
    if not requested_month:
        requested_month = available_months[0]
    if requested_month not in available_months:
        return JsonResponse({'error': 'Этот месяц недоступен в отчёте'}, status=400)
    try:
        year, month = map(int, requested_month.split('-'))
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])
    except ValueError:
        return JsonResponse({'error': 'Ожидается месяц в формате ГГГГ-ММ'}, status=400)
    works = (
        ColoringWork.objects.filter(
            user_book__in=user_books(request),
            completed_at__range=(first_day, last_day),
            hide_in_report=False,
        )
        .select_related('user_book__book', 'page')
        .order_by('-completed_at', '-created_at')
    )
    photo_urls = {
        (photo.user_book_id, photo.page_id): media_url(request, photo.image, photo.updated_at)
        for photo in ColoringPagePhoto.objects.filter(user_book__in=user_books(request))
    }
    daily, books, entries_by_day = defaultdict(int), defaultdict(int), defaultdict(list)
    for work in works:
        daily[work.completed_at.day] += 1
        books[work.user_book.book.title] += 1
        entries_by_day[work.completed_at.isoformat()].append(
            {
                'book': work.user_book.book.title,
                'page': work.page.label,
                'photo': photo_urls.get((work.user_book_id, work.page_id), ''),
                'icon': work.user_book.book.report_icon,
            }
        )
    return JsonResponse(
        {
            'month': first_day.strftime('%Y-%m'),
            'months': available_months,
            'total': works.count(),
            'active_days': len(daily),
            'best_day': max(daily.values(), default=0),
            'days': daily,
            'books': books,
            'entries': [
                {'date': day, 'works': entries_by_day[day]}
                for day in sorted(entries_by_day, reverse=True)
            ],
        }
    )
