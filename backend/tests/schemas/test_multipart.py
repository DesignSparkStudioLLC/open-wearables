"""Tests for multipart upload schema helpers."""

from math import ceil

import pytest
from pydantic import ValidationError

from app.schemas.providers.apple.apple_xml import (
    DEFAULT_PART_SIZE,
    MAX_PART_SIZE,
    MAX_PARTS,
    MIN_PART_SIZE,
    MultipartSignRequest,
    recommended_part_size,
)


class TestRecommendedPartSize:
    def test_small_file_uses_default_part_size(self) -> None:
        assert recommended_part_size(50 * 1024 * 1024) == DEFAULT_PART_SIZE

    def test_file_at_default_capacity_stays_default(self) -> None:
        # DEFAULT_PART_SIZE * MAX_PARTS is the largest file the default handles
        capacity = DEFAULT_PART_SIZE * MAX_PARTS
        assert recommended_part_size(capacity) == DEFAULT_PART_SIZE

    def test_large_file_grows_part_size_within_part_limit(self) -> None:
        # 3 TiB would need > 10,000 parts at the default size
        file_size = 3 * 1024 * 1024 * 1024 * 1024
        part_size = recommended_part_size(file_size)

        assert part_size > DEFAULT_PART_SIZE
        assert ceil(file_size / part_size) <= MAX_PARTS
        # part size is aligned to a whole number of MiB
        assert part_size % (1024 * 1024) == 0

    def test_part_size_never_below_minimum(self) -> None:
        assert recommended_part_size(1) >= MIN_PART_SIZE

    def test_part_size_never_above_maximum(self) -> None:
        # 5 TiB, the max object size
        assert recommended_part_size(5 * 1024 * 1024 * 1024 * 1024) <= MAX_PART_SIZE


class TestMultipartSignRequest:
    def test_accepts_valid_part_numbers(self) -> None:
        req = MultipartSignRequest(key="u/raw/x.xml", upload_id="up", part_numbers=[1, 2, MAX_PARTS])
        assert req.part_numbers == [1, 2, MAX_PARTS]

    @pytest.mark.parametrize("part_number", [0, -1, MAX_PARTS + 1])
    def test_rejects_out_of_range_part_numbers(self, part_number: int) -> None:
        with pytest.raises(ValidationError):
            MultipartSignRequest(key="u/raw/x.xml", upload_id="up", part_numbers=[part_number])

    def test_rejects_empty_part_numbers(self) -> None:
        with pytest.raises(ValidationError):
            MultipartSignRequest(key="u/raw/x.xml", upload_id="up", part_numbers=[])
