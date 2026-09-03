"""Withings strategy wiring and lifecycle hook."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

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


def test_on_disconnect_revokes_the_users_subscriptions() -> None:
    strategy = WithingsStrategy()
    user_id = uuid4()

    with patch.object(strategy.webhook_service, "remove_user") as mock_remove:
        strategy.on_disconnect(MagicMock(), user_id)

    mock_remove.assert_called_once()
    assert mock_remove.call_args.args[1] == user_id
