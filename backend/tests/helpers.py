"""Small sample logs and upload helpers shared by the tests."""
from __future__ import annotations

TXT_LOG = (
    "2026-03-10 09:00:01,100 INFO     [api-gateway] GET /api/orders status=200 latency=80ms request_id=req-aaaa1111\n"
    "2026-03-10 09:00:02,200 WARNING  [orders-service] Connection pool usage high: active=18/20 waiting=2\n"
    "2026-03-10 09:00:03,300 ERROR    [orders-service] java.sql.SQLTransientConnectionException: pool timed out after 30000ms request_id=req-bbbb2222\n"
    "\tat com.zaxxer.hikari.pool.HikariPool.getConnection(HikariPool.java:197)\n"
    "\tat com.shop.orders.OrderRepository.save(OrderRepository.java:54)\n"
    "2026-03-10 09:00:04,400 ERROR    [api-gateway] Upstream orders-service returned 503 for POST /api/orders request_id=req-cccc3333\n"
)

CSV_LOG = (
    "timestamp,level,service,message,request_id,http_status,latency_ms\n"
    "2026-03-10T09:00:01Z,INFO,api-gateway,GET /api/orders ok,req-1,200,80\n"
    "2026-03-10T09:00:02Z,ERROR,orders-service,Database timeout,req-2,503,30000\n"
    "2026-03-10T09:00:03Z,WARN,auth-service,Invalid credentials,req-3,401,12\n"
)

JSONL_LOG = (
    '{"@timestamp": "2026-03-10T09:00:01Z", "level": "info", "service": "api", "message": "started"}\n'
    '{"@timestamp": "2026-03-10T09:00:02Z", "level": "error", "service": "api", "message": "boom", "error": {"stack": "line1\\nline2"}}\n'
)


def upload(client, content: str | bytes, filename: str = "app.log", **form):
    data = content.encode("utf-8") if isinstance(content, str) else content
    return client.post("/api/logs/upload", files={"file": (filename, data)}, data=form)


def error_code(response) -> str:
    return response.json()["error"]["code"]


def big_settings(tmp_path, **overrides):
    """Settings with the real bundled runbooks and limits large enough for the ~10,000-record synthetic samples."""
    from pathlib import Path

    from app.core.config import Settings

    values = dict(_env_file=None, storage_dir=tmp_path / "storage", ai_provider="none", max_upload_mb=25, max_log_records=50_000,
                  sample_runbook_dir=Path(__file__).resolve().parents[1] / "data" / "sample_runbooks")
    values.update(overrides)
    return Settings(**values)
