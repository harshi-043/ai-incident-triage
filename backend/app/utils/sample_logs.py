"""
Synthetic demonstration logs. EVERYTHING HERE IS INVENTED: the services, hosts, users, IP addresses
(documentation ranges only) and incidents do not come from any real system.

Two datasets are produced from a fixed random seed, so the same seed always gives the same files:

* "application": 8 hours of web-shop traffic with five injected incidents and some isolated noise.
* "routing":     4 hours of routing-engine logs with two injected incidents.

Each dataset also returns an ANSWER KEY (which line belongs to which injected scenario). The key is only
used by the evaluation script to check the pipeline. The pipeline itself never sees it.

Run from the backend folder:   python scripts/generate_sample_logs.py
"""
from __future__ import annotations

import csv
import io
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

APPLICATION_START = datetime(2026, 3, 10, 8, 0, 0)
ROUTING_START = datetime(2026, 3, 10, 8, 0, 0)

HOSTS = {
    "api-gateway": "gw-01", "orders-service": "orders-01", "payments-service": "pay-01",
    "auth-service": "auth-01", "inventory-service": "inv-02", "notification-service": "notify-01",
    "cache-service": "cache-01", "routing-engine": "rtr-core-1", "link-monitor": "mon-01", "bgp-agent": "rtr-edge-2",
}


@dataclass
class Event:
    ts: datetime
    level: str
    service: str
    message: str
    scenario: str  # "baseline", "noise", or the injected incident name (kept in the answer key only)
    request_id: str | None = None
    status: int | None = None
    latency_ms: float | None = None
    route_id: str | None = None
    stack: list[str] = field(default_factory=list)
    order: int = 0


@dataclass
class SampleDataset:
    name: str
    description: str
    files: dict[str, str]  # file name -> text
    key: dict[str, Any]  # the answer key (used only by evaluation)


class _Builder:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.events: list[Event] = []

    def rid(self) -> str:
        return "req-" + "".join(self.rng.choice("0123456789abcdef") for _ in range(8))

    def add(self, ts: datetime, level: str, service: str, message: str, scenario: str, **kw: Any) -> Event:
        event = Event(ts=ts, level=level, service=service, message=message, scenario=scenario, order=len(self.events), **kw)
        self.events.append(event)
        return event

    def at(self, start: datetime, seconds: float) -> datetime:
        return start + timedelta(seconds=seconds)

    def sorted_events(self) -> list[Event]:
        return sorted(self.events, key=lambda e: (e.ts, e.order))


# ---------------------------------------------------------------------------------------------
# Application logs
# ---------------------------------------------------------------------------------------------
def _application_baseline(b: _Builder, start: datetime, minutes: int) -> None:
    rng = b.rng
    for minute in range(minutes):
        for _ in range(rng.randint(15, 25)):
            ts = start + timedelta(minutes=minute, seconds=rng.random() * 59.9)
            rid, lat = b.rid(), max(15, int(rng.lognormvariate(4.3, 0.35)))
            roll = rng.random()
            if roll < 0.30:
                b.add(ts, "INFO", "api-gateway", f"GET /api/orders status=200 latency={lat}ms request_id={rid}", "baseline", request_id=rid, status=200, latency_ms=lat)
            elif roll < 0.45:
                b.add(ts, "INFO", "api-gateway", f"POST /api/orders status=201 latency={lat}ms request_id={rid}", "baseline", request_id=rid, status=201, latency_ms=lat)
            elif roll < 0.60:
                b.add(ts, "INFO", "orders-service", f"Order created order_id={rng.randint(10000, 99999)} request_id={rid}", "baseline", request_id=rid)
            elif roll < 0.72:
                b.add(ts, "INFO", "auth-service", f"User login succeeded user_id=u-{rng.randint(1000, 9999)} request_id={rid}", "baseline", request_id=rid)
            elif roll < 0.82:
                b.add(ts, "INFO", "payments-service", f"Payment authorised amount={rng.randint(5, 300)}.{rng.randint(0, 99):02d} currency=USD request_id={rid}", "baseline", request_id=rid)
            elif roll < 0.90:
                b.add(ts, "INFO", "inventory-service", f"Stock reserved sku=SKU-{rng.randint(100, 999)} qty={rng.randint(1, 4)} request_id={rid}", "baseline", request_id=rid)
            elif roll < 0.97:
                b.add(ts, "INFO", "notification-service", f"Email queued template=order_confirmation request_id={rid}", "baseline", request_id=rid)
            else:
                b.add(ts, "WARNING", "api-gateway", f"GET /api/products/{rng.randint(1, 500)} status=404 latency={lat}ms request_id={rid}", "baseline", request_id=rid, status=404, latency_ms=lat)

    # A handful of unrelated, isolated errors. They are far apart, so they must NOT become an incident.
    for minute in (23, 97, 171, 262, 391):
        ts = start + timedelta(minutes=minute, seconds=b.rng.randint(1, 50))
        rid = b.rid()
        b.add(ts, "ERROR", "notification-service", f"SMTP send failed: connection reset by peer, will retry (attempt=1) request_id={rid}", "noise", request_id=rid)


def _incident_db_pool(b: _Builder, start: datetime) -> None:
    """09:05-09:27 database connection pool exhaustion in orders-service and payments-service."""
    rng, name = b.rng, "db_connection_timeout"
    for i in range(14):  # warnings before the failure
        b.add(b.at(start, 5 * 60 + i * 25 + rng.random() * 5), "WARNING", "orders-service",
              f"Connection pool usage high: active={rng.randint(17, 19)}/20 waiting={rng.randint(1, 4)} pool=orders-db", name)
    for sec in range(12 * 60, 26 * 60, 4):  # 12 minutes -> 26 minutes
        if rng.random() < 0.55:
            rid, waiting = b.rid(), rng.randint(8, 40)
            b.add(b.at(start, sec + rng.random() * 3), "ERROR", "orders-service",
                  f"java.sql.SQLTransientConnectionException: orders-db - Connection is not available, request timed out after 30000ms (active=20, idle=0, waiting={waiting}) request_id={rid}",
                  name, request_id=rid, stack=[
                      "\tat com.zaxxer.hikari.pool.HikariPool.createTimeoutException(HikariPool.java:696)",
                      "\tat com.zaxxer.hikari.pool.HikariPool.getConnection(HikariPool.java:197)",
                      "\tat com.shop.orders.OrderRepository.save(OrderRepository.java:54)"])
        if rng.random() < 0.40:
            rid = b.rid()
            b.add(b.at(start, sec + rng.random() * 3), "ERROR", "payments-service",
                  f"Timeout waiting for database connection pool=payments-db after 30000ms request_id={rid}", name, request_id=rid)
        if rng.random() < 0.50:
            rid = b.rid()
            b.add(b.at(start, sec + rng.random() * 3), "ERROR", "api-gateway",
                  f"Upstream orders-service returned 503 for POST /api/orders status=503 request_id={rid}", name, request_id=rid, status=503)
    b.add(b.at(start, 27 * 60), "INFO", "orders-service", "Connection pool recovered active=6/20 waiting=0 pool=orders-db", name)


def _incident_latency(b: _Builder, start: datetime) -> None:
    """11:03-11:20 slow queries after the cache stopped helping."""
    rng, name = b.rng, "api_latency_spike"
    for i in range(6):
        b.add(b.at(start, i * 40 + rng.random() * 5), "WARNING", "cache-service",
              f"Cache hit ratio dropped hit_ratio=0.{rng.randint(10, 18)} keyspace=product-catalog", name)
    for sec in range(60, 17 * 60, 5):
        if rng.random() < 0.5:
            rid, ms = b.rid(), rng.randint(2500, 9000)
            b.add(b.at(start, sec + rng.random() * 4), "WARNING", "orders-service",
                  f"Slow query detected: SELECT * FROM orders WHERE customer_id = ? took {ms}ms request_id={rid}", name, request_id=rid, latency_ms=ms)
        if rng.random() < 0.45:
            rid, ms = b.rid(), rng.randint(2500, 9800)
            b.add(b.at(start, sec + rng.random() * 4), "WARNING", "api-gateway",
                  f"GET /api/orders status=200 latency={ms}ms exceeds threshold 2000ms request_id={rid}", name, request_id=rid, status=200, latency_ms=ms)
        if rng.random() < 0.20:
            rid = b.rid()
            b.add(b.at(start, sec + rng.random() * 4), "ERROR", "api-gateway",
                  f"Upstream timeout after 10000ms GET /api/orders status=504 request_id={rid}", name, request_id=rid, status=504, latency_ms=10000)


def _incident_auth(b: _Builder, start: datetime) -> None:
    """12:40-12:49 burst of failed logins and rejected tokens."""
    rng, name = b.rng, "auth_failures"
    for sec in range(0, 9 * 60, 7):
        rid = b.rid()
        b.add(b.at(start, sec + rng.random() * 5), "WARNING", "auth-service",
              f"Invalid credentials for user_id=u-{rng.randint(1000, 9999)} from ip=203.0.113.{rng.randint(2, 40)} status=401 request_id={rid}",
              name, request_id=rid, status=401)
        if rng.random() < 0.55:
            rid = b.rid()
            b.add(b.at(start, sec + rng.random() * 5), "ERROR", "auth-service",
                  f"JWT signature verification failed for token issued by 'idp-staging' status=401 request_id={rid}", name, request_id=rid, status=401)


def _incident_deploy(b: _Builder, start: datetime) -> None:
    """13:55-14:10 a new payments-service version throws exceptions."""
    rng, name = b.rng, "deploy_exceptions"
    b.add(b.at(start, 0), "INFO", "payments-service", "Deployment started: payments-service version=2.14.1", name)
    b.add(b.at(start, 70), "INFO", "payments-service", "payments-service started version=2.14.1", name)
    for sec in range(100, 14 * 60, 6):
        if rng.random() < 0.6:
            rid = b.rid()
            b.add(b.at(start, sec + rng.random() * 4), "ERROR", "payments-service",
                  f"NullPointerException: Cannot read field 'currency' because 'order' is null while processing payment request_id={rid}",
                  name, request_id=rid, stack=[
                      "\tat com.shop.payments.PaymentProcessor.charge(PaymentProcessor.java:88)",
                      "\tat com.shop.payments.PaymentController.pay(PaymentController.java:41)"])
        if rng.random() < 0.5:
            rid = b.rid()
            b.add(b.at(start, sec + rng.random() * 4), "ERROR", "api-gateway",
                  f"Upstream payments-service returned 500 for POST /api/payments status=500 request_id={rid}", name, request_id=rid, status=500)
    b.add(b.at(start, 14 * 60 + 20), "INFO", "payments-service", "Deployment started: payments-service version=2.14.0 (rollback)", name)


def _incident_disk(b: _Builder, start: datetime) -> None:
    """15:02-15:15 disk full on inventory-service. No sample runbook covers it, on purpose."""
    rng, name = b.rng, "disk_full"
    for i in range(5):
        b.add(b.at(start, -600 + i * 100), "WARNING", "inventory-service", f"Disk usage high usage=9{rng.randint(2, 6)}% mount=/var/data host=inv-02", name)
    b.add(b.at(start, 0), "CRITICAL", "inventory-service", "Disk usage 100% mount=/var/data host=inv-02", name)
    for sec in range(5, 13 * 60, 15):
        rid = b.rid()
        b.add(b.at(start, sec + rng.random() * 8), "ERROR", "inventory-service",
              f"java.io.IOException: No space left on device writing /var/data/inventory/journal.log request_id={rid}",
              name, request_id=rid, stack=["\tat java.base/java.io.FileOutputStream.writeBytes(Native Method)"])
        if rng.random() < 0.7:
            rid = b.rid()
            b.add(b.at(start, sec + 3 + rng.random() * 8), "ERROR", "inventory-service",
                  f"Failed to persist stock update sku=SKU-{rng.randint(100, 999)} request_id={rid}", name, request_id=rid)


def _render_txt(events: list[Event]) -> tuple[str, dict[str, list[int]]]:
    """Render events as a plain-text log and note which line number belongs to which scenario."""
    lines: list[str] = []
    key: dict[str, list[int]] = {}
    for index, e in enumerate(events):
        if index in (900, 4100):  # a few intentionally malformed lines to show the data-quality report
            lines.append("-- log rotated, previous file archived --")
        stamp = e.ts.strftime("%Y-%m-%d %H:%M:%S") + f",{e.ts.microsecond // 1000:03d}"
        lines.append(f"{stamp} {e.level:<8} [{e.service}] {e.message}")
        key.setdefault(e.scenario, []).append(len(lines))
        lines.extend(e.stack)
        if index in (1500, 3000) and e.request_id:
            # An exact duplicate (same time and request id). The pipeline removes it, so it is not in the answer key.
            lines.append(lines[-1 - len(e.stack)])
    return "\n".join(lines) + "\n", key


def _render_csv(events: list[Event]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["timestamp", "level", "service", "host", "request_id", "http_status", "latency_ms", "message", "stack_trace"])
    for e in events:
        writer.writerow([e.ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{e.ts.microsecond // 1000:03d}Z", e.level, e.service,
                         HOSTS.get(e.service, ""), e.request_id or "", e.status or "", e.latency_ms or "", e.message, "\n".join(e.stack)])
    return out.getvalue()


def _render_jsonl(events: list[Event]) -> str:
    rows = []
    for e in events:
        rows.append(json.dumps({
            "@timestamp": e.ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{e.ts.microsecond // 1000:03d}Z",
            "level": e.level.lower(), "service": e.service, "host": HOSTS.get(e.service),
            "request_id": e.request_id, "http_status": e.status, "latency_ms": e.latency_ms,
            "message": e.message, "error": {"stack": "\n".join(e.stack)} if e.stack else None,
        }))
    return "\n".join(rows) + "\n"


def generate_application(seed: int = 42) -> SampleDataset:
    b = _Builder(seed)
    _application_baseline(b, APPLICATION_START, 8 * 60)
    _incident_db_pool(b, APPLICATION_START + timedelta(hours=1))
    _incident_latency(b, APPLICATION_START + timedelta(hours=3, minutes=3))
    _incident_auth(b, APPLICATION_START + timedelta(hours=4, minutes=40))
    _incident_deploy(b, APPLICATION_START + timedelta(hours=5, minutes=55))
    _incident_disk(b, APPLICATION_START + timedelta(hours=7, minutes=2))
    events = b.sorted_events()
    txt, line_key = _render_txt(events)
    return SampleDataset(
        name="application",
        description="SYNTHETIC web-shop application logs, 8 hours, five injected incidents.",
        files={"application.log": txt, "application.csv": _render_csv(events), "application.jsonl": _render_jsonl(events)},
        key={
            "dataset": "application", "seed": seed, "file": "application.log",
            "scenarios": {
                "db_connection_timeout": {"expected_runbook": "database-connectivity.md", "services": ["orders-service", "payments-service", "api-gateway"]},
                "api_latency_spike": {"expected_runbook": "api-latency.md", "services": ["orders-service", "api-gateway", "cache-service"]},
                "auth_failures": {"expected_runbook": "authentication-failures.md", "services": ["auth-service"]},
                "deploy_exceptions": {"expected_runbook": "http-5xx-errors.md", "services": ["payments-service", "api-gateway"]},
                "disk_full": {"expected_runbook": None, "services": ["inventory-service"]},
            },
            "lines_by_scenario": line_key,
        },
    )


# ---------------------------------------------------------------------------------------------
# Routing logs
# ---------------------------------------------------------------------------------------------
def generate_routing(seed: int = 42) -> SampleDataset:
    b = _Builder(seed + 1)
    rng = b.rng
    routes = [f"RT-{n:02d}" for n in range(1, 13)]
    start = ROUTING_START
    for minute in range(4 * 60):
        for _ in range(rng.randint(8, 14)):
            ts = start + timedelta(minutes=minute, seconds=rng.random() * 59.9)
            route, lat = rng.choice(routes), max(4, int(rng.lognormvariate(3.2, 0.3)))
            b.add(ts, "INFO", "routing-engine", f"Route {route} health check ok latency={lat}ms packet_loss=0.{rng.randint(0, 3)}%", "baseline", route_id=route, latency_ms=lat)
    for minute in (44, 150):
        ts = start + timedelta(minutes=minute, seconds=rng.randint(1, 50))
        b.add(ts, "WARNING", "link-monitor", f"Transient jitter on RT-{rng.randint(1, 12):02d} jitter=14ms", "noise")

    # Incident 1: RT-07 loses packets and the BGP session flaps (09:30-09:46)
    name, t0 = "route_packet_loss", start + timedelta(hours=1, minutes=30)
    for sec in range(0, 16 * 60, 5):
        if rng.random() < 0.7:
            b.add(b.at(t0, sec + rng.random() * 3), "ERROR", "routing-engine", "Route RT-07 health check timed out after 3000ms", name, route_id="RT-07", latency_ms=3000)
        if rng.random() < 0.55:
            b.add(b.at(t0, sec + rng.random() * 3), "WARNING", "link-monitor", f"High packet loss on RT-07 packet_loss={rng.randint(120, 260) / 10}%", name, route_id="RT-07")
        if rng.random() < 0.18:
            b.add(b.at(t0, sec + rng.random() * 3), "ERROR", "bgp-agent", "BGP session with peer 10.2.4.1 flapping: session down 6 times in 5 minutes", name, route_id="RT-07")

    # Incident 2: RT-03 and RT-11 degrade, traffic moves to a backup path (11:10-11:22)
    name, t1 = "route_latency_failover", start + timedelta(hours=3, minutes=10)
    for sec in range(0, 12 * 60, 6):
        route = rng.choice(["RT-03", "RT-11"])
        if rng.random() < 0.6:
            b.add(b.at(t1, sec + rng.random() * 3), "WARNING", "routing-engine", f"Route {route} latency above threshold latency={rng.randint(300, 900)}ms threshold=250ms", name, route_id=route)
        if rng.random() < 0.3:
            b.add(b.at(t1, sec + rng.random() * 3), "ERROR", "routing-engine", f"Route {route} failover to backup path completed after {rng.randint(2, 9)}s", name, route_id=route)

    events = b.sorted_events()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["time", "severity", "component", "host", "route", "latency_ms", "msg"])
    line_key: dict[str, list[int]] = {}
    for row_no, e in enumerate(events, start=2):  # row 1 is the header
        writer.writerow([e.ts.strftime("%Y-%m-%d %H:%M:%S"), e.level.lower(), e.service, HOSTS.get(e.service, ""),
                         e.route_id or "", e.latency_ms or "", e.message])
        line_key.setdefault(e.scenario, []).append(row_no)
    return SampleDataset(
        name="routing",
        description="SYNTHETIC routing-engine logs, 4 hours, two injected incidents. Uses non-standard column names on purpose.",
        files={"routing.csv": out.getvalue()},
        key={
            "dataset": "routing", "seed": seed, "file": "routing.csv",
            "scenarios": {
                "route_packet_loss": {"expected_runbook": "network-timeouts.md", "services": ["routing-engine", "link-monitor", "bgp-agent"]},
                "route_latency_failover": {"expected_runbook": "network-timeouts.md", "services": ["routing-engine"]},
            },
            "lines_by_scenario": line_key,
        },
    )


def generate(name: str, seed: int = 42) -> SampleDataset:
    if name == "application":
        return generate_application(seed)
    if name == "routing":
        return generate_routing(seed)
    raise ValueError(f"Unknown sample dataset '{name}'. Choose 'application' or 'routing'.")
