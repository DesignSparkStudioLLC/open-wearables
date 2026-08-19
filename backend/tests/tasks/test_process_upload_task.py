"""
Tests for process_aws_upload Celery task.

Tests XML file processing from S3 for Apple Health data imports.
"""

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.integrations.celery.tasks.process_aws_upload_task import (
    _import_xml_data,
    complete_and_process_aws_upload,
    process_aws_upload,
)
from app.schemas.providers.apple.apple_xml import CompletedPart
from tests.factories import UserFactory


class TestProcessUploadTask:
    """Test suite for process_aws_upload task."""

    @patch("app.integrations.celery.tasks.process_aws_upload_task.SessionLocal")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.get_s3_client")
    @patch("app.integrations.celery.tasks.process_aws_upload_task._import_xml_data")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.user_service")
    def test_process_aws_upload_success(
        self,
        mock_user_service: MagicMock,
        mock_import_xml_data: MagicMock,
        mock_get_s3_client: MagicMock,
        mock_session_local: MagicMock,
        db: Session,
        mock_celery_app: MagicMock,
    ) -> None:
        """Test successful processing of uploaded XML file."""
        # Arrange
        user = UserFactory()
        bucket_name = "test-bucket"
        object_key = f"uploads/{user.id}/apple-health/export.xml"

        mock_s3 = MagicMock()
        mock_get_s3_client.return_value = mock_s3

        mock_session_local.return_value.__enter__ = MagicMock(return_value=db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=None)
        mock_user_service.get.return_value = user

        body = BytesIO(b"<HealthData></HealthData>")
        mock_s3.get_object.return_value = {"Body": body}

        # Act
        result = process_aws_upload(bucket_name, object_key, str(user.id))

        # Assert
        assert result["status"] == "success"
        assert result["bucket"] == bucket_name
        assert result["input_key"] == object_key
        assert result["user_id"] == str(user.id)
        assert result["message"] == "Import completed successfully"

        mock_s3.get_object.assert_called_once_with(Bucket=bucket_name, Key=object_key)
        assert body.closed

        # Verify import was called
        mock_import_xml_data.assert_called_once()
        assert mock_import_xml_data.call_args.args[1] is body

    @patch("app.integrations.celery.tasks.process_aws_upload_task.SessionLocal")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.get_s3_client")
    @patch("app.integrations.celery.tasks.process_aws_upload_task._import_xml_data")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.user_service")
    def test_process_aws_upload_closes_object_stream(
        self,
        mock_user_service: MagicMock,
        mock_import_xml_data: MagicMock,
        mock_get_s3_client: MagicMock,
        mock_session_local: MagicMock,
        db: Session,
        mock_celery_app: MagicMock,
    ) -> None:
        """Test that the S3 response stream is closed after processing."""
        # Arrange
        user = UserFactory()
        bucket_name = "test-bucket"
        object_key = f"uploads/{user.id}/apple-health/export.xml"

        mock_s3 = MagicMock()
        mock_get_s3_client.return_value = mock_s3

        mock_session_local.return_value.__enter__ = MagicMock(return_value=db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=None)
        mock_user_service.get.return_value = user

        body = BytesIO(b"<HealthData></HealthData>")
        mock_s3.get_object.return_value = {"Body": body}

        # Act
        process_aws_upload(bucket_name, object_key, str(user.id))

        assert body.closed

    @patch("app.integrations.celery.tasks.process_aws_upload_task.SessionLocal")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.get_s3_client")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.user_service")
    def test_process_aws_upload_s3_download_error(
        self,
        mock_user_service: MagicMock,
        mock_get_s3_client: MagicMock,
        mock_session_local: MagicMock,
        db: Session,
        mock_celery_app: MagicMock,
    ) -> None:
        """Test handling of S3 download errors."""
        # Arrange
        user = UserFactory()
        bucket_name = "test-bucket"
        object_key = f"uploads/{user.id}/apple-health/export.xml"

        mock_s3 = MagicMock()
        mock_get_s3_client.return_value = mock_s3

        mock_session_local.return_value.__enter__ = MagicMock(return_value=db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=None)
        mock_user_service.get.return_value = user

        mock_s3.get_object.side_effect = Exception("S3 connection failed")

        # Act & Assert
        with pytest.raises(Exception, match="S3 connection failed"):
            process_aws_upload(bucket_name, object_key, str(user.id))

    @patch("app.integrations.celery.tasks.process_aws_upload_task.SessionLocal")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.get_s3_client")
    @patch("app.integrations.celery.tasks.process_aws_upload_task._import_xml_data")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.user_service")
    def test_process_aws_upload_import_error_rolls_back(
        self,
        mock_user_service: MagicMock,
        mock_import_xml_data: MagicMock,
        mock_get_s3_client: MagicMock,
        mock_session_local: MagicMock,
        db: Session,
        mock_celery_app: MagicMock,
    ) -> None:
        """Test that database transaction is rolled back on import error."""
        # Arrange
        user = UserFactory()
        bucket_name = "test-bucket"
        object_key = f"uploads/{user.id}/apple-health/export.xml"

        mock_s3 = MagicMock()
        mock_get_s3_client.return_value = mock_s3

        mock_db = MagicMock(spec=Session)
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=None)
        mock_user_service.get.return_value = user

        body = BytesIO(b"<HealthData></HealthData>")
        mock_s3.get_object.return_value = {"Body": body}

        # Mock import to fail
        mock_import_xml_data.side_effect = Exception("XML parsing error")

        # Act & Assert
        with pytest.raises(Exception, match="XML parsing error"):
            process_aws_upload(bucket_name, object_key, str(user.id))

        # Verify rollback was called
        mock_db.rollback.assert_called_once()
        assert body.closed

    @patch("app.integrations.celery.tasks.process_aws_upload_task.SessionLocal")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.get_s3_client")
    @patch("app.integrations.celery.tasks.process_aws_upload_task._import_xml_data")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.user_service")
    def test_process_aws_upload_extracts_user_id_from_key(
        self,
        mock_user_service: MagicMock,
        mock_import_xml_data: MagicMock,
        mock_get_s3_client: MagicMock,
        mock_session_local: MagicMock,
        db: Session,
        mock_celery_app: MagicMock,
    ) -> None:
        """Test that user ID is correctly extracted from object key."""
        # Arrange
        user_id = "550e8400-e29b-41d4-a716-446655440000"
        bucket_name = "test-bucket"
        object_key = f"uploads/{user_id}/apple-health/export.xml"

        mock_s3 = MagicMock()
        mock_get_s3_client.return_value = mock_s3

        mock_session_local.return_value.__enter__ = MagicMock(return_value=db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=None)
        mock_user_service.get.return_value = MagicMock()

        mock_s3.get_object.return_value = {"Body": BytesIO(b"<HealthData></HealthData>")}

        # Act
        result = process_aws_upload(bucket_name, object_key, user_id)

        # Assert
        assert result["user_id"] == user_id

    @patch("app.integrations.celery.tasks.process_aws_upload_task._process_aws_upload")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.multipart_upload_service")
    def test_complete_and_process_owns_both_operations(
        self,
        mock_multipart_service: MagicMock,
        mock_process: MagicMock,
        mock_celery_app: MagicMock,
    ) -> None:
        key = "user-123/raw/export.xml"
        mock_process.return_value = {"status": "success"}

        result = complete_and_process_aws_upload(
            bucket_name="test-bucket",
            object_key=key,
            upload_id="upload-1",
            parts=[{"part_number": 1, "etag": "etag-1"}],
            user_id="user-123",
        )

        assert result == {"status": "success"}
        mock_multipart_service.complete_upload.assert_called_once_with(
            user_id="user-123",
            key=key,
            upload_id="upload-1",
            parts=[CompletedPart(part_number=1, etag="etag-1")],
            bucket_name="test-bucket",
        )
        mock_process.assert_called_once_with("test-bucket", key, "user-123")


class TestImportXmlData:
    """Test suite for _import_xml_data helper function."""

    @patch("app.integrations.celery.tasks.process_aws_upload_task.XMLService")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.event_record_service")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.timeseries_service")
    def test_import_xml_data_creates_records(
        self,
        mock_timeseries_service: MagicMock,
        mock_event_record_service: MagicMock,
        mock_xml_service_class: MagicMock,
        db: Session,
    ) -> None:
        """Test that XML data is properly imported into database."""
        # Arrange
        user = UserFactory()
        xml_path = "/tmp/test.xml"

        # Mock XMLService to yield test data (time_series_records, workouts)
        mock_record = MagicMock()
        mock_detail = MagicMock()
        mock_time_series_records = [MagicMock(), MagicMock()]
        mock_created_record = MagicMock()
        mock_event_record_service.create.return_value = mock_created_record

        mock_xml_service = MagicMock()
        mock_xml_service.parse_xml.return_value = [
            (mock_time_series_records, [(mock_record, mock_detail)], None),
        ]
        mock_xml_service_class.return_value = mock_xml_service

        # Act
        _import_xml_data(db, xml_path, str(user.id))

        # Assert
        mock_event_record_service.create.assert_called_once_with(db, mock_record)
        mock_event_record_service.create_detail.assert_called_once()
        mock_timeseries_service.bulk_create_samples.assert_called_once_with(db, mock_time_series_records)

    @patch("app.integrations.celery.tasks.process_aws_upload_task.XMLService")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.event_record_service")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.timeseries_service")
    def test_import_xml_data_handles_multiple_workouts(
        self,
        mock_timeseries_service: MagicMock,
        mock_event_record_service: MagicMock,
        mock_xml_service_class: MagicMock,
        db: Session,
    ) -> None:
        """Test importing XML data with multiple workouts."""
        # Arrange
        user = UserFactory()
        xml_path = "/tmp/test.xml"

        # Mock XMLService to yield multiple workouts (time_series_records, workouts)
        workout1 = (MagicMock(), MagicMock())
        workout2 = (MagicMock(), MagicMock())
        mock_created_record = MagicMock()
        mock_event_record_service.create.return_value = mock_created_record

        mock_xml_service = MagicMock()
        mock_xml_service.parse_xml.return_value = [([], [workout1, workout2], None)]
        mock_xml_service_class.return_value = mock_xml_service

        # Act
        _import_xml_data(db, xml_path, str(user.id))

        # Assert
        assert mock_event_record_service.create.call_count == 2
        assert mock_event_record_service.create_detail.call_count == 2

    @patch("app.integrations.celery.tasks.process_aws_upload_task.XMLService")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.event_record_service")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.timeseries_service")
    def test_import_xml_data_skips_empty_time_series(
        self,
        mock_timeseries_service: MagicMock,
        mock_event_record_service: MagicMock,
        mock_xml_service_class: MagicMock,
        db: Session,
    ) -> None:
        """Test that empty time series data is not imported."""
        # Arrange
        user = UserFactory()
        xml_path = "/tmp/test.xml"

        # Mock XMLService with empty time series (time_series_records, workouts)
        mock_xml_service = MagicMock()
        mock_xml_service.parse_xml.return_value = [
            ([], [], None),  # Empty time series and workouts
        ]
        mock_xml_service_class.return_value = mock_xml_service

        # Act
        _import_xml_data(db, xml_path, str(user.id))

        # Assert
        mock_timeseries_service.bulk_create_samples.assert_not_called()
        mock_event_record_service.create.assert_not_called()

    @patch("app.integrations.celery.tasks.process_aws_upload_task.XMLService")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.event_record_service")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.timeseries_service")
    def test_import_xml_data_with_time_series_only(
        self,
        mock_timeseries_service: MagicMock,
        mock_event_record_service: MagicMock,
        mock_xml_service_class: MagicMock,
        db: Session,
    ) -> None:
        """Test importing only time series data."""
        # Arrange
        user = UserFactory()
        xml_path = "/tmp/test.xml"

        mock_time_series_records = [MagicMock(), MagicMock(), MagicMock()]

        mock_xml_service = MagicMock()
        mock_xml_service.parse_xml.return_value = [
            (mock_time_series_records, [], None),  # Only time series, no workouts
        ]
        mock_xml_service_class.return_value = mock_xml_service

        # Act
        _import_xml_data(db, xml_path, str(user.id))

        # Assert
        mock_timeseries_service.bulk_create_samples.assert_called_once_with(db, mock_time_series_records)

    @patch("app.integrations.celery.tasks.process_aws_upload_task.XMLService")
    @patch("app.integrations.celery.tasks.process_aws_upload_task.event_record_service")
    def test_import_xml_data_xmlservice_receives_correct_params(
        self,
        mock_event_record_service: MagicMock,
        mock_xml_service_class: MagicMock,
        db: Session,
    ) -> None:
        """Test that XMLService is initialized with correct parameters."""
        # Arrange
        user = UserFactory()
        xml_path = "/tmp/test.xml"

        mock_xml_service = MagicMock()
        mock_xml_service.parse_xml.return_value = []
        mock_xml_service_class.return_value = mock_xml_service

        # Act
        _import_xml_data(db, xml_path, str(user.id))

        # Assert
        call_args = mock_xml_service_class.call_args[0]
        assert isinstance(call_args[0], Path)
        assert str(call_args[0]) == xml_path
        # Verify parse_xml was called with user_id
        mock_xml_service.parse_xml.assert_called_once_with(str(user.id))

    @patch("app.integrations.celery.tasks.process_aws_upload_task.XMLService")
    def test_import_xml_data_passes_binary_stream_without_copying(
        self,
        mock_xml_service_class: MagicMock,
        db: Session,
    ) -> None:
        user = UserFactory()
        source = BytesIO(b"<HealthData></HealthData>")
        mock_xml_service_class.return_value.parse_xml.return_value = []

        _import_xml_data(db, source, str(user.id))

        assert mock_xml_service_class.call_args.args[0] is source
