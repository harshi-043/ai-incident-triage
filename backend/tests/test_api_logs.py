"""The log upload, sample, browsing and quality endpoints, tested through the real HTTP layer."""
from __future__ import annotations

from tests.helpers import CSV_LOG, JSONL_LOG, TXT_LOG, error_code, upload


def make_source(client, content=TXT_LOG, name="app.log", **form) -> str:
    response = upload(client, content, name, **form)
    assert response.status_code == 201, response.text
    return response.json()["source"]["id"]


# ---- health and errors ---------------------------------------------------------------------
def test_health_reports_database_and_provider(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["checks"] == {"database": "ok", "storage": "ok"}
    assert body["ai_provider"] == "none"


def test_unknown_route_uses_the_error_format(client):
    response = client.get("/api/nothing-here")
    assert response.status_code == 404 and error_code(response) == "not_found"


def test_malformed_and_unknown_ids(client):
    assert client.get("/api/logs/sources/not-an-id").status_code == 422
    assert error_code(client.get("/api/logs/sources/not-an-id")) == "invalid_id"
    missing = client.get("/api/logs/sources/src_0123456789abcdef")
    assert missing.status_code == 404 and error_code(missing) == "source_not_found"
    assert client.get("/api/logs/999999").status_code == 404


# ---- upload --------------------------------------------------------------------------------
def test_upload_text_csv_and_json(client):
    for content, name, fmt, count in ((TXT_LOG, "a.log", "txt", 4), (CSV_LOG, "a.csv", "csv", 3), (JSONL_LOG, "a.jsonl", "json", 2)):
        body = upload(client, content, name).json()
        assert body["source"]["format"] == fmt and body["source"]["record_count"] == count
        assert body["already_ingested"] is False
        assert "warnings" in body["quality"]


def test_same_file_twice_is_not_stored_twice(client):
    first = upload(client, TXT_LOG).json()
    second = upload(client, TXT_LOG).json()
    assert second["already_ingested"] is True and second["source"]["id"] == first["source"]["id"]
    assert len(client.get("/api/logs/sources").json()["items"]) == 1
    third = upload(client, TXT_LOG, force="true").json()
    assert third["already_ingested"] is False and third["source"]["id"] != first["source"]["id"]


def test_upload_rejections_use_stable_codes(client):
    assert error_code(upload(client, "x", "virus.exe")) == "unsupported_file_type"
    assert error_code(upload(client, b"", "a.log")) == "empty_file"
    assert error_code(upload(client, b"\x00\x01\x02", "a.log")) == "binary_file"
    assert error_code(upload(client, "no log lines here\n", "a.log")) == "no_records"
    assert error_code(upload(client, "a,b\n1,2\n", "a.csv")) == "missing_required_columns"
    assert client.post("/api/logs/upload").status_code == 422  # no file at all


def test_oversized_upload_is_refused_with_413(client):
    just_over = b"x" * (1024 * 1024 + 10)  # the test settings allow 1 MB
    assert client.post("/api/logs/upload", files={"file": ("a.log", just_over)}).status_code == 413
    far_over = b"x" * (3 * 1024 * 1024)  # refused before the body is read at all
    response = client.post("/api/logs/upload", files={"file": ("a.log", far_over)})
    assert response.status_code == 413 and error_code(response) == "file_too_large"


def test_column_mapping_is_applied_and_validated(client):
    content = "when,what\n2026-03-10 09:00:00,Disk full\n"
    body = upload(client, content, "a.csv", column_mapping='{"timestamp": "when", "message": "what"}').json()
    assert body["quality"]["column_mapping"] == {"timestamp": "when", "message": "what"}
    assert error_code(upload(client, content, "b.csv", column_mapping="{bad json")) == "invalid_column_mapping"
    assert error_code(upload(client, content, "c.csv", column_mapping='["not", "an", "object"]')) == "invalid_column_mapping"
    assert error_code(upload(client, content, "d.csv", column_mapping='{"message": "missing"}')) == "invalid_column_mapping"


def test_path_traversal_file_name_is_only_a_label(client, settings):
    body = upload(client, TXT_LOG, "../../../etc/passwd.log").json()
    assert body["source"]["name"] == "passwd.log"
    stray = [p for p in settings.storage_dir.parent.rglob("passwd*") if p.is_file()]
    assert stray == []  # nothing was written under that name anywhere


def test_quality_endpoint_and_source_detail(client):
    source_id = make_source(client, TXT_LOG + "\n-- rotated --\n")
    quality = client.get("/api/logs/quality", params={"source_id": source_id}).json()["quality"]
    assert quality["rejected_count"] == 1 and quality["stored_records"] == 4
    detail = client.get(f"/api/logs/sources/{source_id}").json()
    assert detail["filters"]["services"] == ["api-gateway", "orders-service"]
    assert detail["filters"]["levels"] == ["INFO", "WARNING", "ERROR"]


# ---- samples -------------------------------------------------------------------------------
def test_sample_listing_and_loading(client):
    items = client.get("/api/logs/samples").json()["items"]
    assert {i["name"] for i in items} == {"application", "routing"}
    loaded = client.post("/api/logs/samples", json={"name": "routing"})
    assert loaded.status_code == 201 and loaded.json()["source"]["kind"] == "sample"
    assert loaded.json()["source"]["record_count"] == 3026
    again = client.post("/api/logs/samples", json={"name": "routing"}).json()
    assert again["already_ingested"] is True


def test_bad_sample_requests(client):
    assert error_code(client.post("/api/logs/samples", json={"name": "nope"})) == "unknown_sample"
    assert error_code(client.post("/api/logs/samples", json={"name": "routing", "file": "x.csv"})) == "unknown_sample_file"
    assert client.post("/api/logs/samples", json={}).status_code == 422


# ---- browsing ------------------------------------------------------------------------------
def test_listing_pagination_and_totals(client):
    source_id = make_source(client)
    page = client.get("/api/logs", params={"source_id": source_id, "page_size": 3}).json()
    assert page["total"] == 4 and len(page["items"]) == 3 and page["page"] == 1
    page2 = client.get("/api/logs", params={"source_id": source_id, "page_size": 3, "page": 2}).json()
    assert len(page2["items"]) == 1
    assert client.get("/api/logs", params={"source_id": source_id, "page_size": 500}).status_code == 422
    assert client.get("/api/logs", params={"source_id": source_id, "page": 0}).status_code == 422


def test_filters_search_and_sort(client):
    source_id = make_source(client)
    get = lambda **p: client.get("/api/logs", params={"source_id": source_id, **p}).json()  # noqa: E731
    assert get(level="ERROR")["total"] == 2
    assert get(level=["ERROR", "WARNING"])["total"] == 3
    assert get(service="api-gateway")["total"] == 2
    assert get(min_status=500)["total"] == 1
    assert get(request_id="req-bbbb2222")["total"] == 1
    assert get(q="hikari")["total"] == 0  # stack traces are not searched, only message/id/exception/service
    assert get(q="SQLTransient")["total"] == 1  # case-insensitive
    assert get(start="2026-03-10T09:00:02Z", end="2026-03-10T09:00:03.5Z")["total"] == 2
    ordered = get(sort="timestamp", order="desc")["items"]
    assert [r["line_no"] for r in ordered] == sorted((r["line_no"] for r in ordered), reverse=True)
    by_level = [r["level"] for r in get(sort="level", order="desc")["items"]]
    assert by_level[0] == "ERROR" and by_level[-1] == "INFO"


def test_search_treats_percent_and_underscore_as_plain_text(client):
    source_id = make_source(client, "timestamp,message\n2026-03-10 09:00:00,disk at 100% full\n2026-03-10 09:00:01,other thing\n", "a.csv")
    assert client.get("/api/logs", params={"source_id": source_id, "q": "100%"}).json()["total"] == 1
    assert client.get("/api/logs", params={"source_id": source_id, "q": "%"}).json()["total"] == 1
    assert client.get("/api/logs", params={"source_id": source_id, "q": "_"}).json()["total"] == 0


def test_listing_validation(client):
    source_id = make_source(client)
    assert error_code(client.get("/api/logs", params={"source_id": source_id, "level": "LOUD"})) == "invalid_level"
    assert client.get("/api/logs", params={"source_id": source_id, "sort": "password"}).status_code == 422
    assert client.get("/api/logs", params={"source_id": "bad"}).status_code == 422
    assert client.get("/api/logs", params={"source_id": "src_0123456789abcdef"}).status_code == 404
    assert client.get("/api/logs", params={"source_id": source_id, "q": "x" * 300}).status_code == 422


def test_log_detail_includes_neighbours(client):
    source_id = make_source(client)
    rows = client.get("/api/logs", params={"source_id": source_id, "sort": "line_no"}).json()["items"]
    detail = client.get(f"/api/logs/{rows[2]['id']}", params={"context": 1}).json()
    assert detail["record"]["stack_trace"].count("\tat") == 2
    assert detail["record"]["normalized_message"] and detail["record"]["raw_line"]
    assert [r["id"] for r in detail["context"]["before"]] == [rows[1]["id"]]
    assert [r["id"] for r in detail["context"]["after"]] == [rows[3]["id"]]
    assert client.get(f"/api/logs/{rows[2]['id']}", params={"context": 99}).status_code == 422


# ---- deleting ------------------------------------------------------------------------------
def test_deleting_a_source_removes_its_records(client):
    source_id = make_source(client)
    record_id = client.get("/api/logs", params={"source_id": source_id}).json()["items"][0]["id"]
    assert client.delete(f"/api/logs/sources/{source_id}").status_code == 204
    assert client.get(f"/api/logs/sources/{source_id}").status_code == 404
    assert client.get(f"/api/logs/{record_id}").status_code == 404
    assert client.delete(f"/api/logs/sources/{source_id}").status_code == 404


def test_records_survive_a_restart(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(settings)) as first:
        source_id = make_source(first)
    with TestClient(create_app(settings)) as second:  # a new app on the same database file
        assert second.get(f"/api/logs/sources/{source_id}").status_code == 200
        assert second.get("/api/logs", params={"source_id": source_id}).json()["total"] == 4
