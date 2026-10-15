FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# glibc gives every thread its own memory arena; with FastAPI's thread pool (sync endpoints) resident memory can
# balloon far past what the app really uses. Two arenas keep RSS close to real usage on a 1 GB machine.
ENV MALLOC_ARENA_MAX=2
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

EXPOSE 8080
# Migrations run as Fly's release_command (fly.toml), not here, so a crash-loop can't re-run them.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
