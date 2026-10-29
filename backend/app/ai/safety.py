"""
Safety helpers.

This application has no code path that runs a command, restarts a service or changes a configuration. These helpers add
a second layer: text that LOOKS like a change to a system is never recommended as a diagnostic step.
"""
from __future__ import annotations

import re

# Verbs and shell patterns that change something. A diagnostic step may read, compare, count or check; it may not do these.
_CHANGE_PATTERNS = [
    r"\b(restart|reboot|redeploy|roll\s*back|rollback|scale\s+(up|down|out)|fail over to)\b",
    r"\b(delete|remove|drop|truncate|purge|wipe|kill|terminate|stop|shut\s*down|disable|enable)\s+(the\s+|a\s+|all\s+)?(\w+\s+)?(service|server|pod|container|process|table|database|index|cache|queue|user|account|instance|node|port|rule|route|job|key|secret|certificate|file|files|logs?)\b",
    r"\b(set|change|increase|decrease|raise|lower|update|modify|edit|apply|patch|upgrade|downgrade|reset|flush|clear|rotate|revoke|block|unblock|unlock|lock)\s+(the\s+|a\s+|all\s+)?(\w+\s+)?(config|configuration|setting|settings|limit|pool size|pool|timeout|password|credential|credentials|key|secret|certificate|firewall|address|addresses|ip|ips|account|accounts|cache|schema|version|route|routes|permission|permissions)\b",
    r"\bsystemctl\s+(restart|stop|start|reload|disable|enable)\b",
    r"\bkubectl\s+(delete|apply|scale|rollout|patch|replace|drain|cordon|edit|exec)\b",
    r"\b(rm|mv|chmod|chown|kill|pkill|shutdown|reboot|iptables|ufw)\s+-?\S*",
    r"\b(DROP|DELETE|TRUNCATE|UPDATE|ALTER|INSERT)\s+(TABLE|FROM|INTO|DATABASE|INDEX|\w+\s+SET)\b",
    r"\bdocker\s+(rm|stop|kill|restart|rmi|prune)\b",
]
_CHANGE_RE = re.compile("|".join(f"(?:{p})" for p in _CHANGE_PATTERNS), re.IGNORECASE)


def looks_like_change(text: str) -> str | None:
    """Return the matching phrase if the text reads like an action that changes a system, otherwise None."""
    match = _CHANGE_RE.search(text or "")
    return match.group(0).strip() if match else None


def clip(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
