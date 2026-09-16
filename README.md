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

## Telegram-бекап PostgreSQL

Бекап хранится в приватном Telegram-канале отдельным backup-ботом. Интеграция
отключена по умолчанию, пока канал не создан. После создания канала добавьте
бота администратором с правами отправки, удаления и редактирования документов.
ID канала задаётся только в `coloring_tracker/backup_constants.py`.
Заполните в `.env` `TELEGRAM_BACKUP_ENABLED=true`,
`TELEGRAM_API_ID` и `TELEGRAM_API_HASH`. Для Telegram-бекапа используется
основной `TELEGRAM_BOT_TOKEN`, затем проверьте доступ:

```bash
docker compose run --rm web python manage.py telegram_backup_healthcheck
docker compose run --rm worker python manage.py backupdb
```

Каждый бекап публикуется как части PostgreSQL custom dump и JSON manifest.
Для восстановления нужен `file_id` manifest и явное подтверждение:

```bash
docker compose run --rm web python manage.py restoredb <manifest-file-id> --confirm
```

Manifest можно восстановить даже без локальных записей индекса. Старые команды
`backup_tracker_database` и `restore_tracker_backup` сохранены как алиасы.

После восстановления базы или медиа на продакшене пересоберите все маленькие
превью обложек командой:

```bash
python manage.py rebuild_cover_previews
```

Команда не изменяет исходные изображения. Она также удаляет устаревшие превью
у раскрасок, у которых исходная обложка была удалена.

Для поддержки проекта через Telegram Stars включите `TELEGRAM_STARS_ENABLED=true`.
Быстрые варианты суммы хранятся в константе `DONATION_PRESETS`, а пользователь
может указать любую целую сумму. В локальной разработке при
`DJANGO_DEBUG=true` или `VITE_DEV_MODE=true` экран автоматически использует
безопасный тестовый сценарий: Stars не списываются, а оплату можно подтвердить
кнопкой «Проверить без списания».
Порты Django и Vite доступны только с `localhost`; reverse proxy,
туннелирование и связанные с ними сервисы отсутствуют.

## Структура

- `coloring_tracker/` — конфигурация Django;
- `app/` — доменная модель, admin и JSON API;
- `frontend_webapp/` — Vue-интерфейс;
- `tracker_bot/` — бот, открывающий опубликованный WebApp;
