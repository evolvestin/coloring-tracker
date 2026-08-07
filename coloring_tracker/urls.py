from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path
from django.views.static import serve

from app import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/tracker/books/', views.tracker_books),
    path('api/tracker/catalog/', views.tracker_catalog),
    path('api/tracker/catalog/<int:book_id>/', views.tracker_catalog_book_detail),
    path('api/tracker/suggestions/', views.tracker_suggestion),
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
