# Network Timeouts, Packet Loss and Route Failover

> SYNTHETIC EXAMPLE RUNBOOK written for this demo project. It is not real operational guidance.

## Symptoms
- "Connection timed out", "no route to host", "BGP session down" or "link flap" messages.
- Rising packet loss or round-trip time on a link or a route, reported by a link monitor.
- Traffic moving to a backup path (failover) with higher latency.
- Several unrelated services time out at the same moment when they share a network path.

## Common causes
1. A faulty physical link, optics or cable (errors and flaps on one interface).
2. An overloaded link or a congested path.
3. A routing change or a peer that stopped announcing its routes.
4. A firewall or security-group change that drops traffic.

## Diagnostic steps (read-only)
1. List the interfaces, routes and peers named in the error messages and the time of the first message for each.
2. Check interface error counters and packet-loss figures for those links in the incident window.
3. Check the state history of the routing sessions (when they went down and came back).
4. Check whether traffic shifted to a backup route and what its latency was.
5. Check recent network or firewall changes made shortly before the first message.

Example read-only checks that a human may run (shown as text, this tool never runs them):

```
ping -c 20 <next-hop>
traceroute <destination>
```

## What to look for in the logs
- The same peer or route id repeated in many messages.
- Latency that rises on a primary route and then drops after a failover message.

## Escalation
Contact the network team with the interface or peer name, the incident window and the evidence record ids.
