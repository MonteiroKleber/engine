from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


# Prefer a stable alias. If the account doesn't have access, we fall back at runtime.
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "").strip() or "claude-3-5-sonnet-latest"

MODEL_FALLBACKS = [
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-latest",
    "claude-3-sonnet-latest",
    "claude-3-haiku-latest",
]

# Cache of model availability to avoid repeated 404s.
_WORKING_MODEL: Optional[str] = None
_BAD_MODELS: set[str] = set()


@dataclass(frozen=True)
class Env:
    base_url: str
    institution_id: str
    user_token: str
    mod_token: str
    tsm_token: str
    admin_token: str
    anthropic_api_key: str
    claude_model: str


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing env: {name}")
    return value


def load_env(args: argparse.Namespace) -> Env:
    base_url = (args.base_url or os.environ.get("ENGINE_BASE_URL") or "").strip() or "http://127.0.0.1:8001"
    base_url = base_url.rstrip("/")
    institution_id = (args.institution_id or os.environ.get("INSTITUTION_ID") or "").strip()
    if not institution_id:
        raise SystemExit("Missing INSTITUTION_ID (arg --institution-id or env INSTITUTION_ID)")

    return Env(
        base_url=base_url,
        institution_id=institution_id,
        user_token=_require_env("USER_TOKEN"),
        mod_token=_require_env("MOD_TOKEN"),
        tsm_token=_require_env("TSM_TOKEN"),
        admin_token=_require_env("ADMIN_TOKEN"),
        anthropic_api_key=_require_env("ANTHROPIC_API_KEY"),
        claude_model=os.environ.get("CLAUDE_MODEL", "").strip() or DEFAULT_MODEL,
    )


@dataclass
class HttpResult:
    status: int
    json: Optional[Any]
    text: str


def engine_request(
    env: Env,
    method: str,
    path: str,
    role: str,
    body: Optional[dict[str, Any]] = None,
) -> HttpResult:
    token_by_role = {
        "user": env.user_token,
        "moderator": env.mod_token,
        "tsm": env.tsm_token,
        "admin": env.admin_token,
    }
    if role not in token_by_role:
        raise ValueError(f"Unknown role: {role}")

    url = f"{env.base_url}{path}"
    headers = {"X-Institution-Id": env.institution_id, "X-Actor-Token": token_by_role[role]}
    data: Optional[bytes] = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            parsed = None
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            return HttpResult(status=getattr(resp, "status", 200), json=parsed, text=text)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        parsed = None
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        return HttpResult(status=int(getattr(e, "code", 0) or 0), json=parsed, text=text)


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME", "").strip()
    if base:
        return Path(base) / "libervia_llm_runs"
    return Path.home() / ".local" / "state" / "libervia_llm_runs"


def write_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def call_claude_messages(env: Env, messages: list[dict[str, Any]]) -> str:
    url = "https://api.anthropic.com/v1/messages"
    def _do_call(model: str) -> str:
        print(f"[llm] calling Anthropic model={model}", file=sys.stderr)
        payload = {
            "model": model,
            "system": SYSTEM_PROMPT,
            "max_tokens": 900,
            "temperature": 0,
            # NOTE: Anthropic Messages API does not accept role="system" inside messages.
            # System prompt must be provided via the top-level "system" field.
            "messages": [m for m in messages if m.get("role") != "system"],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            method="POST",
            headers={
                "x-api-key": env.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            data=data,
        )
        with urllib.request.urlopen(req, timeout=40) as resp:
            raw = resp.read().decode("utf-8", errors="replace")

        obj = json.loads(raw)
        content = obj.get("content") or []
        # Expect text blocks
        texts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(str(block.get("text") or ""))
        return "\n".join(texts).strip()

    global _WORKING_MODEL
    tried: list[str] = []
    candidates = []
    if _WORKING_MODEL:
        candidates.append(_WORKING_MODEL)
    candidates.append(env.claude_model)
    candidates.extend(MODEL_FALLBACKS)

    for model in candidates:
        if model in tried:
            continue
        if model in _BAD_MODELS:
            continue
        tried.append(model)
        try:
            text = _do_call(model)
            _WORKING_MODEL = model
            return text
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            if int(getattr(e, "code", 0) or 0) == 404:
                print(f"[llm] model not available (404), trying next. model={model}", file=sys.stderr)
                _BAD_MODELS.add(model)
                continue
            raise RuntimeError(f"Anthropic API error: HTTP {e.code}: {raw}") from e

    raise RuntimeError(f"Anthropic API error: no working model found. Tried: {tried}")


ALLOWLIST: set[tuple[str, str]] = {
    ("POST", "/reports"),
    ("GET", "/reports/my"),
    ("GET", "/reports/{report_id}"),
    ("GET", "/moderation/reports"),
    ("POST", "/moderation/reports/{report_id}/triage"),
    ("POST", "/chat/reports"),
    ("POST", "/chat/blocks"),
    ("DELETE", "/chat/blocks/{block_id}"),
    ("POST", "/moderation/actions"),
    ("GET", "/moderation/actions/{action_id}"),
    ("POST", "/moderation/actions/{action_id}/submit"),
    ("POST", "/approvals/{approval_id}/decide"),
    ("POST", "/moderation/actions/{action_id}/apply"),
}

_ALLOWLIST_REGEX: list[tuple[str, str, re.Pattern[str]]] = []
for m, template in sorted(ALLOWLIST):
    # Replace placeholders like {report_id} with a safe path segment matcher.
    pattern = re.escape(template)
    pattern = re.sub(r"\\\{[^\\}]+\\\}", r"[^/]+", pattern)
    _ALLOWLIST_REGEX.append((m, template, re.compile(rf"^{pattern}$")))


def allowlist_check(method: str, path: str) -> tuple[bool, Optional[str]]:
    """Return (allowed, matched_template)."""
    for m, template, rx in _ALLOWLIST_REGEX:
        if m != method:
            continue
        if rx.match(path):
            return True, template
    return False, None


SYSTEM_PROMPT = """You are a careful test agent for Libervia Engine (Bazari).
You do NOT have tokens, shell, or filesystem access. You can only propose API calls.

Rules:
- STRICT headers are enforced by the runner. You must choose a role for each call: user, moderator, tsm, admin.
- Do NOT ask for tokens or provisioning. Tokens are pre-provided.
- You must stay within the allowed endpoint list provided by the runner.
- Prefer small, deterministic bodies; reuse IDs returned by the server.
- If a call fails unexpectedly, diagnose and propose the next best call to gather evidence.

Output format (MUST be valid JSON, no markdown):
{
  "actions": [
    {"role":"user|moderator|tsm|admin","method":"GET|POST|DELETE","path":"/...","body":{... optional}}
  ],
  "done": false,
  "notes": "short"
}
"""

def parse_llm_plan(text: str) -> dict[str, Any]:
    """Parse model output into a plan dict.

    Claude often wraps JSON in ```json fences or adds a short preamble.
    We accept:
    - raw JSON object
    - fenced JSON block
    - any text that contains a single top-level JSON object
    """
    candidate = text.strip()
    # Remove common fenced blocks
    if candidate.startswith("```"):
        # strip first fence line and last fence if present
        parts = candidate.splitlines()
        if parts:
            parts = parts[1:]
        if parts and parts[-1].strip().startswith("```"):
            parts = parts[:-1]
        candidate = "\n".join(parts).strip()
    # Try direct parse
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # Fallback: extract first {...} block
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        obj = json.loads(candidate[start : end + 1])
        if isinstance(obj, dict):
            return obj
    raise ValueError("LLM output is not a JSON object")


def scenario_goal(scenario: str) -> str:
    if scenario == "happy":
        return "Goal: complete report->triage->action->submit->approve->apply. End when action status is APPLIED."
    if scenario == "abuse":
        return "Goal: attempt forbidden actions (user triage/apply) and confirm 403/denied. End when both denials observed."
    if scenario == "sod":
        return "Goal: attempt self-approve and confirm a SoD violation (or other deterministic denial) prevents it."
    if scenario == "sod_strict":
        return (
            "Goal: force a real SoD check (proposer == decider) on an approval that the role is otherwise allowed to decide.\n"
            "Suggested minimal path:\n"
            "1) As admin: POST /reports (create)\n"
            "2) As admin: POST /moderation/actions (create)\n"
            "3) As admin: POST /moderation/actions/{action_id}/submit -> expect pending_approval + approval_id\n"
            "4) As admin: POST /approvals/{approval_id}/decide (approve) -> expect deterministic SoD denial (ideally 409 APPROVAL_SOD_VIOLATION)\n"
            "End once the self-decide denial is observed."
        )
    if scenario == "replay":
        return "Goal: decide same approval twice; first succeeds, second returns 409."
    if scenario == "volume":
        return "Goal: create multiple reports, triage them, and create at least one action+submit."
    if scenario == "all":
        return "Goal: run happy then abuse then sod_strict then replay then volume."
    raise ValueError(f"Unknown scenario: {scenario}")


def _summarize_http(res: HttpResult) -> dict[str, Any]:
    if isinstance(res.json, dict):
        small = dict(res.json)
        # avoid huge payloads
        for k in list(small.keys()):
            if isinstance(small[k], (list, dict)) and k not in {"code", "message", "status", "approval_id", "id", "entity_id"}:
                small[k] = "<omitted>"
        return {"status": res.status, "json": small}
    return {"status": res.status, "text": res.text[:300]}


def run_llm(env: Env, scenario: str, max_requests: int, max_steps: int) -> int:
    run_id = time.strftime("%Y%m%d-%H%M%S")
    log_path = state_dir() / f"bazari_llm_{scenario}_{run_id}.jsonl"

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": json.dumps(
                {
                    "scenario": scenario,
                    "goal": scenario_goal(scenario),
                    "allowed_endpoints": sorted(
                        [{"method": m, "path": p} for (m, p) in ALLOWLIST],
                        key=lambda x: (x["path"], x["method"]),
                    ),
                    "institution_id": env.institution_id,
                    "base_url": env.base_url,
                    "notes": "Use returned IDs from observations. Stay within allowed_endpoints.",
                },
                ensure_ascii=False,
            ),
        }
    ]

    remaining = max_requests
    for step in range(1, max_steps + 1):
        print(f"[runner] step {step}/{max_steps} (remaining_requests={remaining})", file=sys.stderr)
        llm_text = call_claude_messages(env, messages)
        write_jsonl(log_path, {"type": "llm_output", "step": step, "text": llm_text})

        try:
            plan = parse_llm_plan(llm_text)
        except Exception:
            # one retry: ask for valid JSON only
            messages.append({"role": "assistant", "content": llm_text})
            messages.append({"role": "user", "content": "Your last message was not valid JSON. Reply with ONLY valid JSON in the required format."})
            continue

        actions = plan.get("actions") or []
        done = bool(plan.get("done"))
        notes = str(plan.get("notes") or "")

        if not isinstance(actions, list):
            raise SystemExit("LLM returned invalid actions format (expected list). See log: " + str(log_path))

        observations: list[dict[str, Any]] = []
        for i, action in enumerate(actions, 1):
            if remaining <= 0:
                observations.append({"error": "request_budget_exhausted"})
                break

            if not isinstance(action, dict):
                observations.append({"error": "invalid_action", "action": action})
                continue

            role = str(action.get("role") or "")
            method = str(action.get("method") or "").upper()
            path = str(action.get("path") or "")
            body = action.get("body")

            if method not in {"GET", "POST", "DELETE"}:
                observations.append({"error": "invalid_method", "method": method})
                continue
            if not path.startswith("/"):
                observations.append({"error": "invalid_path", "path": path})
                continue

            allowed, matched = allowlist_check(method, path)
            if not allowed:
                observations.append({"error": "not_allowlisted", "method": method, "path": path})
                continue

            if body is not None and not isinstance(body, dict):
                observations.append({"error": "invalid_body", "path": path})
                continue

            res = engine_request(env, method, path, role, body)
            remaining -= 1

            obs = {
                "n": i,
                "role": role,
                "method": method,
                "path": path,
                "matched_template": matched,
                "result": _summarize_http(res),
            }
            observations.append(obs)
            write_jsonl(log_path, {"type": "action", "step": step, **obs})

        messages.append({"role": "assistant", "content": llm_text})
        messages.append(
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "notes": notes,
                        "observations": observations,
                        "remaining_request_budget": remaining,
                    },
                    ensure_ascii=False,
                ),
            }
        )

        if done:
            write_jsonl(log_path, {"type": "done", "step": step, "remaining": remaining})
            print(f"Done. Log: {log_path}")
            return 0

    print(f"Stopped (max_steps reached). Log: {log_path}")
    return 2


def cmd_run(args: argparse.Namespace) -> int:
    env = load_env(args)
    return run_llm(env, args.scenario, max_requests=args.max_requests, max_steps=args.max_steps)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bazari_llm_agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Run Claude-driven E2E scenarios (no token provisioning)")
    run.add_argument("--scenario", required=True, choices=["happy", "abuse", "sod", "sod_strict", "replay", "volume", "all"])
    run.add_argument("--max-requests", type=int, default=100)
    run.add_argument("--max-steps", type=int, default=30)
    run.add_argument("--base-url", default=None)
    run.add_argument("--institution-id", default=None)
    run.set_defaults(func=cmd_run)

    return p


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
