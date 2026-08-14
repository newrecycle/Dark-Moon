"""Non-Docker tests for the bounded headless-browser workflow."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.common import ExecutionResult, ExecutionStatus  # noqa: E402
from src.tools.browser.policy import (  # noqa: E402
    ALLOWED_MODES,
    ALLOWED_WAIT_UNTIL,
    BROWSER_LIMITS,
    BrowserPolicyError,
    normalize_browser_request,
    scrub_browser_output,
    validate_target_url,
)
from src.tools.workflows.headless_browser import HeadlessBrowserWorkflow  # noqa: E402
from src.tools.workflows.list_workflows import WorkflowRegistry  # noqa: E402


class FakeClient:
    def __init__(self, result: ExecutionResult | None = None):
        self.commands = []
        self.result = result or ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            stdout=json.dumps(
                {
                    "ok": True,
                    "engine": {
                        "name": "playwright-chromium",
                        "playwright_version": "1.62.1",
                    },
                    "pages": [],
                    "network": {"requests": [], "responses": [], "failures": []},
                    "console": [],
                    "blocked_requests": [],
                    "artifacts": [],
                    "summary": {"pages_visited": 0},
                }
            ),
            exit_code=0,
        )

    def execute_command(self, command, **kwargs):
        self.commands.append((command, kwargs))
        return self.result


def test_request_normalization_is_bounded():
    request = normalize_browser_request(
        url="https://app.example.test/path",
        mode="snapshot",
        max_pages=9,
        max_depth=3,
    )
    assert request["max_pages"] == 1
    assert request["max_depth"] == 0

    crawl = normalize_browser_request(
        url="https://app.example.test/path",
        mode="crawl",
        max_pages=5,
        max_depth=2,
    )
    assert crawl["max_pages"] == 5
    assert crawl["max_depth"] == 2
    assert crawl["follow_links"] is True

    linked_snapshot = normalize_browser_request(
        url="https://app.example.test/path",
        mode="links",
        max_pages=7,
        max_depth=4,
        follow_links=True,
        wait_until="networkidle",
    )
    assert linked_snapshot["max_pages"] == 7
    assert linked_snapshot["max_depth"] == 4
    assert linked_snapshot["follow_links"] is True
    assert linked_snapshot["wait_until"] == "networkidle"


@pytest.mark.parametrize("mode", sorted(ALLOWED_MODES))
def test_all_advertised_browser_modes_are_accepted(mode):
    request = normalize_browser_request(
        url="https://app.example.test/path",
        mode=mode,
    )
    assert request["mode"] == mode
    assert request["screenshot"] is (mode == "screenshot")


@pytest.mark.parametrize("wait_until", sorted(ALLOWED_WAIT_UNTIL))
def test_all_advertised_wait_modes_are_accepted(wait_until):
    request = normalize_browser_request(
        url="https://app.example.test/path",
        wait_until=wait_until,
    )
    assert request["wait_until"] == wait_until


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,test",
        "https://user:password@app.example.test/",
        "https://app.example.test\\@other.example/",
        "https://app.example.test/with space",
        "https://",
    ],
)
def test_target_url_rejects_unsafe_forms(url):
    with pytest.raises(BrowserPolicyError):
        validate_target_url(url)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_pages", 51),
        ("max_depth", 9),
        ("max_requests", 2501),
        ("timeout", 601),
        ("settle_ms", 30001),
    ],
)
def test_request_limits_fail_closed(field, value):
    kwargs = {field: value}
    with pytest.raises(BrowserPolicyError):
        normalize_browser_request(url="https://app.example.test/", **kwargs)


def test_request_limits_reject_fractional_numbers():
    with pytest.raises(BrowserPolicyError, match="must be an integer"):
        normalize_browser_request(
            url="https://app.example.test/", max_requests=20.5
        )


def test_request_rejects_unknown_mode_and_wait_strategy():
    with pytest.raises(BrowserPolicyError, match="mode must be one of"):
        normalize_browser_request(
            url="https://app.example.test/", mode="unbounded"
        )
    with pytest.raises(BrowserPolicyError, match="wait_until must be one of"):
        normalize_browser_request(
            url="https://app.example.test/", wait_until="forever"
        )


def test_browser_output_drops_state_and_redacts_values():
    cleaned = scrub_browser_output(
        {
            "url": "https://app.example.test/search?q=private&token=secret",
            "headers": {"authorization": "Bearer do-not-return-this"},
            "cookies": [{"value": "do-not-return-this"}],
            "local_storage": {"token": "do-not-return-this"},
            "responseHeaders": {"x-session": "do-not-return-this"},
            "console": (
                "Bearer abcdefghijklmnop password=hunter2 "
                "sk-abcdefghijklmnopqrstuvwxyz"
            ),
        }
    )
    assert "headers" not in cleaned
    assert "cookies" not in cleaned
    assert "local_storage" not in cleaned
    assert "responseHeaders" not in cleaned
    serialized = json.dumps(cleaned)
    assert "private" not in serialized
    assert "token=secret" not in serialized.lower()
    assert "hunter2" not in serialized.lower()
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in serialized
    assert "REDACTED" in serialized


def test_workflow_uses_fixed_argv_and_encoded_request():
    client = FakeClient()
    workflow = HeadlessBrowserWorkflow(client)
    result = workflow.analyze(
        "https://app.example.test/search?q=sensitive",
        mode="crawl",
        max_pages=4,
        max_depth=2,
        screenshot=True,
    )

    assert result["ok"] is True
    command, options = client.commands[0]
    assert isinstance(command, list)
    assert command[0] == "node"
    assert command[1].endswith("/src/tools/browser/headless_runner.mjs")
    assert "app.example.test" not in " ".join(command)
    decoded = json.loads(base64.urlsafe_b64decode(command[2]).decode("utf-8"))
    assert decoded["url"] == "https://app.example.test/search?q=sensitive"
    assert decoded["max_pages"] == 4
    assert decoded["max_depth"] == 2
    assert decoded["screenshot"] is True
    assert decoded["follow_links"] is True
    assert decoded["wait_until"] == "domcontentloaded"
    assert options["workdir"] == "/opt/darkmoon"


def test_workflow_returns_structured_runner_failure():
    client = FakeClient(
        ExecutionResult(
            status=ExecutionStatus.FAILED,
            stdout="",
            stderr="playwright runtime unavailable",
            exit_code=1,
        )
    )
    result = HeadlessBrowserWorkflow(client).analyze("https://app.example.test/")
    assert result["ok"] is False
    assert result["error"]["code"] == "runner_failure"
    assert result["has_errors"] is True


def test_dynamic_registry_discovers_headless_browser():
    metadata = WorkflowRegistry(FakeClient()).list_workflows()
    assert "headless_browser" in metadata["available_workflows"]
    browser = metadata["workflows"]["headless_browser"]
    assert "analyze" in browser["methods"]
    capabilities = browser["capabilities"]
    assert set(capabilities["modes"]) == ALLOWED_MODES
    assert set(capabilities["wait_until"]) == ALLOWED_WAIT_UNTIL
    assert capabilities["limits"] == BROWSER_LIMITS
    parameters = browser["methods"]["analyze"]["parameters"]
    assert parameters["follow_links"]["default"] is False
    assert parameters["wait_until"]["default"] == "domcontentloaded"


def test_mode_projections_return_only_requested_collectors():
    projection = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "tools"
        / "browser"
        / "projection.mjs"
    )
    program = r"""
const { projectPage } = await import(process.argv[1]);
const page = {
  url: "https://app.example.test/",
  title: "Test",
  depth: 0,
  status: 200,
  text_excerpt: "content",
  headings: ["heading"],
  links: ["link"],
  forms: ["form"],
  scripts: ["script"],
  event_handlers: ["handler"],
  accessibility: ["node"],
  performance: { duration_ms: 1 },
  security: { mixed_content_resources: 0 },
};
const projected = {};
for (const mode of [
  "snapshot", "crawl", "full", "content", "metadata", "links", "forms",
  "scripts", "dom_sinks", "network", "console", "accessibility",
  "performance", "security", "screenshot",
]) projected[mode] = Object.keys(projectPage(page, mode)).sort();
process.stdout.write(JSON.stringify(projected));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", program, projection.as_uri()],
        check=True,
        capture_output=True,
        text=True,
    )
    projected = json.loads(completed.stdout)
    complete_fields = sorted(
        [
            "accessibility",
            "depth",
            "event_handlers",
            "forms",
            "headings",
            "links",
            "performance",
            "scripts",
            "security",
            "status",
            "text_excerpt",
            "title",
            "url",
        ]
    )
    for mode in ("snapshot", "crawl", "full"):
        assert projected[mode] == complete_fields
    assert projected["content"] == sorted(
        ["depth", "headings", "status", "text_excerpt", "title", "url"]
    )
    assert projected["network"] == ["depth", "status", "title", "url"]
    assert projected["accessibility"] == sorted(
        ["accessibility", "depth", "status", "title", "url"]
    )
    assert projected["security"] == sorted(
        [
            "depth",
            "event_handlers",
            "forms",
            "scripts",
            "security",
            "status",
            "title",
            "url",
        ]
    )


@pytest.mark.parametrize(
    "params",
    [
        {"max_requests": 20.5},
        {"same_origin": "sometimes"},
    ],
)
def test_registry_cannot_coerce_invalid_browser_bounds(params):
    client = FakeClient()
    result = WorkflowRegistry(client).run_workflow(
        "headless_browser",
        "analyze",
        {"url": "https://app.example.test/", **params},
    )
    assert "error" in result
    assert client.commands == []
