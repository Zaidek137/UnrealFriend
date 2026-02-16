#!/usr/bin/env python3
import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


def request_json(method: str, url: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"success": False, "message": f"HTTP {exc.code}", "raw": body}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": str(exc)}


def parse_json_arg(raw: str, label: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError(f"{label} must be a JSON object")
        return parsed
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid {label}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="IDE bridge for Unreal Agent Web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health")
    sub.add_parser("actions")
    sub.add_parser("recipes")
    sub.add_parser("release-metrics")
    sub.add_parser("info")
    sub.add_parser("state")
    sub.add_parser("approvals")

    approve = sub.add_parser("approve")
    approve.add_argument("--approval-token", required=True)

    run_cmd = sub.add_parser("run-command")
    run_cmd.add_argument("--command", required=True)
    run_cmd.add_argument("--dry-run", action="store_true")
    run_cmd.add_argument("--stop-on-error", action="store_true", default=True)
    run_cmd.add_argument("--no-stop-on-error", action="store_true")
    run_cmd.add_argument("--goal-context-json", default="{}")
    run_cmd.add_argument("--approval-token", default="")

    run_goal = sub.add_parser("run-goal")
    run_goal.add_argument("--goal", required=True)
    run_goal.add_argument("--dry-run", action="store_true")
    run_goal.add_argument("--stop-on-error", action="store_true", default=True)
    run_goal.add_argument("--no-stop-on-error", action="store_true")
    run_goal.add_argument("--goal-context-json", default="{}")
    run_goal.add_argument("--approval-token", default="")

    run_plan = sub.add_parser("run-plan")
    run_plan.add_argument("--plan-json", required=True)
    run_plan.add_argument("--approval-token", default="")

    run_recipe = sub.add_parser("run-recipe")
    run_recipe.add_argument("--recipe-id", required=True)
    run_recipe.add_argument("--inputs-json", default="{}")
    run_recipe.add_argument("--dry-run", action="store_true")
    run_recipe.add_argument("--stop-on-error", action="store_true", default=True)
    run_recipe.add_argument("--no-stop-on-error", action="store_true")
    run_recipe.add_argument("--profile", default="balanced")
    run_recipe.add_argument("--approval-token", default="")

    validate_recipe = sub.add_parser("validate-recipe")
    validate_recipe.add_argument("--recipe-id", required=True)
    validate_recipe.add_argument("--inputs-json", default="{}")
    validate_recipe.add_argument("--profile", default="balanced")

    run_scenario = sub.add_parser("run-scenario")
    run_scenario.add_argument("--assertions-json", required=True)
    run_scenario.add_argument("--dry-run", action="store_true")
    run_scenario.add_argument("--profile", default="balanced")
    run_scenario.add_argument("--release-validation", action="store_true")

    direct = sub.add_parser("direct-execute")
    direct.add_argument("--action", required=True)
    direct.add_argument("--payload-json", default="{}")
    direct.add_argument("--dry-run", action="store_true")
    direct.add_argument("--approval-token", default="")

    args = parser.parse_args()
    base = f"http://{args.host}:{args.port}"

    if args.cmd == "health":
        result = request_json("GET", f"{base}/api/health")
    elif args.cmd == "actions":
        result = request_json("GET", f"{base}/api/actions")
    elif args.cmd == "recipes":
        result = request_json("GET", f"{base}/api/recipes")
    elif args.cmd == "release-metrics":
        result = request_json("GET", f"{base}/api/release-metrics")
    elif args.cmd == "info":
        result = request_json("GET", f"{base}/api/info")
    elif args.cmd == "state":
        result = request_json("GET", f"{base}/api/state")
    elif args.cmd == "approvals":
        result = request_json("GET", f"{base}/api/approvals")
    elif args.cmd == "approve":
        result = request_json("POST", f"{base}/api/approve", {"approval_token": args.approval_token})
    elif args.cmd == "run-command":
        goal_context = parse_json_arg(args.goal_context_json, "goal-context-json")
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        result = request_json(
            "POST",
            f"{base}/api/command",
            {
                "command": args.command,
                "dry_run": bool(args.dry_run),
                "stop_on_error": stop_on_error,
                "goal_context": goal_context,
                "approval_token": args.approval_token,
            },
        )
    elif args.cmd == "run-goal":
        goal_context = parse_json_arg(args.goal_context_json, "goal-context-json")
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        result = request_json(
            "POST",
            f"{base}/api/run-goal",
            {
                "goal": args.goal,
                "dry_run": bool(args.dry_run),
                "stop_on_error": stop_on_error,
                "goal_context": goal_context,
                "approval_token": args.approval_token,
            },
        )
    elif args.cmd == "run-plan":
        plan = parse_json_arg(args.plan_json, "plan-json")
        result = request_json("POST", f"{base}/api/run-plan", {"plan": plan, "approval_token": args.approval_token})
    elif args.cmd == "run-recipe":
        inputs = parse_json_arg(args.inputs_json, "inputs-json")
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        result = request_json(
            "POST",
            f"{base}/api/run-recipe",
            {
                "recipe_id": args.recipe_id,
                "inputs": inputs,
                "dry_run": bool(args.dry_run),
                "stop_on_error": stop_on_error,
                "profile": args.profile,
                "approval_token": args.approval_token,
            },
        )
    elif args.cmd == "validate-recipe":
        inputs = parse_json_arg(args.inputs_json, "inputs-json")
        result = request_json(
            "POST",
            f"{base}/api/validate-recipe",
            {
                "recipe_id": args.recipe_id,
                "inputs": inputs,
                "profile": args.profile,
            },
        )
    elif args.cmd == "run-scenario":
        try:
            assertions = json.loads(args.assertions_json)
            if not isinstance(assertions, list):
                raise ValueError("assertions-json must be a JSON array")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid assertions-json: {exc}") from exc
        result = request_json(
            "POST",
            f"{base}/api/run-scenario",
            {
                "assertions": assertions,
                "dry_run": bool(args.dry_run),
                "profile": args.profile,
                "release_validation": bool(args.release_validation),
            },
        )
    else:
        payload = parse_json_arg(args.payload_json, "payload-json")
        result = request_json(
            "POST",
            f"{base}/api/direct-execute",
            {
                "action": args.action,
                "payload": payload,
                "dry_run": bool(args.dry_run),
                "approval_token": args.approval_token,
            },
        )

    if args.pretty:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result))
    return 0 if result.get("success", False) else 1


if __name__ == "__main__":
    sys.exit(main())
