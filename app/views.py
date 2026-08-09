import hashlib
import hmac
import json
import os
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

from app.models import (
    FLOWER_ICONS,
    ColoringBook,
    ColoringColorCode,
    ColoringPage,
    ColoringPagePhoto,
    ColoringSuggestion,
    ColoringWork,
    StarDonation,
    TrackerUser,
    UserBook,
)
from app.tasks import send_donation_notification, send_suggestion_notification

REPORT_LAUNCH_DATE = date(2026, 8, 1)
SUGGESTION_COOLDOWN_SECONDS = 30
SUGGESTION_TITLE_LIMIT = 500
SUGGESTION_SOURCE_LIMIT = 100_000
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
PERSONAL_BOOK_TITLE_LIMIT = 255
PERSONAL_PAGE_LIMIT = 300
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
    total = user_book.book.pages.count()
    completed = user_book.works.count()
    return {
        'id': user_book.id,
        'catalog_id': user_book.book_id,
        'title': user_book.book.title,
        'author': user_book.book.author,
        'cover': user_book.book.cover.url if user_book.book.cover else '',
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


@require_http_methods(['GET'])
def tracker_catalog(request):
    user = tracker_identity(request)
    owned = set(user_books(request).values_list('book_id', flat=True)) if user else set()
    collection = {item.book_id: item for item in user_books(request)} if user else {}
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
    total = sum(item.book.pages.count() for item in books)
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
