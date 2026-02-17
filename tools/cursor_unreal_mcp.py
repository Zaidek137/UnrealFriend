#!/usr/bin/env python3
"""
Cursor MCP adapter for Unreal Agent Web.

Primary tool: unreal_chat(message, goal_context, dry_run, stop_on_error)
This lets Cursor's agent reason over natural-language goals and execute in Unreal.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


JSONRPC_VERSION = "2.0"

DEFAULT_WEB_BASE = os.environ.get("UNREAL_AGENT_WEB_BASE", "http://127.0.0.1:8787").rstrip("/")
AUTO_APPROVE = os.environ.get("UNREAL_AGENT_AUTO_APPROVE", "true").strip().lower() in {"1", "true", "yes", "on"}
AUTO_START_WEB = os.environ.get("UNREAL_AGENT_WEB_AUTOSTART", "true").strip().lower() in {"1", "true", "yes", "on"}
AUTO_BOOTSTRAP = os.environ.get("UNREAL_AGENT_AUTO_BOOTSTRAP", "true").strip().lower() in {"1", "true", "yes", "on"}
WEB_SERVER_PATH = Path(os.environ.get("UNREAL_AGENT_WEB_SERVER_PATH", "/Users/ericdiaz/Desktop/Unreal Friend/apps/unreal-agent-web/server.py"))

_web_start_attempted = False
_bootstrap_token = ""
_bootstrap_expires_at = 0.0


def request_json(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 120,
    request_headers_extra: Optional[Dict[str, str]] = None,
) -> Tuple[int, Dict[str, Any]]:
    url = f"{DEFAULT_WEB_BASE}{path}"
    data = None
    headers = {"Content-Type": "application/json"}
    if isinstance(request_headers_extra, dict):
        headers.update(request_headers_extra)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            try:
                parsed = json.loads(body)
                if not isinstance(parsed, dict):
                    parsed = {"raw": parsed}
            except json.JSONDecodeError:
                parsed = {"raw": body}
            return response.status, parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                parsed = {"raw": parsed}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed
    except Exception as exc:  # noqa: BLE001
        return 502, {"success": False, "error_code": "HTTP_CLIENT_ERROR", "message": str(exc)}


def ensure_web_available() -> None:
    global _web_start_attempted

    status, _ = request_json("GET", "/api/health", timeout=3)
    if status < 500:
        return

    if not AUTO_START_WEB or _web_start_attempted:
        return

    _web_start_attempted = True
    if not WEB_SERVER_PATH.exists():
        return

    log_path = WEB_SERVER_PATH.parent / ".data" / "mcp-autostart.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log_file:
        subprocess.Popen(  # noqa: S603
            [sys.executable, str(WEB_SERVER_PATH)],
            cwd=str(WEB_SERVER_PATH.parent),
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )

    for _ in range(20):
        time.sleep(0.25)
        status, _ = request_json("GET", "/api/health", timeout=3)
        if status < 500:
            return


def _bootstrap_headers() -> Dict[str, str]:
    if _bootstrap_token:
        return {"X-Agent-Bootstrap-Token": _bootstrap_token}
    return {}


def ensure_agent_bootstrap(force: bool = False) -> Tuple[bool, Dict[str, Any]]:
    global _bootstrap_token, _bootstrap_expires_at

    if not AUTO_BOOTSTRAP:
        return True, {"success": True, "auto_bootstrap": False}

    ensure_web_available()
    now = time.time()
    if not force and _bootstrap_token and now < (_bootstrap_expires_at - 10.0):
        return True, {"success": True, "bootstrap_token": _bootstrap_token, "expires_at": _bootstrap_expires_at}

    payload = {
        "client_name": "cursor_mcp",
        "client_version": "0.1.0",
        "session_label": "cursor_agent_session",
    }
    status, response = request_json("POST", "/api/agent-bootstrap", payload, timeout=30)
    if status >= 400 or not bool(response.get("success", False)):
        _bootstrap_token = ""
        _bootstrap_expires_at = 0.0
        return False, response if isinstance(response, dict) else {"success": False, "message": "Bootstrap failed."}

    _bootstrap_token = str(response.get("bootstrap_token", "")).strip()
    _bootstrap_expires_at = float(response.get("expires_at", 0.0))
    if not _bootstrap_token:
        return False, {"success": False, "message": "Bootstrap response did not contain bootstrap_token.", "response": response}
    return True, response


def request_api(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    timeout: int = 120,
    retry_on_bootstrap_error: bool = True,
) -> Tuple[int, Dict[str, Any]]:
    if path != "/api/agent-bootstrap":
        ok, bootstrap_response = ensure_agent_bootstrap(force=False)
        if not ok:
            return 503, {"success": False, "error_code": "AGENT_BOOTSTRAP_FAILED", "message": "Automatic agent bootstrap failed.", "bootstrap": bootstrap_response}
    status, result = request_json(method, path, payload, timeout=timeout, request_headers_extra=_bootstrap_headers())
    error_code = str(result.get("error_code", "")).strip()
    if retry_on_bootstrap_error and error_code in {"AGENT_BOOTSTRAP_REQUIRED", "AGENT_BOOTSTRAP_INVALID", "AGENT_BOOTSTRAP_EXPIRED"}:
        ok, bootstrap_response = ensure_agent_bootstrap(force=True)
        if not ok:
            return 503, {"success": False, "error_code": "AGENT_BOOTSTRAP_FAILED", "message": "Automatic agent bootstrap failed.", "bootstrap": bootstrap_response}
        status, result = request_json(method, path, payload, timeout=timeout, request_headers_extra=_bootstrap_headers())
    return status, result


def to_text(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def mcp_content(text: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def mcp_error_content(message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out = {"success": False, "message": message}
    if details:
        out["details"] = details
    return {"content": [{"type": "text", "text": to_text(out)}], "isError": True}


def call_unreal_chat(args: Dict[str, Any]) -> Dict[str, Any]:
    ensure_web_available()
    message = str(args.get("message", "")).strip()
    if not message:
        return mcp_error_content("Missing required argument: message")

    goal_context = args.get("goal_context", {})
    if not isinstance(goal_context, dict):
        return mcp_error_content("goal_context must be an object")

    payload = {
        "message": message,
        "dry_run": bool(args.get("dry_run", False)),
        "stop_on_error": bool(args.get("stop_on_error", True)),
        "profile": str(args.get("profile", "strict")).strip() or "strict",
        "goal_context": goal_context,
    }

    status, result = request_api("POST", "/api/chat", payload)

    if result.get("error_code") == "APPROVAL_REQUIRED" and AUTO_APPROVE:
        token = str(result.get("approval_token", "")).strip()
        if token:
            approve_status, approve_result = request_api("POST", "/api/approve", {"approval_token": token})
            if approve_status < 400 and approve_result.get("success", False):
                payload["approval_token"] = token
                status, result = request_api("POST", "/api/chat", payload)
            else:
                return mcp_error_content("Approval failed during auto-approve", {"approval": approve_result, "initial": result})

    if status >= 400 and not result.get("success", False):
        return mcp_error_content("unreal_chat failed", {"http_status": status, "response": result})

    return mcp_content(to_text(result))


def call_endpoint(path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ensure_web_available()
    status, result = request_api(method, path, payload)
    if status >= 400 and not result.get("success", False):
        return mcp_error_content(f"{method} {path} failed", {"http_status": status, "response": result})
    return mcp_content(to_text(result))


def call_execute_action(args: Dict[str, Any]) -> Dict[str, Any]:
    ensure_web_available()
    action = str(args.get("action", "")).strip()
    payload = args.get("payload", {})
    if not action:
        return mcp_error_content("Missing required argument: action")
    if not isinstance(payload, dict):
        return mcp_error_content("payload must be an object")

    body = {
        "action": action,
        "payload": payload,
        "dry_run": bool(args.get("dry_run", False)),
    }

    status, result = request_api("POST", "/api/direct-execute", body)
    if result.get("error_code") == "APPROVAL_REQUIRED" and AUTO_APPROVE:
        token = str(result.get("approval_token", "")).strip()
        if token:
            approve_status, approve_result = request_api("POST", "/api/approve", {"approval_token": token})
            if approve_status < 400 and approve_result.get("success", False):
                body["approval_token"] = token
                status, result = request_api("POST", "/api/direct-execute", body)
            else:
                return mcp_error_content("Approval failed during auto-approve", {"approval": approve_result, "initial": result})

    if status >= 400 and not result.get("success", False):
        return mcp_error_content("unreal_execute_action failed", {"http_status": status, "response": result})

    return mcp_content(to_text(result))


def call_run_recipe(args: Dict[str, Any]) -> Dict[str, Any]:
    ensure_web_available()
    recipe_id = str(args.get("recipe_id", "")).strip()
    if not recipe_id:
        return mcp_error_content("Missing required argument: recipe_id")
    inputs = args.get("inputs", {})
    if not isinstance(inputs, dict):
        return mcp_error_content("inputs must be an object")

    payload = {
        "recipe_id": recipe_id,
        "inputs": inputs,
        "dry_run": bool(args.get("dry_run", False)),
        "stop_on_error": bool(args.get("stop_on_error", True)),
        "profile": str(args.get("profile", "balanced")).strip() or "balanced",
    }
    status, result = request_api("POST", "/api/run-recipe", payload)
    if result.get("error_code") == "APPROVAL_REQUIRED" and AUTO_APPROVE:
        token = str(result.get("approval_token", "")).strip()
        if token:
            approve_status, approve_result = request_api("POST", "/api/approve", {"approval_token": token})
            if approve_status < 400 and approve_result.get("success", False):
                payload["approval_token"] = token
                status, result = request_api("POST", "/api/run-recipe", payload)
            else:
                return mcp_error_content("Approval failed during auto-approve", {"approval": approve_result, "initial": result})
    if status >= 400 and not result.get("success", False):
        return mcp_error_content("unreal_run_recipe failed", {"http_status": status, "response": result})
    return mcp_content(to_text(result))


def call_validate_recipe(args: Dict[str, Any]) -> Dict[str, Any]:
    ensure_web_available()
    recipe_id = str(args.get("recipe_id", "")).strip()
    if not recipe_id:
        return mcp_error_content("Missing required argument: recipe_id")
    inputs = args.get("inputs", {})
    if not isinstance(inputs, dict):
        return mcp_error_content("inputs must be an object")
    payload = {
        "recipe_id": recipe_id,
        "inputs": inputs,
        "stop_on_error": bool(args.get("stop_on_error", True)),
        "profile": str(args.get("profile", "balanced")).strip() or "balanced",
        "release_validation": bool(args.get("release_validation", True)),
    }
    status, result = request_api("POST", "/api/validate-recipe", payload)
    if status >= 400 and not result.get("success", False):
        return mcp_error_content("unreal_validate_recipe failed", {"http_status": status, "response": result})
    return mcp_content(to_text(result))


def call_run_scenario(args: Dict[str, Any]) -> Dict[str, Any]:
    ensure_web_available()
    assertions = args.get("assertions", [])
    if not isinstance(assertions, list) or len(assertions) == 0:
        return mcp_error_content("assertions must be a non-empty array")
    payload = {
        "assertions": assertions,
        "dry_run": bool(args.get("dry_run", False)),
        "profile": str(args.get("profile", "balanced")).strip() or "balanced",
        "release_validation": bool(args.get("release_validation", False)),
    }
    status, result = request_api("POST", "/api/run-scenario", payload)
    if status >= 400 and not result.get("success", False):
        return mcp_error_content("unreal_run_scenario failed", {"http_status": status, "response": result})
    return mcp_content(to_text(result))


def call_post(path: str, args: Dict[str, Any]) -> Dict[str, Any]:
    ensure_web_available()
    payload = args if isinstance(args, dict) else {}
    status, result = request_api("POST", path, payload)
    if status >= 400 and not result.get("success", False):
        return mcp_error_content(f"POST {path} failed", {"http_status": status, "response": result})
    return mcp_content(to_text(result))


TOOLS = [
    {
        "name": "unreal_chat",
        "description": "Primary tool. Send natural-language instructions; agent chooses Unreal actions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Natural-language instruction for Unreal."},
                "goal_context": {
                    "type": "object",
                    "description": "Optional structured hints (asset_name, package_path, variable_name, message, etc.).",
                },
                "dry_run": {"type": "boolean", "default": False},
                "stop_on_error": {"type": "boolean", "default": True},
                "profile": {"type": "string", "default": "strict"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "unreal_info",
        "description": "Get Unreal engine/plugin info.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_state",
        "description": "Get current editor state (world, selection, PIE).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_actions",
        "description": "List available Unreal plugin actions.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_execute_action",
        "description": "Advanced fallback: call a specific Unreal action directly.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "payload": {"type": "object"},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["action"],
        },
    },
    {
        "name": "unreal_run_recipe",
        "description": "Run a deterministic Unreal recipe by id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "recipe_id": {"type": "string"},
                "inputs": {"type": "object"},
                "dry_run": {"type": "boolean", "default": False},
                "stop_on_error": {"type": "boolean", "default": True},
                "profile": {"type": "string", "default": "balanced"},
            },
            "required": ["recipe_id"],
        },
    },
    {
        "name": "unreal_validate_recipe",
        "description": "Validate recipe execution (compile/assert checks only).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "recipe_id": {"type": "string"},
                "inputs": {"type": "object"},
                "stop_on_error": {"type": "boolean", "default": True},
                "profile": {"type": "string", "default": "balanced"},
                "release_validation": {"type": "boolean", "default": True},
            },
            "required": ["recipe_id"],
        },
    },
    {
        "name": "unreal_run_scenario",
        "description": "Run PIE scenario assertions through the shared web contract.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "assertions": {"type": "array", "items": {"type": "object"}},
                "dry_run": {"type": "boolean", "default": False},
                "profile": {"type": "string", "default": "balanced"},
                "release_validation": {"type": "boolean", "default": False},
            },
            "required": ["assertions"],
        },
    },
    {
        "name": "unreal_debug_traces",
        "description": "Get recent Unreal plugin debug traces via web proxy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 50},
                "filter": {"type": "string"},
            },
        },
    },
    {
        "name": "unreal_refactor_catalog",
        "description": "Get deterministic refactor transform catalog (20 transforms) for a blueprint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "mode": {"type": "string", "default": "asset"},
                "profile": {"type": "string", "default": "balanced"},
            },
        },
    },
    {
        "name": "unreal_refactor_preview",
        "description": "Build refactor preview plan from selected transform ids without applying.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "transform_ids": {"type": "array", "items": {"type": "string"}},
                "transform_inputs": {"type": "object"},
                "mode": {"type": "string", "default": "asset"},
                "profile": {"type": "string", "default": "balanced"},
            },
            "required": ["blueprint_path"],
        },
    },
    {
        "name": "unreal_explain_selection",
        "description": "Explain selected blueprint nodes with deterministic evidence and suggested fixes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string"},
                "node_names": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["blueprint_path"],
        },
    },
    {
        "name": "unreal_explain_screenshot",
        "description": "Explain a blueprint screenshot path with deterministic matching and suggested fixes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string"},
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string"},
            },
            "required": ["image_path"],
        },
    },
    {
        "name": "unreal_project_dependencies",
        "description": "Build project dependency graph and hotspots in a package scope.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package_path": {"type": "string", "default": "/Game"},
                "recursive": {"type": "boolean", "default": True},
                "depth": {"type": "integer", "default": 2},
            },
        },
    },
    {
        "name": "unreal_perf_hotspots",
        "description": "Run deterministic project hotspot scoring.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package_path": {"type": "string", "default": "/Game"},
                "analyze_blueprints": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "unreal_impact_analysis",
        "description": "Analyze affected assets and compile targets for a change set.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_paths": {"type": "array", "items": {"type": "string"}},
                "change_type": {"type": "string", "default": "modify_blueprint_graph"},
            },
            "required": ["asset_paths"],
        },
    },
    {
        "name": "unreal_umg_generate",
        "description": "Generate and mutate UMG layout from template and style preset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "widget_blueprint": {"type": "string"},
                "template_id": {"type": "string", "default": "hud_basic"},
                "style_preset": {"type": "string", "default": "minimal"},
                "bindings": {"type": "array", "items": {"type": "object"}},
            },
        },
    },
    {
        "name": "unreal_world_generate",
        "description": "Generate world layout from deterministic template + constraints.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layout_id": {"type": "string", "default": "city_grid"},
                "bounds": {"type": "array", "items": {"type": "number"}},
                "density": {"type": "number", "default": 1.0},
                "seed": {"type": "integer", "default": 1337},
                "constraints": {"type": "object"},
            },
        },
    },
    {
        "name": "unreal_claims_evidence",
        "description": "Get claim-match evidence matrix summary for rollout readiness.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_workflow_catalog",
        "description": "List high-level deterministic workflow templates for gameplay/animation scaffolding.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_node_control_capabilities",
        "description": "Return node/blueprint control capability surface, operations, patterns, and workflow templates.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_workflow_generate",
        "description": "Generate and run a deterministic full workflow plan (gameplay loop, animation scaffold, combo scaffold).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
                "stop_on_error": {"type": "boolean", "default": True},
            },
            "required": ["workflow_id"],
        },
    },
    {
        "name": "unreal_graph_primitives_catalog",
        "description": "List deterministic graph primitive operations and payload contracts.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_graph_primitives_apply",
        "description": "Apply deterministic graph primitive operations (spawn/set/connect/disconnect/inspect/reroute).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string", "default": "EventGraph"},
                "operations": {"type": "array", "items": {"type": "object"}},
                "dry_run": {"type": "boolean", "default": False},
                "stop_on_error": {"type": "boolean", "default": True},
            },
            "required": ["blueprint_path", "operations"],
        },
    },
    {
        "name": "unreal_runtime_validate_repair",
        "description": "Run compile+scenario validation loop with optional deterministic auto-repair attempts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "assertions": {"type": "array", "items": {"type": "object"}},
                "auto_repair": {"type": "boolean", "default": True},
                "max_repair_attempts": {"type": "integer", "default": 1},
                "capture_screenshot_on_fail": {"type": "boolean", "default": True},
            },
            "required": ["blueprint_path"],
        },
    },
    {
        "name": "unreal_autonomous_loop_run",
        "description": "Run bulletproof autonomous loop: compile/analyze/scenario/multiplayer/lint/perf with optional repair and rollback.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string", "default": "EventGraph"},
                "assertions": {"type": "array", "items": {"type": "object"}},
                "scenario_repeats": {"type": "integer", "default": 2},
                "auto_repair": {"type": "boolean", "default": True},
                "max_repair_attempts": {"type": "integer", "default": 1},
                "capture_screenshot_on_fail": {"type": "boolean", "default": True},
                "enable_multiplayer": {"type": "boolean", "default": False},
                "multiplayer": {"type": "object"},
                "include_lint_gate": {"type": "boolean", "default": True},
                "include_perf_gate": {"type": "boolean", "default": True},
                "max_rpc_risk_score": {"type": "number", "default": 40.0},
                "max_multiplayer_lint_risk_score": {"type": "number", "default": 40.0},
                "max_perf_risk_score": {"type": "number", "default": 35.0},
                "rollback_on_failure": {"type": "boolean", "default": True},
                "rollback_accept_as_success": {"type": "boolean", "default": True},
                "rollback_token": {"type": "string"},
            },
            "required": ["blueprint_path"],
        },
    },
    {
        "name": "unreal_animation_autonomy_catalog",
        "description": "List deterministic animation autonomy templates for montage/state-machine/notify wiring.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_animation_autonomy_generate",
        "description": "Generate and run deterministic animation autonomy plan from template id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_id": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
                "stop_on_error": {"type": "boolean", "default": True},
            },
            "required": ["template_id"],
        },
    },
    {
        "name": "unreal_ai_autonomy_catalog",
        "description": "List deterministic AI autonomy templates (BT/EQS/Perception scaffolds).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_ai_autonomy_generate",
        "description": "Generate and run deterministic AI autonomy plan from template id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_id": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
                "stop_on_error": {"type": "boolean", "default": True},
            },
            "required": ["template_id"],
        },
    },
    {
        "name": "unreal_blackboard_schema_evolve",
        "description": "Evolve deterministic blackboard proxy schema in AI controller blueprint variables.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string", "default": "EventGraph"},
                "schema": {"type": "array", "items": {"type": "object"}},
                "remove_keys": {"type": "array", "items": {"type": "string"}},
                "rename_keys": {"type": "array", "items": {"type": "object"}},
                "dry_run": {"type": "boolean", "default": False},
                "stop_on_error": {"type": "boolean", "default": True},
            },
            "required": ["blueprint_path"],
        },
    },
    {
        "name": "unreal_ai_behavior_validate",
        "description": "Run deterministic AI behavior validation (compile + lint + scenario assertions).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string", "default": "EventGraph"},
                "assertions": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["blueprint_path"],
        },
    },
    {
        "name": "unreal_content_pipeline_catalog",
        "description": "List deterministic content/asset pipeline presets.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_content_pipeline_apply",
        "description": "Run deterministic content pipeline preset with dependency safety checks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "preset_id": {"type": "string"},
                "asset_paths": {"type": "array", "items": {"type": "string"}},
                "dependency_depth": {"type": "integer", "default": 2},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["preset_id"],
        },
    },
    {
        "name": "unreal_content_schema_enforce",
        "description": "Enforce deterministic naming/folder schema and produce migration plan.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package_path": {"type": "string", "default": "/Game"},
                "recursive": {"type": "boolean", "default": True},
                "max_assets": {"type": "integer", "default": 500},
                "naming_pattern": {"type": "string"},
                "allowed_roots": {"type": "array", "items": {"type": "string"}},
                "expected_prefix": {"type": "string"},
            },
        },
    },
    {
        "name": "unreal_dependency_safety_check",
        "description": "Run dependency safety checks before mutate/apply on target assets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_paths": {"type": "array", "items": {"type": "string"}},
                "depth": {"type": "integer", "default": 2},
            },
            "required": ["asset_paths"],
        },
    },
    {
        "name": "unreal_multiplayer_correctness_catalog",
        "description": "List deterministic multiplayer correctness profiles and checks.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_multiplayer_lint",
        "description": "Run multiplayer lint for authority/replication/RPC contract risks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string"},
            },
            "required": ["blueprint_path"],
        },
    },
    {
        "name": "unreal_multiplayer_guard_apply",
        "description": "Apply deterministic authority guard insertion plan where applicable.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
                "stop_on_error": {"type": "boolean", "default": True},
            },
            "required": ["blueprint_path"],
        },
    },
    {
        "name": "unreal_multiplayer_pie_test",
        "description": "Run deterministic multi-client PIE harness used by multiplayer release gates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "assertions": {"type": "array", "items": {"type": "object"}},
                "client_count": {"type": "integer", "default": 2},
                "repeats": {"type": "integer", "default": 2},
            },
        },
    },
    {
        "name": "unreal_blueprint_structure_review",
        "description": "Generate deterministic blueprint/node review for a single graph or all graphs in the asset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string", "default": "EventGraph"},
                "review_scope": {"type": "string", "enum": ["graph", "asset"], "default": "graph"},
                "include_all_graphs": {"type": "boolean", "default": False},
                "include_ast": {"type": "boolean", "default": True},
                "include_refactor_catalog": {"type": "boolean", "default": True},
                "max_graph_ast_exports": {"type": "integer", "default": 12},
            },
            "required": ["blueprint_path"],
        },
    },
    {
        "name": "unreal_rpc_contract_lint",
        "description": "Run deterministic RPC/authority contract lint for a blueprint graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string", "default": "EventGraph"},
            },
            "required": ["blueprint_path"],
        },
    },
    {
        "name": "unreal_ai_asset_authoring",
        "description": "Create deterministic AI asset authoring scaffold (AIController, BTTask, native Blackboard/EQS/BehaviorTree assets).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dry_run": {"type": "boolean", "default": False},
                "stop_on_error": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "unreal_native_asset_authoring_catalog",
        "description": "List native editor asset authoring asset-types and create/edit action mappings.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_native_asset_create",
        "description": "Create native editor asset (BT/Blackboard/EQS/AnimBP/Material/Niagara/LevelSequence).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_type": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["asset_type"],
        },
    },
    {
        "name": "unreal_native_asset_edit",
        "description": "Edit native editor asset deterministically using asset-type specific payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_type": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["asset_type"],
        },
    },
    {
        "name": "unreal_native_asset_authoring_workflow",
        "description": "Run create+edit native asset authoring workflow plan for an asset type.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_type": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
                "stop_on_error": {"type": "boolean", "default": True},
            },
            "required": ["asset_type"],
        },
    },
    {
        "name": "unreal_pie_replay_suite",
        "description": "Run deterministic PIE replay suite (single or multi-client) with hash-stability evidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "assertions": {"type": "array", "items": {"type": "object"}},
                "include_multiplayer": {"type": "boolean", "default": True},
                "client_count": {"type": "integer", "default": 2},
                "repeats": {"type": "integer", "default": 2},
            },
        },
    },
    {
        "name": "unreal_material_mesh_presets_catalog",
        "description": "List deterministic mesh/material setup presets for asset authoring.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_material_mesh_setup",
        "description": "Apply deterministic actor blueprint mesh/material setup preset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "preset_id": {"type": "string", "default": "static_mesh_actor_basic"},
                "asset_name": {"type": "string"},
                "package_path": {"type": "string"},
                "blueprint_path": {"type": "string"},
                "static_mesh_path": {"type": "string"},
                "material_path": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["static_mesh_path"],
        },
    },
    {
        "name": "unreal_execution_run_detail",
        "description": "Get execution timeline, graph diff, and determinism score by execution run id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "unreal_execution_artifact",
        "description": "Get compact execution artifact view (summary, graph/pin diff, optional linked snapshot).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "include_snapshot": {"type": "boolean", "default": True},
                "include_full": {"type": "boolean", "default": False},
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "unreal_property_reflect",
        "description": "Set reflected scalar property on blueprint CDO/component templates/world actor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_type": {"type": "string", "default": "blueprint_cdo"},
                "blueprint_path": {"type": "string"},
                "component_name": {"type": "string"},
                "actor": {"type": "string"},
                "property_name": {"type": "string"},
                "value": {},
                "compile_after": {"type": "boolean", "default": False},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["property_name", "value"],
        },
    },
    {
        "name": "unreal_blueprint_function_author",
        "description": "Create deterministic function or macro graph in a blueprint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_kind": {"type": "string", "default": "function"},
                "graph_name": {"type": "string"},
                "category": {"type": "string"},
                "compile_after": {"type": "boolean", "default": True},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["blueprint_path", "graph_name"],
        },
    },
    {
        "name": "unreal_component_hierarchy",
        "description": "Add/remove/update blueprint component hierarchy deterministically.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "operation": {"type": "string", "default": "add_component"},
                "component_name": {"type": "string"},
                "class_path": {"type": "string"},
                "parent_component": {"type": "string"},
                "property_name": {"type": "string"},
                "value": {},
                "compile_after": {"type": "boolean", "default": True},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["blueprint_path"],
        },
    },
    {
        "name": "unreal_graph_pin_wire",
        "description": "Connect/disconnect graph pins in a blueprint graph by node/pin names.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string"},
                "operation": {"type": "string", "default": "connect"},
                "from_node_name": {"type": "string"},
                "from_node_title_contains": {"type": "string"},
                "from_pin_name": {"type": "string"},
                "to_node_name": {"type": "string"},
                "to_node_title_contains": {"type": "string"},
                "to_pin_name": {"type": "string"},
                "compile_after": {"type": "boolean", "default": True},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["blueprint_path", "from_pin_name", "to_pin_name"],
        },
    },
    {
        "name": "unreal_node_author",
        "description": "Spawn or replace call-function nodes in a blueprint graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string"},
                "operation": {"type": "string", "default": "spawn_function_call"},
                "node_name": {"type": "string"},
                "target_node_name": {"type": "string"},
                "target_node_title_contains": {"type": "string"},
                "function_class_path": {"type": "string"},
                "function_name": {"type": "string"},
                "node_position": {"type": "array", "items": {"type": "number"}},
                "compile_after": {"type": "boolean", "default": True},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["blueprint_path", "function_class_path", "function_name"],
        },
    },
    {
        "name": "unreal_compile_diagnostics",
        "description": "Compile and return deterministic diagnostics (inventory + analysis).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string"},
                "include_pins": {"type": "boolean", "default": True},
                "max_nodes": {"type": "integer", "default": 500},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["blueprint_path"],
        },
    },
    {
        "name": "unreal_compile_gate_run",
        "description": "Run compile+diagnostic gate on multiple blueprints.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_paths": {"type": "array", "items": {"type": "string"}},
                "include_pins": {"type": "boolean", "default": True},
                "max_nodes": {"type": "integer", "default": 800},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["blueprint_paths"],
        },
    },
    {
        "name": "unreal_node_pattern_catalog",
        "description": "List generic deterministic node pattern templates.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_node_pattern_preview",
        "description": "Preview generated deterministic plan for a node pattern.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern_id": {"type": "string"},
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string", "default": "EventGraph"},
                "message": {"type": "string"},
                "duration": {"type": "number", "default": 0.25},
                "base_node_name": {"type": "string", "default": "AgentPattern"},
            },
            "required": ["pattern_id", "blueprint_path"],
        },
    },
    {
        "name": "unreal_node_pattern_apply",
        "description": "Apply a deterministic node pattern plan to a blueprint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern_id": {"type": "string"},
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string", "default": "EventGraph"},
                "message": {"type": "string"},
                "duration": {"type": "number", "default": 0.25},
                "base_node_name": {"type": "string", "default": "AgentPattern"},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["pattern_id", "blueprint_path"],
        },
    },
    {
        "name": "unreal_graph_snapshots",
        "description": "List saved graph mutation snapshots and rollback availability.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_replay_suite",
        "description": "Run deterministic replay suite for recipe-routed command cases.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cases": {"type": "array", "items": {"type": "object"}},
                "repeats": {"type": "integer", "default": 2},
            },
            "required": ["cases"],
        },
    },
    {
        "name": "unreal_release_gate_evaluate",
        "description": "Evaluate release gate using replay suite plus compile/contradiction diagnostics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_paths": {"type": "array", "items": {"type": "string"}},
                "replay_cases": {"type": "array", "items": {"type": "object"}},
                "replay_repeats": {"type": "integer", "default": 2},
            },
            "required": ["blueprint_paths"],
        },
    },
    {
        "name": "unreal_rollback_apply",
        "description": "Apply rollback plan from a snapshot token.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rollback_token": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
                "stop_on_error": {"type": "boolean", "default": True},
            },
            "required": ["rollback_token"],
        },
    },
    {
        "name": "unreal_graph_ast_export",
        "description": "Export deterministic graph AST (nodes, pins, exec edges, fingerprint).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string"},
                "include_pins": {"type": "boolean", "default": True},
                "max_nodes": {"type": "integer", "default": 2000},
            },
            "required": ["blueprint_path"],
        },
    },
    {
        "name": "unreal_graph_ast_apply",
        "description": "Apply a deterministic set of graph AST operations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string", "default": "EventGraph"},
                "operations": {"type": "array", "items": {"type": "object"}},
                "dry_run": {"type": "boolean", "default": False},
                "stop_on_error": {"type": "boolean", "default": True},
            },
            "required": ["blueprint_path", "operations"],
        },
    },
    {
        "name": "unreal_signature_edit",
        "description": "Edit blueprint variables/functions through deterministic signature operations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string", "default": "EventGraph"},
                "operation": {"type": "string"},
                "name": {"type": "string"},
                "type": {"type": "string"},
                "default_value": {"type": "string"},
                "category": {"type": "string"},
                "function_name": {"type": "string"},
                "macro_name": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
                "stop_on_error": {"type": "boolean", "default": True},
            },
            "required": ["blueprint_path", "operation"],
        },
    },
    {
        "name": "unreal_actor_transform_control",
        "description": "Set actor location/rotation/scale deterministically in editor world.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "actor": {"type": "string"},
                "actor_label": {"type": "string"},
                "operation": {"type": "string", "default": "set_transform"},
                "location": {"type": "array", "items": {"type": "number"}},
                "rotation": {"type": "array", "items": {"type": "number"}},
                "scale": {"type": "array", "items": {"type": "number"}},
                "dry_run": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "unreal_system_bootstrap",
        "description": "Bootstrap animation/ability/AI blueprint assets deterministically.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "system_type": {"type": "string"},
                "asset_name": {"type": "string"},
                "package_path": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["system_type", "asset_name", "package_path"],
        },
    },
    {
        "name": "unreal_control_surface_catalog",
        "description": "List available full-control Unreal API surfaces.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "unreal_agent_readiness",
        "description": "Verify Unreal bridge and required action surface readiness for fully agent-driven control.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class StdioJsonRpcServer:
    def __init__(self) -> None:
        self.running = True

    def _read_message(self) -> Optional[Dict[str, Any]]:
        content_length = None
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                break
            lower = line.lower()
            if lower.startswith("content-length:"):
                try:
                    content_length = int(line.split(":", 1)[1].strip())
                except ValueError:
                    return None
        if content_length is None:
            return None

        body = sys.stdin.buffer.read(content_length)
        if not body:
            return None
        try:
            parsed = json.loads(body.decode("utf-8"))
            if not isinstance(parsed, dict):
                return None
            return parsed
        except Exception:
            return None

    def _write(self, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("utf-8")
        sys.stdout.buffer.write(header)
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()

    def _respond(self, msg_id: Any, result: Dict[str, Any]) -> None:
        self._write({"jsonrpc": JSONRPC_VERSION, "id": msg_id, "result": result})

    def _respond_error(self, msg_id: Any, code: int, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        err: Dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        self._write({"jsonrpc": JSONRPC_VERSION, "id": msg_id, "error": err})

    def _handle_tool_call(self, msg_id: Any, params: Dict[str, Any]) -> None:
        name = str(params.get("name", "")).strip()
        args = params.get("arguments", {})
        if not isinstance(args, dict):
            self._respond(msg_id, mcp_error_content("Tool arguments must be an object"))
            return

        if name == "unreal_chat":
            self._respond(msg_id, call_unreal_chat(args))
            return
        if name == "unreal_info":
            self._respond(msg_id, call_endpoint("/api/info"))
            return
        if name == "unreal_state":
            self._respond(msg_id, call_endpoint("/api/state"))
            return
        if name == "unreal_actions":
            self._respond(msg_id, call_endpoint("/api/actions"))
            return
        if name == "unreal_execute_action":
            self._respond(msg_id, call_execute_action(args))
            return
        if name == "unreal_run_recipe":
            self._respond(msg_id, call_run_recipe(args))
            return
        if name == "unreal_validate_recipe":
            self._respond(msg_id, call_validate_recipe(args))
            return
        if name == "unreal_run_scenario":
            self._respond(msg_id, call_run_scenario(args))
            return
        if name == "unreal_debug_traces":
            limit = int(args.get("limit", 50))
            flt = str(args.get("filter", "")).strip()
            query = f"?limit={limit}"
            if flt:
                query += f"&filter={urllib.parse.quote(flt)}"
            self._respond(msg_id, call_endpoint(f"/api/debug/traces{query}"))
            return
        if name == "unreal_refactor_catalog":
            self._respond(msg_id, call_post("/api/refactor-catalog", args))
            return
        if name == "unreal_refactor_preview":
            self._respond(msg_id, call_post("/api/refactor-preview", args))
            return
        if name == "unreal_explain_selection":
            self._respond(msg_id, call_post("/api/explain-selection", args))
            return
        if name == "unreal_explain_screenshot":
            self._respond(msg_id, call_post("/api/explain-screenshot", args))
            return
        if name == "unreal_project_dependencies":
            self._respond(msg_id, call_post("/api/project-dependencies", args))
            return
        if name == "unreal_perf_hotspots":
            self._respond(msg_id, call_post("/api/perf-hotspots", args))
            return
        if name == "unreal_impact_analysis":
            self._respond(msg_id, call_post("/api/impact-analysis", args))
            return
        if name == "unreal_umg_generate":
            self._respond(msg_id, call_post("/api/umg-generate", args))
            return
        if name == "unreal_world_generate":
            self._respond(msg_id, call_post("/api/world-generate", args))
            return
        if name == "unreal_claims_evidence":
            self._respond(msg_id, call_endpoint("/api/claims-evidence"))
            return
        if name == "unreal_workflow_catalog":
            self._respond(msg_id, call_endpoint("/api/workflow-catalog"))
            return
        if name == "unreal_node_control_capabilities":
            self._respond(msg_id, call_endpoint("/api/node-control-capabilities"))
            return
        if name == "unreal_workflow_generate":
            self._respond(msg_id, call_post("/api/workflow-generate", args))
            return
        if name == "unreal_graph_primitives_catalog":
            self._respond(msg_id, call_endpoint("/api/graph-primitives-catalog"))
            return
        if name == "unreal_graph_primitives_apply":
            self._respond(msg_id, call_post("/api/graph-primitives-apply", args))
            return
        if name == "unreal_runtime_validate_repair":
            self._respond(msg_id, call_post("/api/runtime-validate-repair", args))
            return
        if name == "unreal_autonomous_loop_run":
            self._respond(msg_id, call_post("/api/autonomous-loop-run", args))
            return
        if name == "unreal_animation_autonomy_catalog":
            self._respond(msg_id, call_endpoint("/api/animation-autonomy-catalog"))
            return
        if name == "unreal_animation_autonomy_generate":
            self._respond(msg_id, call_post("/api/animation-autonomy-generate", args))
            return
        if name == "unreal_ai_autonomy_catalog":
            self._respond(msg_id, call_endpoint("/api/ai-autonomy-catalog"))
            return
        if name == "unreal_ai_autonomy_generate":
            self._respond(msg_id, call_post("/api/ai-autonomy-generate", args))
            return
        if name == "unreal_blackboard_schema_evolve":
            self._respond(msg_id, call_post("/api/blackboard-schema-evolve", args))
            return
        if name == "unreal_ai_behavior_validate":
            self._respond(msg_id, call_post("/api/ai-behavior-validate", args))
            return
        if name == "unreal_content_pipeline_catalog":
            self._respond(msg_id, call_endpoint("/api/content-pipeline-catalog"))
            return
        if name == "unreal_content_pipeline_apply":
            self._respond(msg_id, call_post("/api/content-pipeline-apply", args))
            return
        if name == "unreal_content_schema_enforce":
            self._respond(msg_id, call_post("/api/content-schema-enforce", args))
            return
        if name == "unreal_dependency_safety_check":
            self._respond(msg_id, call_post("/api/dependency-safety-check", args))
            return
        if name == "unreal_multiplayer_correctness_catalog":
            self._respond(msg_id, call_endpoint("/api/multiplayer-correctness-catalog"))
            return
        if name == "unreal_multiplayer_lint":
            self._respond(msg_id, call_post("/api/multiplayer-lint", args))
            return
        if name == "unreal_multiplayer_guard_apply":
            self._respond(msg_id, call_post("/api/multiplayer-guard-apply", args))
            return
        if name == "unreal_multiplayer_pie_test":
            self._respond(msg_id, call_post("/api/multiplayer-pie-test", args))
            return
        if name == "unreal_blueprint_structure_review":
            self._respond(msg_id, call_post("/api/blueprint-structure-review", args))
            return
        if name == "unreal_rpc_contract_lint":
            self._respond(msg_id, call_post("/api/rpc-contract-lint", args))
            return
        if name == "unreal_ai_asset_authoring":
            self._respond(msg_id, call_post("/api/ai-asset-authoring", args))
            return
        if name == "unreal_native_asset_authoring_catalog":
            self._respond(msg_id, call_endpoint("/api/native-asset-authoring-catalog"))
            return
        if name == "unreal_native_asset_create":
            self._respond(msg_id, call_post("/api/native-asset-create", args))
            return
        if name == "unreal_native_asset_edit":
            self._respond(msg_id, call_post("/api/native-asset-edit", args))
            return
        if name == "unreal_native_asset_authoring_workflow":
            self._respond(msg_id, call_post("/api/native-asset-authoring-workflow", args))
            return
        if name == "unreal_pie_replay_suite":
            self._respond(msg_id, call_post("/api/pie-replay-suite", args))
            return
        if name == "unreal_material_mesh_presets_catalog":
            self._respond(msg_id, call_endpoint("/api/material-mesh-presets-catalog"))
            return
        if name == "unreal_material_mesh_setup":
            self._respond(msg_id, call_post("/api/material-mesh-setup", args))
            return
        if name == "unreal_execution_run_detail":
            run_id = urllib.parse.quote(str(args.get("run_id", "")).strip())
            self._respond(msg_id, call_endpoint(f"/api/execution-run-detail?run_id={run_id}"))
            return
        if name == "unreal_execution_artifact":
            run_id = urllib.parse.quote(str(args.get("run_id", "")).strip())
            include_snapshot = bool(args.get("include_snapshot", True))
            include_full = bool(args.get("include_full", False))
            self._respond(
                msg_id,
                call_endpoint(
                    f"/api/execution-artifact?run_id={run_id}&include_snapshot={'1' if include_snapshot else '0'}&include_full={'1' if include_full else '0'}"
                ),
            )
            return
        if name == "unreal_property_reflect":
            self._respond(msg_id, call_post("/api/property-reflect", args))
            return
        if name == "unreal_blueprint_function_author":
            self._respond(msg_id, call_post("/api/blueprint-function-author", args))
            return
        if name == "unreal_component_hierarchy":
            self._respond(msg_id, call_post("/api/component-hierarchy", args))
            return
        if name == "unreal_graph_pin_wire":
            self._respond(msg_id, call_post("/api/graph-pin-wire", args))
            return
        if name == "unreal_node_author":
            self._respond(msg_id, call_post("/api/node-author", args))
            return
        if name == "unreal_compile_diagnostics":
            self._respond(msg_id, call_post("/api/compile-diagnostics", args))
            return
        if name == "unreal_compile_gate_run":
            self._respond(msg_id, call_post("/api/compile-gate-run", args))
            return
        if name == "unreal_node_pattern_catalog":
            self._respond(msg_id, call_endpoint("/api/node-pattern-catalog"))
            return
        if name == "unreal_node_pattern_preview":
            self._respond(msg_id, call_post("/api/node-pattern-preview", args))
            return
        if name == "unreal_node_pattern_apply":
            self._respond(msg_id, call_post("/api/node-pattern-apply", args))
            return
        if name == "unreal_graph_snapshots":
            self._respond(msg_id, call_endpoint("/api/graph-snapshots"))
            return
        if name == "unreal_replay_suite":
            self._respond(msg_id, call_post("/api/replay-suite", args))
            return
        if name == "unreal_release_gate_evaluate":
            self._respond(msg_id, call_post("/api/release-gate-evaluate", args))
            return
        if name == "unreal_rollback_apply":
            self._respond(msg_id, call_post("/api/rollback-apply", args))
            return
        if name == "unreal_graph_ast_export":
            self._respond(msg_id, call_post("/api/graph-ast-export", args))
            return
        if name == "unreal_graph_ast_apply":
            self._respond(msg_id, call_post("/api/graph-ast-apply", args))
            return
        if name == "unreal_signature_edit":
            self._respond(msg_id, call_post("/api/signature-edit", args))
            return
        if name == "unreal_actor_transform_control":
            self._respond(msg_id, call_post("/api/actor-transform-control", args))
            return
        if name == "unreal_system_bootstrap":
            self._respond(msg_id, call_post("/api/system-bootstrap", args))
            return
        if name == "unreal_control_surface_catalog":
            self._respond(msg_id, call_endpoint("/api/control-surface-catalog"))
            return
        if name == "unreal_agent_readiness":
            self._respond(msg_id, call_endpoint("/api/agent-readiness"))
            return

        self._respond(msg_id, mcp_error_content(f"Unknown tool: {name}"))

    def serve(self) -> int:
        while self.running:
            message = self._read_message()
            if message is None:
                break

            method = message.get("method")
            msg_id = message.get("id")
            params = message.get("params", {})
            if not isinstance(params, dict):
                params = {}

            try:
                if method == "initialize":
                    self._respond(
                        msg_id,
                        {
                            "protocolVersion": "2024-11-05",
                            "serverInfo": {"name": "unreal-agent-cursor-mcp", "version": "0.1.0"},
                            "capabilities": {"tools": {}},
                        },
                    )
                elif method == "notifications/initialized":
                    ensure_agent_bootstrap(force=False)
                    # Notification has no response.
                    continue
                elif method == "tools/list":
                    self._respond(msg_id, {"tools": TOOLS})
                elif method == "tools/call":
                    self._handle_tool_call(msg_id, params)
                elif method == "ping":
                    self._respond(msg_id, {})
                elif msg_id is not None:
                    self._respond_error(msg_id, -32601, f"Method not found: {method}")
            except Exception as exc:  # noqa: BLE001
                if msg_id is not None:
                    self._respond_error(
                        msg_id,
                        -32603,
                        "Internal error",
                        {
                            "message": str(exc),
                            "trace": traceback.format_exc(),
                        },
                    )

        return 0


def main() -> int:
    server = StdioJsonRpcServer()
    return server.serve()


if __name__ == "__main__":
    sys.exit(main())
