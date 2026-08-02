# Coloring Tracker

Мобильный трекер раскрасок на Django и Vue 3. Django хранит каталог и данные,
Vue отвечает за WebApp-интерфейс.

## Локальная разработка в контейнерах

1. Скопируйте `.env.example` в `.env`. Для открытия приложения в Telegram
   задайте `TELEGRAM_WEBAPP_URL` — URL опубликованного WebApp.
2. Запустите сервисы: `docker compose up --build`.

Для просмотра интерфейса в браузере откройте `http://localhost:8022/<telegram_id>/`.
Это локальный iframe-предпросмотр с сохранёнными размерами WebApp и без
публикации локального сервера в интернет.

Compose запускает PostgreSQL, Redis, Django, Vite, Celery и Telegram-бота.
Порты Django и Vite доступны только с `localhost`; reverse proxy,
туннелирование и связанные с ними сервисы отсутствуют.

## Структура

- `coloring_tracker/` — конфигурация Django;
- `app/` — доменная модель, admin и JSON API;
- `frontend_webapp/` — Vue-интерфейс;
- `tracker_bot/` — бот, открывающий опубликованный WebApp;
