"""Finding-cohort counters and the allowed public histogram vocabulary."""
from collections import Counter

# Unknown/free-form labels are counted under unknown at the HTTP boundary.
# Arbitrary dictionary keys must not become a route around evidence redaction.
PUBLIC_CATEGORIES = frozenset({
    "sqli", "sql_injection", "xss", "ssrf", "rce", "idor", "xxe", "csrf",
    "lfi", "rfi", "ssti", "auth", "authentication", "authorization",
    "access_control", "config", "configuration", "misconfiguration",
    "information_disclosure", "injection", "other", "unknown",
})


def finding_stats(findings):
    counters = {key: Counter() for key in ("severity", "category", "status")}
    for finding in findings:
        for key, default in (("severity", "unknown"), ("category", "unknown"), ("status", "unconfirmed")):
            value = str(finding.get(key) or default)
            counters[key][value.lower() if key == "severity" else value] += 1
    return {"by_" + key: dict(counter) for key, counter in counters.items()}


def public_histogram(raw, allowed):
    if not isinstance(raw, dict):
        return {}
    result = Counter()
    for key, count in raw.items():
        if type(count) is int and count >= 0:
            result[key if key in allowed else "unknown"] += count
    return dict(result)
