"""Parsing and cleaning of CSV, JSON and text logs, and whole-file validation."""
from __future__ import annotations

import json

import pytest

from app.ingestion.pipeline import IngestError, ingest_bytes, safe_display_name
from app.utils.sample_logs import generate_application, generate_routing
from tests.helpers import CSV_LOG, JSONL_LOG, TXT_LOG

LIMITS = dict(max_bytes=1024 * 1024, max_records=5000)


def ingest(text: str | bytes, name: str = "a.log", **kw):
    data = text.encode() if isinstance(text, str) else text
    return ingest_bytes(data, name, **{**LIMITS, **kw})


# ---- text logs -----------------------------------------------------------------------------
def test_text_log_records_and_stack_trace_attachment():
    result = ingest(TXT_LOG)
    assert [r["level"] for r in result.records] == ["INFO", "WARNING", "ERROR", "ERROR"]
    error = result.records[2]
    assert error["service"] == "orders-service"
    assert error["exception_type"] == "java.sql.SQLTransientConnectionException"
    assert "HikariPool.getConnection" in error["stack_trace"]  # continuation lines joined to the record above
    assert error["request_id"] == "req-bbbb2222"
    assert result.records[3]["http_status"] == 503


def test_original_message_is_preserved_next_to_the_normalised_one():
    record = ingest(TXT_LOG).records[2]
    assert "30000ms" in record["message"]
    assert "30000" not in record["normalized_message"] and "<NUM>ms" in record["normalized_message"]


def test_service_in_colon_form_and_no_service_form():
    text = ("2026-03-10T09:00:00Z ERROR orders-service: disk failed\n"
            "2026-03-10 09:00:01 INFO Starting server\n")
    records = ingest(text).records
    assert records[0]["service"] == "orders-service"
    assert records[1]["service"] == "unknown"


def test_malformed_and_blank_lines_are_counted_not_hidden():
    text = TXT_LOG + "\n-- log rotated --\nthis is not a log line\n"
    q = ingest(text).quality
    assert q["rejected_count"] == 2
    assert q["blank_lines"] == 1
    assert {e["reason"] for e in q["rejected_examples"]} == {"the line does not match a known log pattern"}
    assert any(w["code"] == "rejected_lines" and w["count"] == 2 for w in q["warnings"])


def test_logfmt_and_access_log_lines():
    text = ('time=2026-03-10T09:00:00Z level=error service=api msg="db down" request_id=req-77aa88bb host=h1\n'
            '10.0.0.5 - - [10/Mar/2026:09:00:03 +0000] "GET /orders HTTP/1.1" 503 512\n')
    first, second = ingest(text).records
    assert (first["level"], first["service"], first["request_id"], first["host"]) == ("ERROR", "api", "req-77aa88bb", "h1")
    assert (second["level"], second["http_status"], second["endpoint"]) == ("ERROR", 503, "/orders")


def test_a_stack_trace_with_nothing_above_it_is_rejected():
    result = ingest("\tat com.example.Foo.bar(Foo.java:1)\n" + TXT_LOG)
    assert result.quality["rejected_count"] == 1


# ---- CSV -----------------------------------------------------------------------------------
def test_csv_columns_are_recognised_and_levels_normalised():
    result = ingest(CSV_LOG, "a.csv")
    assert [r["level"] for r in result.records] == ["INFO", "ERROR", "WARNING"]  # WARN -> WARNING
    assert result.records[1]["http_status"] == 503 and result.records[1]["latency_ms"] == 30000
    assert result.quality["column_mapping"]["message"] == "message"


def test_csv_with_other_column_names_and_semicolons():
    text = "time;severity;component;msg\n2026-03-10 09:00:00;fatal;db;Disk full\n"
    record = ingest(text, "a.csv").records[0]
    assert (record["level"], record["service"], record["message"]) == ("CRITICAL", "db", "Disk full")


def test_user_column_mapping_overrides_detection():
    text = "when,sev,what,who\n2026-03-10 09:00:00,error,Disk full,storage\n"
    record = ingest(text, "a.csv", column_mapping={"message": "what", "timestamp": "when", "level": "sev", "service": "who"}).records[0]
    assert (record["message"], record["service"], record["level"]) == ("Disk full", "storage", "ERROR")


def test_mapping_to_a_missing_column_or_unknown_field_is_an_error():
    with pytest.raises(IngestError) as bad_column:
        ingest(CSV_LOG, "a.csv", column_mapping={"message": "nope"})
    assert bad_column.value.code == "invalid_column_mapping"
    with pytest.raises(IngestError) as bad_field:
        ingest(CSV_LOG, "a.csv", column_mapping={"colour": "level"})
    assert bad_field.value.code == "invalid_column_mapping"


def test_csv_without_a_message_column_explains_what_to_do():
    with pytest.raises(IngestError) as exc:
        ingest("a,b\n1,2\n", "a.csv")
    assert exc.value.code == "missing_required_columns" and "message" in exc.value.message


def test_csv_row_problems_are_rejected_with_a_reason():
    text = "timestamp,level,message\n2026-03-10 09:00:00,ERROR,ok\n2026-03-10 09:00:01,ERROR,\n2026-03-10 09:00:02,ERROR,x,y,z\n"
    result = ingest(text, "a.csv")
    assert len(result.records) == 1
    assert {e["reason"] for e in result.quality["rejected_examples"]} == {
        "the message is empty", "row has 5 fields but the header has 3"}


def test_latency_in_seconds_column_is_converted():
    text = "timestamp,message,latency_seconds\n2026-03-10 09:00:00,slow,2.5\n"
    assert ingest(text, "a.csv").records[0]["latency_ms"] == 2500


def test_invalid_status_and_latency_are_ignored_and_counted():
    text = "timestamp,message,http_status,latency_ms\n2026-03-10 09:00:00,x,999,-5\n"
    result = ingest(text, "a.csv")
    record = result.records[0]
    assert record["http_status"] is None and record["latency_ms"] is None
    assert {w["code"] for w in result.quality["warnings"]} >= {"invalid_status", "invalid_latency"}


def test_formula_like_cells_are_stored_as_plain_text():
    text = 'timestamp,message\n2026-03-10 09:00:00,"=HYPERLINK(""http://x"")"\n'
    assert ingest(text, "a.csv").records[0]["message"].startswith("=HYPERLINK")


# ---- JSON ----------------------------------------------------------------------------------
def test_json_lines_with_nested_error_stack():
    records = ingest(JSONL_LOG, "a.jsonl").records
    assert [r["level"] for r in records] == ["INFO", "ERROR"]
    assert records[0]["timestamp"] is not None  # "@timestamp" is recognised
    assert records[1]["stack_trace"] == "line1\nline2"  # "error.stack" is read as the stack trace


def test_json_array_and_non_object_entries():
    text = json.dumps([{"message": "a", "level": "error"}, "just a string", 5])
    result = ingest(text, "a.json")
    assert len(result.records) == 1 and result.quality["rejected_count"] == 2


def test_nested_message_key_is_found():
    text = json.dumps([{"time": "2026-03-10 09:00:00", "error": {"message": "db down", "type": "OperationalError"}}])
    record = ingest(text, "a.json").records[0]
    assert record["message"] == "db down"


def test_invalid_json_lines_are_rejected_individually():
    result = ingest('{"message": "ok"}\n{not json}\n', "a.jsonl")
    assert len(result.records) == 1 and result.quality["rejected_count"] == 1


def test_a_txt_file_that_holds_json_lines_is_read_as_json():
    assert ingest(JSONL_LOG, "a.txt").format == "json"


# ---- cleaning rules ------------------------------------------------------------------------
def test_missing_timestamps_are_kept_and_counted():
    result = ingest("timestamp,message\n,no time here\n2026-03-10 09:00:00,has time\n", "a.csv")
    assert result.records[0]["timestamp"] is None and result.records[1]["timestamp"] is not None
    assert result.quality["missing_timestamp"] == 1


def test_unparseable_timestamp_is_counted_as_missing():
    result = ingest("timestamp,message\nyesterday-ish,x\n", "a.csv")
    assert result.records[0]["timestamp"] is None
    assert any(w["code"] == "unparseable_timestamp" for w in result.quality["warnings"])


def test_naive_timestamps_give_an_info_note_not_a_warning():
    warning = next(w for w in ingest(TXT_LOG).quality["warnings"] if w["code"] == "timestamps_assumed_utc")
    assert warning["severity"] == "info"


def test_missing_level_is_inferred_and_flagged():
    result = ingest("timestamp,message,http_status\n2026-03-10 09:00:00,x,502\n2026-03-10 09:00:01,y,\n", "a.csv")
    assert [r["level"] for r in result.records] == ["ERROR", "INFO"]
    assert result.records[0]["extra"]["level_inferred"] is True


def test_duplicate_with_request_id_removed_but_identical_bursts_without_ids_kept():
    with_id = "2026-03-10 09:00:00 ERROR [a] boom request_id=req-12345678\n" * 2
    without_id = "2026-03-10 09:00:00 ERROR [a] boom\n" * 3
    assert len(ingest(with_id).records) == 1 and ingest(with_id).quality["duplicates_removed"] == 1
    assert len(ingest(without_id).records) == 3  # a burst of the same error is real information


def test_long_message_is_cut_and_reported():
    text = "timestamp,message\n2026-03-10 09:00:00," + "x" * 6000 + "\n"
    result = ingest(text, "a.csv")
    assert len(result.records[0]["message"]) == 5000
    assert any(w["code"] == "long_messages_truncated" for w in result.quality["warnings"])


# ---- whole-file validation -----------------------------------------------------------------
@pytest.mark.parametrize("name", ["evil.exe", "notes.pdf", "noextension", "archive.zip"])
def test_unsupported_extensions_are_rejected(name):
    with pytest.raises(IngestError) as exc:
        ingest("x", name)
    assert exc.value.code == "unsupported_file_type"


def test_empty_binary_oversized_and_unreadable_files():
    with pytest.raises(IngestError) as empty:
        ingest(b"", "a.log")
    assert empty.value.code == "empty_file"
    with pytest.raises(IngestError) as binary:
        ingest(b"\x00\x01\x02garbage", "a.log")
    assert binary.value.code == "binary_file"
    with pytest.raises(IngestError) as big:
        ingest("x" * 2000, "a.log", max_bytes=1000)
    assert big.value.code == "file_too_large" and big.value.status_code == 413
    with pytest.raises(IngestError) as nothing:
        ingest("just some words\nand more words\n", "a.log")
    assert nothing.value.code == "no_records"


def test_too_many_records_is_refused_with_advice():
    text = "timestamp,message\n" + "".join(f"2026-03-10 09:00:{i % 60:02d},m{i}\n" for i in range(50))
    with pytest.raises(IngestError) as exc:
        ingest(text, "a.csv", max_records=10)
    assert exc.value.code == "too_many_records" and "Split the file" in exc.value.message


def test_latin1_file_is_read_with_a_warning():
    text = "timestamp,message\n2026-03-10 09:00:00,caf\xe9 failed\n".encode("latin-1")
    result = ingest(text, "a.csv")
    assert "café" in result.records[0]["message"]
    assert any(w["code"] == "decoded_latin1" for w in result.quality["warnings"])


def test_file_names_are_reduced_to_a_plain_name():
    assert safe_display_name("../../etc/passwd.csv") == "passwd.csv"
    assert safe_display_name("C:\\temp\\logs\\app.log") == "app.log"
    assert safe_display_name("bad\x00name\n.log") == "badname.log"
    assert safe_display_name(None) == "upload"
    assert len(safe_display_name("a" * 500 + ".log")) <= 120


def test_hash_is_stable_for_the_same_bytes():
    assert ingest(TXT_LOG).content_hash == ingest(TXT_LOG).content_hash != ingest(TXT_LOG + "\n2026-03-10 09:00:09 INFO x").content_hash


# ---- the bundled samples -------------------------------------------------------------------
def test_the_three_formats_of_the_application_sample_agree():
    files = generate_application(42).files
    counts = {name: len(ingest(text, name, max_bytes=10**8, max_records=10**6).records) for name, text in files.items()}
    assert len(set(counts.values())) == 1, counts


def test_application_sample_quality_report_matches_the_planted_defects():
    q = ingest(generate_application(42).files["application.log"], "application.log", max_bytes=10**8, max_records=10**6).quality
    assert q["rejected_count"] == 2 and q["duplicates_removed"] == 2  # the generator plants exactly these


def test_routing_sample_uses_non_standard_columns_that_are_still_mapped():
    q = ingest(generate_routing(42).files["routing.csv"], "routing.csv", max_bytes=10**8, max_records=10**6).quality
    assert q["column_mapping"]["message"] == "msg" and q["column_mapping"]["level"] == "severity"


def test_sample_generation_is_reproducible():
    assert generate_application(42).files == generate_application(42).files
    assert generate_application(42).files != generate_application(7).files
