"""Reviewable remediation publication plans; execution is separately opt-in.

Never called by the dashboard, scheduler or remediation pipeline. During the
reconstruction task this module is tested only with fake transports. A future
operator must explicitly choose --execute AND set DARKMOON_ALLOW_PUBLISH=1.
"""
import argparse
import json
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from api import json_storage as data
from .remediation import git
from .store import Store, identifier, now


def destination(url, forge):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Destination must be an HTTPS repository URL without credentials, query or fragment")
    if not parsed.hostname:
        raise ValueError("Destination hostname is required")
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) < 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) and p not in {".", ".."} for p in parts):
        raise ValueError("Destination path must be owner/project (GitLab may have subgroups)")
    if forge in {"github", "gitea"} and len(parts) != 2:
        raise ValueError("GitHub/Gitea destinations require owner/project")
    if forge == "github" and parsed.hostname != "github.com":
        raise ValueError("This GitHub adapter supports github.com; use an explicit new adapter for Enterprise")
    base = f"https://{parsed.netloc}"
    endpoint = ("https://api.github.com/repos/" + path + "/pulls" if forge == "github" else
                base + "/api/v4/projects/" + urllib.parse.quote(path, safe="") + "/merge_requests" if forge == "gitlab" else
                base + "/api/v1/repos/" + path + "/pulls")
    return base + "/" + path + ".git", endpoint


def publication_plan(result, url, forge="github", base="main"):
    if forge not in {"github", "gitlab", "gitea"}:
        raise ValueError("Supported forges: github, gitlab, gitea")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,199}", base) or ".." in base or base.endswith("/"):
        raise ValueError("Invalid base branch")
    if result.get("status") not in {"proposed", "validated", "validation_failed"} or not result.get("patch_path"):
        raise ValueError("A saved local patch is required")
    repo_url, endpoint = destination(url, forge)
    branch = "remediation/" + identifier(result["id"])
    draft = result["status"] != "validated"
    summary = ("Local remediation proposal for " + str(result.get("finding_id", "")) + ".\n\n"
               + str(result.get("explanation", "")) + "\n\n"
               + "Validation disposition: " + result["status"] + ".\n"
               + "Human review and manual merge required.\n\n"
               + "Before/after probe results:\n```json\n"
               + json.dumps({phase: [{"name": p.get("name"), "kind": p.get("kind"), "passed": p.get("passed"),
                                      "exit_code": p.get("exit_code"), "timed_out": p.get("timed_out")}
                                     for p in result.get("validation", {}).get(phase, [])] for phase in ("before", "after")}, indent=2)
               + "\n```\n\nLocal evidence is retained with the proposal. Raw evidence is not uploaded automatically.")
    title = "Fix: " + str(result.get("title") or result.get("finding_id", "finding"))[:150]
    if forge == "gitlab":
        payload = {"title": ("Draft: " if draft else "") + title, "source_branch": branch, "target_branch": base,
                   "description": summary, "remove_source_branch": False}
    elif forge == "gitea":
        # CreatePullRequestOption does not accept the response's draft field.
        # Gitea uses configured WIP title prefixes (default: WIP: / [WIP]).
        payload = {"title": ("WIP: " if draft else "") + title, "head": branch, "base": base, "body": summary}
    else:
        payload = {"title": title, "head": branch, "base": base, "body": summary, "draft": draft}
    return {"proposal_id": result["id"], "forge": forge, "destination": repo_url,
            "push_argv": ["git", "-c", "credential.helper=", "-c", "core.hooksPath=/dev/null", "push", "--no-verify", repo_url, f"HEAD:refs/heads/{branch}"],
            "request": {"method": "POST", "url": endpoint, "json": payload}, "draft": draft, "merge": False}


def request_json(url, payload, token, forge):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    auth = {"PRIVATE-TOKEN": token} if forge == "gitlab" else {"Authorization": ("token " if forge == "gitea" else "Bearer ") + token}
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Accept": "application/json", **auth})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=60) as response:
        body = response.read(1024 * 1024 + 1)
    if len(body) > 1024 * 1024:
        raise ValueError("Forge response exceeds 1 MiB; inspect the destination before retrying")
    return json.loads(body)


def publish(store, proposal_id, url, forge="github", base="main", execute=False, run=subprocess.run, post=request_json):
    identifier(proposal_id)
    path = store.root / "remediation" / proposal_id / "result.json"
    result = data._read_json(path)
    if not isinstance(result, dict):
        raise ValueError("Proposal not found")
    plan = publication_plan(result, url, forge, base)
    if not execute:
        return {"executed": False, "plan": plan}
    if os.environ.get("DARKMOON_ALLOW_PUBLISH") != "1":
        raise ValueError("Execution additionally requires DARKMOON_ALLOW_PUBLISH=1")
    token = os.environ.get("DARKMOON_FORGE_TOKEN", "")
    if not token and result.get("credential_ref"):
        from .auth import CredentialVault
        token = CredentialVault(store).resolve(result["credential_ref"])
    if not token:
        raise ValueError("DARKMOON_FORGE_TOKEN is required for explicit publication")
    username = os.environ.get("DARKMOON_FORGE_USERNAME") or ("oauth2" if forge == "gitlab" else "x-access-token")
    if forge == "gitea" and not os.environ.get("DARKMOON_FORGE_USERNAME"):
        raise ValueError("Gitea publication also requires DARKMOON_FORGE_USERNAME")
    # Serialize publication, so a double invocation cannot create duplicate PRs.
    with data._file_lock(path):
        result = data._read_json(path)
        prior = result.get("publication", {})
        if prior.get("url"):
            return {"executed": True, "publication": prior}
        if prior.get("destination") and prior["destination"] != plan["destination"]:
            raise ValueError("Proposal was already pushed to a different destination")
        worktree = Path(result["worktree"])
        if git(worktree, "symbolic-ref", "--short", "HEAD") != result["branch"]:
            raise ValueError("Proposal worktree is no longer on its recorded branch")
        patch = (path.parent / "fix.patch").read_text().rstrip("\n")
        if prior.get("commit"):
            if git(worktree, "rev-parse", "HEAD") != prior["commit"] or git(worktree, "status", "--porcelain"):
                raise ValueError("Committed proposal changed since its first publication attempt")
        else:
            current = git(worktree, "diff", "--no-ext-diff", "--no-textconv", result["base_commit"], "--")
            if current.rstrip("\n") != patch or git(worktree, "ls-files", "--others", "--exclude-standard"):
                raise ValueError("Proposal differs from the recorded patch; review and revalidate it")
            # Only the recorded source paths are staged. Commit identity comes
            # from the operator's Git configuration; no identity is invented.
            git(worktree, "-c", "core.hooksPath=/dev/null", "add", "--", *result["changed_files"])
            git(worktree, "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "commit", "-m", plan["request"]["json"]["title"])
            prior.update(commit=git(worktree, "rev-parse", "HEAD"), destination=plan["destination"], started_at=now())
            result["publication"] = prior
            data._write_json(path, result)
        # Askpass is a fixed script, contains no secret, and is removed on exit.
        # The token is not placed in URL, Git config, argv, prompt or output.
        with tempfile.TemporaryDirectory(prefix="darkmoon-askpass-") as temporary:
            helper = Path(temporary) / "askpass"
            helper.write_text('#!/bin/sh\ncase "$1" in *Username*) printf "%s\\n" "$DM_GIT_USERNAME";; *) printf "%s\\n" "$DARKMOON_FORGE_TOKEN";; esac\n')
            helper.chmod(0o700)
            env = {**os.environ, "GIT_ASKPASS": str(helper), "GIT_TERMINAL_PROMPT": "0",
                   "DM_GIT_USERNAME": username, "DARKMOON_FORGE_TOKEN": token}
            if not prior.get("branch_pushed"):
                completed = run(plan["push_argv"], cwd=worktree, env=env, capture_output=True, text=True, timeout=120)
                if completed.returncode != 0:
                    raise ValueError("Git push failed; inspect the destination and local proposal before retrying")
                prior.update(branch_pushed=True)
                result["publication"] = prior
                data._write_json(path, result)
        # Mark the request before making it. An ambiguous response must be
        # reconciled by a human instead of blindly creating a second PR.
        if prior.get("pr_request_started"):
            raise ValueError("A previous PR request has an ambiguous result; inspect the forge before retrying")
        prior["pr_request_started"] = now()
        data._write_json(path, result)
        response = post(plan["request"]["url"], plan["request"]["json"], token, forge)
        pr_url = response.get("html_url") or response.get("web_url")
        if not isinstance(pr_url, str) or not pr_url.startswith("https://"):
            raise ValueError("Forge response lacked a PR URL; inspect the destination")
        prior.update(url=pr_url, id=response.get("number") or response.get("iid") or response.get("id"),
                     completed_at=now(), draft=plan["draft"])
        result.update(publication=prior, published=True)
        data._write_json(path, result)
        return {"executed": True, "publication": prior}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal-id", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--forge", choices=("github", "gitlab", "gitea"), default="github")
    parser.add_argument("--base", default="main")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(publish(Store(args.state_dir), args.proposal_id, args.destination, args.forge, args.base, args.execute), indent=2))


if __name__ == "__main__":
    main()
