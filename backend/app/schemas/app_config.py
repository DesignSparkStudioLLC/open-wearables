from datetime import timedelta

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from app.schemas.enums import DataGranularity
from app.utils.config_utils import AccessLogLevel, format_duration, parse_duration


class AppConfig(BaseModel):
    """Effective runtime config: the DB value where set, otherwise the config.py default.

    Field set mirrors the app_settings columns (minus id/created_at). Built by
    ConfigService and cached in Redis (JSON snapshot) + process RAM.
    """

    model_config = ConfigDict(extra="ignore")

    # Sync behaviour
    pull_sync_lookback: timedelta | None
    historical_sync_on_connect: bool
    ingest_workout_samples: bool
    default_data_granularity: DataGranularity
    score_backfill_days: int

    # Raw payload storage
    raw_payload_storage: str
    raw_payload_max_size_bytes: int
    store_fit_files: bool

    # Sleep session tracking
    sleep_end_gap_minutes: int

    # API
    paging_limit: int

    # Email / invitations
    email_from_address: str | None
    email_from_name: str
    invitation_expire_days: int
    email_max_retries: int
    user_invitation_code_expire_days: int

    # Periodic task intervals (require a restart to take effect)
    sync_interval_seconds: int
    sleep_sync_interval_seconds: int
    sleep_score_interval_seconds: int
    resilience_score_interval_seconds: int

    # Outgoing webhooks + access log (require a restart to take effect)
    outgoing_webhooks_enabled: bool
    access_log_level: AccessLogLevel
    log_error_response_body: bool
    log_error_response_body_max_bytes: int
    log_error_response_body_max_per_minute: int

    # Data lifecycle
    archive_after_days: int | None
    delete_after_days: int | None

    @field_validator("pull_sync_lookback", mode="before")
    @classmethod
    def _parse_lookback(cls, v: object) -> object:
        # DB / Redis store the compact form ("2d"); config.py already gives a timedelta.
        return parse_duration(v) if isinstance(v, str) else v

    @field_serializer("pull_sync_lookback")
    def _dump_lookback(self, v: timedelta | None) -> str | None:
        return format_duration(v) if v is not None else None


class AppConfigUpdate(BaseModel):
    """Partial update from the frontend. Only set fields are persisted (exclude_unset)."""

    model_config = ConfigDict(extra="forbid")

    pull_sync_lookback: str | None = None
    historical_sync_on_connect: bool | None = None
    ingest_workout_samples: bool | None = None
    default_data_granularity: DataGranularity | None = None
    score_backfill_days: int | None = None

    raw_payload_storage: str | None = None
    raw_payload_max_size_bytes: int | None = None
    store_fit_files: bool | None = None

    sleep_end_gap_minutes: int | None = None
    paging_limit: int | None = None

    email_from_address: str | None = None
    email_from_name: str | None = None
    invitation_expire_days: int | None = None
    email_max_retries: int | None = None
    user_invitation_code_expire_days: int | None = None

    sync_interval_seconds: int | None = None
    sleep_sync_interval_seconds: int | None = None
    sleep_score_interval_seconds: int | None = None
    resilience_score_interval_seconds: int | None = None

    outgoing_webhooks_enabled: bool | None = None
    access_log_level: AccessLogLevel | None = None
    log_error_response_body: bool | None = None
    log_error_response_body_max_bytes: int | None = None
    log_error_response_body_max_per_minute: int | None = None

    archive_after_days: int | None = None
    delete_after_days: int | None = None

    @field_validator("pull_sync_lookback")
    @classmethod
    def _validate_lookback(cls, v: str | None) -> str | None:
        if v is not None:
            parse_duration(v)  # raises ValueError on a bad format -> 422
        return v
