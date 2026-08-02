# Coloring Tracker

Мобильный веб‑трекер раскрасок на Django + Vue 3.

## Что уже есть

- каталог раскрасок, который редактирует только администратор Django;
- личная коллекция книг пользователя: Telegram WebApp безопасно связывает её с Telegram ID; вне Telegram используется сессия браузера;
- сетка страниц, загрузка фотографии готовой работы и снятие отметки;
- развороты: одна запись страницы с полем «Последняя страница разворота» — это одна работа и одна карточка в сетке;
- месячный отчёт с активными днями, лучшим днём и разбивкой по книгам;
- поиск по каталогу, избранные раскраски и профиль с личной статистикой;
- Docker Compose с PostgreSQL, Redis, Django/Gunicorn и Celery worker.

## Первый запуск

1. Скопируйте `.env.example` в `.env` и укажите `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DJANGO_SECRET_KEY` и `TELEGRAM_BOT_TOKEN`.
2. Создайте первую миграцию: `python manage.py makemigrations app`.
3. Запустите сервисы: `docker compose --profile tunnel up --build`. Compose поднимает Django, Vite dev server с HMR, PostgreSQL, Redis, Celery, Telegram-бот и Tunnelmole. Туннель публикует HTTPS URL в `data/tunnel_url.txt`; бот использует его автоматически.
4. Создайте администратора: `docker compose exec web python manage.py createsuperuser`.
5. В `/admin/` добавьте раскраску и её страницы. Для разворота укажите первую и последнюю страницы в одной строке.

## Структура

- `coloring_tracker/` — конфигурация Django;
- `app/` — чистый домен трекера и API;
- `frontend_webapp/` — Vue-интерфейс;
- `legacy_kinopub/` — изолированный архив донорского проекта. Он не подключён к приложению и не участвует в сборке;
- `data/` — автоматически создаваемые PostgreSQL-совместимые медиа и собранная статика при первом запуске.
