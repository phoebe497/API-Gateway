from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from . import payloads, plan
from .audit import AuditLog
from .client import Client, Result
from .config import Config

# The command-line surface. Every action funnels through the same Client and is
# recorded to the audit log (with the key redacted at the sink). The tool never
# consults a local allowlist: it either asks the gateway (`routes`) or simply
# sends and lets the gateway decide.

AUDIT_PATH = "data/tool-audit.jsonl"


def _audit(config: Config) -> AuditLog:
    return AuditLog(AUDIT_PATH, api_key=config.api_key)


def _record(log: AuditLog, action: str, path: str, result: Result, **extra: Any) -> None:
    log.write(
        {
            "action": action,
            "path": path,
            "status": result.status,
            "ok": result.ok,
            "route": result.route,
            "error": result.error,
            "response_snippet": result.body[:500],
            **extra,
        }
    )


def _fill_params(path: str, sample: str = "1") -> str:
    # Discovered paths may contain {id}; the tool has no policy knowledge, so it
    # just substitutes a harmless sample value to exercise the route.
    return re.sub(r"\{[^/}]+\}", sample, path)


def cmd_routes(client: Client, log: AuditLog, _args: argparse.Namespace) -> int:
    result = client.routes()
    _record(log, "routes", "/_gateway/routes", result)
    if not result.ok and result.status is None:
        print(result.summary(), file=sys.stderr)
        return 2
    print(result.body)
    return 0


def cmd_get(client: Client, log: AuditLog, args: argparse.Namespace) -> int:
    headers = _parse_headers(args.header)
    result = client.get(args.path, headers=headers)
    _record(log, "get", args.path, result)
    print(result.summary())
    return 0 if result.ok else 3


def cmd_post(client: Client, log: AuditLog, args: argparse.Namespace) -> int:
    headers = _parse_headers(args.header)
    payload = payloads.get(args.payload) if args.payload else None
    result = client.post(args.path, payload=payload, headers=headers)
    _record(log, "post", args.path, result, payload_id=args.payload)
    print(result.summary())
    return 0 if result.ok else 3


def cmd_suite(client: Client, log: AuditLog, _args: argparse.Namespace) -> int:
    discovered = client.routes()
    _record(log, "routes", "/_gateway/routes", discovered)
    if not discovered.ok or discovered.status != 200:
        print(f"cannot discover routes: {discovered.summary()}", file=sys.stderr)
        return 2

    routes = json.loads(discovered.body).get("routes", [])
    failures = 0
    for route in routes:
        path = _fill_params(route["path"])
        if route["method"] == "GET":
            result = client.get(path)
            _record(log, "suite-get", path, result, route_id=route["id"])
            print(f"GET  {path:<20} -> {result.summary()}")
        elif route["method"] == "POST":
            for pid in payloads.ids():
                result = client.post(path, payload=payloads.get(pid))
                _record(log, "suite-post", path, result, route_id=route["id"], payload_id=pid)
                print(f"POST {path:<20} [{pid:<26}] -> {result.status} {result.route or ''}")
                if not result.ok and result.status is None:
                    failures += 1
    return 0 if failures == 0 else 3


def cmd_plan(client: Client, log: AuditLog, args: argparse.Namespace) -> int:
    # Discover the menu the gateway publishes, ask the planner to propose steps
    # (route_id + payload_id only), validate them, then optionally execute.
    discovered = client.routes()
    _record(log, "routes", "/_gateway/routes", discovered)
    if not discovered.ok or discovered.status != 200:
        print(f"cannot discover routes: {discovered.summary()}", file=sys.stderr)
        return 2

    routes = json.loads(discovered.body).get("routes", [])
    by_id = {r["id"]: r for r in routes}

    steps = plan.propose(args.goal, routes)
    try:
        plan.validate(steps, routes)
    except plan.PlanError as exc:
        # A planner that names something off-menu is rejected before any call.
        print(f"plan rejected: {exc}", file=sys.stderr)
        return 2

    print(f"# Agent proposes {len(steps)} step(s) for goal: {args.goal!r}")
    for i, step in enumerate(steps, 1):
        payload = f" payload={step.payload_id}" if step.payload_id else ""
        print(f"  {i:>2}. {by_id[step.route_id]['method']:<4} route={step.route_id}{payload}  # {step.reason}")

    if args.dry_run:
        return 0

    print("\n# Tool executes (via gateway; it resolves route_id -> path, never the planner):")
    for i, step in enumerate(steps, 1):
        route = by_id[step.route_id]
        path = _fill_params(route["path"])
        if step.payload_id is None:
            result = client.get(path)
        else:
            result = client.post(path, payload=payloads.get(step.payload_id))
        _record(
            log,
            "plan-step",
            path,
            result,
            goal=args.goal,
            route_id=step.route_id,
            payload_id=step.payload_id,
        )
        payload = f" [{step.payload_id}]" if step.payload_id else ""
        print(f"  {i:>2}. {route['method']:<4} {path}{payload} -> {result.status} {result.route or ''}")
    return 0


def cmd_payloads(_client: Client, _log: AuditLog, _args: argparse.Namespace) -> int:
    for pid in payloads.ids():
        print(pid)
    return 0


def _parse_headers(items: list[str] | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in items or []:
        if ":" not in item:
            raise SystemExit(f"invalid --header {item!r}; expected 'Name: value'")
        name, _, value = item.partition(":")
        headers[name.strip()] = value.strip()
    return headers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="safe_probe", description="Safe request probe (via gateway only)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("routes", help="show the allowlist the gateway publishes")
    sub.add_parser("payloads", help="list safe payload ids")
    sub.add_parser("suite", help="run every safe payload against every allowlisted route")

    p_get = sub.add_parser("get", help="send a GET request")
    p_get.add_argument("path")
    p_get.add_argument("-H", "--header", action="append", help="'Name: value'")

    p_post = sub.add_parser("post", help="send a POST request with a safe payload")
    p_post.add_argument("path")
    p_post.add_argument("--payload", help="payload id (see `payloads`)")
    p_post.add_argument("-H", "--header", action="append", help="'Name: value'")

    p_plan = sub.add_parser("plan", help="Agent proposes safe requests for a goal, tool executes them")
    p_plan.add_argument("--goal", required=True, help="natural-language testing goal")
    p_plan.add_argument("--dry-run", action="store_true", help="only propose; do not execute")

    return parser


_COMMANDS = {
    "routes": cmd_routes,
    "get": cmd_get,
    "post": cmd_post,
    "suite": cmd_suite,
    "payloads": cmd_payloads,
    "plan": cmd_plan,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = Config.from_env()
    client = Client(config=config)
    log = _audit(config)
    return _COMMANDS[args.command](client, log, args)


if __name__ == "__main__":
    raise SystemExit(main())
