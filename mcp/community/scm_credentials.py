"""SCM request-field schemas for the existing encrypted checkout adapter.

Connection metadata is descriptive configuration, not an authorization scope
or a provider API implementation. Checkout still uses its explicitly supplied
repository URL; publication keeps its separate operator opt-ins.
"""
from urllib.parse import urlsplit


SCM_PROVIDERS = {
    "github": {"name": "GitHub", "fields": ("endpoint_url", "username", "token"),
               "required": ("token",), "endpoint": "https://api.github.com"},
    "gitlab": {"name": "GitLab", "fields": ("endpoint_url", "token"),
               "required": ("token",), "endpoint": "https://gitlab.com"},
    "gitea": {"name": "Gitea", "fields": ("endpoint_url", "username", "token"),
              "required": ("endpoint_url", "token")},
    "gogs": {"name": "Gogs", "fields": ("endpoint_url", "username", "token"),
             "required": ("endpoint_url", "token")},
    "bitbucket": {"name": "Bitbucket", "fields": ("endpoint_url", "username", "token"),
                  "required": ("username", "token"), "endpoint": "https://api.bitbucket.org/2.0"},
    "azure_devops": {"name": "Azure DevOps", "fields": ("endpoint_url", "project", "token"),
                     "required": ("endpoint_url", "token")},
    "generic_git": {"name": "Generic Git over HTTPS", "fields": ("endpoint_url", "username", "token"),
                    "required": ("token",), "endpoint": ""},
}


def endpoint(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("Invalid SCM endpoint URL")
    if not value:
        return value
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == "https" and parsed.hostname and parsed.username is None
                 and parsed.password is None and "?" not in value and "#" not in value
                 and "\\" not in value and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
                 and (parsed.port is None or 1 <= parsed.port <= 65535))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("SCM endpoint must be HTTPS without credentials, query or fragment")
    return value


def catalog():
    return [{"id": key, "name": spec["name"], "label": spec["name"], "group": "Source control",
             "capabilities": ["source_checkout"],
             "adapter": "scm_token", "default_scope": "private",
             "fields": [{"name": field, "type": "password" if field == "token" else "text",
                         "secret": field == "token", "required": field in spec["required"],
                         **({"default": spec["endpoint"]} if field == "endpoint_url" and "endpoint" in spec else {})}
                        for field in spec["fields"]]}
            for key, spec in SCM_PROVIDERS.items()]
