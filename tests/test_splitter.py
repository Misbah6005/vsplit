"""Tests for vsplit.splitter."""

import pytest

from vsplit.splitter import calculate_chunks


class TestCalculateChunks:
    def test_basic(self):
        chunks = calculate_chunks(100, 20)
        assert chunks == [(0.0, 20.0), (20.0, 40.0), (40.0, 60.0), (60.0, 80.0), (80.0, 100.0)]

    def test_exact_division(self):
        chunks = calculate_chunks(60, 20)
        assert len(chunks) == 3
        assert chunks[-1] == (40.0, 60.0)

    def test_remainder_short_chunk(self):
        chunks = calculate_chunks(65, 20)
        assert len(chunks) == 4
        assert chunks[-1] == (60.0, 65.0)
        assert chunks[-1][1] - chunks[-1][0] == 5

    def test_chunk_larger_than_total(self):
        chunks = calculate_chunks(30, 100)
        assert chunks == [(0.0, 30.0)]

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            calculate_chunks(100, 0)

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            calculate_chunks(100, -10)

    def test_no_gaps(self):
        chunks = calculate_chunks(90, 20)
        for i in range(len(chunks) - 1):
            assert chunks[i][1] == chunks[i + 1][0]

    def test_no_overlap(self):
        chunks = calculate_chunks(90, 20)
        for i in range(len(chunks) - 1):
            assert chunks[i][1] <= chunks[i + 1][0]

    def test_starts_at_zero(self):
        chunks = calculate_chunks(100, 20)
        assert chunks[0][0] == 0.0

    def test_ends_at_total(self):
        chunks = calculate_chunks(100, 20)
        assert chunks[-1][1] == 100.0
