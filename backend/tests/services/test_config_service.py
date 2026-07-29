from app.schemas.app_config import RESTART_REQUIRED_KEYS, AppConfig
from app.services.config_service import MANAGED_KEYS


def test_app_config_fields_match_managed_keys() -> None:
    """AppConfig must expose exactly the app_settings columns ConfigService manages.

    Guards against drift: adding a column to AppSetting (and MANAGED_KEYS) without a matching
    AppConfig field — or vice versa — breaks resolution/serialization, so fail loudly here.
    """
    assert set(AppConfig.model_fields) == set(MANAGED_KEYS)


def test_restart_required_keys_are_managed() -> None:
    """Every restart-required marker must sit on a real managed setting."""
    assert set(RESTART_REQUIRED_KEYS) <= set(MANAGED_KEYS)
