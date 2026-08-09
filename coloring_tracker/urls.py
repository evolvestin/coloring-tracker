from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path
from django.views.static import serve

from app import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/tracker/books/', views.tracker_books),
    path('api/tracker/randomizer/', views.tracker_randomizer),
    path('api/tracker/personal-books/', views.tracker_personal_book_create),
    path('api/tracker/personal-books/<int:user_book_id>/', views.tracker_personal_book),
    path('api/tracker/personal-books/<int:user_book_id>/pages/', views.tracker_personal_pages),
    path(
        'api/tracker/personal-books/<int:user_book_id>/pages/<int:page_id>/',
        views.tracker_personal_page,
    ),
    path('api/tracker/catalog/', views.tracker_catalog),
    path('api/tracker/catalog/<int:book_id>/', views.tracker_catalog_book_detail),
    path('api/tracker/suggestions/', views.tracker_suggestion),
    path('api/tracker/stars/', views.tracker_stars),
    path('api/tracker/stars/invoice/', views.tracker_stars_invoice),
    path(
        'api/tracker/stars/<int:donation_id>/test-complete/',
        views.tracker_stars_test_complete,
    ),
    path('api/tracker/stars/<int:donation_id>/', views.tracker_stars_status),
    path('api/tracker/profile/', views.tracker_profile),
    path('api/tracker/catalog/<int:book_id>/collection/', views.tracker_collection_book),
    path('api/tracker/books/<int:user_book_id>/', views.tracker_book_detail),
    path('api/tracker/books/<int:user_book_id>/pages/<int:page_id>/', views.tracker_work),
    path(
        'api/tracker/books/<int:user_book_id>/pages/<int:page_id>/color-code/',
        views.tracker_color_code,
    ),
    path('api/tracker/report/', views.tracker_month_report),
    path(
        'tracker-preview-app/<int:telegram_id>/',
        views.tracker_preview_webapp,
        name='tracker-preview-webapp',
    ),
    path('tracker-preview/<int:telegram_id>/', views.tracker_preview, name='tracker-preview'),
    path('', views.webapp_index),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
