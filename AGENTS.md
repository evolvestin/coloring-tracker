# Coloring Tracker: архитектура и правила разработки

## Назначение

Это Telegram WebApp и мобильный веб‑трекер раскрасок. Django — источник истины
и административный каталог; Vue 3 — пользовательский интерфейс.
`legacy_kinopub/` — архив донора и не импортируется активным приложением.

## Активная структура

- `coloring_tracker/` — настройки, URL и Celery-конфигурация Django.
- `app/` — модели трекера, Django admin и JSON API.
- `frontend_webapp/` — Vue 3/Vite интерфейс.
- `tracker_bot/` — Telegram-бот, открывающий опубликованный WebApp.

Для локальной разработки Docker Compose запускает PostgreSQL, Redis, Django,
Vite, Celery и бота. Reverse proxy и туннелирование не используются. Для
проверки интерфейса используйте iframe-предпросмотр `/<telegram_id>/`.

## Доменная модель

1. `TrackerUser` — пользователь: Telegram `telegram_id` или временный `session_key`.
2. `ColoringBook` — книга каталога, которую редактирует только Django admin.
3. `ColoringPage` — работа с номером; разворот — одна запись с `spread_end`.
4. `UserBook` — книга в личной коллекции.
5. `ColoringWork` — завершённая работа с датой и необязательной фотографией.
6. `FavoriteBook` — сохранённая пользователем книга каталога.

Не используйте кино-термины (`Show`, `ViewUser`, `Wishlist`, `rating`) для
новых сущностей.

## Целостность данных

- Пользователь добавляет в коллекцию только опубликованные книги; каталог создаёт admin.
- Номер страницы уникален в книге; диапазоны страниц и разворотов не пересекаются.
- Разворот требует `spread_end > number`.
- Страница или разворот имеет только одну работу в рамках `UserBook`.
- При удалении работы удаляется её фотография.
- Повторная загрузка фото не меняет `completed_at`.

## Telegram-авторизация

- Фронтенд передаёт `Telegram.WebApp.initData` только в `X-Telegram-Init-Data`.
- Сервер проверяет Telegram HMAC до чтения `user.id`; токен — `TELEGRAM_BOT_TOKEN`.
- `initDataUnsafe.user` нельзя считать достоверным.
- Гостевая сессия допустима только для локального браузерного тестирования.
- Бот берёт адрес опубликованного приложения из `TELEGRAM_WEBAPP_URL`.

## API и интерфейс

- JSON API находится под `/api/tracker/`.
- Все клиентские запросы проходят через `frontend_webapp/src/api.js`.
- После изменения работы, избранного или коллекции перезагружайте данные из API.
- Тексты интерфейса — на русском; интерфейс — compact mobile-first.
- Важные фильтры и поиск отражайте в query-параметрах Vue Router.

## Локальная разработка

- Основной запуск: `docker compose up --build`.
- Django и Vite можно запускать на машине при локальных PostgreSQL и Redis.
- Локальный iframe-предпросмотр доступен по `http://localhost:8022/<telegram_id>/`.
- Production-сборка Vue использует Vite manifest; dev-режим включается `VITE_DEV_MODE=true`.

## Конфигурация и проверка

- Не коммитьте `.env`, `data/`, `node_modules/` и `dist/`.
- Переменная `GOOGLE_DRIVE_BACKUP_FILENAME` обязательна и не имеет значения по умолчанию.
- После изменения моделей выполняйте `python manage.py makemigrations app`.
- Перед сдачей запускайте:

  ```bash
  python manage.py check
  python manage.py makemigrations --check
  npm run build --prefix frontend_webapp
  docker compose config --quiet
  ```

## Визуальный стиль WebApp

Сохраняйте лёгкую пудрово-розовую тему с кремовыми акцентами, мягкими
градиентами, скруглёнными карточками и деликатным цветочным декором. Для пустой
обложки используйте `❀`. Контраст, фокус и нажимаемость на малых экранах важнее
декора.
