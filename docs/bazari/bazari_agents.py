from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Env:
    base_url: str
    institution_id: str
    user_token: str
    mod_token: str
    tsm_token: str
    admin_token: str


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing env: {name}")
    return value


def load_env(args: argparse.Namespace) -> Env:
    base_url = (args.base_url or os.environ.get("ENGINE_BASE_URL") or "").strip()
    if not base_url:
        base_url = "http://127.0.0.1:8001"
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
    )


def _short_token(token: str) -> str:
    if len(token) <= 10:
        return token
    return token[:6] + "…" + token[-4:]


@dataclass
class HttpResult:
    status: int
    headers: dict[str, str]
    json: Optional[Any]
    text: str


def http_json(
    env: Env,
    method: str,
    path: str,
    actor_token: Optional[str],
    body: Optional[dict[str, Any]] = None,
) -> HttpResult:
    url = f"{env.base_url}{path}"
    headers = {"X-Institution-Id": env.institution_id}
    if actor_token:
        headers["X-Actor-Token"] = actor_token

    data: Optional[bytes] = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            parsed = None
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            return HttpResult(
                status=getattr(resp, "status", 200),
                headers={k: v for k, v in resp.headers.items()},
                json=parsed,
                text=text,
            )
    except urllib.error.HTTPError as e:
        raw = e.read()
        text = raw.decode("utf-8", errors="replace")
        parsed = None
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        return HttpResult(
            status=int(getattr(e, "code", 0) or 0),
            headers={k: v for k, v in getattr(e, "headers", {}).items()},
            json=parsed,
            text=text,
        )


def assert_status(res: HttpResult, expected: int, label: str) -> None:
    if res.status != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, got {res.status}: {res.text}")


def create_report(env: Env, content_id: str) -> str:
    res = http_json(
        env,
        "POST",
        "/reports",
        env.user_token,
        {"content_type": "POST", "content_id": content_id, "reason": "SPAM", "details": "agent test"},
    )
    assert_status(res, 200, "create_report")
    if not isinstance(res.json, dict) or "id" not in res.json:
        raise AssertionError(f"create_report: missing id: {res.text}")
    return str(res.json["id"])


def triage_report(env: Env, report_id: str, actor_token: str) -> HttpResult:
    return http_json(env, "POST", f"/moderation/reports/{report_id}/triage", actor_token, {})


def create_action(env: Env, report_id: str, action: str = "BAN") -> str:
    res = http_json(
        env,
        "POST",
        "/moderation/actions",
        env.mod_token,
        {
            "target_type": "POST",
            "target_id": "post-123",
            "action": action,
            "reason": "spam",
            "report_id": report_id,
        },
    )
    assert_status(res, 200, "create_action")
    if not isinstance(res.json, dict) or "id" not in res.json:
        raise AssertionError(f"create_action: missing id: {res.text}")
    return str(res.json["id"])


def submit_action(env: Env, action_id: str) -> str:
    res = http_json(env, "POST", f"/moderation/actions/{action_id}/submit", env.mod_token, {})
    assert_status(res, 200, "submit_action")
    if not isinstance(res.json, dict) or "approval_id" not in res.json:
        raise AssertionError(f"submit_action: missing approval_id: {res.text}")
    return str(res.json["approval_id"])


def decide_approval(env: Env, approval_id: str, actor_token: str, decision: str) -> HttpResult:
    return http_json(
        env,
        "POST",
        f"/approvals/{approval_id}/decide",
        actor_token,
        {"decision": decision, "reason": "agent decision"},
    )


def apply_action(env: Env, action_id: str, actor_token: str) -> HttpResult:
    return http_json(env, "POST", f"/moderation/actions/{action_id}/apply", actor_token, {})


def get_action(env: Env, action_id: str) -> HttpResult:
    return http_json(env, "GET", f"/moderation/actions/{action_id}", env.mod_token, None)


def scenario_happy(env: Env) -> None:
    print(f"[happy] base={env.base_url} inst={env.institution_id}")
    print(
        "[happy] tokens "
        f"user={_short_token(env.user_token)} "
        f"mod={_short_token(env.mod_token)} "
        f"tsm={_short_token(env.tsm_token)} "
        f"admin={_short_token(env.admin_token)}"
    )

    report_id = create_report(env, content_id=f"post-{int(time.time())}")
    res = triage_report(env, report_id, env.mod_token)
    assert_status(res, 200, "triage_report")

    action_id = create_action(env, report_id)
    approval_id = submit_action(env, action_id)

    res = decide_approval(env, approval_id, env.tsm_token, "approve")
    assert_status(res, 200, "decide_approval")

    res = apply_action(env, action_id, env.admin_token)
    assert_status(res, 200, "apply_action")

    res = get_action(env, action_id)
    assert_status(res, 200, "get_action")
    if isinstance(res.json, dict) and res.json.get("status") != "APPLIED":
        raise AssertionError(f"happy: expected APPLIED, got {res.json.get('status')}")
    print("[happy] OK")


def scenario_abuse(env: Env) -> None:
    print("[abuse] user should NOT triage/apply")
    report_id = create_report(env, content_id=f"post-{int(time.time())}")

    res = triage_report(env, report_id, env.user_token)
    if res.status != 403:
        raise AssertionError(f"abuse: user triage expected 403, got {res.status}: {res.text}")

    action_id = create_action(env, report_id)
    approval_id = submit_action(env, action_id)
    _ = decide_approval(env, approval_id, env.tsm_token, "approve")

    res = apply_action(env, action_id, env.user_token)
    if res.status != 403:
        raise AssertionError(f"abuse: user apply expected 403, got {res.status}: {res.text}")
    print("[abuse] OK")


def scenario_sod(env: Env) -> None:
    print("[sod] proposer should NOT decide")
    report_id = create_report(env, content_id=f"post-{int(time.time())}")
    _ = triage_report(env, report_id, env.mod_token)
    action_id = create_action(env, report_id)
    approval_id = submit_action(env, action_id)

    res = decide_approval(env, approval_id, env.mod_token, "approve")
    if res.status != 409:
        raise AssertionError(f"sod: expected 409, got {res.status}: {res.text}")
    print("[sod] OK")


def scenario_replay(env: Env) -> None:
    print("[replay] deciding twice should conflict")
    report_id = create_report(env, content_id=f"post-{int(time.time())}")
    _ = triage_report(env, report_id, env.mod_token)
    action_id = create_action(env, report_id)
    approval_id = submit_action(env, action_id)

    res = decide_approval(env, approval_id, env.tsm_token, "approve")
    assert_status(res, 200, "replay: first decide")

    res2 = decide_approval(env, approval_id, env.tsm_token, "approve")
    if res2.status != 409:
        raise AssertionError(f"replay: expected 409 second decide, got {res2.status}: {res2.text}")
    print("[replay] OK")


def scenario_volume(env: Env, count: int) -> None:
    print(f"[volume] creating {count} reports")
    report_ids: list[str] = []
    for i in range(count):
        report_ids.append(create_report(env, content_id=f"post-{int(time.time())}-{i}"))
    for rid in report_ids:
        res = triage_report(env, rid, env.mod_token)
        assert_status(res, 200, "volume: triage")
    print("[volume] OK")


SCENARIOS = {
    "happy": lambda env, args: scenario_happy(env),
    "abuse": lambda env, args: scenario_abuse(env),
    "sod": lambda env, args: scenario_sod(env),
    "replay": lambda env, args: scenario_replay(env),
    "volume": lambda env, args: scenario_volume(env, args.count),
}


def cmd_run(args: argparse.Namespace) -> int:
    env = load_env(args)
    if args.scenario == "all":
        for name in ["happy", "abuse", "sod", "replay", "volume"]:
            SCENARIOS[name](env, args)
        return 0

    SCENARIOS[args.scenario](env, args)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bazari_agents")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Run E2E scenarios against a running engine")
    run.add_argument("--scenario", required=True, choices=["happy", "abuse", "sod", "replay", "volume", "all"])
    run.add_argument("--count", type=int, default=10, help="Used by scenario=volume")
    run.add_argument("--base-url", default=None, help="ENGINE_BASE_URL override (default: env ENGINE_BASE_URL)")
    run.add_argument("--institution-id", default=None, help="INSTITUTION_ID override (default: env INSTITUTION_ID)")
    run.set_defaults(func=cmd_run)

    return p


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

