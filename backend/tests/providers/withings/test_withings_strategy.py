"""Withings strategy wiring and lifecycle hook."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.schemas.auth import LiveSyncMode
from app.services.providers.withings.strategy import WithingsStrategy


def test_capabilities_declare_pull_with_per_user_webhook_subscriptions() -> None:
    caps = WithingsStrategy().capabilities

    assert caps.rest_pull is True
    assert caps.webhook_ping is True
    assert caps.webhook_registration_api is True
    assert caps.webhook_subscription_per_user is True


def test_webhook_components_are_wired_and_the_mode_is_admin_configurable() -> None:
    strategy = WithingsStrategy()

    assert strategy.webhooks is not None
    assert strategy.webhook_service is not None
    assert strategy.live_sync_configurable is True


@patch("app.services.providers.withings.strategy.celery_app.send_task")
def test_on_connect_enqueues_registration_only_in_webhook_mode(mock_send: MagicMock) -> None:
    strategy = WithingsStrategy()
    user_id = uuid4()

    with patch.object(strategy, "effective_live_sync_mode", return_value=LiveSyncMode.PULL):
        strategy.on_connect(MagicMock(), user_id)
    mock_send.assert_not_called()

    with patch.object(strategy, "effective_live_sync_mode", return_value=LiveSyncMode.WEBHOOK):
        strategy.on_connect(MagicMock(), user_id)

    assert mock_send.call_args.kwargs["args"] == ["withings", str(user_id)]
    assert mock_send.call_args.kwargs["queue"] == "webhook_sync"
