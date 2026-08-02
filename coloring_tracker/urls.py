from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from app import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/tracker/books/', views.tracker_books),
    path('api/tracker/catalog/', views.tracker_catalog),
    path('api/tracker/profile/', views.tracker_profile),
    path('api/tracker/catalog/<int:book_id>/collection/', views.tracker_collection_book),
    path('api/tracker/books/<int:user_book_id>/', views.tracker_book_detail),
    path('api/tracker/books/<int:user_book_id>/pages/<int:page_id>/', views.tracker_work),
    path('api/tracker/report/', views.tracker_month_report),
    path('local-preview-app/<int:telegram_id>/', views.local_preview_webapp, name='local-preview-webapp'),
    path('<int:telegram_id>/', views.local_preview, name='local-preview'),
    path('', views.webapp_index),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
