# API Latency Spikes and Slow Responses

> SYNTHETIC EXAMPLE RUNBOOK written for this demo project. It is not real operational guidance.

## Symptoms
- Request durations (`latency`, `duration`, `took`) far above the usual level for an endpoint.
- Timeouts reported by a gateway or a client, with few outright failures at first.
- A falling cache hit ratio, for example "Cache hit ratio dropped", or a cache that was recently restarted or flushed.

## Common causes
1. A cache lost its content (restart, eviction, key change), so every request goes to the slower backend.
2. A slow downstream dependency (database, third-party API).
3. CPU or memory pressure, long garbage-collection pauses.
4. A traffic increase or a retry storm.

## Diagnostic steps (read-only)
1. Find the endpoint and the service where the slowdown starts. Compare its latency with the baseline before the incident.
2. Check the cache hit ratio and cache restarts for the same time window.
3. Check downstream call durations (database queries, internal APIs) to see where the time is spent.
4. Check CPU, memory and garbage-collection metrics of the slow service.
5. Compare request volume with the previous day at the same time to rule out a traffic spike.

## What to look for in the logs
- A latency value that rises step by step in consecutive records.
- Cache warnings shortly before the slow requests.
- Timeouts that name the same downstream host.

## Escalation
If the cause is a downstream team's service, share the time window and the evidence record ids with them.
