# Contributing to Visio-Display

Thank you for considering a contribution! This document covers everything you need to get started: local setup, architecture overview, coding standards, and how to submit changes.

---

## Table of contents

1. [Local development setup](#1-local-development-setup)
2. [Running the tests](#2-running-the-tests)
3. [Linting](#3-linting)
4. [Architecture overview](#4-architecture-overview)
5. [Adding or editing translations](#5-adding-or-editing-translations)
6. [Docker Compose dev workflow](#6-docker-compose-dev-workflow)
7. [Submitting a pull request](#7-submitting-a-pull-request)

---

## 1. Local development setup

**Prerequisites:** Python 3.10+, Redis (for queue tests, `fakeredis` is used so no real Redis needed for unit tests).

```bash
git clone https://github.com/<your-fork>/Visio-Display.git
cd Visio-Display/web

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes everything in `requirements.txt` plus `pytest`, `pytest-flask`, and `fakeredis`.

---

## 2. Running the tests

```bash
cd web
pytest -v
```

The test suite runs **in-memory SQLite** and **fakeredis** — no real database, no real Redis, no ffmpeg needed. All 57 tests complete in ~2 seconds.

```
tests/test_config_svc.py    — app config read/write (5 tests)
tests/test_users_svc.py     — user CRUD + permissions (16 tests)
tests/test_queue_svc.py     — encoding queue + time window (18 tests)
tests/test_queue_rq.py      — RQ task enqueueing (9 tests)
```

Test configuration lives in `web/pyproject.toml` (`[tool.pytest.ini_options]`).

---

## 3. Linting

We use [ruff](https://docs.astral.sh/ruff/) for linting.

```bash
pip install ruff          # already included in requirements-dev.txt
ruff check .
```

Rules are configured in `web/pyproject.toml`:
- `line-length = 120`
- `E701` ignored — the `if guard: return guard` one-liner is intentional in blueprints
- `E501` ignored in `translations.py` and `services/ephemeris_svc.py` (long strings / aligned draw calls)

The CI pipeline (`ci.yml`) runs both `ruff check` and `pytest` on every push and pull request.

---

## 4. Architecture overview

### Request flow

```
Browser → Blueprint (web/blueprints/*.py)
              └─ calls → Service (web/services/*.py)
                              └─ reads/writes → SQLAlchemy models (web/db.py)
```

### Blueprints

Each blueprint owns one area of the UI/API. Guards are applied at the top of each route using helpers from `blueprints/guards.py`:

```python
# pattern used throughout the codebase — intentional one-liner
def my_route():
    g = perm_guard('upload')
    if g: return g
    ...
```

| Blueprint | Routes |
|---|---|
| `admin.py` | `/admin` — dashboard |
| `api.py` | `/api/*` — public JSON API |
| `auth.py` | `/login`, `/logout` |
| `ephemeris.py` | `/regen_ephemeride`, `/admin/events/*` |
| `media.py` | `/upload`, `/delete`, `/toggle`, `/reorder`, `/compress`, `/schedule`, `/screen_assign`, `/set_duration` |
| `queue.py` | `/admin/queue`, `/queue/cancel`, `/admin/queue/force`, `/admin/compress/*/force` |
| `screens.py` | `/admin/screens/*` |
| `settings.py` | `/admin/settings/*`, `/admin/logo/*` |
| `users.py` | `/admin/users/*` |

### Services

Services contain all business logic — blueprints should not query the database directly.

| Service | Responsibility |
|---|---|
| `config_svc.py` | Read/write the global app config (media order, durations, schedules, events, screens) |
| `users_svc.py` | User CRUD, session helpers (`is_admin`, `is_superadmin`, `has_permission`, `has_screen_access`) |
| `queue_svc.py` | Encoding queue persistence, RQ task functions (`_rq_upload_encode`, `_rq_compress_job`), overnight scheduler |
| `media_svc.py` | File listing, metadata, disk usage |
| `ephemeris_svc.py` | Daily ephemeris image generation (weather, sun times, saint of the day, events) |

### Database models (`web/db.py`)

| Model | Description |
|---|---|
| `AppConfig` | Single row (id=1) — full app config stored as a JSON blob |
| `User` | One row per user — username (PK), bcrypt password, superadmin flag, permissions (JSON), screens (JSON) |
| `EncodeJob` | One row per encoding job — tracks status, progress, before/after file sizes |

### Background workers

Two RQ queues run in the `worker` container:

| Queue | Purpose |
|---|---|
| `ramses:upload` | Re-encode videos on upload to H.264/MP4 |
| `ramses:compress` | Overnight compression (22:00–06:00 window) — aggressive CRF to shrink file size |

A scheduler thread in the `app` container enqueues pending jobs when the time window opens (Redis NX lock prevents double-scheduling).

---

## 5. Adding or editing translations

All UI strings live in `web/translations.py` as a nested dict:

```python
TRANSLATIONS = {
    'fr': { 'key': 'Valeur en français', ... },
    'en': { 'key': 'English value', ... },
}
```

To add a new string:

1. Add the key to **both** `'fr'` and `'en'` dictionaries.
2. Use `_t('your_key', lang)` in a service or `{{ t('your_key') }}` in a template (the `t` helper is injected via `app.jinja_env.globals`).
3. Run the tests — they don't cover translations directly, but a missing key will surface as a `KeyError` in the relevant test if a service uses it.

---

## 6. Docker Compose dev workflow

For a full-stack test with Redis and the RQ worker:

```bash
cp .env.example .env
# Edit .env — set ADMIN_USER, ADMIN_PASSWORD, SECRET_KEY

docker compose up --build
```

The `app` service (Gunicorn, 4 workers) is exposed on port **801**.  
The `worker` service listens on both RQ queues.  
Redis data is persisted in the `redis_data` named volume.

**Volume note:** the `docker-compose.yml` mounts `/srv/7To/Docker/visio/data` by default (the original production path). Change this to a local path for development:

```yaml
volumes:
  - ./data:/app/static/data     # local dev override
```

---

## 7. Submitting a pull request

1. **Fork** the repository and create a feature branch from `main`.
2. Make your changes — keep commits focused and descriptive.
3. Run `ruff check .` and `pytest -v` — both must pass cleanly.
4. Open a PR against `main`. Describe what the change does and why.

The CI pipeline will run automatically on your PR. A green check is required before merging.

For bug reports or feature requests, please open a GitHub issue first.

---

MIT License — Copyright (c) 2026 Woofix
