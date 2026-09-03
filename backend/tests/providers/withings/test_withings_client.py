"""Withings RPC envelope, pagination and callback-URL policy."""

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.providers.withings import WithingsMeasure
from app.services.providers.withings import _client, callback


def _request(**overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "db": MagicMock(),
        "user_id": uuid4(),
        "connection_repo": MagicMock(),
        "oauth": MagicMock(),
        "service_path": "/measure",
        "action": "getmeas",
        "params": {},
    }
    kwargs.update(overrides)
    return kwargs


def test_scale_measure_applies_power_of_ten() -> None:
    assert _client.scale_measure(WithingsMeasure(value=7500, type=1, unit=-2)) == Decimal("75.00")
    assert _client.scale_measure(WithingsMeasure(value=65, type=11, unit=0)) == Decimal("65")


@patch("app.services.providers.withings._client.make_authenticated_request")
def test_request_posts_form_data_and_unwraps_body(mock_req: MagicMock) -> None:
    mock_req.return_value = {"status": 0, "body": {"measuregrps": [1, 2]}}

    body = _client.withings_request(**_request(params={"meastypes": "1"}))

    assert body == {"measuregrps": [1, 2]}
    kwargs = mock_req.call_args.kwargs
    assert kwargs["method"] == "POST"
    assert kwargs["form_data"] == {"action": "getmeas", "meastypes": "1"}


@pytest.mark.parametrize(
    ("withings_status", "http_status"),
    [(100, 401), (601, 429), (503, 502)],
)
@patch("app.services.providers.withings._client.make_authenticated_request")
def test_nonzero_status_is_an_error_even_on_http_200(
    mock_req: MagicMock, withings_status: int, http_status: int
) -> None:
    mock_req.return_value = {"status": withings_status, "body": {}}

    with pytest.raises(_client.WithingsAPIError) as exc_info:
        _client.withings_request(**_request())

    assert exc_info.value.withings_status == withings_status
    assert exc_info.value.status_code == http_status


@patch("app.services.providers.withings._client.make_authenticated_request")
def test_paginate_follows_more_and_keeps_first_page_envelope(mock_req: MagicMock) -> None:
    mock_req.side_effect = [
        {"status": 0, "body": {"timezone": "Europe/Paris", "measuregrps": [1], "more": 1, "offset": 1}},
        {"status": 0, "body": {"measuregrps": [2]}},
    ]

    result = _client.paginate(**_request(list_key="measuregrps"))

    assert result.rows == [1, 2]
    assert result.envelope["timezone"] == "Europe/Paris"
    assert mock_req.call_args_list[1].kwargs["form_data"]["offset"] == 1


@patch("app.services.providers.withings._client.make_authenticated_request")
def test_paginate_rejects_non_advancing_offset(mock_req: MagicMock) -> None:
    mock_req.return_value = {"status": 0, "body": {"measuregrps": [1], "more": 1, "offset": 0}}

    with pytest.raises(_client.WithingsPaginationError):
        _client.paginate(**_request(list_key="measuregrps"))


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/api/v1/providers/withings/webhooks",
        "https://localhost/api/v1/providers/withings/webhooks",
        "https://203.0.113.4/api/v1/providers/withings/webhooks",
        "https://example.com.:8443/api/v1/providers/withings/webhooks",
    ],
)
def test_callback_url_must_be_a_public_https_endpoint(url: str) -> None:
    with pytest.raises(callback.WithingsCallbackUrlInvalidError):
        callback._validate_callback_url(url)


def test_callback_identity_is_exact_but_ownership_ignores_a_rotated_token() -> None:
    base = "https://example.com/api/v1/providers/withings/webhooks"
    assert callback.callback_urls_match(f"{base}?token=a&x=1", f"{base}?x=1&token=a")
    assert not callback.callback_urls_match(f"{base}?token=a", f"{base}?token=b")
    assert callback.callback_endpoints_match(f"{base}?token=old", f"{base}?token=new")
    assert not callback.callback_endpoints_match("https://other.example/webhooks?token=a", f"{base}?token=a")


def test_redact_callback_url_drops_the_token() -> None:
    redacted = callback.redact_callback_url("https://example.com/webhooks?token=secret")
    assert "secret" not in redacted
