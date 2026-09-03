"""Unit tests for the SDK ingestion window (``settings.sdk_max_historical_days``).

HealthKit hands the SDK a user's entire archive on first connect. These tests pin the
cap that stops that archive reaching the database, and - just as importantly - pin the
boundary rule, which is the part a well-meaning "simplification" would get wrong.
"""

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DataPointSeries
from app.schemas.providers.mobile_sdk import SyncRequest as SDKSyncRequest
from app.services.apple.healthkit.import_service import ImportService, _apply_historical_cutoff
from tests.factories import UserFactory

NOW = datetime.now(timezone.utc)


def _request(records: Sequence[dict] = (), sleep: Sequence[dict] = (), workouts: Sequence[dict] = ()) -> SDKSyncRequest:
    return SDKSyncRequest.model_validate(
        {
            "provider": "apple",
            "sdkVersion": "1.0.0",
            "syncTimestamp": NOW.isoformat(),
            "data": {"records": list(records), "sleep": list(sleep), "workouts": list(workouts)},
        }
    )


def _record(days_ago: float, duration_minutes: int = 1) -> dict:
    end = NOW - timedelta(days=days_ago)
    return {
        "type": "HEART_RATE",
        "startDate": (end - timedelta(minutes=duration_minutes)).isoformat(),
        "endDate": end.isoformat(),
        "value": 60,
        "unit": "count/min",
    }


def _sleep(days_ago: float) -> dict:
    end = NOW - timedelta(days=days_ago)
    return {
        "stage": "light",
        "startDate": (end - timedelta(hours=1)).isoformat(),
        "endDate": end.isoformat(),
    }


def _workout(days_ago: float) -> dict:
    end = NOW - timedelta(days=days_ago)
    return {
        "type": "RUNNING",
        "startDate": (end - timedelta(minutes=30)).isoformat(),
        "endDate": end.isoformat(),
    }


class TestIngestionWindow:
    def test_no_cap_configured_keeps_everything(self) -> None:
        """None is the default and must preserve the previous unbounded behaviour."""
        request = _request(records=[_record(3650)], sleep=[_sleep(3650)], workouts=[_workout(3650)])

        assert _apply_historical_cutoff(request, None) == {}
        assert len(request.data.records) == 1
        assert len(request.data.sleep) == 1
        assert len(request.data.workouts) == 1

    def test_cap_drops_old_items_across_all_three_collections(self) -> None:
        """records, sleep and workouts all flow from `request` - the cap must cover each."""
        request = _request(
            records=[_record(400), _record(2)],
            sleep=[_sleep(400), _sleep(2)],
            workouts=[_workout(400), _workout(2)],
        )

        dropped = _apply_historical_cutoff(request, 90)

        assert dropped == {"records": 1, "sleep": 1, "workouts": 1}
        assert len(request.data.records) == 1
        assert len(request.data.sleep) == 1
        assert len(request.data.workouts) == 1

    def test_recent_items_are_untouched(self) -> None:
        request = _request(records=[_record(1), _record(30), _record(89)])

        assert _apply_historical_cutoff(request, 90) == {}
        assert len(request.data.records) == 3

    def test_boundary_uses_end_date_not_start_date(self) -> None:
        """A session that STARTED outside the window but ENDED inside it is real, recent data.

        Keying on startDate would silently delete it. The two directions are not
        symmetric: keeping a slightly-old item costs one row, dropping a genuine one
        loses it for good.
        """
        # starts 91 days ago, ends 89 days ago -> inside a 90-day window by endDate only
        end = NOW - timedelta(days=89)
        spanning = {
            "type": "HEART_RATE",
            "startDate": (NOW - timedelta(days=91)).isoformat(),
            "endDate": end.isoformat(),
            "value": 60,
            "unit": "count/min",
        }
        request = _request(records=[spanning])

        assert _apply_historical_cutoff(request, 90) == {}
        assert len(request.data.records) == 1

    def test_naive_datetimes_do_not_raise(self) -> None:
        """A payload without an offset must not blow up the comparison."""
        naive_old = {
            "type": "HEART_RATE",
            "startDate": "2019-01-01T00:00:00",
            "endDate": "2019-01-01T00:01:00",
            "value": 60,
            "unit": "count/min",
        }
        naive_recent_end = (NOW - timedelta(days=1)).replace(tzinfo=None).isoformat()
        naive_recent = {
            "type": "HEART_RATE",
            "startDate": naive_recent_end,
            "endDate": naive_recent_end,
            "value": 60,
            "unit": "count/min",
        }
        request = _request(records=[naive_old, naive_recent])

        assert _apply_historical_cutoff(request, 90) == {"records": 1}
        assert len(request.data.records) == 1

    def test_empty_collections_report_nothing(self) -> None:
        request = _request()

        assert _apply_historical_cutoff(request, 90) == {}


class TestSettingDefault:
    def test_default_is_none_so_upstream_behaviour_is_unchanged(self) -> None:
        from app.config import settings

        assert settings.sdk_max_historical_days is None or isinstance(settings.sdk_max_historical_days, int)


@pytest.mark.parametrize("max_days", [1, 30, 90, 365])
def test_cutoff_is_exactly_max_days_wide(max_days: int) -> None:
    """Just inside is kept, just outside is dropped, for every configured width."""
    request = _request(records=[_record(max_days - 0.5), _record(max_days + 0.5)])

    assert _apply_historical_cutoff(request, max_days) == {"records": 1}
    assert len(request.data.records) == 1


class TestLoadDataAppliesTheWindow:
    """The helper being correct is not enough - `load_data` has to actually call it.

    These tests go through the real import path and assert on the database, so removing
    the cutoff call from `load_data` fails here even though the unit tests above still pass.
    """

    @pytest.fixture
    def import_service(self) -> ImportService:
        return ImportService(log=logging.getLogger("test"))

    def _payload(self) -> dict:
        return {
            "provider": "apple",
            "sdkVersion": "1.0.0",
            "syncTimestamp": NOW.isoformat(),
            "data": {"records": [_record(400), _record(2)], "sleep": [], "workouts": []},
        }

    def test_old_records_never_reach_the_database(self, db: Session, import_service: ImportService) -> None:
        user = UserFactory()

        with patch.object(settings, "sdk_max_historical_days", 90):
            result = import_service.load_data(db, self._payload(), str(user.id))

        assert result["outside_window"] == {"records": 1}
        assert result["records_inserted"] == 1
        assert db.query(DataPointSeries).count() == 1

    def test_without_a_cap_both_records_are_written(self, db: Session, import_service: ImportService) -> None:
        """The opposite direction: proves the assertion above is caused by the cap."""
        user = UserFactory()

        with patch.object(settings, "sdk_max_historical_days", None):
            result = import_service.load_data(db, self._payload(), str(user.id))

        assert result["outside_window"] == {}
        assert result["records_inserted"] == 2
        assert db.query(DataPointSeries).count() == 2
