"""Launch choices derived from upstream scope docs; no remote fetch at runtime."""

NOISE_LEVELS = ["stealth", "low", "moderate"]
SEVERITY_CAPS = ["critical", "high", "medium", "low"]
FOCUS = [
    ("sqli", "SQL injection"),
    ("xss", "Cross-site scripting"),
    ("idor", "Access control / IDOR"),
    ("auth-bypass", "Authentication bypass"),
    ("jwt", "JWT security"),
    ("ssrf", "Server-side request forgery"),
    ("rce", "Remote code execution"),
    ("lfi", "File inclusion"),
    ("deserialization", "Unsafe deserialization"),
    ("graphql", "GraphQL"),
    ("auth", "Authentication"),
    ("api", "API security"),
    ("web", "Web application"),
    ("configuration", "Configuration"),
    ("html-injection", "HTML injection"),
    ("llm", "AI / LLM endpoints"),
    ("dos", "Denial of service"),
    ("bruteforce", "Brute force"),
]
EXCLUSIONS = [
    ("H1", "HackerOne core ineligible findings"),
    ("dom-xss", "DOM XSS"),
    ("self-xss", "Self XSS"),
    ("clickjacking", "Clickjacking"),
    ("open-redirect", "Open redirects"),
    ("brute-force", "Brute force"),
    ("rate-limiting", "Rate-limit testing"),
    ("CWE-352", "CSRF / CWE-352"),
    ("dos", "Denial of service"),
]
PRESETS = [
    {
        "id": "custom",
        "label": "Custom engagement",
        "focus": [],
        "exclude": [],
        "noise": "moderate",
        "format": "standard",
    },
    {
        "id": "web",
        "label": "Web application review",
        "focus": ["sqli", "xss", "idor", "auth-bypass"],
        "exclude": ["dos", "brute-force"],
        "noise": "moderate",
        "format": "standard",
    },
    {
        "id": "api",
        "label": "API / GraphQL review",
        "focus": ["api", "graphql", "idor", "jwt", "auth-bypass"],
        "exclude": ["dos", "brute-force"],
        "noise": "low",
        "format": "standard",
    },
    {
        "id": "bounty",
        "label": "HackerOne engagement",
        "focus": ["sqli", "xss", "idor", "auth-bypass", "ssrf"],
        "exclude": ["H1", "dom-xss", "self-xss", "clickjacking", "dos", "brute-force"],
        "noise": "low",
        "format": "h1",
    },
    {
        "id": "lab",
        "label": "Local lab verification",
        "focus": ["web", "configuration"],
        "exclude": ["dos", "brute-force"],
        "noise": "low",
        "format": "standard",
    },
]
SOURCES = {
    "scope": "https://github.com/ASCIT31/Dark-Moon/blob/master/docs/full.md#ii7c-launch-darkmoon-with-tui-console",
    "integrations": "https://github.com/ASCIT31/Dark-Moon#-darkmoon-everywhere",
    "n8n": "https://github.com/ASCIT31/darkmoon-n8n",
    "benchmark": "https://github.com/ASCIT31/Darkmoon-Benchmarks",
}
INTEGRATIONS = [
    {"name": name, "url": url, "usage": usage}
    for name, url, usage in [
        (
            "GitHub Actions",
            "https://github.com/marketplace/actions/darkmoon-pentest",
            "CI severity gates and report artifacts",
        ),
        (
            "GitLab CI/CD",
            "https://gitlab.com/explore/catalog/Dark-Moon-X/darkmoon-scan",
            "Code Quality and SAST reports",
        ),
        (
            "Jenkins",
            "https://github.com/ASCIT31/darkmoon-jenkins",
            "Warnings-NG findings",
        ),
        (
            "VS Code",
            "https://marketplace.visualstudio.com/items?itemName=Darkmoon.darkmoon-vscode",
            "Editor campaigns and findings",
        ),
        (
            "JetBrains",
            "https://plugins.jetbrains.com/plugin/34497-darkmoon",
            "IDE campaign views",
        ),
        (
            "n8n",
            SOURCES["n8n"],
            "Campaigns, findings, reports, retests, metrics and signed events",
        ),
        (
            "Grafana",
            "https://github.com/ASCIT31/darkmoon-grafana",
            "Security-posture dashboards",
        ),
        (
            "Splunk",
            "https://github.com/ASCIT31/darkmoon-splunk",
            "Metadata ingestion and alert actions",
        ),
        (
            "SDK / CLI",
            "https://www.npmjs.com/package/@darkmoon_ai/client",
            "Authenticated API clients",
        ),
    ]
]


def catalog():
    def choices(pairs):
        return [{"value": value, "label": label} for value, label in pairs]

    return {
        "focus": choices(FOCUS),
        "exclude": choices(list(dict(EXCLUSIONS + FOCUS).items())),
        "noise": NOISE_LEVELS,
        "severity_caps": SEVERITY_CAPS,
        "formats": choices(
            [
                ("standard", "Standard"),
                ("h1", "HackerOne"),
                ("bugcrowd", "Bugcrowd"),
                ("custom", "Custom"),
            ]
        ),
        "presets": PRESETS,
        "sources": SOURCES,
        "integrations": INTEGRATIONS,
        "severity_semantics": "Maximum severity cap for the assessment; not a minimum reporting filter",
    }
