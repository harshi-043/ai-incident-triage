"""Levels, timestamps, message masking and field extraction."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.incident.templates import mask_message
from app.ingestion.extract import extract_fields
from app.ingestion.normalize import iso_z, normalize_level, parse_timestamp, to_naive_utc


@pytest.mark.parametrize("raw,expected", [
    ("warn", "WARNING"), ("WARNING", "WARNING"), ("Err", "ERROR"), ("FATAL", "CRITICAL"), ("crit", "CRITICAL"),
    ("information", "INFO"), ("[INFO]", "INFO"), ("trace", "DEBUG"), ("  error ", "ERROR"),
])
def test_level_aliases_are_normalised(raw, expected):
    assert normalize_level(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "banana", "42"])
def test_unknown_level_is_none_not_a_guess(raw):
    assert normalize_level(raw) is None


def test_iso_with_z_and_offset_give_the_same_instant():
    a, assumed_a = parse_timestamp("2026-03-10T09:00:00Z")
    b, assumed_b = parse_timestamp("2026-03-10T11:00:00+02:00")
    assert a == b == datetime(2026, 3, 10, 9, 0, tzinfo=UTC)
    assert not assumed_a and not assumed_b


def test_naive_timestamp_is_assumed_utc_and_flagged():
    parsed, assumed = parse_timestamp("2026-03-10 09:00:03")
    assert parsed == datetime(2026, 3, 10, 9, 0, 3, tzinfo=UTC)
    assert assumed is True


def test_java_comma_milliseconds():
    parsed, _ = parse_timestamp("2026-03-10 09:00:03,250")
    assert parsed.microsecond == 250_000


def test_epoch_seconds_and_milliseconds():
    seconds, _ = parse_timestamp("1773133200")
    millis, _ = parse_timestamp("1773133200000")
    assert seconds == millis == datetime(2026, 3, 10, 9, 0, tzinfo=UTC)


def test_web_server_timestamp_format():
    parsed, assumed = parse_timestamp("10/Mar/2026:09:00:03 +0000")
    assert parsed == datetime(2026, 3, 10, 9, 0, 3, tzinfo=UTC) and not assumed


@pytest.mark.parametrize("raw", ["", None, "not a date", "2026-13-45 99:99:99", "-", "null", "99999999999999999999"])
def test_garbage_timestamps_return_none(raw):
    assert parse_timestamp(raw) == (None, False)


def test_stored_and_sent_formats_round_trip():
    stored = to_naive_utc(datetime(2026, 3, 10, 11, 0, tzinfo=UTC))
    assert stored == datetime(2026, 3, 10, 11, 0)
    assert iso_z(stored) == "2026-03-10T11:00:00Z"
    assert iso_z(datetime(2026, 3, 10, 11, 0, 0, 250_000)) == "2026-03-10T11:00:00.250Z"
    assert iso_z(None) is None


# ---- masking -------------------------------------------------------------------------------
def test_variable_parts_are_masked():
    text = "Timeout for req-9f3a1c22 from 10.2.4.17:8080 after 30000ms on node-12 (waiting=14)"
    masked = mask_message(text)
    assert "req-9f3a1c22" not in masked and "10.2.4.17" not in masked
    assert masked == "Timeout for <ID> from <IP> after <NUM>ms on node-<NUM> (waiting=<NUM>)"


def test_two_lines_that_differ_only_in_numbers_share_a_template():
    a = mask_message("Connection pool usage high: active=18/20 waiting=2 pool=orders-db")
    b = mask_message("Connection pool usage high: active=19/20 waiting=4 pool=orders-db")
    assert a == b


def test_different_messages_keep_different_templates():
    assert mask_message("Disk usage 100% on host") != mask_message("Connection refused by host")


def test_uuid_and_hex_and_timestamp_are_masked():
    masked = mask_message("job 3f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b90 at 2026-03-10T09:00:01Z hash=deadbeefcafe0123")
    assert "<UUID>" in masked and "<TS>" in masked and "<HEX>" in masked


def test_names_with_digits_are_not_destroyed():
    assert "utf8" in mask_message("decoding utf8 failed") and "ipv4" in mask_message("ipv4 lookup failed")


def test_masking_is_safe_on_empty_and_huge_input():
    assert mask_message("") == ""
    assert len(mask_message("x" * 100_000)) <= 500


# ---- extraction ----------------------------------------------------------------------------
def test_extracts_the_usual_fields_from_a_message():
    found = extract_fields("GET /api/orders status=503 latency=2.5s request_id=req-abc12345 route RT-07 host=gw-01")
    assert found["http_status"] == 503
    assert found["latency_ms"] == 2500
    assert found["request_id"] == "req-abc12345"
    assert found["route_id"] == "RT-07"
    assert found["endpoint"] == "/api/orders"
    assert found["host"] == "gw-01"


@pytest.mark.parametrize("text,status", [
    ("Upstream returned 503 for POST", 503), ("HTTP 404 not found", 404), ('"GET / HTTP/1.1" 502 12', 502),
])
def test_status_code_patterns(text, status):
    assert extract_fields(text)["http_status"] == status


def test_exception_type_is_found_with_package_prefix():
    assert extract_fields("java.sql.SQLTransientConnectionException: pool timed out")["exception_type"] == "java.sql.SQLTransientConnectionException"
    assert extract_fields("ConnectionRefusedError: [Errno 111]")["exception_type"] == "ConnectionRefusedError"


def test_plain_words_are_not_mistaken_for_exceptions():
    assert "exception_type" not in extract_fields("There was an error while reading the file")


def test_packet_loss_and_milliseconds():
    found = extract_fields("High packet loss on RT-07 packet_loss=18.2% took 3000 ms")
    assert found["packet_loss_pct"] == 18.2 and found["latency_ms"] == 3000


def test_no_fields_in_plain_text():
    assert extract_fields("Service started") == {}
