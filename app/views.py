import hashlib
import hmac
import json
import os
from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import parse_qsl

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
    ColoringBook,
    ColoringColorCode,
    ColoringPage,
    ColoringPagePhoto,
    ColoringSuggestion,
    ColoringWork,
    TrackerUser,
    UserBook,
)
from app.tasks import send_suggestion_notification

REPORT_LAUNCH_DATE = date(2026, 8, 1)
SUGGESTION_COOLDOWN_SECONDS = 30
SUGGESTION_TITLE_LIMIT = 500
SUGGESTION_SOURCE_LIMIT = 100_000
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


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
        'total': total,
        'done': completed,
        'progress': round(completed * 100 / total) if total else 0,
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
        book = get_object_or_404(ColoringBook, pk=payload.get('book_id'), is_published=True)
        user_book, _ = UserBook.objects.get_or_create(book=book, user=user)
        return JsonResponse({'book': book_data(user_book)}, status=201)
    return JsonResponse({'books': [book_data(item) for item in user_books(request)]})


@require_http_methods(['GET'])
def tracker_catalog(request):
    user = tracker_identity(request)
    owned = set(user_books(request).values_list('book_id', flat=True)) if user else set()
    collection = {item.book_id: item for item in user_books(request)} if user else {}
    query = request.GET.get('q', '').strip()
    catalogue = ColoringBook.objects.filter(is_published=True).prefetch_related('pages')
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
        ColoringBook.objects.prefetch_related('pages'), pk=book_id, is_published=True
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


@csrf_exempt
@require_http_methods(['DELETE'])
def tracker_collection_book(request, book_id):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    user_book = get_object_or_404(UserBook, user=user, book_id=book_id)
    deleted_works = user_book.works.count()
    user_book.delete()
    return JsonResponse({'ok': True, 'deleted_works': deleted_works})


@require_http_methods(['GET'])
def tracker_profile(request):
    user = tracker_identity(request)
    if not user:
        return JsonResponse({'error': 'Доступно только через Telegram WebApp.'}, status=401)
    books = user_books(request)
    total = sum(item.book.total_pages_count for item in books)
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
                'progress': round(completed * 100 / sum(item.book.pages.count() for item in books))
                if books
                else 0,
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
            'color_code': media_url(
                request, color_codes_by_page[page.id].image, color_codes_by_page[page.id].updated_at
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
        page_photo, _ = ColoringPagePhoto.objects.get_or_create(user_book=user_book, page=page)
        page_photo.image = photo
        page_photo.save()
    page_photo = ColoringPagePhoto.objects.filter(user_book=user_book, page=page).first()
    return JsonResponse(
        {
            'id': work.id,
            'hide_in_report': work.hide_in_report,
            'photo': media_url(request, page_photo.image, page_photo.updated_at)
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
    if color_code:
        color_code.image = image
        color_code.save(update_fields=('image', 'updated_at'))
    else:
        color_code = ColoringColorCode.objects.create(user_book=user_book, page=page, image=image)
    return JsonResponse(
        {
            'id': color_code.id,
            'image': media_url(request, color_code.image, color_code.updated_at),
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
    photo_pages = set(
        ColoringPagePhoto.objects.filter(user_book__in=user_books(request)).values_list(
            'user_book_id', 'page_id'
        )
    )
    daily, books, entries_by_day = defaultdict(int), defaultdict(int), defaultdict(list)
    for work in works:
        daily[work.completed_at.day] += 1
        books[work.user_book.book.title] += 1
        entries_by_day[work.completed_at.isoformat()].append(
            {
                'book': work.user_book.book.title,
                'page': work.page.label,
                'photo': (work.user_book_id, work.page_id) in photo_pages,
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
