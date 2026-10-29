# Database Connectivity and Connection Pool Exhaustion

> SYNTHETIC EXAMPLE RUNBOOK written for this demo project. It is not real operational guidance.

## Symptoms
- Errors such as `SQLTransientConnectionException`, "pool timed out", "Timeout waiting for connection" or "Connection refused" from a service that uses a database.
- Warnings like "Connection pool usage high" with `active` close to the pool maximum and `waiting` greater than zero.
- Upstream services (an API gateway, for example) start returning HTTP 503 or 504 for requests that need the database.
- Slow requests first, then failures: latency grows before the errors begin.

## Common causes
1. The pool is too small for the current traffic.
2. Connections are not returned to the pool (a leak), often after a code change.
3. The database is slow or locked, so each connection is held for longer.
4. The database host is unreachable, restarting or has hit its connection limit.

## Diagnostic steps (read-only)
1. Compare the time of the first pool warning with the time of the first error. Warnings that start earlier point to pool pressure building up, not a sudden database outage.
2. Check the pool metrics for the affected service: active, idle and waiting connections over the last hour.
3. Check the database server's current connection count against its configured limit.
4. Look for long-running queries or lock waits on the database during the incident window.
5. Check whether a deployment or configuration change happened shortly before the first warning.

Example read-only checks that a human may run (shown as text, this tool never runs them):

```
SELECT count(*) FROM pg_stat_activity;
SELECT pid, state, now() - query_start AS running FROM pg_stat_activity ORDER BY running DESC LIMIT 10;
```

## What to look for in the logs
- Stack traces containing `HikariPool.getConnection` or a similar pool class.
- The same error across several services that share one database.
- Retry storms: many identical requests a few hundred milliseconds apart.

## Escalation
If the database host is unreachable or the connection limit is reached, contact the database owners. Changes to pool size or database settings need a reviewed change request.
