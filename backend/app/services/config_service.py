import time
from datetime import timedelta
from typing import Any

from app.config import settings
from app.database import SessionLocal
from app.integrations.redis_client import get_redis_client
from app.models import AppSetting
from app.repositories.app_settings_repository import AppSettingRepository
from app.schemas.app_config import AppConfig, AppConfigUpdate
from app.utils.config_utils import format_duration

# Columns that ConfigService manages (everything on app_settings except the bookkeeping ones).
MANAGED_KEYS: tuple[str, ...] = tuple(
    c.name for c in AppSetting.__table__.columns if c.name not in ("id", "created_at")
)

# access_log_level is derived from ENVIRONMENT at runtime, not a real env customization —
# leave it NULL so the fallback (settings.access_log_level) keeps deriving it.
_BACKFILL_SKIP = frozenset({"access_log_level"})

_REDIS_KEY = "config"
_MICRO_TTL_SECONDS = 5.0


def _to_column(value: Any) -> Any:
    # DB stores pull_sync_lookback as a compact duration string; everything else stores as-is.
    if isinstance(value, timedelta):
        return format_duration(value)
    return value


class ConfigService:
    """Effective config resolved as DB-value-else-config.py-default, cached in Redis + RAM.

    Reads hit process RAM (nanoseconds). At most once per _MICRO_TTL a process checks the
    shared Redis `version`; when it changed, the process reloads the snapshot. Writes bump
    the version so every process picks the change up without a restart.
    """

    def __init__(self) -> None:
        self._repo = AppSettingRepository()
        self._cache: AppConfig | None = None
        self._seen_version: int = -1
        self._checked_at: float = 0.0

    def get(self) -> AppConfig:
        now = time.monotonic()
        if self._cache is not None and now - self._checked_at < _MICRO_TTL_SECONDS:
            return self._cache

        snapshot = get_redis_client().hgetall(_REDIS_KEY)
        if snapshot.get("data") is None or snapshot.get("version") is None:
            snapshot = self._seed_cold()

        version = int(snapshot["version"])
        if self._cache is not None and version == self._seen_version:
            self._checked_at = now
            return self._cache

        self._cache = AppConfig.model_validate_json(snapshot["data"])
        self._seen_version = version
        self._checked_at = now
        return self._cache

    def update(self, update: AppConfigUpdate) -> AppConfig:
        fields = update.model_dump(exclude_unset=True)
        if fields:
            with SessionLocal() as db:
                row = self._repo.get(db)
                for key, value in fields.items():
                    setattr(row, key, value)
                self._repo.update(db, row)

        config = self._reload_from_db()
        # Publish data + version atomically so no reader ever pairs new data with the old version.
        pipe = get_redis_client().pipeline()
        pipe.hset(_REDIS_KEY, "data", config.model_dump_json())
        pipe.hincrby(_REDIS_KEY, "version", 1)
        version = pipe.execute()[1]

        self._cache = config
        self._seen_version = version
        self._checked_at = time.monotonic()
        return config

    def _seed_cold(self) -> dict:
        """Seed a cold/flushed Redis from the DB source of truth without clobbering a concurrent
        writer, then return a fresh snapshot so data and version come from the same state."""
        seed = self._reload_from_db().model_dump_json()
        pipe = get_redis_client().pipeline()
        pipe.hsetnx(_REDIS_KEY, "data", seed)
        pipe.hsetnx(_REDIS_KEY, "version", 0)
        pipe.execute()
        return get_redis_client().hgetall(_REDIS_KEY)

    def backfill_from_env(self) -> None:
        """One-time copy of customized .env values into NULL columns (idempotent).

        Only fills columns that are still NULL and whose env value differs from the
        config.py default, so untouched settings keep tracking the code default and
        admin-set values are never overwritten.
        """
        settings_fields = type(settings).model_fields
        with SessionLocal() as db:
            row = self._repo.get(db)
            changed = False
            for key in MANAGED_KEYS:
                if key in _BACKFILL_SKIP or getattr(row, key) is not None:
                    continue
                if key not in settings_fields:  # e.g. archive/delete_after_days have no env source
                    continue
                value = getattr(settings, key)
                if value == settings_fields[key].default:
                    continue
                setattr(row, key, _to_column(value))
                changed = True
            if changed:
                db.commit()

    def _reload_from_db(self) -> AppConfig:
        with SessionLocal() as db:
            row = self._repo.get(db)
        effective = {
            key: (getattr(row, key) if getattr(row, key) is not None else getattr(settings, key, None))
            for key in MANAGED_KEYS
        }
        return AppConfig.model_validate(effective)


config_service = ConfigService()


def get_config() -> AppConfig:
    """Effective app config (cached). Use in place of reading these values off `settings`."""
    return config_service.get()
