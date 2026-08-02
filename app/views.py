import hashlib
import hmac
import json
import os
from calendar import monthrange
from collections import defaultdict
from datetime import date
from urllib.parse import parse_qsl

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.decorators.clickjacking import xframe_options_sameorigin

from app.models import ColoringBook, ColoringPage, ColoringWork, TrackerUser, UserBook


def media_url(request, field, updated_at=None):
    """Return a same-origin, cache-busted media URL for the WebApp."""
    if not field:
        return ''
    # Keep this relative: it must use the HTTPS tunnel/Caddy origin, never the
    # internal Django container host received by a reverse proxy.
    url = field.url
    return f'{url}?v={int(updated_at.timestamp())}' if updated_at else url


def webapp_index(request):
    vite_dev_mode = os.getenv('VITE_DEV_MODE', 'False').lower() == 'true'
    vite_hmr_enabled = os.getenv('VITE_HMR_ENABLED', 'true').lower() != 'false'
    return render(
        request,
        'webapp/coloring.html',
        {
            'vite_dev_mode': vite_dev_mode,
            'vite_hmr_enabled': vite_hmr_enabled,
            'local_preview_telegram_id': local_preview_telegram_id(request),
        },
    )


def local_preview_telegram_id(request):
    """Return the impersonated user only for the loopback development preview."""
    raw_id = request.headers.get('X-Local-Preview-Telegram-ID', '')
    host = request.get_host().split(':', 1)[0].lower()
    is_local_dev = settings.DEBUG or os.getenv('VITE_DEV_MODE', 'False').lower() == 'true'
    if not raw_id or not is_local_dev or host not in {'localhost', '127.0.0.1', '::1'}:
        return None
    try:
        return int(raw_id)
    except ValueError:
        return None


def local_preview(request, telegram_id):
    """A local-only frame that recreates a saved Telegram WebApp viewport."""
    is_local_dev = settings.DEBUG or os.getenv('VITE_DEV_MODE', 'False').lower() == 'true'
    if not is_local_dev or request.get_host().split(':', 1)[0].lower() not in {'localhost', '127.0.0.1', '::1'}:
        raise Http404
    user = get_object_or_404(TrackerUser, telegram_id=telegram_id)
    viewport = None
    if user.webapp_viewport_width and user.webapp_viewport_height:
        viewport = {'width': user.webapp_viewport_width, 'height': user.webapp_viewport_height}
    return render(request, 'webapp/local_preview.html', {'user': user, 'viewport': viewport})


@xframe_options_sameorigin
def local_preview_webapp(request, telegram_id):
    """Serve the actual WebApp only inside the local preview frame."""
    is_local_dev = settings.DEBUG or os.getenv('VITE_DEV_MODE', 'False').lower() == 'true'
    if not is_local_dev or request.get_host().split(':', 1)[0].lower() not in {'localhost', '127.0.0.1', '::1'}:
        raise Http404
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

    preview_telegram_id = local_preview_telegram_id(request)
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
    token = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('BOT_TOKEN', '')
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
            return JsonResponse({'error': 'Ожидается JSON с идентификатором книги.'}, status=400)
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
        from django.db.models import Q

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
                    'pages': book.pages.count(),
                    'owned': book.id in owned,
                    'collection_id': collection[book.id].id if book.id in collection else None,
                    'completed': collection[book.id].works.count() if book.id in collection else 0,
                }
                for book in catalogue
            ]
        }
    )


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
    pages = [
        {
            'id': page.id,
            'number': page.number,
            'spread_end': page.spread_end,
            'label': page.label,
            'completed': page.id in works_by_page,
            'photo': media_url(
                request, works_by_page[page.id].photo, works_by_page[page.id].updated_at
            )
            if page.id in works_by_page and works_by_page[page.id].photo
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
    if photo := request.FILES.get('photo'):
        work.photo = photo
        work.save(update_fields=('photo', 'updated_at'))
    return JsonResponse({'id': work.id, 'photo': media_url(request, work.photo, work.updated_at)})


@require_http_methods(['GET'])
def tracker_month_report(request):
    try:
        year, month = map(int, request.GET.get('month', date.today().strftime('%Y-%m')).split('-'))
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])
    except ValueError:
        return JsonResponse({'error': 'Ожидается месяц в формате ГГГГ-ММ'}, status=400)
    works = ColoringWork.objects.filter(
        user_book__in=user_books(request), completed_at__range=(first_day, last_day)
    ).select_related('user_book__book', 'page').order_by('-completed_at', '-created_at')
    daily, books, entries_by_day = defaultdict(int), defaultdict(int), defaultdict(list)
    for work in works:
        daily[work.completed_at.day] += 1
        books[work.user_book.book.title] += 1
        entries_by_day[work.completed_at.isoformat()].append(
            {
                'book': work.user_book.book.title,
                'page': work.page.label,
                'photo': bool(work.photo),
            }
        )
    return JsonResponse(
        {
            'month': first_day.strftime('%Y-%m'),
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
