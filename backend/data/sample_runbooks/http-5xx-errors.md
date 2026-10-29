# HTTP 5xx Errors After a Deployment

> SYNTHETIC EXAMPLE RUNBOOK written for this demo project. It is not real operational guidance.

## Symptoms
- A sudden rise of HTTP 500, 502, 503 or 504 responses for one endpoint or one service.
- The same exception type repeated in many requests, for example `NullPointerException` or `IllegalStateException`, with the same top stack frame.
- The start of the errors is close to a deployment or a configuration rollout.

## Common causes
1. A code defect introduced by the latest release (a missing null check, a changed contract between services).
2. A configuration or secret that is missing in the new release.
3. An upstream service that returns errors, which the gateway turns into 502 or 503.

## Diagnostic steps (read-only)
1. Note the time of the first 5xx response and check the deployment history for a release shortly before it.
2. Read the top stack frame of the repeated exception. Which class and method is it?
3. Check whether only one version or one instance group is affected (a partial rollout shows a clear split).
4. Check the error rate per endpoint to see whether it is one route or the whole service.
5. Compare the failing request's payload shape with requests that worked before the release.

## What to look for in the logs
- One dominant exception type and one repeated stack frame.
- A gateway error such as "Upstream returned 503" appearing right after the service error.
- Errors that stop for a short time and return (a restart loop).

## Escalation
The service owner decides about a rollback. This tool only shows evidence and does not change releases.
