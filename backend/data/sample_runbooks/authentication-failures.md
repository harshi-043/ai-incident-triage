# Authentication Failures and Login Spikes

> SYNTHETIC EXAMPLE RUNBOOK written for this demo project. It is not real operational guidance.

## Symptoms
- Many "Invalid credentials", "authentication failed", HTTP 401 or 403 responses in a short time.
- Failures for many different accounts from few source addresses (possible credential stuffing), or failures for one account from many addresses.
- Account lock-out messages.
- Failures for every user at once after a change (expired signing key or certificate, clock skew, identity provider outage).

## Common causes
1. A real attack (password guessing against many accounts).
2. An expired or rotated key, secret or certificate.
3. A problem in the identity provider or a clock difference between servers.
4. A client with a wrong stored password that retries in a loop.

## Diagnostic steps (read-only)
1. Count failures per account and per source address in the incident window.
2. Check whether successful logins continued during the same time. If they did, the identity system itself is working.
3. Check whether the failures started at a time that matches a key, secret or certificate change.
4. Check for lock-out messages and whether they affect real users.
5. Compare the source addresses with known internal ranges.

## What to look for in the logs
- A single address with a very high attempt count.
- The same error text for different accounts one after another.

## Escalation
Share the evidence with the security team if the pattern looks like an attack. Blocking addresses or resetting accounts is a decision for authorised staff.
