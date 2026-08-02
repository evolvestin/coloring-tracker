from django.contrib import admin

from app.models import ColoringBook, ColoringPage, ColoringWork, TrackerUser, UserBook


class ColoringPageInline(admin.TabularInline):
    model = ColoringPage
    extra = 1
    fields = ('number', 'spread_end', 'title')


@admin.register(ColoringBook)
class ColoringBookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'publisher', 'is_published', 'work_count')
    list_filter = ('is_published',)
    search_fields = ('title', 'author', 'publisher')
    inlines = (ColoringPageInline,)

    @admin.display(description='Работ')
    def work_count(self, book):
        return book.pages.count()


@admin.register(UserBook)
class UserBookAdmin(admin.ModelAdmin):
    list_display = ('book', 'user', 'created_at')
    search_fields = ('book__title', 'user__username')


@admin.register(ColoringWork)
class ColoringWorkAdmin(admin.ModelAdmin):
    list_display = ('user_book', 'page', 'completed_at', 'has_photo')
    list_filter = ('completed_at', 'user_book__book')

    @admin.display(boolean=True, description='Фото')
    def has_photo(self, work):
        return bool(work.photo)


@admin.register(TrackerUser)
class TrackerUserAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'username', 'telegram_id', 'webapp_viewport', 'created_at')
    search_fields = ('display_name', 'username', 'telegram_id')

    @admin.display(description='Размер WebApp')
    def webapp_viewport(self, user):
        if not user.webapp_viewport_width or not user.webapp_viewport_height:
            return '—'
        return f'{user.webapp_viewport_width} × {user.webapp_viewport_height}'

