"""Tests for the SDK_MAX_HISTORICAL_DAYS bound.

A negative value is not a harmless typo: it puts the cutoff in the FUTURE, so
``_apply_historical_cutoff`` drops EVERY SDK item instead of none. That is the exact
inverse of the operator's intent and it fails silently, so it has to be rejected at
startup rather than discovered from an empty database.
"""

import pytest
from pydantic import ValidationError

from app.config import Settings


class TestSdkMaxHistoricalDaysBound:
    def test_negative_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(sdk_max_historical_days=-1)

    def test_none_is_valid_and_means_unbounded(self) -> None:
        settings = Settings(sdk_max_historical_days=None)

        assert settings.sdk_max_historical_days is None

    def test_zero_is_valid(self) -> None:
        """Zero is a deliberate 'live data only' choice, not a misconfiguration."""
        settings = Settings(sdk_max_historical_days=0)

        assert settings.sdk_max_historical_days == 0

    def test_a_normal_window_is_accepted(self) -> None:
        settings = Settings(sdk_max_historical_days=90)

        assert settings.sdk_max_historical_days == 90
