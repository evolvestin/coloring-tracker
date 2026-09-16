FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend_webapp/package*.json ./
RUN npm ci
COPY frontend_webapp ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=coloring_tracker.settings
RUN apt-get update \
    && apt-get install --no-install-recommends -y postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home app \
    && if getent group 101 >/dev/null; then \
        usermod -aG "$(getent group 101 | cut -d: -f1)" app; \
    else \
        groupadd --gid 101 telegram-bot-api \
        && usermod -aG telegram-bot-api app; \
    fi
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend /build/dist ./frontend_webapp/dist
RUN mkdir -p /app/data /var/lib/coloring-tracker/telegram-backups \
    && chown -R app:app /app /var/lib/coloring-tracker
USER app
CMD ["gunicorn", "coloring_tracker.wsgi:application", "--bind", "0.0.0.0:8000", "--worker-class", "gthread", "--workers", "2", "--threads", "4", "--timeout", "60", "--keep-alive", "5"]
