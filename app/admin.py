from django.contrib import admin

from app.models import (
    ColoringBook,
    ColoringColorCode,
    ColoringPage,
    ColoringPagePhoto,
    ColoringWork,
    TrackerUser,
    UserBook,
)


class ColoringPageInline(admin.TabularInline):
    model = ColoringPage
    extra = 1
    fields = ('number', 'spread_end', 'title')
    template = 'admin/app/coloringpage/tabular.html'


@admin.register(ColoringBook)
class ColoringBookAdmin(admin.ModelAdmin):
    list_display = ('title', 'report_icon', 'author', 'publisher', 'is_published', 'page_count')
    list_filter = ('is_published',)
    search_fields = ('title', 'author', 'publisher')
    inlines = (ColoringPageInline,)

    @admin.display(description='Страниц')
    def page_count(self, book):
        return book.pages.count()


@admin.register(UserBook)
class UserBookAdmin(admin.ModelAdmin):
    list_display = ('book', 'user', 'created_at')
    search_fields = ('book__title', 'user__username')


@admin.register(ColoringWork)
class ColoringWorkAdmin(admin.ModelAdmin):
    list_display = ('user_book', 'page', 'completed_at')
    list_filter = ('completed_at', 'user_book__book')
    fields = ('user_book', 'page', 'completed_at', 'note')


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


@admin.register(TrackerUser)
class TrackerUserAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'username', 'telegram_id', 'webapp_viewport', 'created_at')
    search_fields = ('display_name', 'username', 'telegram_id')

    @admin.display(description='Размер WebApp')
    def webapp_viewport(self, user):
        if not user.webapp_viewport_width or not user.webapp_viewport_height:
            return '—'
        return f'{user.webapp_viewport_width} × {user.webapp_viewport_height}'
