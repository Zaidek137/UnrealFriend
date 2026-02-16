#!/usr/bin/env python3
import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


def request_json(method: str, url: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url=url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"success": False, "message": f"HTTP {exc.code}", "payload_raw": raw}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Call Unreal Agent HTTP bridge")
    parser.add_argument("--port", type=int, default=47777)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health")
    subparsers.add_parser("actions")
    subparsers.add_parser("recipes")

    execute = subparsers.add_parser("execute")
    execute.add_argument("--action", required=True)
    execute.add_argument("--dry-run", action="store_true")
    execute.add_argument(
        "--payload-json",
        default="{}",
        help="JSON object string for action payload",
    )

    run_plan = subparsers.add_parser("run-plan")
    run_plan.add_argument(
        "--plan-json",
        default="{}",
        help="JSON object string for plan payload (must include steps array)",
    )

    run_goal = subparsers.add_parser("run-goal")
    run_goal.add_argument("--goal", required=True, help="Natural language goal")
    run_goal.add_argument("--dry-run", action="store_true")
    run_goal.add_argument("--no-stop-on-error", action="store_true")
    run_goal.add_argument(
        "--context-json",
        default="{}",
        help="JSON object string for goal_context",
    )

    run_recipe = subparsers.add_parser("run-recipe")
    run_recipe.add_argument("--recipe-id", required=True)
    run_recipe.add_argument("--inputs-json", default="{}")
    run_recipe.add_argument("--dry-run", action="store_true")
    run_recipe.add_argument("--no-stop-on-error", action="store_true")
    run_recipe.add_argument("--profile", default="balanced")

    validate_recipe = subparsers.add_parser("validate-recipe")
    validate_recipe.add_argument("--recipe-id", required=True)
    validate_recipe.add_argument("--inputs-json", default="{}")
    validate_recipe.add_argument("--profile", default="balanced")

    run_scenario = subparsers.add_parser("run-scenario")
    run_scenario.add_argument("--assertions-json", required=True, help="JSON array of assertion objects")
    run_scenario.add_argument("--dry-run", action="store_true")
    run_scenario.add_argument("--profile", default="balanced")
    run_scenario.add_argument("--release-validation", action="store_true")

    args = parser.parse_args()
    base = f"http://127.0.0.1:{args.port}/unreal-agent/v1"

    if args.command == "health":
        response = request_json("GET", f"{base}/health")
    elif args.command == "actions":
        response = request_json("GET", f"{base}/actions")
    elif args.command == "recipes":
        response = request_json("GET", f"{base}/recipes")
    elif args.command == "run-plan":
        try:
            plan = json.loads(args.plan_json)
            if not isinstance(plan, dict):
                raise ValueError("plan must be a JSON object")
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"success": False, "message": str(exc)}))
            return 2

        response = request_json(
            "POST",
            f"{base}/run-plan",
            plan,
        )
    elif args.command == "run-goal":
        try:
            context = json.loads(args.context_json)
            if not isinstance(context, dict):
                raise ValueError("context must be a JSON object")
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"success": False, "message": str(exc)}))
            return 2

        response = request_json(
            "POST",
            f"{base}/run-goal",
            {
                "goal": args.goal,
                "dry_run": args.dry_run,
                "stop_on_error": not args.no_stop_on_error,
                "goal_context": context,
            },
        )
    elif args.command == "run-recipe":
        try:
            inputs = json.loads(args.inputs_json)
            if not isinstance(inputs, dict):
                raise ValueError("inputs must be a JSON object")
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"success": False, "message": str(exc)}))
            return 2
        response = request_json(
            "POST",
            f"{base}/run-recipe",
            {
                "recipe_id": args.recipe_id,
                "inputs": inputs,
                "dry_run": args.dry_run,
                "stop_on_error": not args.no_stop_on_error,
                "profile": args.profile,
            },
        )
    elif args.command == "validate-recipe":
        try:
            inputs = json.loads(args.inputs_json)
            if not isinstance(inputs, dict):
                raise ValueError("inputs must be a JSON object")
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"success": False, "message": str(exc)}))
            return 2
        response = request_json(
            "POST",
            f"{base}/validate-recipe",
            {
                "recipe_id": args.recipe_id,
                "inputs": inputs,
                "profile": args.profile,
            },
        )
    elif args.command == "run-scenario":
        try:
            assertions = json.loads(args.assertions_json)
            if not isinstance(assertions, list):
                raise ValueError("assertions must be a JSON array")
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"success": False, "message": str(exc)}))
            return 2
        response = request_json(
            "POST",
            f"{base}/run-scenario",
            {
                "assertions": assertions,
                "dry_run": args.dry_run,
                "profile": args.profile,
                "release_validation": args.release_validation,
            },
        )
    else:
        try:
            payload = json.loads(args.payload_json)
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"success": False, "message": str(exc)}))
            return 2

        response = request_json(
            "POST",
            f"{base}/execute",
            {
                "action": args.action,
                "dry_run": args.dry_run,
                "payload": payload,
            },
        )

    print(json.dumps(response, indent=2))
    return 0 if response.get("success", False) else 1


if __name__ == "__main__":
    sys.exit(main())
