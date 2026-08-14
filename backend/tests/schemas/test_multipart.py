"""Tests for multipart upload schema helpers."""

from math import ceil

from app.schemas.providers.apple.apple_xml import (
    DEFAULT_PART_SIZE,
    MAX_PART_SIZE,
    MAX_PARTS,
    MIN_PART_SIZE,
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
