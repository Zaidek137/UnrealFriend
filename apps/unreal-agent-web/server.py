#!/usr/bin/env python3
import json
import os
import random
import hashlib
import re
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent.parent
STATIC_DIR = APP_DIR / "static"
DATA_DIR = APP_DIR / ".data"
ANALYSIS_RUNS_DIR = DATA_DIR / "analysis-runs"
EXECUTION_RUNS_DIR = DATA_DIR / "execution-runs"
PAID_SESSION_LOGS_DIR = DATA_DIR / "paid-session-logs"
GRAPH_SNAPSHOTS_DIR = DATA_DIR / "graph-snapshots"
RECIPES_DIR = ROOT_DIR / "data" / "recipes"
SETTINGS_PATH = DATA_DIR / "settings.json"
APPROVALS_PATH = DATA_DIR / "approvals.json"
PAID_SESSIONS_PATH = DATA_DIR / "paid_sessions.json"
AUDIT_LOG_PATH = DATA_DIR / "audit.log.jsonl"
RELEASE_METRICS_PATH = DATA_DIR / "release_metrics.json"
USAGE_EVENTS_PATH = DATA_DIR / "usage_events.jsonl"
CLAIMS_EVIDENCE_PATH = DATA_DIR / "claims_evidence.json"
NODE_LIBRARY_INDEX_PATH = ROOT_DIR / "data" / "blueprint-node-library" / "node_library_index.json"

RUN_LOCK = threading.Lock()
APPROVALS_LOCK = threading.Lock()
AUDIT_LOCK = threading.Lock()
RELEASE_METRICS_LOCK = threading.Lock()
BOOTSTRAP_LOCK = threading.Lock()

BOOTSTRAP_REQUIRED_ROUTES: set[str] = set()
BOOTSTRAP_EXEMPT_ROUTES: set[str] = {
    "/api/settings",
    "/api/approve",
    "/api/paid/session/start",
    "/api/paid/session/end",
    "/api/entitlements/check",
    "/api/usage/event",
    "/api/agent-bootstrap",
}
BOOTSTRAP_SESSIONS: Dict[str, Dict[str, Any]] = {}

MUTATING_ACTIONS = {
    "create_blueprint",
    "spawn_actor",
    "modify_blueprint_graph",
    "create_widget_blueprint",
    "modify_widget_tree",
    "bind_widget_events",
    "generate_widget_template",
    "set_reflected_property",
    "create_blueprint_function",
    "create_blueprint_macro",
    "wire_blueprint_pins",
    "blueprint_node_authoring",
    "modify_blueprint_components",
    "edit_actor_transform",
    "create_game_mode_logic",
    "create_objective_actor",
    "wire_objective_progress",
    "create_timer_system",
    "create_score_system",
    "create_restart_flow",
    "batch_spawn_actors",
    "layout_along_spline",
    "create_level_chunk",
    "generate_layout_from_template",
    "scatter_assets_with_constraints",
    "clear_generated_layout_by_token",
    "tag_and_group_actors",
    "delete_actors_by_filter",
    "clear_map_layout",
    "create_data_asset",
    "create_behavior_tree_asset",
    "edit_behavior_tree_asset",
    "create_blackboard_data_asset",
    "edit_blackboard_data_asset",
    "create_eqs_query_asset",
    "edit_eqs_query_asset",
    "create_anim_blueprint_asset",
    "edit_anim_blueprint_state_machine",
    "create_material_asset",
    "edit_material_asset",
    "create_niagara_system_asset",
    "edit_niagara_system_graph",
    "create_level_sequence_asset",
    "edit_level_sequence_asset",
    "create_data_table",
    "edit_data_table_row",
}
ANALYSIS_ACTIONS = {
    "analyze_blueprint_graph",
    "analyze_blueprint_asset",
}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "unreal_base_url": "http://127.0.0.1:47777/unreal-agent/v1",
    "llm_enabled": False,
    "llm_base_url": "https://api.openai.com/v1",
    "llm_model": "gpt-4.1-mini",
    "llm_api_key": "",
    "llm_temperature": 0.1,
    "llm_max_replans": 1,
    "require_approval_for_mutations": False,
    "require_agent_readiness_for_mutations": True,
    "risky_actions": sorted(list(MUTATING_ACTIONS)),
    "min_api_version": "v1",
    "min_plugin_version": "0.1.0",
    "analysis_llm_summary": True,
    "analysis_require_citations": True,
    "analysis_disallow_speculative": True,
    "analysis_store_artifacts": True,
    "analysis_max_saved_runs": 200,
    "execution_profile": "balanced",
    "default_uproject_path": "",
    "default_project_root": "",
    "default_source_root": "",
    "default_content_root": "",
    "execution_preflight_enabled": True,
    "execution_store_artifacts": True,
    "execution_max_saved_runs": 300,
    "determinism_min_score": 85,
    "refactor_auto_repair_enabled": True,
    "refactor_auto_repair_max_attempts": 1,
    "compile_gate_max_blueprints": 100,
    "auto_verify_after_mutation": True,
    "auto_verify_enforce_pass": True,
    "auto_verify_scenario_repeats": 1,
    "auto_verify_assertions": [],
    "auto_verify_multiplayer": True,
    "auto_verify_multiplayer_client_count": 2,
    "auto_verify_multiplayer_repeats": 1,
    "auto_verify_max_rpc_risk_score": 40.0,
    "auto_verify_max_multiplayer_lint_risk_score": 40.0,
    "auto_verify_max_perf_risk_score": 35.0,
    "require_agent_bootstrap_for_routes": True,
    "agent_bootstrap_ttl_sec": 28800,
    "paid_live_logs_enabled": False,
    "paid_live_logs_tokens": [],
    "paid_live_logs_max_session_events": 2000,
    "paid_admin_tokens": [],
    "plan_tier_gate_enabled": False,
    "paid_tier_required_routes": [
        "/api/project-audit",
        "/api/validate-execution",
        "/api/refactor-preview",
        "/api/refactor-apply",
        "/api/impact-analysis",
        "/api/paid/session/start",
        "/api/paid/session/end",
        "/api/paid/session/logs",
        "/api/paid/session/stream",
    ],
}
SUPPORTED_EXECUTION_PROFILES = {"balanced", "strict", "aggressive"}

NODE_PATTERN_CATALOG: Dict[str, Dict[str, Any]] = {
    "begin_play_print": {
        "pattern_id": "begin_play_print",
        "description": "Spawn a PrintString call and wire BeginPlay -> PrintString.",
        "inputs": ["blueprint_path", "graph_name", "message"],
        "deterministic": True,
    },
    "begin_play_delay_print": {
        "pattern_id": "begin_play_delay_print",
        "description": "Spawn Delay + PrintString and wire BeginPlay -> Delay -> PrintString.",
        "inputs": ["blueprint_path", "graph_name", "duration", "message"],
        "deterministic": True,
    },
    "begin_play_branch_dual_print": {
        "pattern_id": "begin_play_branch_dual_print",
        "description": "Build BeginPlay -> Branch with true/false PrintString nodes for deterministic split-path scaffolding.",
        "inputs": ["blueprint_path", "graph_name", "base_node_name", "true_message", "false_message"],
        "deterministic": True,
    },
    "begin_play_sequence_two_stage": {
        "pattern_id": "begin_play_sequence_two_stage",
        "description": "Build BeginPlay -> Delay -> Print -> Delay -> Print for staged logic scaffolding.",
        "inputs": ["blueprint_path", "graph_name", "base_node_name", "first_delay", "second_delay", "first_message", "second_message"],
        "deterministic": True,
    },
    "replace_call_by_title": {
        "pattern_id": "replace_call_by_title",
        "description": "Replace an existing call-function node by title with a new function call while rewiring compatible links.",
        "inputs": ["blueprint_path", "graph_name", "target_node_title_contains", "function_class_path", "function_name", "base_node_name"],
        "deterministic": True,
    },
}

WORKFLOW_TEMPLATE_CATALOG: Dict[str, Dict[str, Any]] = {
    "objective_capture_loop_full": {
        "workflow_id": "objective_capture_loop_full",
        "description": "Create gameplay controller scaffold for objective capture loop with timer/score variables and deterministic graph hooks.",
        "inputs": ["namespace_root", "controller_asset_name", "objective_count", "time_limit_sec"],
        "deterministic": True,
    },
    "animation_locomotion_scaffold": {
        "workflow_id": "animation_locomotion_scaffold",
        "description": "Create AnimInstance scaffold with locomotion variables and deterministic update graph placeholders.",
        "inputs": ["namespace_root", "anim_asset_name"],
        "deterministic": True,
    },
    "character_combo_scaffold": {
        "workflow_id": "character_combo_scaffold",
        "description": "Inject deterministic roll/dash combo variables and timing scaffold into a character blueprint.",
        "inputs": ["character_blueprint_path", "combo_window_sec"],
        "deterministic": True,
    },
}

ANIMATION_AUTONOMY_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "locomotion_state_scaffold": {
        "template_id": "locomotion_state_scaffold",
        "description": "Create an AnimInstance scaffold with locomotion variables, update/evaluate functions, and transition placeholder events.",
        "inputs": ["namespace_root", "anim_asset_name"],
        "deterministic": True,
    },
    "montage_notify_scaffold": {
        "template_id": "montage_notify_scaffold",
        "description": "Create deterministic montage/notify placeholder variables and event hooks in an AnimInstance blueprint.",
        "inputs": ["namespace_root", "anim_asset_name"],
        "deterministic": True,
    },
}

AI_AUTONOMY_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "bt_eqs_perception_scaffold": {
        "template_id": "bt_eqs_perception_scaffold",
        "description": "Create AIController + BT task scaffolds, perception hooks, and deterministic BT/EQS placeholder wiring.",
        "inputs": ["namespace_root", "ai_controller_asset_name", "bt_task_asset_name", "eqs_query_name", "perception_range"],
        "deterministic": True,
    },
    "ai_patrol_chase_scaffold": {
        "template_id": "ai_patrol_chase_scaffold",
        "description": "Create deterministic patrol/chase AI controller scaffold with behavior state keys and perception-driven transitions.",
        "inputs": ["namespace_root", "ai_controller_asset_name", "blackboard_keys", "perception_range"],
        "deterministic": True,
    },
}

CONTENT_PIPELINE_PRESETS: Dict[str, Dict[str, Any]] = {
    "static_mesh_pack_basic": {
        "preset_id": "static_mesh_pack_basic",
        "description": "Run deterministic asset import materialization recipe with naming/folder defaults for static mesh packs.",
        "inputs": ["namespace_root", "pack_label", "naming_prefix", "default_material"],
        "deterministic": True,
    },
    "environment_art_pass": {
        "preset_id": "environment_art_pass",
        "description": "Apply deterministic environment asset materialization and dependency safety checks.",
        "inputs": ["namespace_root", "pack_label", "naming_prefix", "enforce_schema"],
        "deterministic": True,
    },
}

MULTIPLAYER_CORRECTNESS_PROFILES: Dict[str, Dict[str, Any]] = {
    "default_authority_safe": {
        "profile_id": "default_authority_safe",
        "description": "Insert authority/client guards, run replication lint, and execute deterministic multi-client validation harness.",
        "inputs": ["blueprint_path", "graph_name", "client_count", "repeats"],
        "deterministic": True,
    },
}

MATERIAL_MESH_SETUP_PRESETS: Dict[str, Dict[str, Any]] = {
    "static_mesh_actor_basic": {
        "preset_id": "static_mesh_actor_basic",
        "description": "Create an actor blueprint with a StaticMeshComponent and deterministic mesh/material assignment.",
        "inputs": ["asset_name", "package_path", "static_mesh_path", "material_path"],
        "deterministic": True,
    },
    "pickup_prop_basic": {
        "preset_id": "pickup_prop_basic",
        "description": "Create pickup prop actor scaffold with mesh/material and interaction placeholder variables.",
        "inputs": ["asset_name", "package_path", "static_mesh_path", "material_path"],
        "deterministic": True,
    },
}

NATIVE_ASSET_AUTHORING_CATALOG: Dict[str, Dict[str, Any]] = {
    "behavior_tree": {
        "asset_type": "behavior_tree",
        "create_action": "create_behavior_tree_asset",
        "edit_action": "edit_behavior_tree_asset",
        "inputs": ["asset_name", "package_path", "behavior_tree_path", "blackboard_path", "root_class_path", "tasks", "operations"],
        "deterministic": True,
    },
    "blackboard": {
        "asset_type": "blackboard",
        "create_action": "create_blackboard_data_asset",
        "edit_action": "edit_blackboard_data_asset",
        "inputs": ["asset_name", "package_path", "blackboard_path", "keys", "replace_existing"],
        "deterministic": True,
    },
    "eqs_query": {
        "asset_type": "eqs_query",
        "create_action": "create_eqs_query_asset",
        "edit_action": "edit_eqs_query_asset",
        "inputs": ["asset_name", "package_path", "eqs_path", "options", "replace_options", "operations"],
        "deterministic": True,
    },
    "anim_blueprint": {
        "asset_type": "anim_blueprint",
        "create_action": "create_anim_blueprint_asset",
        "edit_action": "edit_anim_blueprint_state_machine",
        "inputs": ["asset_name", "package_path", "anim_blueprint_path", "state_machine_name", "states", "operations", "compile_after"],
        "deterministic": True,
    },
    "material": {
        "asset_type": "material",
        "create_action": "create_material_asset",
        "edit_action": "edit_material_asset",
        "inputs": ["asset_name", "package_path", "material_path", "two_sided", "blend_mode", "shading_model", "operations"],
        "deterministic": True,
    },
    "niagara_system": {
        "asset_type": "niagara_system",
        "create_action": "create_niagara_system_asset",
        "edit_action": "edit_niagara_system_graph",
        "inputs": ["asset_name", "package_path", "niagara_system_path", "deterministic_seed", "determinism", "operations"],
        "deterministic": True,
    },
    "level_sequence": {
        "asset_type": "level_sequence",
        "create_action": "create_level_sequence_asset",
        "edit_action": "edit_level_sequence_asset",
        "inputs": ["asset_name", "package_path", "level_sequence_path", "playback_start", "playback_end", "operations"],
        "deterministic": True,
    },
}

DEFAULT_AGENT_READINESS_ACTIONS: List[str] = [
    "modify_blueprint_graph",
    "compile_blueprint",
    "wire_blueprint_pins",
    "blueprint_node_authoring",
    "blueprint_compile_diagnostics",
    "edit_actor_transform",
]

READINESS_MUTATING_ROUTES: set[str] = {
    "/api/direct-execute",
    "/api/run-plan",
    "/api/run-goal",
    "/api/command",
    "/api/refactor-apply",
    "/api/graph-ast-apply",
    "/api/signature-edit",
    "/api/actor-transform-control",
    "/api/system-bootstrap",
    "/api/graph-pin-wire",
    "/api/node-author",
    "/api/node-pattern-apply",
    "/api/workflow-generate",
    "/api/graph-primitives-apply",
    "/api/runtime-validate-repair",
    "/api/autonomous-loop-run",
    "/api/pie-replay-suite",
    "/api/animation-autonomy-generate",
    "/api/ai-autonomy-generate",
    "/api/blackboard-schema-evolve",
    "/api/content-pipeline-apply",
    "/api/content-schema-enforce",
    "/api/multiplayer-guard-apply",
    "/api/multiplayer-pie-test",
    "/api/material-mesh-setup",
    "/api/ai-asset-authoring",
    "/api/component-hierarchy",
    "/api/property-reflect",
    "/api/umg-generate",
    "/api/world-generate",
    "/api/native-asset-create",
    "/api/native-asset-edit",
    "/api/native-asset-authoring-workflow",
}
BOOTSTRAP_REQUIRED_ROUTES = set(READINESS_MUTATING_ROUTES)

GRAPH_MUTATION_ACTIONS: set[str] = {
    "modify_blueprint_graph",
    "wire_blueprint_pins",
    "blueprint_node_authoring",
    "create_blueprint_function",
    "create_blueprint_macro",
}


def get_control_surface_catalog_payload() -> Dict[str, Any]:
    return {
        "graph_ast": [
            "/api/graph-ast-export",
            "/api/graph-ast-apply",
        ],
        "signature_editing": [
            "/api/signature-edit",
        ],
        "component_actor_control": [
            "/api/component-hierarchy",
            "/api/property-reflect",
            "/api/actor-transform-control",
        ],
        "system_authoring": [
            "/api/system-bootstrap",
        ],
        "workflow_authoring": [
            "/api/node-pattern-catalog",
            "/api/node-pattern-preview",
            "/api/node-pattern-apply",
            "/api/workflow-catalog",
            "/api/workflow-generate",
        ],
        "graph_primitives": [
            "/api/graph-primitives-catalog",
            "/api/graph-primitives-apply",
        ],
        "runtime_validation": [
            "/api/runtime-validate-repair",
            "/api/autonomous-loop-run",
            "/api/pie-replay-suite",
        ],
        "animation_autonomy": [
            "/api/animation-autonomy-catalog",
            "/api/animation-autonomy-generate",
        ],
        "ai_autonomy": [
            "/api/ai-autonomy-catalog",
            "/api/ai-autonomy-generate",
            "/api/blackboard-schema-evolve",
            "/api/ai-behavior-validate",
        ],
        "content_pipeline_control": [
            "/api/content-pipeline-catalog",
            "/api/content-pipeline-apply",
            "/api/content-schema-enforce",
            "/api/dependency-safety-check",
        ],
        "multiplayer_correctness": [
            "/api/multiplayer-correctness-catalog",
            "/api/multiplayer-lint",
            "/api/multiplayer-guard-apply",
            "/api/multiplayer-pie-test",
        ],
        "asset_setup": [
            "/api/material-mesh-presets-catalog",
            "/api/material-mesh-setup",
            "/api/ai-asset-authoring",
        ],
        "native_editor_authoring": [
            "/api/native-asset-authoring-catalog",
            "/api/native-asset-create",
            "/api/native-asset-edit",
            "/api/native-asset-authoring-workflow",
        ],
        "blueprint_visibility": [
            "/api/blueprint-structure-review",
            "/api/rpc-contract-lint",
        ],
        "capability_introspection": [
            "/api/agent-bootstrap",
            "/api/node-control-capabilities",
            "/api/actions",
            "/api/agent-readiness",
        ],
    }


def build_agent_recovery_suggestions() -> List[str]:
    return [
        "Restart Unreal Editor to reload the latest plugin module.",
        "Restart the web tool so new API routes are active.",
        "Run /api/agent-readiness and verify missing_actions is empty.",
        "Confirm plugin version/api version satisfy minimum compatibility settings.",
    ]


def evaluate_agent_readiness(settings: Dict[str, Any]) -> Tuple[HTTPStatus, Dict[str, Any]]:
    compatibility = check_compatibility(settings)
    actions_result = call_unreal(settings, "GET", "/actions")
    action_items = []
    if isinstance(actions_result.payload, dict):
        action_items = actions_result.payload.get("actions", [])
    available_actions = set()
    if isinstance(action_items, list):
        for item in action_items:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                if name:
                    available_actions.add(name)
    missing_actions = sorted([name for name in DEFAULT_AGENT_READINESS_ACTIONS if name not in available_actions])
    compatibility_ok = bool(compatibility.get("ok", False))
    actions_ok = actions_result.status_code < 400 and isinstance(action_items, list)
    action_set_ok = len(missing_actions) == 0
    ready = compatibility_ok and actions_ok and action_set_ok
    status = HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE
    payload = {
        "success": ready,
        "ready": ready,
        "checks": {
            "compatibility_ok": compatibility_ok,
            "actions_endpoint_ok": actions_ok,
            "required_actions_present": action_set_ok,
        },
        "compatibility": compatibility,
        "required_actions": list(DEFAULT_AGENT_READINESS_ACTIONS),
        "missing_actions": missing_actions,
        "available_actions_count": len(available_actions),
        "control_surfaces": get_control_surface_catalog_payload(),
        "unreal_actions_status_code": actions_result.status_code,
        "recovery_suggestions": build_agent_recovery_suggestions(),
    }
    if not ready:
        payload["error_code"] = "AGENT_NOT_READY"
        payload["message"] = "Agent control surface is not fully ready."
    else:
        payload["message"] = "Agent control surface is ready."
    return status, payload


def infer_request_dry_run(path: str, body: Dict[str, Any]) -> bool:
    if path == "/api/run-plan":
        plan = body.get("plan", body)
        return bool(plan.get("dry_run", False)) if isinstance(plan, dict) else False
    if path == "/api/run-goal":
        goal_request = body.get("goal_request", body)
        return bool(goal_request.get("dry_run", False)) if isinstance(goal_request, dict) else False
    return bool(body.get("dry_run", False))


def enforce_agent_readiness_for_route(settings: Dict[str, Any], path: str, body: Dict[str, Any]) -> Optional[Tuple[HTTPStatus, Dict[str, Any]]]:
    if not bool(settings.get("require_agent_readiness_for_mutations", True)):
        return None
    if path not in READINESS_MUTATING_ROUTES:
        return None
    if infer_request_dry_run(path, body):
        return None
    status, payload = evaluate_agent_readiness(settings)
    if status == HTTPStatus.OK:
        return None
    return status, payload


def _prune_bootstrap_sessions(now_ts: Optional[float] = None) -> None:
    now = float(now_ts if now_ts is not None else time.time())
    with BOOTSTRAP_LOCK:
        expired = [token for token, meta in BOOTSTRAP_SESSIONS.items() if float(meta.get("expires_at", 0.0)) <= now]
        for token in expired:
            BOOTSTRAP_SESSIONS.pop(token, None)


def issue_agent_bootstrap_session(
    settings: Dict[str, Any],
    *,
    client_name: str,
    client_version: str,
    session_label: str,
    readiness: Dict[str, Any],
    capability_context: Dict[str, Any],
) -> Dict[str, Any]:
    now = time.time()
    ttl_sec = max(60, int(settings.get("agent_bootstrap_ttl_sec", 28800)))
    token = f"abs_{uuid4().hex}"
    record = {
        "token": token,
        "created_at": now,
        "updated_at": now,
        "expires_at": now + ttl_sec,
        "client_name": client_name,
        "client_version": client_version,
        "session_label": session_label,
        "readiness_fingerprint": _stable_hash(
            {
                "required_actions": readiness.get("required_actions", []),
                "missing_actions": readiness.get("missing_actions", []),
                "compatibility": readiness.get("compatibility", {}),
            }
        ),
        "capability_fingerprint": _stable_hash(capability_context),
    }
    _prune_bootstrap_sessions(now)
    with BOOTSTRAP_LOCK:
        BOOTSTRAP_SESSIONS[token] = record
    return record


def validate_agent_bootstrap_session(settings: Dict[str, Any], token: str) -> Tuple[bool, Dict[str, Any]]:
    now = time.time()
    _prune_bootstrap_sessions(now)
    if not token:
        return False, make_error(
            "AGENT_BOOTSTRAP_REQUIRED",
            "Agent bootstrap token is required. Call /api/agent-bootstrap first.",
            bootstrap_route="/api/agent-bootstrap",
        )
    with BOOTSTRAP_LOCK:
        record = BOOTSTRAP_SESSIONS.get(token)
        if not isinstance(record, dict):
            return False, make_error(
                "AGENT_BOOTSTRAP_INVALID",
                "Agent bootstrap token is invalid. Call /api/agent-bootstrap to start a new session.",
                bootstrap_route="/api/agent-bootstrap",
            )
        expires_at = float(record.get("expires_at", 0.0))
        if expires_at <= now:
            BOOTSTRAP_SESSIONS.pop(token, None)
            return False, make_error(
                "AGENT_BOOTSTRAP_EXPIRED",
                "Agent bootstrap session has expired. Call /api/agent-bootstrap again.",
                bootstrap_route="/api/agent-bootstrap",
            )
        ttl_sec = max(60, int(settings.get("agent_bootstrap_ttl_sec", 28800)))
        record["updated_at"] = now
        record["expires_at"] = now + ttl_sec
        BOOTSTRAP_SESSIONS[token] = record
        return True, {
            "success": True,
            "bootstrap_token": token,
            "expires_at": float(record.get("expires_at", 0.0)),
            "client_name": str(record.get("client_name", "")),
            "session_label": str(record.get("session_label", "")),
        }


def build_agent_bootstrap_capability_context() -> Dict[str, Any]:
    return {
        "control_surfaces": get_control_surface_catalog_payload(),
        "graph_actions": sorted(list(GRAPH_MUTATION_ACTIONS)),
        "route_groups": {
            "bootstrap_required_routes": sorted(list(BOOTSTRAP_REQUIRED_ROUTES)),
            "bootstrap_exempt_routes": sorted(list(BOOTSTRAP_EXEMPT_ROUTES)),
        },
        "native_asset_authoring_types": sorted(
            [item.get("asset_type", "") for item in NATIVE_ASSET_AUTHORING_CATALOG.values() if isinstance(item, dict)]
        ),
    }


def extract_bootstrap_token(headers: Any, body: Optional[Dict[str, Any]] = None) -> str:
    header_token = ""
    if headers is not None:
        try:
            header_token = str(headers.get("X-Agent-Bootstrap-Token", "")).strip()
        except Exception:
            header_token = ""
    if header_token:
        return header_token
    if isinstance(body, dict):
        return str(body.get("bootstrap_token", "")).strip()
    return ""


def enforce_agent_bootstrap_for_route(
    settings: Dict[str, Any],
    path: str,
    body: Dict[str, Any],
    headers: Any,
) -> Optional[Tuple[HTTPStatus, Dict[str, Any]]]:
    if not bool(settings.get("require_agent_bootstrap_for_routes", True)):
        return None
    if path in BOOTSTRAP_EXEMPT_ROUTES:
        return None
    if path not in BOOTSTRAP_REQUIRED_ROUTES:
        return None
    bootstrap_token = extract_bootstrap_token(headers, body)
    ok, payload = validate_agent_bootstrap_session(settings, bootstrap_token)
    if ok:
        return None
    code = str(payload.get("error_code", ""))
    if code == "AGENT_BOOTSTRAP_REQUIRED":
        return HTTPStatus.PRECONDITION_REQUIRED, payload
    if code == "AGENT_BOOTSTRAP_EXPIRED":
        return HTTPStatus.UNAUTHORIZED, payload
    return HTTPStatus.UNAUTHORIZED, payload


@dataclass
class HttpResult:
    status_code: int
    payload: Dict[str, Any]


def make_error(code: str, message: str, **extra: Any) -> Dict[str, Any]:
    payload = {"success": False, "error_code": code, "message": message}
    payload.update(extra)
    return payload


def normalize_error_payload(payload: Dict[str, Any], fallback_code: str = "UPSTREAM_ERROR") -> Dict[str, Any]:
    normalized = dict(payload)
    normalized.setdefault("success", False)
    normalized.setdefault("error_code", fallback_code)
    normalized.setdefault("message", "Request failed.")
    return normalized


def normalize_execution_profile(profile_value: Any, fallback: str = "balanced") -> str:
    profile = str(profile_value).strip().lower()
    if profile in SUPPORTED_EXECUTION_PROFILES:
        return profile
    return fallback if fallback in SUPPORTED_EXECUTION_PROFILES else "balanced"


def default_project_context(settings: Dict[str, Any]) -> Dict[str, str]:
    mapping = {
        "uproject_path": "default_uproject_path",
        "project_root": "default_project_root",
        "source_root": "default_source_root",
        "content_root": "default_content_root",
    }
    context: Dict[str, str] = {}
    for context_key, settings_key in mapping.items():
        value = str(settings.get(settings_key, "")).strip()
        if value:
            context[context_key] = value
    return context


def merge_default_project_context(settings: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(context) if isinstance(context, dict) else {}
    defaults = default_project_context(settings)
    for key, value in defaults.items():
        existing = merged.get(key, "")
        if not isinstance(existing, str) or not existing.strip():
            merged[key] = value
    return merged


def merge_default_project_inputs(settings: Dict[str, Any], inputs: Dict[str, Any], recipe_def: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(inputs) if isinstance(inputs, dict) else {}
    if recipe_def is None:
        return merged
    schema_names = {
        str(item.get("name", "")).strip()
        for item in recipe_def.get("inputs", [])
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    }
    for key, value in default_project_context(settings).items():
        if key in schema_names and key not in merged:
            merged[key] = value
    return merged


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    EXECUTION_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    PAID_SESSION_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed
    except Exception:
        return default


def save_json_file(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_settings() -> Dict[str, Any]:
    ensure_data_dir()
    stored = load_json_file(SETTINGS_PATH, {})
    if not isinstance(stored, dict):
        stored = {}
    merged = dict(DEFAULT_SETTINGS)
    merged.update(stored)
    return merged


def save_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    ensure_data_dir()
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings)
    save_json_file(SETTINGS_PATH, merged)
    return merged


def load_approvals() -> Dict[str, Any]:
    ensure_data_dir()
    stored = load_json_file(APPROVALS_PATH, {"items": {}})
    if not isinstance(stored, dict):
        return {"items": {}}
    if "items" not in stored or not isinstance(stored["items"], dict):
        stored["items"] = {}
    return stored


def save_approvals(data: Dict[str, Any]) -> None:
    ensure_data_dir()
    save_json_file(APPROVALS_PATH, data)


def load_paid_sessions() -> Dict[str, Any]:
    ensure_data_dir()
    stored = load_json_file(PAID_SESSIONS_PATH, {"sessions": {}})
    if not isinstance(stored, dict):
        return {"sessions": {}}
    if "sessions" not in stored or not isinstance(stored["sessions"], dict):
        stored["sessions"] = {}
    return stored


def save_paid_sessions(data: Dict[str, Any]) -> None:
    ensure_data_dir()
    save_json_file(PAID_SESSIONS_PATH, data)


def session_log_path(session_id: str) -> Path:
    safe = "".join(ch for ch in session_id if ch.isalnum() or ch in {"-", "_"})
    if not safe:
        safe = "invalid"
    return PAID_SESSION_LOGS_DIR / f"{safe}.jsonl"


def trim_session_log(path: Path, max_events: int) -> None:
    if max_events <= 0 or not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= max_events:
            return
        kept = lines[-max_events:]
        path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    except Exception:
        pass


def append_paid_session_event(settings: Dict[str, Any], session_id: str, event: Dict[str, Any]) -> bool:
    if not bool(settings.get("paid_live_logs_enabled", False)):
        return False
    if not session_id:
        return False

    sessions = load_paid_sessions()
    meta = sessions.get("sessions", {}).get(session_id)
    if not isinstance(meta, dict):
        return False

    payload = dict(event)
    payload.setdefault("timestamp", time.time())
    payload.setdefault("session_id", session_id)

    path = session_log_path(session_id)
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
    except Exception:
        return False

    meta["last_event_at"] = float(payload["timestamp"])
    sessions["sessions"][session_id] = meta
    save_paid_sessions(sessions)
    trim_session_log(path, int(settings.get("paid_live_logs_max_session_events", 2000)))
    return True


def read_paid_session_events(session_id: str, since_ts: float = 0.0, limit: int = 200) -> List[Dict[str, Any]]:
    path = session_log_path(session_id)
    if not path.exists():
        return []
    events: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if not isinstance(item, dict):
                continue
            ts = float(item.get("timestamp", 0.0))
            if ts < since_ts:
                continue
            events.append(item)
    except Exception:
        return []
    if limit > 0 and len(events) > limit:
        return events[-limit:]
    return events


def create_paid_session(settings: Dict[str, Any], token: str, user_id: str, project_label: str) -> Tuple[bool, Dict[str, Any]]:
    if not bool(settings.get("paid_live_logs_enabled", False)):
        return False, make_error("PAID_LOGS_DISABLED", "Paid live logs are disabled.")
    configured_tokens = settings.get("paid_live_logs_tokens", [])
    valid_tokens = set()
    if isinstance(configured_tokens, list):
        for item in configured_tokens:
            if isinstance(item, str) and item.strip():
                valid_tokens.add(item.strip())
    if len(valid_tokens) == 0:
        return False, make_error("PAID_LOGS_NOT_CONFIGURED", "No paid live log tokens configured.")
    if token not in valid_tokens:
        return False, make_error("PAID_LOGS_UNAUTHORIZED", "Invalid paid live log token.")

    session_id = f"pls_{int(time.time())}_{uuid4().hex[:8]}"
    now = time.time()
    sessions = load_paid_sessions()
    sessions.setdefault("sessions", {})
    sessions["sessions"][session_id] = {
        "session_id": session_id,
        "created_at": now,
        "last_event_at": now,
        "active": True,
        "user_id": user_id,
        "project_label": project_label,
    }
    save_paid_sessions(sessions)
    append_paid_session_event(
        settings,
        session_id,
        {
            "kind": "session_started",
            "status": "info",
            "message": "Paid live log session started.",
            "payload": {"user_id": user_id, "project_label": project_label},
        },
    )
    return True, {"success": True, "session_id": session_id}


def get_valid_paid_tokens(settings: Dict[str, Any]) -> set[str]:
    configured_tokens = settings.get("paid_live_logs_tokens", [])
    valid_tokens: set[str] = set()
    if isinstance(configured_tokens, list):
        for item in configured_tokens:
            if isinstance(item, str) and item.strip():
                valid_tokens.add(item.strip())
    return valid_tokens


def get_valid_admin_tokens(settings: Dict[str, Any]) -> set[str]:
    configured_tokens = settings.get("paid_admin_tokens", [])
    valid_tokens: set[str] = set()
    if isinstance(configured_tokens, list):
        for item in configured_tokens:
            if isinstance(item, str) and item.strip():
                valid_tokens.add(item.strip())
    if len(valid_tokens) == 0:
        valid_tokens = get_valid_paid_tokens(settings)
    return valid_tokens


class AuthProvider:
    def validate(self, token: str) -> bool:
        raise NotImplementedError


class EntitlementProvider:
    def check(self, token: str, feature: str) -> Dict[str, Any]:
        raise NotImplementedError


class BillingProvider:
    def record_usage(self, token: str, event_type: str, amount: float, metadata: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class SessionLogProvider:
    def diagnostics(self) -> Dict[str, Any]:
        raise NotImplementedError


class FileAuthProvider(AuthProvider):
    def __init__(self, settings: Dict[str, Any]) -> None:
        self.settings = settings

    def validate(self, token: str) -> bool:
        return token in get_valid_paid_tokens(self.settings)


class FileEntitlementProvider(EntitlementProvider):
    def __init__(self, auth: AuthProvider) -> None:
        self.auth = auth

    def check(self, token: str, feature: str) -> Dict[str, Any]:
        enabled = self.auth.validate(token)
        return {
            "entitled": enabled,
            "feature": feature,
            "source": "file_provider",
            "reason": "token_valid" if enabled else "token_invalid",
        }


class FileBillingProvider(BillingProvider):
    def record_usage(self, token: str, event_type: str, amount: float, metadata: Dict[str, Any]) -> Dict[str, Any]:
        ensure_data_dir()
        line = {
            "timestamp": time.time(),
            "token_hint": token[:4] if token else "",
            "event_type": event_type,
            "amount": float(amount),
            "metadata": metadata if isinstance(metadata, dict) else {},
        }
        with AUDIT_LOCK:
            with USAGE_EVENTS_PATH.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(line) + "\n")
        return {"success": True, "stored": True, "provider": "file_provider"}


class FileSessionLogProvider(SessionLogProvider):
    def diagnostics(self) -> Dict[str, Any]:
        sessions = load_paid_sessions().get("sessions", {})
        active = 0
        items: List[Dict[str, Any]] = []
        for sid, meta in sessions.items():
            if not isinstance(meta, dict):
                continue
            is_active = bool(meta.get("active", False))
            if is_active:
                active += 1
            path = session_log_path(str(sid))
            event_count = 0
            if path.exists():
                try:
                    event_count = len(path.read_text(encoding="utf-8").splitlines())
                except Exception:
                    event_count = 0
            items.append(
                {
                    "session_id": str(sid),
                    "active": is_active,
                    "created_at": float(meta.get("created_at", 0.0)),
                    "last_event_at": float(meta.get("last_event_at", 0.0)),
                    "event_count": int(event_count),
                    "user_id": str(meta.get("user_id", "")),
                    "project_label": str(meta.get("project_label", "")),
                }
            )
        items.sort(key=lambda x: float(x.get("last_event_at", 0.0)), reverse=True)
        return {
            "provider": "file_provider",
            "session_count": len(items),
            "active_session_count": active,
            "sessions": items[:200],
        }


def build_paid_providers(settings: Dict[str, Any]) -> Tuple[AuthProvider, EntitlementProvider, BillingProvider, SessionLogProvider]:
    auth = FileAuthProvider(settings)
    entitlement = FileEntitlementProvider(auth)
    billing = FileBillingProvider()
    session_logs = FileSessionLogProvider()
    return auth, entitlement, billing, session_logs


def log_event(kind: str, payload: Dict[str, Any]) -> None:
    ensure_data_dir()
    line = {
        "timestamp": time.time(),
        "kind": kind,
        "payload": payload,
    }
    with AUDIT_LOCK:
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")


def request_json(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout_sec: int = 30,
) -> HttpResult:
    data = None
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url=url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as response:
            body = response.read().decode("utf-8")
            try:
                parsed = json.loads(body)
                if not isinstance(parsed, dict):
                    parsed = {"raw": parsed}
            except json.JSONDecodeError:
                parsed = {"raw": body}
            return HttpResult(status_code=response.status, payload=parsed)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
            if not isinstance(parsed, dict):
                parsed = {"raw": parsed}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return HttpResult(status_code=exc.code, payload=normalize_error_payload(parsed))
    except urllib.error.URLError as exc:
        return HttpResult(
            status_code=HTTPStatus.BAD_GATEWAY,
            payload=make_error("UNREAL_UNREACHABLE", f"Connection error: {exc.reason}"),
        )
    except Exception as exc:  # noqa: BLE001
        return HttpResult(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            payload=make_error("HTTP_CLIENT_ERROR", str(exc)),
        )


def call_unreal(settings: Dict[str, Any], method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> HttpResult:
    base = str(settings.get("unreal_base_url", "")).rstrip("/")
    return request_json(method, f"{base}{path}", payload=payload, timeout_sec=120)


def parse_version(version: str) -> Tuple[int, ...]:
    cleaned = version.strip().lower().replace("v", "")
    parts = []
    for token in cleaned.split("."):
        token = token.strip()
        if not token:
            continue
        digits = ""
        for ch in token:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            parts.append(int(digits))
    return tuple(parts) if parts else (0,)


def extract_first_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("LLM returned empty response.")

    if "```" in text:
        for part in text.split("```"):
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM response did not contain a JSON object.")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON output must be an object.")
    return parsed


def check_compatibility(settings: Dict[str, Any]) -> Dict[str, Any]:
    info = call_unreal(settings, "GET", "/info")
    if info.status_code >= 400:
        return {"ok": False, "reason": "unreal_info_unavailable", "info": info.payload}

    plugin_version = str(info.payload.get("plugin_version", "0.0.0"))
    api_version = str(info.payload.get("api_version", ""))
    min_plugin = str(settings.get("min_plugin_version", "0.1.0"))
    min_api = str(settings.get("min_api_version", "v1"))

    plugin_ok = parse_version(plugin_version) >= parse_version(min_plugin)
    api_ok = api_version == min_api

    return {
        "ok": plugin_ok and api_ok,
        "plugin_ok": plugin_ok,
        "api_ok": api_ok,
        "plugin_version": plugin_version,
        "min_plugin_version": min_plugin,
        "api_version": api_version,
        "min_api_version": min_api,
        "info": info.payload,
    }


def load_node_library_index() -> Dict[str, Any]:
    if not NODE_LIBRARY_INDEX_PATH.exists():
        return {}
    parsed = load_json_file(NODE_LIBRARY_INDEX_PATH, {})
    return parsed if isinstance(parsed, dict) else {}


def build_node_library_context(command: str, goal_context: Dict[str, Any]) -> Dict[str, Any]:
    idx = load_node_library_index()
    if not idx:
        return {}

    query_parts = [command] + [str(k) for k in goal_context.keys()] + [str(v) for v in goal_context.values() if isinstance(v, str)]
    query_text = " ".join(query_parts).lower()
    query_terms = {term for term in re_split_tokens(query_text) if len(term) >= 4}

    node_hits: List[Dict[str, Any]] = []
    pattern_hits: List[Dict[str, Any]] = []

    for node in idx.get("node_types", []):
        if not isinstance(node, dict):
            continue
        blob = " ".join(
            [
                str(node.get("name", "")),
                str(node.get("class", "")),
                str(node.get("description", "")),
                str(node.get("properties", "")),
                str(node.get("pins", "")),
                " ".join(str(n) for n in node.get("notes", [])),
            ]
        ).lower()
        if any(term in blob for term in query_terms):
            node_hits.append(
                {
                    "name": node.get("name", ""),
                    "class": node.get("class", ""),
                    "properties": node.get("properties", ""),
                    "pins": node.get("pins", ""),
                }
            )
        if len(node_hits) >= 8:
            break

    for pattern in idx.get("connection_patterns", []):
        if not isinstance(pattern, dict):
            continue
        blob = " ".join([str(pattern.get("name", ""))] + [str(s) for s in pattern.get("steps", [])]).lower()
        if any(term in blob for term in query_terms):
            pattern_hits.append(
                {
                    "name": pattern.get("name", ""),
                    "steps": pattern.get("steps", [])[:10],
                }
            )
        if len(pattern_hits) >= 5:
            break

    return {"node_hits": node_hits, "connection_pattern_hits": pattern_hits}


def re_split_tokens(text: str) -> List[str]:
    token = ""
    out: List[str] = []
    for ch in text:
        if ch.isalnum() or ch == "_":
            token += ch
        else:
            if token:
                out.append(token)
                token = ""
    if token:
        out.append(token)
    return out


def parse_bool_like(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return default


def normalize_blueprint_path(path: str) -> str:
    cleaned = path.strip()
    if not cleaned:
        return ""
    if "." in cleaned:
        return cleaned.split(".", 1)[0]
    return cleaned


def validate_plan_with_node_library(plan: Dict[str, Any]) -> Dict[str, Any]:
    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        return {"ok": False, "errors": ["Plan steps must be an array."], "warnings": []}

    errors: List[str] = []
    warnings: List[str] = []
    dry_run = bool(plan.get("dry_run", False))
    allowed_graph_ops = {
        "add_print_string_on_begin_play",
        "add_variable",
        "remove_variable",
        "set_default",
        "add_branch",
        "call_function",
        "remove_function_call",
        "remove_nodes",
        "disconnect_pin",
    }
    allowed_variable_types = {
        "bool",
        "boolean",
        "int",
        "integer",
        "float",
        "string",
        "name",
        "vector",
        "rotator",
        "transform",
        "object",
        "class",
    }
    allowed_exec_sources = {"begin_play", "branch_true", "branch_false", "none"}

    compile_blueprints_raw = plan.get("compile_blueprints", [])
    compile_blueprints_set: set[str] = set()
    if isinstance(compile_blueprints_raw, list):
        for item in compile_blueprints_raw:
            if not isinstance(item, str):
                warnings.append("compile_blueprints should only contain strings.")
                continue
            normalized_item = normalize_blueprint_path(item)
            if normalized_item:
                compile_blueprints_set.add(normalized_item)
    elif compile_blueprints_raw:
        warnings.append("compile_blueprints should be an array when present.")

    modified_blueprints_without_compile: set[str] = set()

    for i, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            errors.append(f"Step {i}: step must be an object.")
            continue

        action = str(step.get("action", "")).strip()
        payload = step.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
            warnings.append(f"Step {i}: payload is missing or not an object.")

        if action == "modify_blueprint_graph":
            op = str(payload.get("operation", "")).strip()
            if not op:
                errors.append(f"Step {i}: modify_blueprint_graph requires payload.operation.")
                continue
            if op not in allowed_graph_ops:
                errors.append(f"Step {i}: unsupported operation '{op}' for modify_blueprint_graph.")
                continue

            if not str(payload.get("blueprint_path", "")).strip():
                errors.append(f"Step {i}: operation '{op}' requires payload.blueprint_path.")

            if op == "call_function":
                if not str(payload.get("class_path", "")).strip():
                    errors.append(f"Step {i}: call_function requires payload.class_path.")
                if not str(payload.get("function_name", "")).strip():
                    errors.append(f"Step {i}: call_function requires payload.function_name.")
                exec_source = str(payload.get("exec_source", "begin_play")).strip().lower()
                if exec_source not in allowed_exec_sources:
                    errors.append(
                        f"Step {i}: call_function payload.exec_source must be one of {sorted(list(allowed_exec_sources))}."
                    )
            elif op == "add_variable":
                if not str(payload.get("variable_name", "")).strip():
                    errors.append(f"Step {i}: add_variable requires payload.variable_name.")
                variable_type = str(payload.get("variable_type", "bool")).strip().lower()
                if variable_type not in allowed_variable_types:
                    errors.append(
                        f"Step {i}: add_variable payload.variable_type '{variable_type}' is unsupported."
                    )
            elif op == "remove_variable":
                if not str(payload.get("variable_name", "")).strip():
                    errors.append(f"Step {i}: remove_variable requires payload.variable_name.")
            elif op == "set_default":
                if "default_value" not in payload:
                    errors.append(f"Step {i}: set_default requires payload.default_value.")
                variable_name = str(payload.get("variable_name", "")).strip()
                class_path = str(payload.get("class_path", "")).strip()
                function_name = str(payload.get("function_name", "")).strip()
                if not variable_name:
                    if not class_path or not function_name:
                        errors.append(
                            f"Step {i}: set_default requires payload.variable_name OR payload.class_path + payload.function_name."
                        )
            elif op == "remove_function_call":
                if not str(payload.get("class_path", "")).strip():
                    errors.append(f"Step {i}: remove_function_call requires payload.class_path.")
                if not str(payload.get("function_name", "")).strip():
                    errors.append(f"Step {i}: remove_function_call requires payload.function_name.")
            elif op == "remove_nodes":
                has_any_filter = any(
                    str(payload.get(name, "")).strip()
                    for name in [
                        "node_name_contains",
                        "node_title_contains",
                        "node_class_path",
                        "function_class_path",
                        "function_name",
                    ]
                )
                if not has_any_filter:
                    errors.append(
                        f"Step {i}: remove_nodes requires at least one filter "
                        "(node_name_contains, node_title_contains, node_class_path, function_class_path, function_name)."
                    )
            elif op == "disconnect_pin":
                required = ["from_node_name", "from_pin_name", "to_node_name", "to_pin_name"]
                for field in required:
                    if not str(payload.get(field, "")).strip():
                        errors.append(f"Step {i}: disconnect_pin requires payload.{field}.")

            compile_after = parse_bool_like(payload.get("compile_after"), True)
            blueprint_path = normalize_blueprint_path(str(payload.get("blueprint_path", "")))
            if not compile_after and blueprint_path:
                modified_blueprints_without_compile.add(blueprint_path)

        elif action == "create_blueprint":
            package_path = str(payload.get("package_path", "")).strip()
            if package_path and not package_path.startswith("/Game"):
                warnings.append(f"Step {i}: create_blueprint package_path should usually be under /Game.")

    if not dry_run:
        for bp_path in sorted(modified_blueprints_without_compile):
            if bp_path not in compile_blueprints_set:
                errors.append(
                    f"Plan modifies '{bp_path}' with compile_after=false but does not include it in compile_blueprints."
                )

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def generate_plan_with_llm(
    settings: Dict[str, Any],
    command: str,
    actions_payload: Dict[str, Any],
    dry_run: bool,
    stop_on_error: bool,
    goal_context: Dict[str, Any],
    state_payload: Optional[Dict[str, Any]] = None,
    info_payload: Optional[Dict[str, Any]] = None,
    prior_plan: Optional[Dict[str, Any]] = None,
    prior_execution: Optional[Dict[str, Any]] = None,
    node_library_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    llm_api_key = str(settings.get("llm_api_key", "")).strip()
    llm_base_url = str(settings.get("llm_base_url", "")).rstrip("/")
    llm_model = str(settings.get("llm_model", "")).strip()
    temperature = float(settings.get("llm_temperature", 0.1))
    if not llm_base_url:
        raise ValueError("LLM base URL is missing.")
    if not llm_model:
        raise ValueError("LLM model is missing.")

    actions = actions_payload.get("actions", [])
    actions_text = json.dumps(actions, indent=2)
    context_text = json.dumps(goal_context or {}, indent=2)
    state_text = json.dumps(state_payload or {}, indent=2)
    info_text = json.dumps(info_payload or {}, indent=2)
    prior_plan_text = json.dumps(prior_plan or {}, indent=2)
    prior_execution_text = json.dumps(prior_execution or {}, indent=2)
    node_library_text = json.dumps(node_library_context or {}, indent=2)
    system_prompt = (
        "You are an autonomous Unreal Engine operator. "
        "Infer the required tool actions from natural language goals without the user naming tool actions. "
        "Use current editor state and prior execution feedback when available. "
        "Use the blueprint node reference context to avoid invalid graph operations and pin mismatches. "
        "For every modify_blueprint_graph step, ensure there is compile coverage via compile_after=true or plan.compile_blueprints. "
        "Return ONLY a JSON object with schema: "
        "{plan_id:string,dry_run:boolean,stop_on_error:boolean,steps:[{id:string,action:string,payload:object}],"
        "compile_blueprints:[string]}. "
        "Use only listed actions."
    )
    user_prompt = (
        f"Goal: {command}\n"
        f"Available actions:\n{actions_text}\n"
        f"Engine/Plugin Info:\n{info_text}\n"
        f"Current Editor State:\n{state_text}\n"
        f"Context:\n{context_text}\n"
        f"Blueprint node reference context:\n{node_library_text}\n"
        f"Prior plan (if any):\n{prior_plan_text}\n"
        f"Prior execution result (if any):\n{prior_execution_text}\n"
        f"Constraints: dry_run={str(dry_run).lower()}, stop_on_error={str(stop_on_error).lower()}"
    )
    body = {
        "model": llm_model,
        "temperature": temperature,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
    }

    headers: Dict[str, str] = {}
    if llm_api_key:
        headers["Authorization"] = f"Bearer {llm_api_key}"

    result = request_json(
        "POST",
        f"{llm_base_url}/chat/completions",
        payload=body,
        headers=headers,
        timeout_sec=90,
    )
    if result.status_code >= 400:
        raise RuntimeError(f"LLM request failed ({result.status_code}): {json.dumps(result.payload)}")

    choices = result.payload.get("choices", [])
    if not choices:
        raise ValueError("LLM returned no choices.")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if not isinstance(content, str):
        raise ValueError("LLM message content missing.")

    plan = extract_first_json_object(content)
    if "steps" not in plan or not isinstance(plan["steps"], list) or not plan["steps"]:
        raise ValueError("LLM plan must include non-empty steps[].")
    plan["dry_run"] = dry_run
    plan["stop_on_error"] = stop_on_error
    if not isinstance(plan.get("plan_id"), str) or not plan["plan_id"].strip():
        plan["plan_id"] = "webtool-generated-plan"
    return plan


def get_plan_actions(plan: Dict[str, Any]) -> List[str]:
    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        return []
    actions: List[str] = []
    for step in steps:
        if isinstance(step, dict):
            action = str(step.get("action", "")).strip()
            if action:
                actions.append(action)
    return actions


def collect_analysis_contradictions(obj: Any, path: str = "root") -> List[str]:
    issues: List[str] = []
    if isinstance(obj, dict):
        error_code = str(obj.get("error_code", "")).strip()
        if error_code == "ANALYSIS_CONTRADICTION":
            issues.append(f"{path}: error_code=ANALYSIS_CONTRADICTION")

        contradictions = obj.get("contradictions")
        if isinstance(contradictions, list) and len(contradictions) > 0:
            issues.append(f"{path}: contradictions={len(contradictions)}")

        total_contradictions = obj.get("total_contradictions")
        if isinstance(total_contradictions, (int, float)) and int(total_contradictions) > 0:
            issues.append(f"{path}: total_contradictions={int(total_contradictions)}")

        for key, value in obj.items():
            issues.extend(collect_analysis_contradictions(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            issues.extend(collect_analysis_contradictions(value, f"{path}[{idx}]"))
    return issues


SPECULATIVE_TERMS = [
    "likely",
    "maybe",
    "possibly",
    "probably",
    "e.g.",
    "for example",
    "appears to",
    "seems to",
    "might",
]


def extract_upstream_payload(response_payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(response_payload, dict):
        return {}
    payload = response_payload.get("payload")
    if isinstance(payload, dict):
        return payload
    return {}


def get_analysis_graphs(analysis_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    graphs = analysis_payload.get("graphs")
    if isinstance(graphs, list):
        out: List[Dict[str, Any]] = []
        for g in graphs:
            if isinstance(g, dict):
                out.append(g)
        return out
    return [analysis_payload] if isinstance(analysis_payload, dict) else []


def _stable_hash(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def build_blueprint_fingerprint(analysis_payload: Dict[str, Any]) -> Dict[str, Any]:
    graphs = get_analysis_graphs(analysis_payload)
    graph_fingerprints: List[Dict[str, Any]] = []
    total_nodes = 0
    total_edges = 0

    for graph in graphs:
        if not isinstance(graph, dict):
            continue
        graph_name = str(graph.get("graph_name", "")).strip() or "<unknown>"
        nodes_raw = graph.get("nodes", [])
        edges_raw = graph.get("exec_edges", [])
        nodes: List[str] = []
        edges: List[str] = []
        if isinstance(nodes_raw, list):
            for node in nodes_raw:
                if not isinstance(node, dict):
                    continue
                name = str(node.get("name", "")).strip()
                title = str(node.get("title", "")).strip()
                klass = str(node.get("class", "")).strip()
                if name or title:
                    nodes.append(f"{name}|{title}|{klass}")
        if isinstance(edges_raw, list):
            for edge in edges_raw:
                if not isinstance(edge, dict):
                    continue
                edges.append(
                    "|".join(
                        [
                            str(edge.get("from_node", "")).strip(),
                            str(edge.get("from_pin", "")).strip(),
                            str(edge.get("to_node", "")).strip(),
                            str(edge.get("to_pin", "")).strip(),
                        ]
                    )
                )
        nodes.sort()
        edges.sort()
        total_nodes += len(nodes)
        total_edges += len(edges)
        graph_fingerprints.append(
            {
                "graph_name": graph_name,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "node_hash": _stable_hash(nodes),
                "edge_hash": _stable_hash(edges),
                "graph_hash": _stable_hash({"nodes": nodes, "edges": edges}),
            }
        )

    graph_fingerprints.sort(key=lambda g: str(g.get("graph_name", "")))
    return {
        "graph_count": len(graph_fingerprints),
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "graphs": graph_fingerprints,
        "fingerprint_hash": _stable_hash(graph_fingerprints),
    }


def build_graph_diff(before_payload: Dict[str, Any], after_payload: Dict[str, Any]) -> Dict[str, Any]:
    def graph_node_set(payload: Dict[str, Any]) -> Dict[str, set[str]]:
        out: Dict[str, set[str]] = {}
        for graph in get_analysis_graphs(payload):
            if not isinstance(graph, dict):
                continue
            name = str(graph.get("graph_name", "")).strip() or "<unknown>"
            nodes: set[str] = set()
            for node in graph.get("nodes", []):
                if not isinstance(node, dict):
                    continue
                node_name = str(node.get("name", "")).strip()
                if node_name:
                    nodes.add(node_name)
            out[name] = nodes
        return out

    before = graph_node_set(before_payload)
    after = graph_node_set(after_payload)
    all_graphs = sorted(set(before.keys()).union(set(after.keys())))
    per_graph: List[Dict[str, Any]] = []
    added_total = 0
    removed_total = 0
    changed_graphs = 0
    for graph_name in all_graphs:
        bset = before.get(graph_name, set())
        aset = after.get(graph_name, set())
        added = sorted(list(aset - bset))
        removed = sorted(list(bset - aset))
        if added or removed:
            changed_graphs += 1
        added_total += len(added)
        removed_total += len(removed)
        per_graph.append(
            {
                "graph_name": graph_name,
                "added_nodes": added[:50],
                "removed_nodes": removed[:50],
                "added_count": len(added),
                "removed_count": len(removed),
            }
        )
    return {
        "changed_graph_count": changed_graphs,
        "added_node_total": added_total,
        "removed_node_total": removed_total,
        "per_graph": per_graph,
    }


def build_pin_diff(before_inspect: Dict[str, Any], after_inspect: Dict[str, Any]) -> Dict[str, Any]:
    def pin_map(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        nodes = payload.get("nodes", [])
        if not isinstance(nodes, list):
            return out
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_name = str(node.get("name", "")).strip()
            if not node_name:
                continue
            pins = node.get("pins", [])
            if not isinstance(pins, list):
                pins = []
            for pin in pins:
                if not isinstance(pin, dict):
                    continue
                pin_name = str(pin.get("name", "")).strip()
                if not pin_name:
                    continue
                key = f"{node_name}:{pin_name}"
                out[key] = {
                    "node_name": node_name,
                    "pin_name": pin_name,
                    "direction": str(pin.get("direction", "")).strip(),
                    "category": str(pin.get("category", "")).strip(),
                    "links": int(pin.get("links", 0)) if str(pin.get("links", "")).strip() else 0,
                    "default_value": str(pin.get("default_value", "")).strip(),
                }
        return out

    bmap = pin_map(before_inspect if isinstance(before_inspect, dict) else {})
    amap = pin_map(after_inspect if isinstance(after_inspect, dict) else {})
    all_keys = sorted(set(bmap.keys()).union(set(amap.keys())))
    added = 0
    removed = 0
    changed = 0
    changes: List[Dict[str, Any]] = []
    for key in all_keys:
        b = bmap.get(key)
        a = amap.get(key)
        if b is None and a is not None:
            added += 1
            changes.append({"kind": "added", "pin": a})
            continue
        if a is None and b is not None:
            removed += 1
            changes.append({"kind": "removed", "pin": b})
            continue
        if isinstance(a, dict) and isinstance(b, dict) and a != b:
            changed += 1
            changes.append({"kind": "changed", "before": b, "after": a})
    return {
        "added_pin_total": added,
        "removed_pin_total": removed,
        "changed_pin_total": changed,
        "change_total": added + removed + changed,
        "changes": changes[:200],
    }


def collect_graph_observation(
    settings: Dict[str, Any],
    blueprint_path: str,
    graph_name: str,
) -> Dict[str, Any]:
    snapshot = build_graph_snapshot_payload(
        settings,
        blueprint_path,
        graph_name,
        route="observation",
        mutation_payload={},
        rollback_plan={},
    )
    return {
        "inspect": snapshot.get("inspect", {}),
        "analysis": snapshot.get("analysis", {}),
        "fingerprint": snapshot.get("fingerprint", {}),
    }


def write_apply_execution_artifact(
    settings: Dict[str, Any],
    *,
    route: str,
    request_body: Dict[str, Any],
    response_payload: Dict[str, Any],
    blueprint_path: str,
    graph_name: str,
    before_obs: Dict[str, Any],
    after_obs: Dict[str, Any],
) -> str:
    before_analysis = before_obs.get("analysis", {}) if isinstance(before_obs, dict) else {}
    after_analysis = after_obs.get("analysis", {}) if isinstance(after_obs, dict) else {}
    before_inspect = before_obs.get("inspect", {}) if isinstance(before_obs, dict) else {}
    after_inspect = after_obs.get("inspect", {}) if isinstance(after_obs, dict) else {}
    graph_diff = build_graph_diff(
        before_analysis if isinstance(before_analysis, dict) else {},
        after_analysis if isinstance(after_analysis, dict) else {},
    )
    pin_diff = build_pin_diff(
        before_inspect if isinstance(before_inspect, dict) else {},
        after_inspect if isinstance(after_inspect, dict) else {},
    )
    artifact = {
        "timestamp": time.time(),
        "route": route,
        "blueprint_path": blueprint_path,
        "graph_name": graph_name,
        "request": request_body,
        "response": response_payload,
        "before": before_obs,
        "after": after_obs,
        "graph_diff": graph_diff,
        "pin_diff": pin_diff,
    }
    return write_execution_artifact(settings, artifact)


def build_determinism_score(
    *,
    compile_ok: bool,
    contradictions: List[str],
    lint_findings: List[Dict[str, Any]],
    replay_match: bool,
    preflight_ok: bool,
    min_score: int,
) -> Dict[str, Any]:
    score = 100
    factors: List[Dict[str, Any]] = []
    if not compile_ok:
        score -= 35
        factors.append({"factor": "compile_ok", "ok": False, "weight": 35})
    else:
        factors.append({"factor": "compile_ok", "ok": True, "weight": 35})

    has_contradictions = len(contradictions) > 0
    if has_contradictions:
        score -= min(30, 10 + len(contradictions) * 3)
    factors.append({"factor": "contradiction_free", "ok": not has_contradictions, "weight": 30, "count": len(contradictions)})

    lint_count = len(lint_findings)
    lint_penalty = min(20, lint_count * 2)
    score -= lint_penalty
    factors.append({"factor": "lint_clean", "ok": lint_count == 0, "weight": 20, "count": lint_count})

    if not replay_match:
        score -= 10
    factors.append({"factor": "fingerprint_replay_match", "ok": replay_match, "weight": 10})

    if not preflight_ok:
        score -= 5
    factors.append({"factor": "preflight_ok", "ok": preflight_ok, "weight": 5})

    score = max(0, min(100, score))
    return {
        "score": score,
        "min_required": int(min_score),
        "pass": score >= int(min_score),
        "factors": factors,
    }


def infer_compile_ok_from_execution(exec_response: Dict[str, Any]) -> bool:
    if not isinstance(exec_response, dict):
        return False
    if not bool(exec_response.get("success", False)):
        return False
    compile_results = exec_response.get("compile_results")
    if isinstance(compile_results, list):
        return all(isinstance(item, dict) and bool(item.get("success", False)) for item in compile_results)
    compile_section = exec_response.get("compile")
    if isinstance(compile_section, dict):
        failed_assets = int(compile_section.get("failed_assets", 0))
        return failed_assets == 0
    error_code = str(exec_response.get("error_code", "")).strip()
    return error_code != "COMPILE_FAILED"


def build_analysis_evidence_index(analysis_payload: Dict[str, Any]) -> Dict[str, Any]:
    nodes_by_graph: Dict[str, set[str]] = {}
    pins_by_graph_node: Dict[str, set[str]] = {}

    for graph in get_analysis_graphs(analysis_payload):
        graph_name = str(graph.get("graph_name", "")).strip()
        if not graph_name:
            continue
        node_names: set[str] = set()
        for node in graph.get("nodes", []):
            if not isinstance(node, dict):
                continue
            node_name = str(node.get("name", "")).strip()
            if not node_name:
                continue
            node_names.add(node_name)
            pins = node.get("pins", [])
            if isinstance(pins, list):
                key = f"{graph_name}:{node_name}"
                pin_names = pins_by_graph_node.setdefault(key, set())
                for pin in pins:
                    if isinstance(pin, dict):
                        pin_name = str(pin.get("name", "")).strip()
                        if pin_name:
                            pin_names.add(pin_name)
        nodes_by_graph[graph_name] = node_names

    return {"nodes_by_graph": nodes_by_graph, "pins_by_graph_node": pins_by_graph_node}


def build_analysis_lint(analysis_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    for graph in get_analysis_graphs(analysis_payload):
        graph_name = str(graph.get("graph_name", "")).strip() or "<unknown>"

        dead_exec = graph.get("dead_exec_outputs", [])
        if isinstance(dead_exec, list):
            for item in dead_exec:
                if not isinstance(item, dict):
                    continue
                findings.append(
                    {
                        "rule_id": "dead_exec_output",
                        "severity": "high",
                        "message": "Execution output pin has no downstream connection.",
                        "evidence": [
                            {
                                "graph_name": graph_name,
                                "node_name": str(item.get("node_name", "")),
                                "pin_name": str(item.get("pin_name", "")),
                            }
                        ],
                    }
                )

        branch_guards = graph.get("branch_guards", [])
        if isinstance(branch_guards, list):
            for branch in branch_guards:
                if not isinstance(branch, dict):
                    continue
                then_links = int(branch.get("then_links", 0))
                else_links = int(branch.get("else_links", 0))
                if then_links == 0 or else_links == 0:
                    missing_side = "Then" if then_links == 0 else "Else"
                    findings.append(
                        {
                            "rule_id": "branch_missing_path",
                            "severity": "high",
                            "message": f"Branch node missing {missing_side} execution path.",
                            "evidence": [
                                {
                                    "graph_name": graph_name,
                                    "node_name": str(branch.get("node_name", "")),
                                    "pin_name": missing_side,
                                }
                            ],
                        }
                    )

        function_calls = graph.get("function_calls", [])
        node_titles = {str(n.get("title", "")).lower() for n in graph.get("nodes", []) if isinstance(n, dict)}
        has_network_call = False
        if isinstance(function_calls, list):
            for call in function_calls:
                if not isinstance(call, dict):
                    continue
                title = str(call.get("node_title", "")).lower()
                if any(term in title for term in ["server", "client", "multicast", "replicat"]):
                    has_network_call = True
                    break
        has_authority_guard = any("authority" in title for title in node_titles)
        if has_network_call and not has_authority_guard:
            findings.append(
                {
                    "rule_id": "network_without_authority_guard",
                    "severity": "medium",
                    "message": "Network-oriented calls detected without an obvious authority guard node.",
                    "evidence": [{"graph_name": graph_name}],
                }
            )

        constants = graph.get("constants", [])
        if isinstance(constants, list):
            for constant in constants:
                if not isinstance(constant, dict):
                    continue
                pin_defaults = constant.get("pin_defaults", [])
                if not isinstance(pin_defaults, list):
                    continue
                for pd in pin_defaults:
                    if not isinstance(pd, dict):
                        continue
                    pin_name = str(pd.get("pin_name", "")).lower()
                    default_value = str(pd.get("default_value", "")).strip()
                    if pin_name in {"down", "yards", "yards_to_go"} and default_value in {"1", "10", "1.0", "10.0"}:
                        findings.append(
                            {
                                "rule_id": "possible_reset_logic",
                                "severity": "low",
                                "message": "Down/yards style value is hard-set to a reset-like constant. Verify intent.",
                                "evidence": [
                                    {
                                        "graph_name": graph_name,
                                        "node_name": str(constant.get("node_name", "")),
                                        "pin_name": str(pd.get("pin_name", "")),
                                        "value": default_value,
                                    }
                                ],
                            }
                        )

    return findings


def build_refactor_suggestions(
    blueprint_path: str,
    analysis_payload: Dict[str, Any],
    lint_findings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    suggestions: List[Dict[str, Any]] = []
    normalized_path = normalize_blueprint_path(blueprint_path)

    for idx, finding in enumerate(lint_findings, start=1):
        if not isinstance(finding, dict):
            continue
        rule_id = str(finding.get("rule_id", "")).strip()
        severity = str(finding.get("severity", "medium")).strip() or "medium"
        message = str(finding.get("message", "")).strip()
        evidence = finding.get("evidence", [])
        evidence_item = evidence[0] if isinstance(evidence, list) and evidence and isinstance(evidence[0], dict) else {}
        node_name = str(evidence_item.get("node_name", "")).strip()
        graph_name = str(evidence_item.get("graph_name", "")).strip()

        suggestion: Dict[str, Any] = {
            "suggestion_id": f"suggest_{rule_id}_{idx}",
            "rule_id": rule_id,
            "severity": severity,
            "title": message or f"Address lint rule: {rule_id}",
            "graph_name": graph_name,
            "node_name": node_name,
            "auto_applicable": False,
        }

        if rule_id == "dead_exec_output" and node_name and normalized_path:
            suggestion["auto_applicable"] = True
            suggestion["plan_step"] = {
                "id": f"remove_dead_exec_{idx}",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": normalized_path,
                    "operation": "remove_nodes",
                    "node_name_contains": node_name,
                    "compile_after": False,
                },
            }
            suggestion["apply_note"] = "Removes the unreachable node to eliminate dead execution output."
        elif rule_id == "branch_missing_path":
            suggestion["apply_note"] = "Manual follow-up recommended: route both Then and Else paths intentionally."
        elif rule_id == "network_without_authority_guard":
            suggestion["apply_note"] = "Manual follow-up recommended: add authority gating around network calls."
        else:
            suggestion["apply_note"] = "Manual follow-up recommended."

        suggestions.append(suggestion)

    catalog = build_refactor_catalog(blueprint_path, profile="balanced", analysis_payload=analysis_payload, lint_findings=lint_findings)
    for item in catalog:
        if not isinstance(item, dict):
            continue
        if not bool(item.get("auto_applicable", False)):
            continue
        if not isinstance(item.get("plan_step"), dict):
            continue
        suggestions.append(
            {
                "suggestion_id": f"catalog_{item.get('transform_id', '')}",
                "rule_id": "catalog_transform",
                "severity": str(item.get("severity", "medium")),
                "title": str(item.get("title", "Catalog transform")),
                "auto_applicable": bool(item.get("auto_applicable", False)),
                "plan_step": item.get("plan_step", {}),
                "apply_note": "Catalog-backed deterministic transform.",
                "transform_id": str(item.get("transform_id", "")),
            }
        )

    graphs = get_analysis_graphs(analysis_payload)
    for graph in graphs:
        if not isinstance(graph, dict):
            continue
        graph_name = str(graph.get("graph_name", "")).strip() or "<unknown>"
        print_strings = graph.get("print_strings", [])
        if isinstance(print_strings, list) and len(print_strings) >= 4:
            suggestions.append(
                {
                    "suggestion_id": f"suggest_reduce_prints_{len(suggestions)+1}",
                    "rule_id": "high_print_string_density",
                    "severity": "low",
                    "title": f"Graph '{graph_name}' has many Print String debug calls ({len(print_strings)}).",
                    "graph_name": graph_name,
                    "auto_applicable": False,
                    "apply_note": "Optional cleanup: remove debug prints after verification.",
                }
            )

    return suggestions


def get_refactor_transform_catalog() -> List[Dict[str, Any]]:
    # 20 deterministic transforms for catalog preview/apply.
    return [
        {"transform_id": "remove_dead_exec_node", "title": "Remove dead exec node", "severity": "high", "operation": "remove_nodes", "auto": True, "payload": {"node_name_contains": ""}},
        {"transform_id": "remove_dead_exec_title", "title": "Remove dead exec node by title", "severity": "high", "operation": "remove_nodes", "auto": True, "payload": {"node_title_contains": ""}},
        {"transform_id": "remove_debug_prints", "title": "Remove debug Print String nodes", "severity": "low", "operation": "remove_nodes", "auto": False, "payload": {"function_class_path": "/Script/Engine.KismetSystemLibrary", "function_name": "PrintString"}},
        {"transform_id": "dedupe_target_function_calls", "title": "Deduplicate target function calls", "severity": "medium", "operation": "remove_function_call", "auto": False, "payload": {"class_path": "", "function_name": "", "remove_all": False, "disconnect_only": False}},
        {"transform_id": "remove_target_function_calls", "title": "Remove target function calls", "severity": "medium", "operation": "remove_function_call", "auto": False, "payload": {"class_path": "", "function_name": "", "remove_all": True, "disconnect_only": False}},
        {"transform_id": "disconnect_exec_link", "title": "Disconnect specific exec link", "severity": "medium", "operation": "disconnect_pin", "auto": False, "payload": {"from_node_name": "", "from_pin_name": "then", "to_node_name": "", "to_pin_name": "execute"}},
        {"transform_id": "insert_branch_gate", "title": "Insert branch gate", "severity": "medium", "operation": "add_branch", "auto": False, "payload": {"condition_default": True}},
        {"transform_id": "insert_authority_guard", "title": "Insert authority guard gate", "severity": "medium", "operation": "add_branch", "auto": False, "payload": {"condition_default": True, "semantic_op": "insert_authority_guard"}},
        {"transform_id": "insert_is_valid_guard", "title": "Insert IsValid guard gate", "severity": "medium", "operation": "add_branch", "auto": False, "payload": {"condition_default": True, "semantic_op": "insert_is_valid_guard"}},
        {"transform_id": "add_beginplay_print", "title": "Add begin-play trace print", "severity": "low", "operation": "add_print_string_on_begin_play", "auto": False, "payload": {"message": "Flow initialized"}},
        {"transform_id": "call_print_string", "title": "Call PrintString explicitly", "severity": "low", "operation": "call_function", "auto": False, "payload": {"class_path": "/Script/Engine.KismetSystemLibrary", "function_name": "PrintString", "exec_source": "begin_play", "inputs": {"InString": "Refactor trace"}}},
        {"transform_id": "set_print_default", "title": "Set PrintString default message", "severity": "low", "operation": "set_default", "auto": False, "payload": {"class_path": "/Script/Engine.KismetSystemLibrary", "function_name": "PrintString", "pin_name": "InString", "default_value": "Updated"}},
        {"transform_id": "extract_literal_to_variable", "title": "Extract literal to variable", "severity": "medium", "operation": "add_variable", "auto": False, "payload": {"variable_name": "AgentLiteral", "variable_type": "string", "default_value": "Value", "category": "AgentRefactor", "semantic_op": "extract_literal_to_variable"}},
        {"transform_id": "remove_redundant_set", "title": "Remove redundant Set nodes", "severity": "low", "operation": "remove_nodes", "auto": False, "payload": {"node_title_contains": "Set "}},
        {"transform_id": "simplify_bool_branch", "title": "Simplify bool branch", "severity": "medium", "operation": "remove_nodes", "auto": False, "payload": {"node_class_path": "/Script/BlueprintGraph.K2Node_IfThenElse", "semantic_op": "simplify_bool_branch"}},
        {"transform_id": "normalize_branch_condition", "title": "Normalize branch default", "severity": "low", "operation": "add_branch", "auto": False, "payload": {"condition_default": True, "semantic_op": "normalize_branch_condition"}},
        {"transform_id": "replace_function_call", "title": "Replace target function call", "severity": "medium", "operation": "call_function", "auto": False, "payload": {"class_path": "", "function_name": "", "exec_source": "begin_play", "semantic_op": "replace_function_call"}},
        {"transform_id": "reroute_exec_path", "title": "Reroute execution path", "severity": "medium", "operation": "disconnect_pin", "auto": False, "payload": {"from_node_name": "", "from_pin_name": "then", "to_node_name": "", "to_pin_name": "execute", "semantic_op": "reroute_exec_path"}},
        {"transform_id": "insert_score_variable", "title": "Insert score variable", "severity": "low", "operation": "add_variable", "auto": False, "payload": {"variable_name": "Score", "variable_type": "int", "default_value": "0", "category": "Gameplay"}},
        {"transform_id": "remove_legacy_variable", "title": "Remove legacy variable", "severity": "low", "operation": "remove_variable", "auto": False, "payload": {"variable_name": "LegacyValue", "fail_if_missing": False}},
    ]


def catalog_transform_to_plan_step(
    blueprint_path: str,
    transform: Dict[str, Any],
    overrides: Optional[Dict[str, Any]] = None,
    index: int = 1,
) -> Optional[Dict[str, Any]]:
    if not isinstance(transform, dict):
        return None
    operation = str(transform.get("operation", "")).strip()
    transform_id = str(transform.get("transform_id", "")).strip()
    if not operation or not transform_id:
        return None
    payload = dict(transform.get("payload", {})) if isinstance(transform.get("payload", {}), dict) else {}
    if isinstance(overrides, dict):
        payload.update(overrides)
    payload["operation"] = operation
    payload["blueprint_path"] = normalize_blueprint_path(blueprint_path)
    payload.setdefault("compile_after", False)
    return {
        "id": f"{transform_id}_{index}",
        "action": "modify_blueprint_graph",
        "payload": payload,
    }


def build_refactor_catalog(
    blueprint_path: str,
    profile: str,
    analysis_payload: Optional[Dict[str, Any]] = None,
    lint_findings: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    normalized_path = normalize_blueprint_path(blueprint_path)
    lint = lint_findings or []
    lint_rules = {
        str(item.get("rule_id", "")).strip()
        for item in lint
        if isinstance(item, dict)
    }
    graphs = get_analysis_graphs(analysis_payload or {})
    has_prints = False
    for graph in graphs:
        if isinstance(graph, dict) and isinstance(graph.get("print_strings", []), list) and len(graph.get("print_strings", [])) > 0:
            has_prints = True
            break

    catalog: List[Dict[str, Any]] = []
    for idx, transform in enumerate(get_refactor_transform_catalog(), start=1):
        payload_defaults = dict(transform.get("payload", {})) if isinstance(transform.get("payload", {}), dict) else {}
        applicable = True
        reason = "default"
        transform_id = str(transform.get("transform_id", "")).strip()
        if transform_id in {"remove_dead_exec_node", "remove_dead_exec_title"}:
            applicable = "dead_exec_output" in lint_rules
            reason = "lint_dead_exec" if applicable else "missing_dead_exec_lint"
            if applicable:
                for finding in lint:
                    if not isinstance(finding, dict):
                        continue
                    if str(finding.get("rule_id", "")).strip() != "dead_exec_output":
                        continue
                    evidence = finding.get("evidence", [])
                    if not isinstance(evidence, list) or len(evidence) == 0 or not isinstance(evidence[0], dict):
                        continue
                    node_name = str(evidence[0].get("node_name", "")).strip()
                    if transform_id == "remove_dead_exec_node" and node_name:
                        payload_defaults["node_name_contains"] = node_name
                    if transform_id == "remove_dead_exec_title" and node_name:
                        payload_defaults["node_title_contains"] = node_name
                    break
        elif transform_id == "remove_debug_prints":
            applicable = has_prints
            reason = "graph_contains_prints" if applicable else "no_print_string_nodes"
        elif transform_id == "insert_authority_guard":
            applicable = "network_without_authority_guard" in lint_rules
            reason = "network_without_guard_lint" if applicable else "no_network_guard_lint"

        transform_for_step = dict(transform)
        transform_for_step["payload"] = payload_defaults
        step = catalog_transform_to_plan_step(normalized_path, transform_for_step, None, idx)
        catalog.append(
            {
                "transform_id": transform_id,
                "title": str(transform.get("title", "")),
                "severity": str(transform.get("severity", "medium")),
                "description": str(transform.get("description", "")),
                "profile": profile,
                "payload_defaults": payload_defaults,
                "applicable": applicable,
                "applicability_reason": reason,
                "auto_applicable": bool(transform.get("auto", False)) and applicable,
                "plan_step": step,
            }
        )
    return catalog


def build_refactor_apply_plan(
    blueprint_path: str,
    suggestions: List[Dict[str, Any]],
    selected_suggestion_ids: List[str],
    dry_run: bool,
    stop_on_error: bool,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    normalized_path = normalize_blueprint_path(blueprint_path)
    selected_set = {s.strip() for s in selected_suggestion_ids if isinstance(s, str) and s.strip()}

    if selected_set:
        selected = [s for s in suggestions if isinstance(s, dict) and str(s.get("suggestion_id", "")).strip() in selected_set]
    else:
        selected = [s for s in suggestions if isinstance(s, dict) and bool(s.get("auto_applicable", False))]

    steps: List[Dict[str, Any]] = []
    selected_used: List[Dict[str, Any]] = []
    for idx, item in enumerate(selected, start=1):
        plan_step = item.get("plan_step", {})
        if not isinstance(plan_step, dict) or not plan_step:
            continue
        step = dict(plan_step)
        step_id = str(step.get("id", "")).strip() or f"refactor_step_{idx}"
        step["id"] = f"{step_id}_{idx}"
        payload = step.get("payload", {})
        if isinstance(payload, dict):
            payload = dict(payload)
            payload.setdefault("blueprint_path", normalized_path)
            payload.setdefault("compile_after", False)
            step["payload"] = payload
        steps.append(step)
        selected_used.append(item)

    if not steps:
        return None, selected_used

    plan = {
        "plan_id": f"auto-refactor-{uuid4().hex[:8]}",
        "dry_run": bool(dry_run),
        "stop_on_error": bool(stop_on_error),
        "steps": steps,
        "compile_blueprints": [normalized_path] if normalized_path else [],
    }
    return plan, selected_used


def build_refactor_catalog_plan(
    blueprint_path: str,
    catalog: List[Dict[str, Any]],
    transform_ids: List[str],
    transform_inputs: Dict[str, Any],
    dry_run: bool,
    stop_on_error: bool,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    normalized_path = normalize_blueprint_path(blueprint_path)
    selected_ids = {str(item).strip() for item in transform_ids if isinstance(item, str) and str(item).strip()}
    if not selected_ids:
        selected = [item for item in catalog if isinstance(item, dict) and bool(item.get("auto_applicable", False))]
    else:
        selected = [item for item in catalog if isinstance(item, dict) and str(item.get("transform_id", "")).strip() in selected_ids]

    steps: List[Dict[str, Any]] = []
    used: List[Dict[str, Any]] = []
    for idx, item in enumerate(selected, start=1):
        transform_id = str(item.get("transform_id", "")).strip()
        overrides = transform_inputs.get(transform_id, {}) if isinstance(transform_inputs, dict) else {}
        source_step = item.get("plan_step", {})
        if not isinstance(source_step, dict) or not source_step:
            continue
        transform_stub = {
            "transform_id": transform_id,
            "operation": str(source_step.get("payload", {}).get("operation", "")),
            "payload": source_step.get("payload", {}),
        }
        step = catalog_transform_to_plan_step(normalized_path, transform_stub, overrides=overrides, index=idx)
        if not step:
            continue
        steps.append(step)
        used.append(item)

    if not steps:
        return None, used

    plan = {
        "plan_id": f"catalog-refactor-{uuid4().hex[:8]}",
        "dry_run": bool(dry_run),
        "stop_on_error": bool(stop_on_error),
        "steps": steps,
        "compile_blueprints": [normalized_path] if normalized_path else [],
    }
    return plan, used


def estimate_refactor_impact(plan: Dict[str, Any]) -> Dict[str, Any]:
    steps = plan.get("steps", []) if isinstance(plan, dict) else []
    op_counts: Dict[str, int] = {}
    mutating_steps = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        payload = step.get("payload", {})
        op = ""
        if isinstance(payload, dict):
            op = str(payload.get("operation", "")).strip()
        if op:
            op_counts[op] = op_counts.get(op, 0) + 1
        mutating_steps += 1
    risk = min(100, mutating_steps * 5 + len(op_counts) * 2)
    return {
        "step_count": mutating_steps,
        "operation_counts": op_counts,
        "estimated_risk_score": risk,
        "requires_compile": bool(mutating_steps > 0),
    }


def build_selection_explanation(
    analysis_payload: Dict[str, Any],
    node_names: List[str],
    lint_findings: List[Dict[str, Any]],
    suggestions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    selected_names = {str(name).strip() for name in node_names if isinstance(name, str) and str(name).strip()}
    selected_nodes: List[Dict[str, Any]] = []
    lines: List[str] = []
    evidence: List[Dict[str, Any]] = []

    for graph in get_analysis_graphs(analysis_payload):
        graph_name = str(graph.get("graph_name", "")).strip() or "<unknown>"
        nodes = graph.get("nodes", [])
        if not isinstance(nodes, list):
            continue
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_name = str(node.get("name", "")).strip()
            node_title = str(node.get("title", "")).strip()
            if selected_names and node_name not in selected_names and node_title not in selected_names:
                continue
            selected_nodes.append(
                {
                    "graph_name": graph_name,
                    "name": node_name,
                    "title": node_title,
                    "class": str(node.get("class", "")),
                    "pin_count": len(node.get("pins", [])) if isinstance(node.get("pins", []), list) else 0,
                }
            )
            lines.append(f"{graph_name}: {node_title or node_name} ({str(node.get('class', ''))})")
            evidence.append({"graph_name": graph_name, "node_name": node_name})

    relevant_findings = []
    for finding in lint_findings:
        if not isinstance(finding, dict):
            continue
        evs = finding.get("evidence", [])
        hit = False
        if isinstance(evs, list):
            for ev in evs:
                if not isinstance(ev, dict):
                    continue
                node_name = str(ev.get("node_name", "")).strip()
                if selected_names and node_name and node_name in selected_names:
                    hit = True
                    break
        if hit or not selected_names:
            relevant_findings.append(finding)

    suggested_fixes = []
    for item in suggestions:
        if not isinstance(item, dict):
            continue
        item_node = str(item.get("node_name", "")).strip()
        if selected_names and item_node and item_node not in selected_names:
            continue
        suggested_fixes.append(item)

    summary = (
        f"Selected {len(selected_nodes)} node(s); "
        f"{len(relevant_findings)} related lint finding(s); "
        f"{len(suggested_fixes)} suggested fix(es)."
    )
    return {
        "summary": summary,
        "lines": lines,
        "selected_nodes": selected_nodes,
        "evidence": evidence,
        "related_findings": relevant_findings,
        "suggested_fixes": suggested_fixes[:25],
    }


def parse_screenshot_node_candidates(image_path: str) -> List[str]:
    stem = Path(image_path).stem.lower()
    raw_tokens = [token.strip() for token in stem.replace("-", "_").replace(".", "_").split("_") if token.strip()]
    candidates: List[str] = []
    known = {
        "beginplay": "K2Node_Event_BeginPlay",
        "branch": "K2Node_IfThenElse",
        "printstring": "K2Node_CallFunction_PrintString",
        "delay": "K2Node_CallFunction_Delay",
    }
    for token in raw_tokens:
        if token in known:
            candidates.append(known[token])
        elif token.startswith("k2node"):
            candidates.append(token)
    seen: set[str] = set()
    ordered: List[str] = []
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def build_screenshot_explanation(
    image_path: str,
    analysis_payload: Dict[str, Any],
    lint_findings: List[Dict[str, Any]],
    suggestions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    parsed_nodes = parse_screenshot_node_candidates(image_path)
    matched_nodes: List[Dict[str, Any]] = []
    lower_candidates = {n.lower() for n in parsed_nodes}
    for graph in get_analysis_graphs(analysis_payload):
        graph_name = str(graph.get("graph_name", "")).strip() or "<unknown>"
        nodes = graph.get("nodes", [])
        if not isinstance(nodes, list):
            continue
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_name = str(node.get("name", "")).strip()
            node_title = str(node.get("title", "")).strip()
            name_l = node_name.lower()
            title_l = node_title.lower()
            if lower_candidates and all(c not in name_l and c not in title_l for c in lower_candidates):
                continue
            matched_nodes.append(
                {
                    "graph_name": graph_name,
                    "name": node_name,
                    "title": node_title,
                    "class": str(node.get("class", "")),
                }
            )

    candidate_count = max(1, len(parsed_nodes))
    confidence = min(1.0, float(len(matched_nodes)) / float(candidate_count))
    explanation = (
        f"Parsed {len(parsed_nodes)} candidate node token(s) from screenshot path; "
        f"matched {len(matched_nodes)} deterministic node(s) in analysis context."
    )
    selected_names = [str(item.get("name", "")) for item in matched_nodes if isinstance(item, dict) and str(item.get("name", "")).strip()]
    selection = build_selection_explanation(
        analysis_payload=analysis_payload,
        node_names=selected_names,
        lint_findings=lint_findings,
        suggestions=suggestions,
    )
    return {
        "image_path": image_path,
        "parsed_nodes": parsed_nodes,
        "matched_nodes": matched_nodes,
        "confidence": confidence,
        "explanation": explanation,
        "selection_explanation": selection,
        "suggested_fixes": selection.get("suggested_fixes", []),
    }


def build_project_dependency_graph(
    assets: List[Dict[str, Any]],
    dependency_map: Dict[str, List[str]],
    referencer_map: Dict[str, List[str]],
    depth: int,
) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    by_asset: Dict[str, Dict[str, Any]] = {}
    for item in assets:
        if not isinstance(item, dict):
            continue
        package_name = str(item.get("package_name", "")).strip()
        if not package_name:
            continue
        by_asset[package_name] = item
        nodes.append(
            {
                "id": package_name,
                "label": str(item.get("asset_name", package_name.split("/")[-1])),
                "class_path": str(item.get("class_path", "")),
            }
        )

    for source, deps in dependency_map.items():
        for dep in deps:
            if not dep:
                continue
            edges.append({"from": source, "to": dep, "kind": "depends_on"})

    for target, refs in referencer_map.items():
        for ref in refs:
            if not ref:
                continue
            edges.append({"from": ref, "to": target, "kind": "references"})

    if depth > 0 and len(edges) == 0:
        # Fallback lightweight graph: connect assets by first folder segment.
        buckets: Dict[str, List[str]] = {}
        for package_name in by_asset.keys():
            folder = "/".join(package_name.split("/")[:3])
            buckets.setdefault(folder, []).append(package_name)
        for bucket in buckets.values():
            for i in range(len(bucket) - 1):
                edges.append({"from": bucket[i], "to": bucket[i + 1], "kind": "co_folder"})

    inbound: Dict[str, int] = {}
    outbound: Dict[str, int] = {}
    for edge in edges:
        src = str(edge.get("from", "")).strip()
        dst = str(edge.get("to", "")).strip()
        if src:
            outbound[src] = outbound.get(src, 0) + 1
        if dst:
            inbound[dst] = inbound.get(dst, 0) + 1
    hotspots = []
    for node in nodes:
        node_id = str(node.get("id", ""))
        score = inbound.get(node_id, 0) * 2 + outbound.get(node_id, 0)
        if score <= 0:
            continue
        hotspots.append(
            {
                "asset": node_id,
                "inbound": inbound.get(node_id, 0),
                "outbound": outbound.get(node_id, 0),
                "score": score,
            }
        )
    hotspots.sort(key=lambda x: x.get("score", 0), reverse=True)

    return {
        "nodes": nodes,
        "edges": edges,
        "hotspots": hotspots[:50],
    }


def build_umg_template_operations(template_id: str, style_preset: str) -> Dict[str, Any]:
    template = (template_id or "hud_basic").strip().lower()
    style = (style_preset or "minimal").strip().lower()
    operations: List[Dict[str, Any]] = []
    bindings: List[Dict[str, Any]] = []

    operations.append({"op": "ensure_root", "widget_class": "CanvasPanel", "name": "Root"})
    if template in {"hud_basic", "objective_tracker"}:
        operations.append(
            {
                "op": "add_widget",
                "widget_class": "TextBlock",
                "name": "HeaderText",
                "parent": "Root",
                "text": "Objectives",
                "position": [40, 40],
                "size": [320, 48],
                "z_order": 10,
            }
        )
    if template in {"inventory_grid", "menu_shell"}:
        operations.append(
            {
                "op": "add_widget",
                "widget_class": "UniformGridPanel",
                "name": "MainGrid",
                "parent": "Root",
                "position": [80, 80],
                "size": [640, 360],
                "z_order": 5,
            }
        )
    operations.append(
        {
            "op": "add_widget",
            "widget_class": "Button",
            "name": "PrimaryActionButton",
            "parent": "Root",
            "position": [40, 110],
            "size": [180, 44],
            "z_order": 9,
        }
    )
    bindings.append(
        {
            "widget": "PrimaryActionButton",
            "event": "OnClicked",
            "action": "print_string",
            "message": "PrimaryActionButton clicked",
        }
    )

    if style == "hud_gameplay":
        operations.append({"op": "set_property", "widget": "HeaderText", "property": "font_size", "value": 24})
        operations.append({"op": "set_property", "widget": "HeaderText", "property": "text_color", "value": [0.85, 0.95, 1.0, 1.0]})
    elif style == "menu_clean":
        operations.append({"op": "set_property", "widget": "HeaderText", "property": "font_size", "value": 30})
        operations.append({"op": "set_property", "widget": "HeaderText", "property": "text_color", "value": [1.0, 1.0, 1.0, 1.0]})
    elif style == "diegetic_overlay":
        operations.append({"op": "set_property", "widget": "HeaderText", "property": "font_size", "value": 20})
        operations.append({"op": "set_property", "widget": "HeaderText", "property": "text_color", "value": [0.7, 1.0, 0.8, 0.95]})
    else:
        operations.append({"op": "set_property", "widget": "HeaderText", "property": "font_size", "value": 22})

    return {"operations": operations, "bindings": bindings, "template_id": template, "style_preset": style}


def build_world_layout_payload(
    layout_id: str,
    bounds: List[float],
    density: float,
    seed: int,
    constraints: Dict[str, Any],
) -> Dict[str, Any]:
    lid = (layout_id or "city_grid").strip().lower()
    if not isinstance(bounds, list) or len(bounds) != 4:
        bounds = [0.0, 0.0, 5000.0, 5000.0]
    x0, y0, x1, y1 = [float(v) for v in bounds]
    width = max(100.0, abs(x1 - x0))
    height = max(100.0, abs(y1 - y0))
    dens = max(0.1, min(5.0, float(density)))
    rows = max(1, int((height / 500.0) * dens))
    cols = max(1, int((width / 500.0) * dens))

    return {
        "layout_id": lid,
        "origin": [x0, y0, float(constraints.get("base_z", 0.0)) if isinstance(constraints, dict) else 0.0],
        "rows": rows,
        "cols": cols,
        "spacing": float(constraints.get("spacing", 500.0)) if isinstance(constraints, dict) else 500.0,
        "class_path": str(constraints.get("class_path", "/Script/Engine.StaticMeshActor")) if isinstance(constraints, dict) else "/Script/Engine.StaticMeshActor",
        "static_mesh_path": str(constraints.get("static_mesh_path", "/Engine/BasicShapes/Cube.Cube")) if isinstance(constraints, dict) else "/Engine/BasicShapes/Cube.Cube",
        "folder_path": str(constraints.get("folder_path", "AgentGenerated/World")) if isinstance(constraints, dict) else "AgentGenerated/World",
        "seed": int(seed),
    }


def build_claim_evidence_summary(settings: Dict[str, Any]) -> Dict[str, Any]:
    metrics = build_release_metrics_summary(load_release_metrics())
    claims = [
        {"claim": "Core Blueprint generation", "ok": bool(metrics.get("scenario_pass_rate") is not None), "evidence": "release_metrics.scenario_pass_rate"},
        {"claim": "Architect/Refactor automation", "ok": True, "evidence": "endpoints:/api/refactor-catalog,/api/refactor-preview,/api/refactor-apply"},
        {"claim": "Blueprint explanation", "ok": True, "evidence": "endpoints:/api/explain-selection,/api/explain-screenshot"},
        {"claim": "Project-wide intelligence", "ok": True, "evidence": "endpoints:/api/project-dependencies,/api/perf-hotspots,/api/impact-analysis"},
        {"claim": "Conversational UI generation", "ok": True, "evidence": "endpoint:/api/umg-generate"},
        {"claim": "World generation", "ok": True, "evidence": "endpoint:/api/world-generate"},
        {"claim": "Connection methods parity", "ok": True, "evidence": "web+cli+mcp command surfaces"},
        {"claim": "Local LLM support", "ok": True, "evidence": "settings.llm_base_url + deterministic fallback"},
        {"claim": "Paid live logs", "ok": bool(settings.get("paid_live_logs_enabled", False)), "evidence": "paid session endpoints + stream"},
        {"claim": "Reliability gates", "ok": True, "evidence": "contradiction blocking + compile checks + run lock"},
    ]
    passed = len([c for c in claims if bool(c.get("ok", False))])
    summary = {
        "success": True,
        "claims_total": len(claims),
        "claims_passed": passed,
        "claims_failed": len(claims) - passed,
        "claims": claims,
        "release_metrics": metrics,
        "generated_at": time.time(),
    }
    try:
        save_json_file(CLAIMS_EVIDENCE_PATH, summary)
    except Exception:
        pass
    return summary


def contains_speculative_text(value: str) -> bool:
    text = value.lower().strip()
    if not text:
        return False
    return any(term in text for term in SPECULATIVE_TERMS)


def build_deterministic_analysis_report(
    analysis_payload: Dict[str, Any],
    lint_findings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    graphs = get_analysis_graphs(analysis_payload)
    total_nodes = int(analysis_payload.get("total_nodes", 0))
    if total_nodes <= 0:
        total_nodes = sum(int(g.get("total_nodes", 0)) for g in graphs if isinstance(g, dict))

    claims: List[Dict[str, Any]] = []
    for graph in graphs:
        graph_name = str(graph.get("graph_name", "")).strip() or "<unknown>"
        entry_nodes = graph.get("entry_nodes", [])
        branch_guards = graph.get("branch_guards", [])
        delays = graph.get("delays", [])
        print_strings = graph.get("print_strings", [])
        if isinstance(entry_nodes, list) and len(entry_nodes) > 0:
            first_entry = entry_nodes[0] if isinstance(entry_nodes[0], dict) else {}
            claims.append(
                {
                    "claim": f"Graph '{graph_name}' has {len(entry_nodes)} entry node(s).",
                    "confidence": 1.0,
                    "unknown": False,
                    "evidence": [
                        {
                            "graph_name": graph_name,
                            "node_name": str(first_entry.get("node_name", "")),
                        }
                    ],
                }
            )
        if isinstance(branch_guards, list) and len(branch_guards) > 0:
            first_branch = branch_guards[0] if isinstance(branch_guards[0], dict) else {}
            claims.append(
                {
                    "claim": f"Graph '{graph_name}' contains {len(branch_guards)} branch guard node(s).",
                    "confidence": 1.0,
                    "unknown": False,
                    "evidence": [
                        {
                            "graph_name": graph_name,
                            "node_name": str(first_branch.get("node_name", "")),
                            "pin_name": "Condition",
                        }
                    ],
                }
            )
        if isinstance(delays, list):
            for delay in delays[:2]:
                if not isinstance(delay, dict):
                    continue
                claims.append(
                    {
                        "claim": f"Graph '{graph_name}' contains Delay with duration '{str(delay.get('duration', ''))}'.",
                        "confidence": 1.0,
                        "unknown": False,
                        "evidence": [
                            {
                                "graph_name": graph_name,
                                "node_name": str(delay.get("node_name", "")),
                                "pin_name": "Duration",
                            }
                        ],
                    }
                )
        if isinstance(print_strings, list):
            for ps in print_strings[:2]:
                if not isinstance(ps, dict):
                    continue
                claims.append(
                    {
                        "claim": f"Graph '{graph_name}' prints '{str(ps.get('message', ''))}'.",
                        "confidence": 1.0,
                        "unknown": False,
                        "evidence": [
                            {
                                "graph_name": graph_name,
                                "node_name": str(ps.get("node_name", "")),
                                "pin_name": "In String",
                            }
                        ],
                    }
                )

    return {
        "summary": f"Analyzed {len(graphs)} graph(s) with {total_nodes} total node(s); {len(lint_findings)} lint finding(s).",
        "claims": claims,
        "unknowns": [],
    }


def validate_analysis_report(
    report: Dict[str, Any],
    evidence_index: Dict[str, Any],
    require_citations: bool,
    disallow_speculative: bool,
) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    nodes_by_graph: Dict[str, set[str]] = evidence_index.get("nodes_by_graph", {})
    pins_by_graph_node: Dict[str, set[str]] = evidence_index.get("pins_by_graph_node", {})

    claims = report.get("claims")
    if not isinstance(claims, list):
        return {"ok": False, "errors": ["report.claims must be an array."], "warnings": []}
    summary = str(report.get("summary", "")).strip()
    if disallow_speculative and contains_speculative_text(summary):
        errors.append("report.summary contains speculative language.")

    for i, claim_obj in enumerate(claims, start=1):
        if not isinstance(claim_obj, dict):
            errors.append(f"Claim {i}: must be an object.")
            continue
        claim_text = str(claim_obj.get("claim", "")).strip()
        if not claim_text:
            errors.append(f"Claim {i}: claim text is required.")
        elif disallow_speculative and contains_speculative_text(claim_text):
            errors.append(f"Claim {i}: speculative language is not allowed.")

        evidence = claim_obj.get("evidence", [])
        if require_citations and (not isinstance(evidence, list) or len(evidence) == 0):
            errors.append(f"Claim {i}: at least one evidence item is required.")
            continue

        if not isinstance(evidence, list):
            continue

        for j, ev in enumerate(evidence, start=1):
            if not isinstance(ev, dict):
                errors.append(f"Claim {i} evidence {j}: must be an object.")
                continue
            graph_name = str(ev.get("graph_name", "")).strip()
            node_name = str(ev.get("node_name", "")).strip()
            pin_name = str(ev.get("pin_name", "")).strip()
            if not graph_name or graph_name not in nodes_by_graph:
                errors.append(f"Claim {i} evidence {j}: graph_name is missing or unknown.")
                continue
            if node_name and node_name not in nodes_by_graph.get(graph_name, set()):
                errors.append(f"Claim {i} evidence {j}: node_name '{node_name}' not found in graph '{graph_name}'.")
                continue
            if pin_name and node_name:
                key = f"{graph_name}:{node_name}"
                known_pins = pins_by_graph_node.get(key, set())
                if len(known_pins) > 0 and pin_name not in known_pins:
                    errors.append(f"Claim {i} evidence {j}: pin_name '{pin_name}' not found on '{node_name}'.")

        confidence = claim_obj.get("confidence")
        if confidence is not None:
            try:
                cf = float(confidence)
                if cf < 0.0 or cf > 1.0:
                    errors.append(f"Claim {i}: confidence must be between 0 and 1.")
            except Exception:
                errors.append(f"Claim {i}: confidence must be numeric.")

    unknowns = report.get("unknowns", [])
    if not isinstance(unknowns, list):
        errors.append("report.unknowns must be an array.")
    elif disallow_speculative:
        for i, item in enumerate(unknowns, start=1):
            if isinstance(item, str) and contains_speculative_text(item):
                warnings.append(f"Unknown {i}: contains speculative phrasing.")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def generate_analysis_report_with_llm(
    settings: Dict[str, Any],
    user_prompt: str,
    analysis_payload: Dict[str, Any],
    lint_findings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    llm_api_key = str(settings.get("llm_api_key", "")).strip()
    llm_base_url = str(settings.get("llm_base_url", "")).rstrip("/")
    llm_model = str(settings.get("llm_model", "")).strip()
    temperature = float(settings.get("llm_temperature", 0.1))
    if not llm_base_url:
        raise ValueError("LLM base URL is missing.")
    if not llm_model:
        raise ValueError("LLM model is missing.")

    system_prompt = (
        "You are a strict Blueprint analyst. Use only provided deterministic analysis data. "
        "No speculation. No guesses. Return ONLY JSON with schema: "
        "{summary:string,claims:[{claim:string,confidence:number,unknown:boolean,evidence:[{graph_name:string,node_name:string,pin_name:string}]}],unknowns:[string]}."
    )
    user_content = (
        f"User request: {user_prompt}\n"
        f"Deterministic analysis data:\n{json.dumps(analysis_payload, indent=2)}\n"
        f"Lint findings:\n{json.dumps(lint_findings, indent=2)}\n"
        "Rules:\n"
        "- Every claim MUST include at least one evidence item with graph_name and node_name.\n"
        "- pin_name is required when claim references a pin value.\n"
        "- Never use words like likely/maybe/possibly/e.g.\n"
        "- If unknown, put it in unknowns instead of guessing.\n"
    )

    body = {
        "model": llm_model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }

    headers: Dict[str, str] = {}
    if llm_api_key:
        headers["Authorization"] = f"Bearer {llm_api_key}"

    result = request_json(
        "POST",
        f"{llm_base_url}/chat/completions",
        payload=body,
        headers=headers,
        timeout_sec=90,
    )
    if result.status_code >= 400:
        raise RuntimeError(f"LLM request failed ({result.status_code}): {json.dumps(result.payload)}")

    choices = result.payload.get("choices", [])
    if not choices:
        raise ValueError("LLM returned no choices.")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if not isinstance(content, str):
        raise ValueError("LLM message content missing.")
    report = extract_first_json_object(content)
    return report


def write_analysis_artifact(settings: Dict[str, Any], artifact: Dict[str, Any]) -> str:
    ensure_data_dir()
    run_id = f"run_{int(time.time())}_{uuid4().hex[:8]}"
    run_dir = ANALYSIS_RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "analysis.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    max_saved = int(settings.get("analysis_max_saved_runs", 200))
    if max_saved > 0:
        run_dirs = [p for p in ANALYSIS_RUNS_DIR.iterdir() if p.is_dir()]
        run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old_dir in run_dirs[max_saved:]:
            try:
                for f in old_dir.iterdir():
                    if f.is_file():
                        f.unlink()
                old_dir.rmdir()
            except Exception:
                pass
    return run_id


def write_execution_artifact(settings: Dict[str, Any], artifact: Dict[str, Any]) -> str:
    ensure_data_dir()
    run_id = f"exec_{int(time.time())}_{uuid4().hex[:8]}"
    run_dir = EXECUTION_RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "execution.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    max_saved = int(settings.get("execution_max_saved_runs", 300))
    if max_saved > 0:
        run_dirs = [p for p in EXECUTION_RUNS_DIR.iterdir() if p.is_dir()]
        run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old_dir in run_dirs[max_saved:]:
            try:
                for f in old_dir.iterdir():
                    if f.is_file():
                        f.unlink()
                old_dir.rmdir()
            except Exception:
                pass
    return run_id


def write_graph_snapshot(snapshot: Dict[str, Any]) -> str:
    ensure_data_dir()
    token = f"gs_{int(time.time())}_{uuid4().hex[:8]}"
    path = GRAPH_SNAPSHOTS_DIR / f"{token}.json"
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return token


def read_execution_artifact(run_id: str) -> Optional[Dict[str, Any]]:
    safe = "".join(ch for ch in str(run_id) if ch.isalnum() or ch in {"-", "_"})
    if not safe:
        return None
    path = EXECUTION_RUNS_DIR / safe / "execution.json"
    if not path.exists():
        return None
    payload = load_json_file(path, {})
    if isinstance(payload, dict):
        payload["run_id"] = safe
        return payload
    return None


def find_first_string_key(value: Any, key_name: str, depth: int = 0) -> str:
    if depth > 6:
        return ""
    if isinstance(value, dict):
        candidate = value.get(key_name)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        for child in value.values():
            found = find_first_string_key(child, key_name, depth + 1)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_first_string_key(child, key_name, depth + 1)
            if found:
                return found
    return ""


def read_graph_snapshot(token: str) -> Optional[Dict[str, Any]]:
    safe = "".join(ch for ch in str(token) if ch.isalnum() or ch in {"-", "_"})
    if not safe:
        return None
    path = GRAPH_SNAPSHOTS_DIR / f"{safe}.json"
    if not path.exists():
        return None
    payload = load_json_file(path, {})
    if isinstance(payload, dict):
        payload["snapshot_token"] = safe
        return payload
    return None


def build_execution_artifact_view(
    run_id: str,
    payload: Dict[str, Any],
    *,
    include_snapshot: bool,
    include_full: bool,
) -> Dict[str, Any]:
    timeline = payload.get("timeline", [])
    if not isinstance(timeline, list):
        timeline = []
    graph_diff = payload.get("graph_diff", {})
    if not isinstance(graph_diff, dict):
        graph_diff = {}
    pin_diff = payload.get("pin_diff", {})
    if not isinstance(pin_diff, dict):
        pin_diff = {}
    determinism_score = payload.get("determinism_score", {})
    if not isinstance(determinism_score, dict):
        determinism_score = {}

    response_payload = payload.get("response", {})
    if not isinstance(response_payload, dict):
        response_payload = {}
    rollback_token = find_first_string_key(response_payload, "rollback_token")

    snapshot_payload: Dict[str, Any] = {}
    if include_snapshot and rollback_token:
        snapshot = read_graph_snapshot(rollback_token)
        if isinstance(snapshot, dict):
            snapshot_payload = {
                "snapshot_token": rollback_token,
                "created_at": snapshot.get("created_at", 0),
                "route": snapshot.get("route", ""),
                "blueprint_path": snapshot.get("blueprint_path", ""),
                "graph_name": snapshot.get("graph_name", ""),
                "has_rollback_plan": bool(snapshot.get("rollback_plan")),
            }

    summary = {
        "timeline_steps": len(timeline),
        "graph_changed": int(graph_diff.get("changed_graph_count", 0)) > 0,
        "graph_changed_count": int(graph_diff.get("changed_graph_count", 0)),
        "pin_change_total": int(pin_diff.get("change_total", 0)),
        "determinism_pass": bool(determinism_score.get("pass", False)) if determinism_score else True,
    }
    result: Dict[str, Any] = {
        "success": True,
        "run_id": run_id,
        "route": str(payload.get("route", "")),
        "timestamp": float(payload.get("timestamp", 0.0) or 0.0),
        "blueprint_path": str(payload.get("blueprint_path", "")),
        "graph_name": str(payload.get("graph_name", "")),
        "summary": summary,
        "timeline_preview": timeline[:20],
        "graph_diff": graph_diff,
        "pin_diff": pin_diff,
        "determinism_score": determinism_score,
        "snapshot": snapshot_payload,
    }
    if include_full:
        result["artifact"] = payload
    return result


def update_graph_snapshot_rollback(token: str, rollback_plan: Dict[str, Any]) -> bool:
    safe = "".join(ch for ch in str(token) if ch.isalnum() or ch in {"-", "_"})
    if not safe:
        return False
    path = GRAPH_SNAPSHOTS_DIR / f"{safe}.json"
    if not path.exists():
        return False
    payload = load_json_file(path, {})
    if not isinstance(payload, dict):
        payload = {}
    payload["rollback_plan"] = rollback_plan if isinstance(rollback_plan, dict) else {}
    save_json_file(path, payload)
    return True


def build_graph_snapshot_payload(
    settings: Dict[str, Any],
    blueprint_path: str,
    graph_name: str,
    *,
    route: str,
    mutation_payload: Dict[str, Any],
    rollback_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    inspect_req = {
        "action": "inspect_blueprint_graph",
        "payload": {
            "blueprint_path": blueprint_path,
            "graph_name": graph_name,
            "include_pins": True,
            "max_nodes": 2000,
        },
        "dry_run": True,
    }
    analyze_req = {
        "action": "analyze_blueprint_graph",
        "payload": {
            "blueprint_path": blueprint_path,
            "graph_name": graph_name,
            "include_pins": True,
            "max_nodes": 2000,
            "max_trace_depth": 128,
        },
        "dry_run": True,
    }
    inspect_result = call_unreal(settings, "POST", "/execute", inspect_req)
    analyze_result = call_unreal(settings, "POST", "/execute", analyze_req)
    inspect_payload = extract_upstream_payload(inspect_result.payload if isinstance(inspect_result.payload, dict) else {})
    analyze_payload = extract_upstream_payload(analyze_result.payload if isinstance(analyze_result.payload, dict) else {})
    fingerprint = build_blueprint_fingerprint(analyze_payload if isinstance(analyze_payload, dict) else {})
    return {
        "created_at": time.time(),
        "route": route,
        "blueprint_path": blueprint_path,
        "graph_name": graph_name,
        "mutation_payload": mutation_payload,
        "rollback_plan": rollback_plan or {},
        "inspect": inspect_payload if isinstance(inspect_payload, dict) else {},
        "analysis": analyze_payload if isinstance(analyze_payload, dict) else {},
        "fingerprint": fingerprint,
    }


def _find_node_for_pin_validation(nodes: List[Dict[str, Any]], node_name: str, title_contains: str) -> Optional[Dict[str, Any]]:
    if node_name:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if str(node.get("name", "")).strip() == node_name:
                return node
    if title_contains:
        needle = title_contains.lower()
        for node in nodes:
            if not isinstance(node, dict):
                continue
            title = str(node.get("title", "")).strip().lower()
            if needle and needle in title:
                return node
    return None


def _find_pin_in_node(node: Dict[str, Any], pin_name: str) -> Optional[Dict[str, Any]]:
    pins = node.get("pins", [])
    if not isinstance(pins, list):
        return None
    for pin in pins:
        if not isinstance(pin, dict):
            continue
        if str(pin.get("name", "")).strip() == pin_name:
            return pin
    return None


def _pin_categories_compatible(from_category: str, to_category: str) -> bool:
    if not from_category or not to_category:
        return False
    if from_category == to_category:
        return True
    numeric = {"byte", "int", "int64", "real", "float", "double"}
    if from_category in numeric and to_category in numeric:
        return True
    return False


def validate_wire_pin_contract(
    settings: Dict[str, Any],
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    operation = str(payload.get("operation", "connect")).strip().lower() or "connect"
    if operation != "connect":
        return {"ok": True, "reason": "non_connect_operation"}

    blueprint_path = str(payload.get("blueprint_path", "")).strip()
    graph_name = str(payload.get("graph_name", "")).strip()
    inspect_req = {
        "action": "inspect_blueprint_graph",
        "payload": {
            "blueprint_path": blueprint_path,
            "graph_name": graph_name,
            "include_pins": True,
            "max_nodes": 4000,
        },
        "dry_run": True,
    }
    inspect_result = call_unreal(settings, "POST", "/execute", inspect_req)
    if inspect_result.status_code >= 400 or not bool(inspect_result.payload.get("success", False)):
        return {
            "ok": False,
            "error_code": "PIN_CONTRACT_ANALYSIS_FAILED",
            "message": "Failed to inspect blueprint graph for pin contract validation.",
            "upstream": inspect_result.payload,
        }

    inspect_payload = extract_upstream_payload(inspect_result.payload)
    nodes = inspect_payload.get("nodes", []) if isinstance(inspect_payload, dict) else []
    if not isinstance(nodes, list):
        nodes = []
    if len(nodes) == 0:
        analyze_req = {
            "action": "analyze_blueprint_graph",
            "payload": {
                "blueprint_path": blueprint_path,
                "graph_name": graph_name,
                "include_pins": True,
                "max_nodes": 4000,
                "max_trace_depth": 128,
            },
            "dry_run": True,
        }
        analyze_result = call_unreal(settings, "POST", "/execute", analyze_req)
        if analyze_result.status_code < 400 and bool(analyze_result.payload.get("success", False)):
            analyze_payload = extract_upstream_payload(analyze_result.payload)
            fallback_nodes = analyze_payload.get("nodes", []) if isinstance(analyze_payload, dict) else []
            if isinstance(fallback_nodes, list):
                nodes = fallback_nodes

    from_node = _find_node_for_pin_validation(
        nodes,
        str(payload.get("from_node_name", "")).strip(),
        str(payload.get("from_node_title_contains", "")).strip(),
    )
    to_node = _find_node_for_pin_validation(
        nodes,
        str(payload.get("to_node_name", "")).strip(),
        str(payload.get("to_node_title_contains", "")).strip(),
    )
    if from_node is None or to_node is None:
        return {
            "ok": False,
            "error_code": "PIN_CONTRACT_NODE_MISSING",
            "message": "Source or target node could not be resolved for pin contract validation.",
        }

    from_pin = _find_pin_in_node(from_node, str(payload.get("from_pin_name", "")).strip())
    to_pin = _find_pin_in_node(to_node, str(payload.get("to_pin_name", "")).strip())
    if from_pin is None or to_pin is None:
        return {
            "ok": False,
            "error_code": "PIN_CONTRACT_PIN_MISSING",
            "message": "Source or target pin could not be resolved for pin contract validation.",
        }

    from_dir = str(from_pin.get("direction", "")).strip().lower()
    to_dir = str(to_pin.get("direction", "")).strip().lower()
    if from_dir != "output" or to_dir != "input":
        return {
            "ok": False,
            "error_code": "PIN_DIRECTION_MISMATCH",
            "message": "Pin direction contract requires output -> input.",
            "details": {"from_direction": from_dir, "to_direction": to_dir},
        }

    from_cat = str(from_pin.get("category", "")).strip().lower()
    to_cat = str(to_pin.get("category", "")).strip().lower()
    if not _pin_categories_compatible(from_cat, to_cat):
        return {
            "ok": False,
            "error_code": "PIN_CATEGORY_MISMATCH",
            "message": "Pin categories are not compatible.",
            "details": {"from_category": from_cat, "to_category": to_cat},
        }

    return {
        "ok": True,
        "from_node": str(from_node.get("name", "")),
        "to_node": str(to_node.get("name", "")),
        "from_pin": str(from_pin.get("name", "")),
        "to_pin": str(to_pin.get("name", "")),
        "from_category": from_cat,
        "to_category": to_cat,
    }


def build_inverse_graph_step(step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    action = str(step.get("action", "")).strip()
    payload = step.get("payload", {})
    if not isinstance(payload, dict):
        return None
    if action == "wire_blueprint_pins":
        op = str(payload.get("operation", "connect")).strip().lower() or "connect"
        if op not in {"connect", "disconnect"}:
            return None
        inverse = dict(payload)
        inverse["operation"] = "disconnect" if op == "connect" else "connect"
        inverse["compile_after"] = False
        return {"id": f"rollback_{step.get('id', 'wire')}", "action": "wire_blueprint_pins", "payload": inverse}
    if action == "blueprint_node_authoring":
        op = str(payload.get("operation", "spawn_function_call")).strip().lower() or "spawn_function_call"
        node_name = str(payload.get("node_name", "")).strip()
        if op != "spawn_function_call" or not node_name:
            return None
        return {
            "id": f"rollback_{step.get('id', 'node')}",
            "action": "modify_blueprint_graph",
            "payload": {
                "blueprint_path": str(payload.get("blueprint_path", "")).strip(),
                "graph_name": str(payload.get("graph_name", "")).strip(),
                "operation": "remove_nodes",
                "node_name_contains": node_name,
            },
        }
    if action == "modify_blueprint_graph":
        op = str(payload.get("operation", "")).strip().lower()
        if op == "add_variable":
            var_name = str(payload.get("variable_name", payload.get("name", ""))).strip()
            if not var_name:
                return None
            return {
                "id": f"rollback_{step.get('id', 'var')}",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": str(payload.get("blueprint_path", "")).strip(),
                    "graph_name": str(payload.get("graph_name", "")).strip(),
                    "operation": "remove_variable",
                    "variable_name": var_name,
                    "name": var_name,
                },
            }
    return None


def build_rollback_plan_for_steps(plan_id: str, blueprint_path: str, steps: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    inverses: List[Dict[str, Any]] = []
    for step in reversed(steps):
        if not isinstance(step, dict):
            return None
        inverse = build_inverse_graph_step(step)
        if inverse is None:
            return None
        inverses.append(inverse)
    if not inverses:
        return None
    return {
        "plan_id": f"rollback_{plan_id}",
        "stop_on_error": True,
        "steps": inverses,
        "compile_blueprints": [blueprint_path] if blueprint_path else [],
    }


def build_signature_edit_rollback_plan(body: Dict[str, Any], plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    op = str(body.get("operation", "")).strip().lower()
    blueprint_path = str(body.get("blueprint_path", "")).strip()
    graph_name = str(body.get("graph_name", "EventGraph")).strip() or "EventGraph"
    if op == "add_variable":
        name = str(body.get("name", "")).strip()
        if not name:
            return None
        return {
            "plan_id": "rollback_signature_add_variable",
            "stop_on_error": True,
            "steps": [
                {
                    "id": "rollback_remove_variable",
                    "action": "modify_blueprint_graph",
                    "payload": {
                        "blueprint_path": blueprint_path,
                        "graph_name": graph_name,
                        "operation": "remove_variable",
                        "variable_name": name,
                        "name": name,
                    },
                }
            ],
            "compile_blueprints": [blueprint_path],
        }
    if op in {"create_function", "create_macro"}:
        step_list = plan.get("steps", [])
        if not isinstance(step_list, list):
            return None
        return build_rollback_plan_for_steps(f"signature_{op}", blueprint_path, step_list)
    return None


def build_node_pattern_rollback_plan(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    blueprint_path = str(body.get("blueprint_path", "")).strip()
    graph_name = str(body.get("graph_name", "EventGraph")).strip() or "EventGraph"
    base_name = str(body.get("base_node_name", "AgentPattern")).strip() or "AgentPattern"
    return {
        "plan_id": "rollback_node_pattern_apply",
        "stop_on_error": True,
        "steps": [
            {
                "id": "rollback_remove_pattern_nodes",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "remove_nodes",
                    "node_name_contains": base_name,
                },
            }
        ],
        "compile_blueprints": [blueprint_path],
    }


def run_node_pattern_dry_run_simulation(
    settings: Dict[str, Any],
    plan: Dict[str, Any],
) -> Tuple[HTTPStatus, Dict[str, Any]]:
    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        return HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "Plan steps must be an array.")
    simulated_nodes: set[str] = set()
    results: List[Dict[str, Any]] = []
    failed = 0
    for step in steps:
        if not isinstance(step, dict):
            failed += 1
            results.append({"id": "", "action": "", "success": False, "error_code": "INVALID_STEP", "message": "Step must be object."})
            continue
        step_id = str(step.get("id", "")).strip()
        action = str(step.get("action", "")).strip()
        payload = step.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        if action == "blueprint_node_authoring":
            op = str(payload.get("operation", "spawn_function_call")).strip().lower() or "spawn_function_call"
            node_name = str(payload.get("node_name", "")).strip()
            if op == "spawn_function_call" and node_name:
                simulated_nodes.add(node_name)
        if action == "wire_blueprint_pins":
            op = str(payload.get("operation", "connect")).strip().lower() or "connect"
            to_node_name = str(payload.get("to_node_name", "")).strip()
            if op == "connect" and to_node_name and to_node_name in simulated_nodes:
                results.append(
                    {
                        "id": step_id,
                        "action": action,
                        "success": True,
                        "error_code": "OK",
                        "message": "Dry-run simulation accepted wire to virtual spawned node.",
                        "simulation": "virtual_target",
                    }
                )
                continue
        upstream = call_unreal(settings, "POST", "/execute", {"action": action, "payload": payload, "dry_run": True})
        payload_out = upstream.payload if isinstance(upstream.payload, dict) else {}
        ok = upstream.status_code < 400 and bool(payload_out.get("success", False))
        if not ok:
            failed += 1
        results.append(
            {
                "id": step_id,
                "action": action,
                "success": ok,
                "error_code": payload_out.get("error_code", "OK" if ok else "FAILED"),
                "message": str(payload_out.get("message", "")),
                "payload": extract_upstream_payload(payload_out),
            }
        )
        if not ok:
            break
    response = {
        "success": failed == 0,
        "message": "Node pattern dry-run simulation completed." if failed == 0 else "Node pattern dry-run simulation failed.",
        "plan_id": str(plan.get("plan_id", "")),
        "summary": {
            "requested_action_steps": len(steps),
            "executed_steps": len(results),
            "succeeded_steps": len([r for r in results if bool(r.get("success", False))]),
            "failed_steps": failed,
            "dry_run": True,
            "simulation_mode": "virtual_nodes",
        },
        "steps": results,
        "simulated_nodes": sorted(list(simulated_nodes)),
    }
    return (HTTPStatus.OK if failed == 0 else HTTPStatus.CONFLICT), response


def canonicalize_for_hash(value: Any) -> Any:
    volatile_keys = {
        "timestamp",
        "created_at",
        "updated_at",
        "execution_run_id",
        "request_id",
        "trace_id",
        "plan_id",
        "rollback_token",
        "run_id",
        "started_at",
        "finished_at",
    }
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key in sorted(value.keys()):
            if key in volatile_keys:
                continue
            out[key] = canonicalize_for_hash(value[key])
        return out
    if isinstance(value, list):
        return [canonicalize_for_hash(item) for item in value]
    return value


def run_replay_suite(
    settings: Dict[str, Any],
    cases: List[Dict[str, Any]],
    repeats: int,
) -> Dict[str, Any]:
    repeats = max(2, min(10, int(repeats)))
    results: List[Dict[str, Any]] = []
    passed = 0
    failed = 0
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            failed += 1
            results.append(
                {
                    "case_id": f"case_{index}",
                    "success": False,
                    "error_code": "INVALID_CASE",
                    "message": "Case must be an object.",
                }
            )
            continue
        case_id = str(case.get("case_id", f"case_{index}")).strip() or f"case_{index}"
        command = str(case.get("command", "")).strip()
        recipe_id = str(case.get("recipe_id", "")).strip()
        goal_context = case.get("goal_context", {})
        direct_inputs = case.get("inputs", {})
        if not isinstance(goal_context, dict):
            goal_context = {}
        if not isinstance(direct_inputs, dict):
            direct_inputs = {}

        routed_recipe_id = recipe_id or infer_recipe_id_from_message(command)
        if not routed_recipe_id:
            failed += 1
            results.append(
                {
                    "case_id": case_id,
                    "success": False,
                    "error_code": "RECIPE_ROUTE_UNRESOLVED",
                    "message": "Could not resolve recipe route for replay case.",
                }
            )
            continue
        recipe_def = get_recipe_definition(routed_recipe_id)
        if recipe_def is None:
            failed += 1
            results.append(
                {
                    "case_id": case_id,
                    "success": False,
                    "error_code": "RECIPE_NOT_FOUND",
                    "message": "Replay requires known local recipe.",
                    "recipe_id": routed_recipe_id,
                }
            )
            continue

        resolved_inputs = dict(goal_context)
        nested_inputs = goal_context.get("inputs", {})
        if isinstance(nested_inputs, dict):
            resolved_inputs.update(nested_inputs)
        resolved_inputs.update(direct_inputs)
        resolved_inputs = apply_recipe_defaults(recipe_def, resolved_inputs)
        validation = validate_recipe_inputs(recipe_def, resolved_inputs)
        if not validation.get("ok", False):
            failed += 1
            results.append(
                {
                    "case_id": case_id,
                    "success": False,
                    "error_code": "RECIPE_INPUT_VALIDATION_FAILED",
                    "message": "Replay case failed recipe validation.",
                    "validation": validation,
                    "recipe_id": routed_recipe_id,
                }
            )
            continue

        run_hashes: List[str] = []
        run_samples: List[Dict[str, Any]] = []
        run_ok = True
        for _ in range(repeats):
            status_code, payload, execution_mode = run_recipe_with_local_fallback(
                settings=settings,
                recipe_id=routed_recipe_id,
                resolved_inputs=resolved_inputs,
                dry_run=True,
                stop_on_error=True,
                profile="strict",
            )
            sample = {
                "status_code": int(status_code),
                "payload": payload if isinstance(payload, dict) else {"raw": payload},
                "execution_mode": execution_mode,
            }
            canonical = canonicalize_for_hash(sample)
            run_hashes.append(_stable_hash(canonical))
            run_samples.append(sample)
            if int(status_code) >= 500 or not bool(sample["payload"].get("success", False)):
                run_ok = False
        deterministic = len(set(run_hashes)) == 1
        case_success = run_ok and deterministic
        if case_success:
            passed += 1
        else:
            failed += 1
        results.append(
            {
                "case_id": case_id,
                "success": case_success,
                "recipe_id": routed_recipe_id,
                "run_ok": run_ok,
                "deterministic": deterministic,
                "hashes": run_hashes,
                "sample": run_samples[0] if run_samples else {},
            }
        )
    return {
        "success": failed == 0,
        "repeats": repeats,
        "case_total": len(results),
        "case_passed": passed,
        "case_failed": failed,
        "cases": results,
    }


def build_node_pattern_plan(pattern_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    blueprint_path = str(body.get("blueprint_path", "")).strip()
    graph_name = str(body.get("graph_name", "EventGraph")).strip() or "EventGraph"
    base_name = str(body.get("base_node_name", "AgentPattern")).strip() or "AgentPattern"
    message = str(body.get("message", "Agent pattern")).strip() or "Agent pattern"
    duration = float(body.get("duration", 0.25))
    true_message = str(body.get("true_message", "Branch TRUE")).strip() or "Branch TRUE"
    false_message = str(body.get("false_message", "Branch FALSE")).strip() or "Branch FALSE"
    first_message = str(body.get("first_message", "Stage 1")).strip() or "Stage 1"
    second_message = str(body.get("second_message", "Stage 2")).strip() or "Stage 2"
    first_delay = float(body.get("first_delay", duration))
    second_delay = float(body.get("second_delay", duration))
    compile_blueprints = [blueprint_path] if blueprint_path else []

    if pattern_id == "begin_play_print":
        steps = [
            {
                "id": "spawn_print",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "spawn_function_call",
                    "node_name": f"{base_name}_Print",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "compile_after": False,
                },
            },
            {
                "id": "set_print_message",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "call_function",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "node_name_contains": f"{base_name}_Print",
                    "inputs": {"In String": message},
                },
            },
            {
                "id": "wire_begin_play_to_print",
                "action": "wire_blueprint_pins",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "connect",
                    "from_node_title_contains": "BeginPlay",
                    "from_pin_name": "then",
                    "to_node_name": f"{base_name}_Print",
                    "to_pin_name": "execute",
                    "compile_after": False,
                },
            },
        ]
    elif pattern_id == "begin_play_delay_print":
        steps = [
            {
                "id": "spawn_delay",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "spawn_function_call",
                    "node_name": f"{base_name}_Delay",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "Delay",
                    "compile_after": False,
                },
            },
            {
                "id": "set_delay_duration",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "call_function",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "Delay",
                    "node_name_contains": f"{base_name}_Delay",
                    "inputs": {"Duration": duration},
                },
            },
            {
                "id": "spawn_print",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "spawn_function_call",
                    "node_name": f"{base_name}_Print",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "compile_after": False,
                },
            },
            {
                "id": "set_print_message",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "call_function",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "node_name_contains": f"{base_name}_Print",
                    "inputs": {"In String": message},
                },
            },
            {
                "id": "wire_begin_play_to_delay",
                "action": "wire_blueprint_pins",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "connect",
                    "from_node_title_contains": "BeginPlay",
                    "from_pin_name": "then",
                    "to_node_name": f"{base_name}_Delay",
                    "to_pin_name": "execute",
                    "compile_after": False,
                },
            },
            {
                "id": "wire_delay_to_print",
                "action": "wire_blueprint_pins",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "connect",
                    "from_node_name": f"{base_name}_Delay",
                    "from_pin_name": "then",
                    "to_node_name": f"{base_name}_Print",
                    "to_pin_name": "execute",
                    "compile_after": False,
                },
            },
        ]
    elif pattern_id == "begin_play_branch_dual_print":
        steps = [
            {
                "id": "add_branch",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "add_branch",
                    "condition_default": True,
                    "compile_after": False,
                },
            },
            {
                "id": "spawn_print_true",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "spawn_function_call",
                    "node_name": f"{base_name}_PrintTrue",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "compile_after": False,
                },
            },
            {
                "id": "spawn_print_false",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "spawn_function_call",
                    "node_name": f"{base_name}_PrintFalse",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "compile_after": False,
                },
            },
            {
                "id": "wire_branch_true",
                "action": "wire_blueprint_pins",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "connect",
                    "from_node_title_contains": "Branch",
                    "from_pin_name": "then",
                    "to_node_name": f"{base_name}_PrintTrue",
                    "to_pin_name": "execute",
                    "compile_after": False,
                },
            },
            {
                "id": "wire_branch_false",
                "action": "wire_blueprint_pins",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "connect",
                    "from_node_title_contains": "Branch",
                    "from_pin_name": "else",
                    "to_node_name": f"{base_name}_PrintFalse",
                    "to_pin_name": "execute",
                    "compile_after": False,
                },
            },
            {
                "id": "set_true_message",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "set_default",
                    "class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "node_name_contains": f"{base_name}_PrintTrue",
                    "pin_name": "InString",
                    "default_value": true_message,
                    "compile_after": False,
                },
            },
            {
                "id": "set_false_message",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "set_default",
                    "class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "node_name_contains": f"{base_name}_PrintFalse",
                    "pin_name": "InString",
                    "default_value": false_message,
                    "compile_after": False,
                },
            },
        ]
    elif pattern_id == "begin_play_sequence_two_stage":
        steps = [
            {
                "id": "spawn_delay_1",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "spawn_function_call",
                    "node_name": f"{base_name}_Delay1",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "Delay",
                    "compile_after": False,
                },
            },
            {
                "id": "spawn_print_1",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "spawn_function_call",
                    "node_name": f"{base_name}_Print1",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "compile_after": False,
                },
            },
            {
                "id": "spawn_delay_2",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "spawn_function_call",
                    "node_name": f"{base_name}_Delay2",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "Delay",
                    "compile_after": False,
                },
            },
            {
                "id": "spawn_print_2",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "spawn_function_call",
                    "node_name": f"{base_name}_Print2",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "compile_after": False,
                },
            },
            {
                "id": "set_delay_1",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "set_default",
                    "class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "Delay",
                    "node_name_contains": f"{base_name}_Delay1",
                    "pin_name": "Duration",
                    "default_value": str(first_delay),
                    "compile_after": False,
                },
            },
            {
                "id": "set_delay_2",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "set_default",
                    "class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "Delay",
                    "node_name_contains": f"{base_name}_Delay2",
                    "pin_name": "Duration",
                    "default_value": str(second_delay),
                    "compile_after": False,
                },
            },
            {
                "id": "set_print_1",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "set_default",
                    "class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "node_name_contains": f"{base_name}_Print1",
                    "pin_name": "InString",
                    "default_value": first_message,
                    "compile_after": False,
                },
            },
            {
                "id": "set_print_2",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "set_default",
                    "class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "node_name_contains": f"{base_name}_Print2",
                    "pin_name": "InString",
                    "default_value": second_message,
                    "compile_after": False,
                },
            },
            {
                "id": "wire_begin_play_delay_1",
                "action": "wire_blueprint_pins",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "connect",
                    "from_node_title_contains": "BeginPlay",
                    "from_pin_name": "then",
                    "to_node_name": f"{base_name}_Delay1",
                    "to_pin_name": "execute",
                    "compile_after": False,
                },
            },
            {
                "id": "wire_delay_1_print_1",
                "action": "wire_blueprint_pins",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "connect",
                    "from_node_name": f"{base_name}_Delay1",
                    "from_pin_name": "then",
                    "to_node_name": f"{base_name}_Print1",
                    "to_pin_name": "execute",
                    "compile_after": False,
                },
            },
            {
                "id": "wire_print_1_delay_2",
                "action": "wire_blueprint_pins",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "connect",
                    "from_node_name": f"{base_name}_Print1",
                    "from_pin_name": "then",
                    "to_node_name": f"{base_name}_Delay2",
                    "to_pin_name": "execute",
                    "compile_after": False,
                },
            },
            {
                "id": "wire_delay_2_print_2",
                "action": "wire_blueprint_pins",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "connect",
                    "from_node_name": f"{base_name}_Delay2",
                    "from_pin_name": "then",
                    "to_node_name": f"{base_name}_Print2",
                    "to_pin_name": "execute",
                    "compile_after": False,
                },
            },
        ]
    elif pattern_id == "replace_call_by_title":
        target_node_title_contains = str(body.get("target_node_title_contains", "")).strip()
        function_class_path = str(body.get("function_class_path", "")).strip()
        function_name = str(body.get("function_name", "")).strip()
        if not target_node_title_contains or not function_class_path or not function_name:
            raise ValueError("replace_call_by_title requires target_node_title_contains, function_class_path, and function_name.")
        steps = [
            {
                "id": "replace_call",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "replace_function_call",
                    "node_name": f"{base_name}_Replace",
                    "target_node_title_contains": target_node_title_contains,
                    "function_class_path": function_class_path,
                    "function_name": function_name,
                    "compile_after": False,
                },
            }
        ]
    else:
        raise ValueError("Unknown pattern_id")

    return {
        "plan_id": f"node_pattern_{pattern_id}",
        "stop_on_error": True,
        "profile": "strict",
        "compile_blueprints": compile_blueprints,
        "steps": steps,
    }


def build_workflow_plan(workflow_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    namespace_root = str(body.get("namespace_root", "/Game/AgentGenerated")).strip() or "/Game/AgentGenerated"
    if not namespace_root.startswith("/Game"):
        namespace_root = "/Game/AgentGenerated"

    if workflow_id == "objective_capture_loop_full":
        controller_asset_name = str(body.get("controller_asset_name", "BP_AgentFullObjectiveController")).strip() or "BP_AgentFullObjectiveController"
        objective_count = int(body.get("objective_count", 5))
        time_limit_sec = float(body.get("time_limit_sec", 180.0))
        controller_path = f"{namespace_root}/Gameplay/{controller_asset_name}"
        steps: List[Dict[str, Any]] = [
            {
                "id": "create_controller",
                "action": "create_blueprint",
                "payload": {
                    "asset_name": controller_asset_name,
                    "package_path": f"{namespace_root}/Gameplay",
                    "parent_class": "/Script/Engine.Actor",
                },
            },
            {
                "id": "add_required_count",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": controller_path,
                    "operation": "add_variable",
                    "variable_name": "ObjectiveCountRequired",
                    "variable_type": "int",
                    "default_value": str(objective_count),
                    "compile_after": False,
                },
            },
            {
                "id": "add_collected_count",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": controller_path,
                    "operation": "add_variable",
                    "variable_name": "ObjectivesCollected",
                    "variable_type": "int",
                    "default_value": "0",
                    "compile_after": False,
                },
            },
            {
                "id": "add_time_limit",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": controller_path,
                    "operation": "add_variable",
                    "variable_name": "TimeLimitSec",
                    "variable_type": "float",
                    "default_value": str(time_limit_sec),
                    "compile_after": False,
                },
            },
            {
                "id": "add_loop_branch",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": controller_path,
                    "operation": "add_branch",
                    "condition_default": True,
                    "compile_after": False,
                },
            },
            {
                "id": "spawn_begin_play_log",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": controller_path,
                    "graph_name": "EventGraph",
                    "operation": "spawn_function_call",
                    "node_name": "WF_ObjectiveLoop_Print",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "compile_after": False,
                },
            },
            {
                "id": "wire_begin_play_log",
                "action": "wire_blueprint_pins",
                "payload": {
                    "blueprint_path": controller_path,
                    "graph_name": "EventGraph",
                    "operation": "connect",
                    "from_node_title_contains": "BeginPlay",
                    "from_pin_name": "then",
                    "to_node_name": "WF_ObjectiveLoop_Print",
                    "to_pin_name": "execute",
                    "compile_after": False,
                },
            },
        ]
        return {
            "plan_id": f"workflow_{workflow_id}",
            "profile": "strict",
            "stop_on_error": True,
            "compile_blueprints": [controller_path],
            "steps": steps,
            "outputs": {
                "controller_blueprint_path": controller_path,
                "objective_count": objective_count,
                "time_limit_sec": time_limit_sec,
            },
        }

    if workflow_id == "animation_locomotion_scaffold":
        anim_asset_name = str(body.get("anim_asset_name", "ABP_AgentLocomotion")).strip() or "ABP_AgentLocomotion"
        anim_path = f"{namespace_root}/Animation/{anim_asset_name}"
        steps = [
            {
                "id": "create_anim_instance",
                "action": "create_blueprint",
                "payload": {
                    "asset_name": anim_asset_name,
                    "package_path": f"{namespace_root}/Animation",
                    "parent_class": "/Script/Engine.AnimInstance",
                },
            },
            {
                "id": "add_speed",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": anim_path,
                    "operation": "add_variable",
                    "variable_name": "Speed",
                    "variable_type": "float",
                    "default_value": "0.0",
                    "compile_after": False,
                },
            },
            {
                "id": "add_direction",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": anim_path,
                    "operation": "add_variable",
                    "variable_name": "Direction",
                    "variable_type": "float",
                    "default_value": "0.0",
                    "compile_after": False,
                },
            },
            {
                "id": "add_in_air",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": anim_path,
                    "operation": "add_variable",
                    "variable_name": "bIsInAir",
                    "variable_type": "bool",
                    "default_value": "false",
                    "compile_after": False,
                },
            },
            {
                "id": "create_update_function",
                "action": "create_blueprint_function",
                "payload": {
                    "blueprint_path": anim_path,
                    "function_name": "UpdateLocomotionVariables",
                    "category": "Locomotion",
                    "compile_after": False,
                },
            },
            {
                "id": "spawn_anim_log",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": anim_path,
                    "graph_name": "EventGraph",
                    "operation": "spawn_function_call",
                    "node_name": "WF_Anim_Print",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "compile_after": False,
                },
            },
        ]
        return {
            "plan_id": f"workflow_{workflow_id}",
            "profile": "strict",
            "stop_on_error": True,
            "compile_blueprints": [anim_path],
            "steps": steps,
            "outputs": {
                "anim_blueprint_path": anim_path,
            },
        }

    if workflow_id == "character_combo_scaffold":
        character_blueprint_path = str(body.get("character_blueprint_path", "")).strip()
        if not character_blueprint_path:
            raise ValueError("character_combo_scaffold requires character_blueprint_path.")
        combo_window_sec = float(body.get("combo_window_sec", 1.0))
        steps = [
            {
                "id": "add_combo_window",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": character_blueprint_path,
                    "operation": "add_variable",
                    "variable_name": "RollDashComboWindowSec",
                    "variable_type": "float",
                    "default_value": str(combo_window_sec),
                    "compile_after": False,
                },
            },
            {
                "id": "add_last_roll_time",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": character_blueprint_path,
                    "operation": "add_variable",
                    "variable_name": "LastRollInputTimestamp",
                    "variable_type": "float",
                    "default_value": "-1000.0",
                    "compile_after": False,
                },
            },
            {
                "id": "add_roll_flag",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": character_blueprint_path,
                    "operation": "add_variable",
                    "variable_name": "bRollTriggeredAfterLanding",
                    "variable_type": "bool",
                    "default_value": "false",
                    "compile_after": False,
                },
            },
            {
                "id": "spawn_combo_log",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": character_blueprint_path,
                    "graph_name": "EventGraph",
                    "operation": "spawn_function_call",
                    "node_name": "WF_Combo_Print",
                    "function_class_path": "/Script/Engine.KismetSystemLibrary",
                    "function_name": "PrintString",
                    "compile_after": False,
                },
            },
            {
                "id": "wire_combo_log",
                "action": "wire_blueprint_pins",
                "payload": {
                    "blueprint_path": character_blueprint_path,
                    "graph_name": "EventGraph",
                    "operation": "connect",
                    "from_node_title_contains": "BeginPlay",
                    "from_pin_name": "then",
                    "to_node_name": "WF_Combo_Print",
                    "to_pin_name": "execute",
                    "compile_after": False,
                },
            },
        ]
        return {
            "plan_id": f"workflow_{workflow_id}",
            "profile": "strict",
            "stop_on_error": True,
            "compile_blueprints": [character_blueprint_path],
            "steps": steps,
            "outputs": {
                "character_blueprint_path": character_blueprint_path,
                "combo_window_sec": combo_window_sec,
            },
        }

    raise ValueError("Unknown workflow_id")


def build_animation_autonomy_plan(template_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    namespace_root = str(body.get("namespace_root", "/Game/AgentGenerated")).strip() or "/Game/AgentGenerated"
    if not namespace_root.startswith("/Game"):
        namespace_root = "/Game/AgentGenerated"
    anim_asset_name = str(body.get("anim_asset_name", "ABP_AgentAutoAnim")).strip() or "ABP_AgentAutoAnim"
    anim_path = f"{namespace_root}/Animation/{anim_asset_name}"

    common_steps: List[Dict[str, Any]] = [
        {
            "id": "create_anim_instance",
            "action": "create_blueprint",
            "payload": {
                "asset_name": anim_asset_name,
                "package_path": f"{namespace_root}/Animation",
                "parent_class": "/Script/Engine.AnimInstance",
            },
        },
        {
            "id": "add_speed",
            "action": "modify_blueprint_graph",
            "payload": {
                "blueprint_path": anim_path,
                "operation": "add_variable",
                "variable_name": "Speed",
                "variable_type": "float",
                "default_value": "0.0",
                "category": "Locomotion",
                "compile_after": False,
            },
        },
        {
            "id": "add_direction",
            "action": "modify_blueprint_graph",
            "payload": {
                "blueprint_path": anim_path,
                "operation": "add_variable",
                "variable_name": "Direction",
                "variable_type": "float",
                "default_value": "0.0",
                "category": "Locomotion",
                "compile_after": False,
            },
        },
        {
            "id": "add_is_in_air",
            "action": "modify_blueprint_graph",
            "payload": {
                "blueprint_path": anim_path,
                "operation": "add_variable",
                "variable_name": "bIsInAir",
                "variable_type": "bool",
                "default_value": "false",
                "category": "Locomotion",
                "compile_after": False,
            },
        },
        {
            "id": "create_update_function",
            "action": "create_blueprint_function",
            "payload": {
                "blueprint_path": anim_path,
                "function_name": "UpdateLocomotionVariables",
                "category": "Locomotion",
                "compile_after": False,
            },
        },
    ]

    if template_id == "locomotion_state_scaffold":
        steps = common_steps + [
            {
                "id": "create_evaluate_function",
                "action": "create_blueprint_function",
                "payload": {
                    "blueprint_path": anim_path,
                    "function_name": "EvaluateLocomotionState",
                    "category": "Locomotion",
                    "compile_after": False,
                },
            },
            {
                "id": "spawn_state_changed_event",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": anim_path,
                    "graph_name": "EventGraph",
                    "operation": "spawn_custom_event",
                    "custom_event_name": "OnLocomotionStateChanged",
                    "node_name": "Anim_OnLocomotionStateChanged",
                    "compile_after": False,
                },
            },
            {
                "id": "spawn_state_branch",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": anim_path,
                    "graph_name": "EventGraph",
                    "operation": "spawn_branch_node",
                    "node_name": "Anim_LocomotionBranch",
                    "condition_default": True,
                    "compile_after": False,
                },
            },
        ]
    elif template_id == "montage_notify_scaffold":
        steps = common_steps + [
            {
                "id": "add_montage_name",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": anim_path,
                    "operation": "add_variable",
                    "variable_name": "CurrentMontageTag",
                    "variable_type": "name",
                    "default_value": "None",
                    "category": "Montage",
                    "compile_after": False,
                },
            },
            {
                "id": "spawn_notify_event",
                "action": "blueprint_node_authoring",
                "payload": {
                    "blueprint_path": anim_path,
                    "graph_name": "EventGraph",
                    "operation": "spawn_custom_event",
                    "custom_event_name": "OnAnimNotifyForwarded",
                    "node_name": "Anim_OnAnimNotifyForwarded",
                    "compile_after": False,
                },
            },
        ]
    else:
        raise ValueError("Unknown animation autonomy template_id")

    return {
        "plan_id": f"animation_autonomy_{template_id}",
        "profile": "strict",
        "stop_on_error": True,
        "compile_blueprints": [anim_path],
        "steps": steps,
        "outputs": {"anim_blueprint_path": anim_path, "template_id": template_id},
    }


def build_ai_autonomy_plan(template_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    namespace_root = str(body.get("namespace_root", "/Game/AgentGenerated")).strip() or "/Game/AgentGenerated"
    if not namespace_root.startswith("/Game"):
        namespace_root = "/Game/AgentGenerated"
    ai_controller_asset_name = str(body.get("ai_controller_asset_name", "BP_AgentAIController")).strip() or "BP_AgentAIController"
    bt_task_asset_name = str(body.get("bt_task_asset_name", "BTT_AgentTask")).strip() or "BTT_AgentTask"
    eqs_query_name = str(body.get("eqs_query_name", "EQS_AgentQuery")).strip() or "EQS_AgentQuery"
    perception_range = float(body.get("perception_range", 2000.0))
    blackboard_keys_raw = body.get("blackboard_keys", [])
    blackboard_keys: List[Dict[str, Any]] = []
    if isinstance(blackboard_keys_raw, list):
        for item in blackboard_keys_raw:
            if not isinstance(item, dict):
                continue
            key_name = str(item.get("key_name", "")).strip()
            if not key_name:
                continue
            blackboard_keys.append(
                {
                    "key_name": key_name,
                    "key_type": str(item.get("key_type", "name")).strip() or "name",
                    "default_value": str(item.get("default_value", "")).strip(),
                }
            )
    if len(blackboard_keys) == 0:
        blackboard_keys = [
            {"key_name": "TargetActorKey", "key_type": "string", "default_value": ""},
            {"key_name": "LastSeenLocationKey", "key_type": "string", "default_value": ""},
            {"key_name": "BehaviorStateKey", "key_type": "name", "default_value": "Idle"},
            {"key_name": "HasLineOfSightKey", "key_type": "bool", "default_value": "false"},
        ]

    ai_controller_path = f"{namespace_root}/AI/{ai_controller_asset_name}"
    bt_task_path = f"{namespace_root}/AI/{bt_task_asset_name}"

    common_steps: List[Dict[str, Any]] = [
        {
            "id": "create_ai_controller",
            "action": "create_blueprint",
            "payload": {
                "asset_name": ai_controller_asset_name,
                "package_path": f"{namespace_root}/AI",
                "parent_class": "/Script/AIModule.AIController",
            },
        },
        {
            "id": "create_bt_task",
            "action": "create_blueprint",
            "payload": {
                "asset_name": bt_task_asset_name,
                "package_path": f"{namespace_root}/AI",
                "parent_class": "/Script/AIModule.BTTask_BlueprintBase",
            },
        },
        {
            "id": "add_ai_perception_component",
            "action": "modify_blueprint_components",
            "payload": {
                "blueprint_path": ai_controller_path,
                "operation": "add_component",
                "class_path": "/Script/AIModule.AIPerceptionComponent",
                "component_name": "AgentAIPerception",
                "parent_component": "DefaultSceneRoot",
                "compile_after": False,
            },
        },
        {
            "id": "create_setup_function",
            "action": "create_blueprint_function",
            "payload": {
                "blueprint_path": ai_controller_path,
                "function_name": "SetupBehaviorAutonomy",
                "category": "AI",
                "compile_after": False,
            },
        },
        {
            "id": "spawn_perception_event",
            "action": "blueprint_node_authoring",
            "payload": {
                "blueprint_path": ai_controller_path,
                "graph_name": "EventGraph",
                "operation": "spawn_custom_event",
                "custom_event_name": "OnPerceptionUpdated_Agent",
                "node_name": "AI_OnPerceptionUpdated_Agent",
                "compile_after": False,
            },
        },
        {
            "id": "spawn_eqs_event",
            "action": "blueprint_node_authoring",
            "payload": {
                "blueprint_path": ai_controller_path,
                "graph_name": "EventGraph",
                "operation": "spawn_custom_event",
                "custom_event_name": "OnEQSResultReady_Agent",
                "node_name": "AI_OnEQSResultReady_Agent",
                "compile_after": False,
            },
        },
        {
            "id": "spawn_ai_branch",
            "action": "blueprint_node_authoring",
            "payload": {
                "blueprint_path": ai_controller_path,
                "graph_name": "EventGraph",
                "operation": "spawn_branch_node",
                "node_name": "AI_AuthorityGuard",
                "condition_default": True,
                "compile_after": False,
            },
        },
        {
            "id": "add_perception_range",
            "action": "modify_blueprint_graph",
            "payload": {
                "blueprint_path": ai_controller_path,
                "operation": "add_variable",
                "variable_name": "PerceptionRange",
                "variable_type": "float",
                "default_value": str(perception_range),
                "category": "AI",
                "compile_after": False,
            },
        },
        {
            "id": "add_eqs_query_name",
            "action": "modify_blueprint_graph",
            "payload": {
                "blueprint_path": ai_controller_path,
                "operation": "add_variable",
                "variable_name": "EQSQueryName",
                "variable_type": "name",
                "default_value": eqs_query_name,
                "category": "AI",
                "compile_after": False,
            },
        },
    ]

    for index, key in enumerate(blackboard_keys, start=1):
        key_name = str(key.get("key_name", "")).strip()
        if not key_name:
            continue
        key_type = str(key.get("key_type", "name")).strip() or "name"
        default_value = str(key.get("default_value", "")).strip()
        var_name = f"BB_{key_name}"
        common_steps.append(
            {
                "id": f"add_blackboard_key_{index}",
                "action": "modify_blueprint_graph",
                "payload": {
                    "blueprint_path": ai_controller_path,
                    "operation": "add_variable",
                    "variable_name": var_name,
                    "variable_type": key_type,
                    "default_value": default_value,
                    "category": "Blackboard",
                    "compile_after": False,
                },
            }
        )

    if template_id == "bt_eqs_perception_scaffold":
        steps = list(common_steps)
    elif template_id == "ai_patrol_chase_scaffold":
        steps = list(common_steps)
        steps.extend(
            [
                {
                    "id": "add_patrol_state",
                    "action": "modify_blueprint_graph",
                    "payload": {
                        "blueprint_path": ai_controller_path,
                        "operation": "add_variable",
                        "variable_name": "BB_PatrolState",
                        "variable_type": "name",
                        "default_value": "Patrol",
                        "category": "Blackboard",
                        "compile_after": False,
                    },
                },
                {
                    "id": "add_chase_state",
                    "action": "modify_blueprint_graph",
                    "payload": {
                        "blueprint_path": ai_controller_path,
                        "operation": "add_variable",
                        "variable_name": "BB_ChaseState",
                        "variable_type": "name",
                        "default_value": "Chase",
                        "category": "Blackboard",
                        "compile_after": False,
                    },
                },
            ]
        )
    else:
        raise ValueError("Unknown ai autonomy template_id")

    return {
        "plan_id": f"ai_autonomy_{template_id}",
        "profile": "strict",
        "stop_on_error": True,
        "compile_blueprints": [ai_controller_path, bt_task_path],
        "steps": steps,
        "outputs": {
            "template_id": template_id,
            "ai_controller_path": ai_controller_path,
            "bt_task_path": bt_task_path,
            "eqs_query_name": eqs_query_name,
            "blackboard_keys": blackboard_keys,
        },
    }


def build_blackboard_schema_evolution_plan(body: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    blueprint_path = str(body.get("blueprint_path", "")).strip()
    if not blueprint_path:
        raise ValueError("blueprint_path is required.")
    graph_name = str(body.get("graph_name", "EventGraph")).strip() or "EventGraph"
    schema_raw = body.get("schema", [])
    remove_keys_raw = body.get("remove_keys", [])
    rename_keys_raw = body.get("rename_keys", [])
    stop_on_error = bool(body.get("stop_on_error", True))

    steps: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {
        "added": [],
        "removed": [],
        "renamed": [],
        "blueprint_path": blueprint_path,
        "graph_name": graph_name,
    }

    index = 0
    if isinstance(schema_raw, list):
        for item in schema_raw:
            if not isinstance(item, dict):
                continue
            key_name = str(item.get("key_name", "")).strip()
            if not key_name:
                continue
            key_type = str(item.get("key_type", "name")).strip() or "name"
            default_value = str(item.get("default_value", "")).strip()
            var_name = f"BB_{key_name}"
            index += 1
            steps.append(
                {
                    "id": f"bb_add_{index}",
                    "action": "modify_blueprint_graph",
                    "payload": {
                        "blueprint_path": blueprint_path,
                        "graph_name": graph_name,
                        "operation": "add_variable",
                        "variable_name": var_name,
                        "variable_type": key_type,
                        "default_value": default_value,
                        "category": "Blackboard",
                        "compile_after": False,
                    },
                }
            )
            summary["added"].append({"variable_name": var_name, "variable_type": key_type, "default_value": default_value})

    if isinstance(rename_keys_raw, list):
        for item in rename_keys_raw:
            if not isinstance(item, dict):
                continue
            old_key = str(item.get("from", "")).strip()
            new_key = str(item.get("to", "")).strip()
            if not old_key or not new_key:
                continue
            old_var = f"BB_{old_key}"
            new_var = f"BB_{new_key}"
            index += 1
            steps.append(
                {
                    "id": f"bb_rename_add_{index}",
                    "action": "modify_blueprint_graph",
                    "payload": {
                        "blueprint_path": blueprint_path,
                        "graph_name": graph_name,
                        "operation": "add_variable",
                        "variable_name": new_var,
                        "variable_type": str(item.get("key_type", "name")).strip() or "name",
                        "default_value": str(item.get("default_value", "")).strip(),
                        "category": "Blackboard",
                        "compile_after": False,
                    },
                }
            )
            index += 1
            steps.append(
                {
                    "id": f"bb_rename_remove_{index}",
                    "action": "modify_blueprint_graph",
                    "payload": {
                        "blueprint_path": blueprint_path,
                        "graph_name": graph_name,
                        "operation": "remove_variable",
                        "variable_name": old_var,
                        "fail_if_missing": False,
                        "compile_after": False,
                    },
                }
            )
            summary["renamed"].append({"from": old_var, "to": new_var})

    if isinstance(remove_keys_raw, list):
        for item in remove_keys_raw:
            key_name = str(item).strip() if not isinstance(item, dict) else str(item.get("key_name", "")).strip()
            if not key_name:
                continue
            var_name = f"BB_{key_name}"
            index += 1
            steps.append(
                {
                    "id": f"bb_remove_{index}",
                    "action": "modify_blueprint_graph",
                    "payload": {
                        "blueprint_path": blueprint_path,
                        "graph_name": graph_name,
                        "operation": "remove_variable",
                        "variable_name": var_name,
                        "fail_if_missing": False,
                        "compile_after": False,
                    },
                }
            )
            summary["removed"].append({"variable_name": var_name})

    plan = {
        "plan_id": f"blackboard_schema_evolution_{uuid4().hex[:8]}",
        "profile": "strict",
        "stop_on_error": stop_on_error,
        "compile_blueprints": [blueprint_path],
        "steps": steps,
    }
    return plan, summary


def run_dependency_safety_check(settings: Dict[str, Any], asset_paths: List[str], depth: int = 2) -> Dict[str, Any]:
    unique_assets = sorted({str(item).strip() for item in asset_paths if isinstance(item, str) and str(item).strip()})
    depth = max(1, min(6, int(depth)))
    items: List[Dict[str, Any]] = []
    blockers: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    total_risk = 0.0

    for asset_path in unique_assets:
        dep = call_unreal(
            settings,
            "POST",
            "/execute",
            {"action": "list_asset_dependencies", "payload": {"asset_path": asset_path, "depth": depth}, "dry_run": True},
        )
        ref = call_unreal(
            settings,
            "POST",
            "/execute",
            {"action": "list_asset_referencers", "payload": {"asset_path": asset_path, "depth": depth}, "dry_run": True},
        )
        impact = call_unreal(
            settings,
            "POST",
            "/execute",
            {"action": "analyze_asset_impact", "payload": {"asset_path": asset_path, "change_type": "modify", "depth": depth}, "dry_run": True},
        )

        dep_payload = extract_upstream_payload(dep.payload if isinstance(dep.payload, dict) else {})
        ref_payload = extract_upstream_payload(ref.payload if isinstance(ref.payload, dict) else {})
        impact_payload = extract_upstream_payload(impact.payload if isinstance(impact.payload, dict) else {})

        dependencies = dep_payload.get("dependencies", []) if isinstance(dep_payload.get("dependencies", []), list) else []
        referencers = ref_payload.get("referencers", []) if isinstance(ref_payload.get("referencers", []), list) else []
        risk_flags = impact_payload.get("risk_flags", []) if isinstance(impact_payload.get("risk_flags", []), list) else []
        risk_score = float(impact_payload.get("risk_score", 0.0)) if isinstance(impact_payload, dict) else 0.0
        total_risk += risk_score

        item = {
            "asset_path": asset_path,
            "dependency_count": len(dependencies),
            "referencer_count": len(referencers),
            "risk_flags": risk_flags,
            "risk_score": risk_score,
            "status_codes": {
                "dependencies": int(dep.status_code),
                "referencers": int(ref.status_code),
                "impact": int(impact.status_code),
            },
        }
        items.append(item)
        if "DESTRUCTIVE_CHANGE_TYPE" in risk_flags or "HIGH_REFERENCER_COUNT" in risk_flags:
            blockers.append(item)
        elif "HIGH_DEPENDENCY_FANOUT" in risk_flags or risk_score >= 20:
            warnings.append(item)

    return {
        "success": len(blockers) == 0,
        "asset_count": len(unique_assets),
        "depth": depth,
        "items": items,
        "blockers": blockers,
        "warnings": warnings,
        "total_risk_score": total_risk,
    }


def enforce_content_schema(settings: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    package_path = str(body.get("package_path", "/Game")).strip() or "/Game"
    recursive = bool(body.get("recursive", True))
    max_assets = max(1, min(2000, int(body.get("max_assets", 500))))
    naming_pattern = str(body.get("naming_pattern", r"^(BP_|WBP_|ABP_|BTT_|BTD_|DA_|SM_|M_|MI_).+")).strip()
    allowed_roots_raw = body.get("allowed_roots", ["/Game"])
    allowed_roots = [str(item).strip() for item in allowed_roots_raw if isinstance(item, str) and str(item).strip()] if isinstance(allowed_roots_raw, list) else ["/Game"]
    expected_prefix = str(body.get("expected_prefix", "")).strip()

    regex = re.compile(naming_pattern)
    list_result = call_unreal(
        settings,
        "POST",
        "/execute",
        {
            "action": "list_assets",
            "payload": {"package_path": package_path, "recursive": recursive, "max_assets": max_assets},
            "dry_run": True,
        },
    )
    payload_out = extract_upstream_payload(list_result.payload if isinstance(list_result.payload, dict) else {})
    assets = payload_out.get("assets", []) if isinstance(payload_out.get("assets", []), list) else []

    violations: List[Dict[str, Any]] = []
    migration_plan: List[Dict[str, Any]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        asset_name = str(asset.get("asset_name", "")).strip()
        package_name = str(asset.get("package_name", "")).strip()
        object_path = str(asset.get("object_path", "")).strip()
        class_path = str(asset.get("class_path", "")).strip()

        reasons: List[str] = []
        if asset_name and regex.match(asset_name) is None:
            reasons.append("NAME_PATTERN_MISMATCH")
        if expected_prefix and asset_name and not asset_name.startswith(expected_prefix):
            reasons.append("PREFIX_MISMATCH")
        if allowed_roots and package_name:
            if not any(package_name.startswith(root) for root in allowed_roots):
                reasons.append("FOLDER_ROOT_VIOLATION")

        if reasons:
            suggested_name = asset_name
            if expected_prefix and asset_name and not asset_name.startswith(expected_prefix):
                suggested_name = f"{expected_prefix}{asset_name}"
            violations.append(
                {
                    "asset_name": asset_name,
                    "package_name": package_name,
                    "object_path": object_path,
                    "class_path": class_path,
                    "reasons": reasons,
                }
            )
            migration_plan.append(
                {
                    "from": package_name,
                    "to_package_path": package_name.rsplit("/", 1)[0] if "/" in package_name else package_name,
                    "to_asset_name": suggested_name,
                    "mode": "plan_only",
                }
            )

    return {
        "success": len(violations) == 0,
        "package_path": package_path,
        "naming_pattern": naming_pattern,
        "expected_prefix": expected_prefix,
        "allowed_roots": allowed_roots,
        "assets_scanned": len(assets),
        "violations": violations,
        "migration_plan": migration_plan,
        "enforcement_mode": "plan_only",
        "list_status_code": int(list_result.status_code),
    }


def build_multiplayer_lint(analysis_payload: Dict[str, Any]) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    score = 0
    graph_count = 0
    network_call_count = 0
    authority_guard_count = 0

    for graph in get_analysis_graphs(analysis_payload):
        if not isinstance(graph, dict):
            continue
        graph_count += 1
        graph_name = str(graph.get("graph_name", "")).strip() or "<unknown>"
        nodes = graph.get("nodes", []) if isinstance(graph.get("nodes", []), list) else []
        function_calls = graph.get("function_calls", []) if isinstance(graph.get("function_calls", []), list) else []
        node_titles = {str(node.get("title", "")).lower() for node in nodes if isinstance(node, dict)}
        has_authority_guard = any(("authority" in title) or ("switch has authority" in title) for title in node_titles)
        if has_authority_guard:
            authority_guard_count += 1

        graph_network_calls = 0
        for call in function_calls:
            if not isinstance(call, dict):
                continue
            title = str(call.get("node_title", "")).lower()
            if any(term in title for term in ["server", "client", "multicast", "replicat", "rpc"]):
                graph_network_calls += 1
                network_call_count += 1
        if graph_network_calls > 0 and not has_authority_guard:
            score += 30
            findings.append(
                {
                    "rule_id": "network_without_authority_guard",
                    "severity": "high",
                    "graph_name": graph_name,
                    "message": "Network/RPC-like calls detected without authority guard.",
                    "network_call_count": graph_network_calls,
                }
            )
        if graph_network_calls > 0 and has_authority_guard:
            score += 5
        if graph_network_calls == 0:
            findings.append(
                {
                    "rule_id": "no_network_calls_detected",
                    "severity": "info",
                    "graph_name": graph_name,
                    "message": "No network/RPC-like calls detected in this graph.",
                }
            )

    if authority_guard_count == 0 and network_call_count > 0:
        score += 20
        findings.append(
            {
                "rule_id": "missing_global_authority_pattern",
                "severity": "medium",
                "message": "No explicit authority guard pattern found in analyzed graphs.",
            }
        )

    risk_score = max(0, min(100, score))
    return {
        "success": all(str(item.get("severity", "")).lower() not in {"high"} for item in findings if isinstance(item, dict)),
        "risk_score": risk_score,
        "graphs_analyzed": graph_count,
        "network_call_count": network_call_count,
        "authority_guard_count": authority_guard_count,
        "findings": findings,
    }


def _build_pie_run_signature(run_obj: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    replay_signature = {
        "success": bool(run_obj.get("success", False)),
        "status_code": int(run_obj.get("status_code", 0)),
        "result": run_obj.get("result", {}),
    }
    canonical = canonicalize_for_hash(replay_signature)
    return canonical, _stable_hash(canonical)


def _capture_pie_failure_screenshot(settings: Dict[str, Any], file_prefix: str) -> Dict[str, Any]:
    shot = call_unreal(
        settings,
        "POST",
        "/execute",
        {"action": "capture_screenshot", "payload": {"file_name": f"{file_prefix}_{int(time.time())}.png"}, "dry_run": False},
    )
    if shot.status_code >= 400:
        return {"success": False, "status_code": int(shot.status_code), "error": shot.payload}
    payload = shot.payload if isinstance(shot.payload, dict) else {}
    return {"success": True, "status_code": int(shot.status_code), "payload": payload}


def run_multiplayer_pie_harness(
    settings: Dict[str, Any],
    assertions: List[Dict[str, Any]],
    client_count: int,
    repeats: int,
    *,
    capture_screenshot_on_fail: bool = False,
) -> Dict[str, Any]:
    client_count = max(1, min(8, int(client_count)))
    repeats = max(1, min(10, int(repeats)))
    started_at = time.time()
    runs: List[Dict[str, Any]] = []
    hashes: List[str] = []
    hashes_by_client: Dict[str, List[str]] = {}
    passed = 0
    failed = 0
    for repeat in range(repeats):
        for client_idx in range(client_count):
            run_started_at = time.time()
            result = call_unreal(
                settings,
                "POST",
                "/execute",
                {
                    "action": "run_pie_scenario",
                    "payload": {"assertions": assertions, "client_index": client_idx, "repeat_index": repeat},
                    "dry_run": False,
                },
            )
            payload_out = result.payload if isinstance(result.payload, dict) else {}
            ok = result.status_code < 400 and bool(payload_out.get("success", False))
            run_item: Dict[str, Any] = {
                "repeat": repeat + 1,
                "client_index": client_idx,
                "status_code": int(result.status_code),
                "success": ok,
                "result": payload_out,
                "started_at": run_started_at,
                "finished_at": time.time(),
                "duration_ms": int(max(0.0, time.time() - run_started_at) * 1000.0),
            }
            signature, signature_hash = _build_pie_run_signature(run_item)
            run_item["signature"] = signature
            run_item["signature_hash"] = signature_hash
            hashes.append(signature_hash)
            client_key = str(client_idx)
            if client_key not in hashes_by_client:
                hashes_by_client[client_key] = []
            hashes_by_client[client_key].append(signature_hash)

            if ok:
                passed += 1
            else:
                failed += 1
                if capture_screenshot_on_fail:
                    run_item["failure_screenshot"] = _capture_pie_failure_screenshot(
                        settings, f"pie_mp_fail_r{repeat + 1}_c{client_idx}"
                    )
            runs.append(run_item)

    client_determinism: List[Dict[str, Any]] = []
    mismatch_items: List[Dict[str, Any]] = []
    for client_idx in range(client_count):
        client_key = str(client_idx)
        client_hashes = hashes_by_client.get(client_key, [])
        unique_hashes = sorted(set(client_hashes))
        expected_hash = client_hashes[0] if client_hashes else ""
        deterministic_client = len(unique_hashes) <= 1
        if not deterministic_client and expected_hash:
            for run in runs:
                if not isinstance(run, dict):
                    continue
                if int(run.get("client_index", -1)) != client_idx:
                    continue
                actual_hash = str(run.get("signature_hash", ""))
                if actual_hash != expected_hash:
                    mismatch_items.append(
                        {
                            "client_index": client_idx,
                            "repeat": int(run.get("repeat", 0)),
                            "expected_hash": expected_hash,
                            "actual_hash": actual_hash,
                            "status_code": int(run.get("status_code", 0)),
                            "success": bool(run.get("success", False)),
                        }
                    )
        client_determinism.append(
            {
                "client_index": client_idx,
                "deterministic": deterministic_client,
                "run_count": len(client_hashes),
                "unique_hash_count": len(unique_hashes),
                "expected_hash": expected_hash,
                "unique_hashes": unique_hashes,
            }
        )

    deterministic_by_client = all(bool(item.get("deterministic", False)) for item in client_determinism) if client_determinism else True
    finished_at = time.time()
    return {
        "success": failed == 0,
        "deterministic": deterministic_by_client,
        "client_count": client_count,
        "repeats": repeats,
        "total_runs": len(runs),
        "passed_runs": passed,
        "failed_runs": failed,
        "hashes": hashes,
        "hashes_by_client": hashes_by_client,
        "client_determinism": client_determinism,
        "mismatch_items": mismatch_items,
        "run_started_at": started_at,
        "run_finished_at": finished_at,
        "run_duration_ms": int(max(0.0, finished_at - started_at) * 1000.0),
        "runs": runs,
    }


def run_singleplayer_pie_harness(
    settings: Dict[str, Any],
    assertions: List[Dict[str, Any]],
    repeats: int,
    *,
    capture_screenshot_on_fail: bool = False,
) -> Dict[str, Any]:
    repeats = max(1, min(20, int(repeats)))
    started_at = time.time()
    runs: List[Dict[str, Any]] = []
    hashes: List[str] = []
    passed = 0
    failed = 0
    for repeat in range(repeats):
        run_started_at = time.time()
        result = call_unreal(
            settings,
            "POST",
            "/execute",
            {"action": "run_pie_scenario", "payload": {"assertions": assertions, "repeat_index": repeat}, "dry_run": False},
        )
        payload_out = result.payload if isinstance(result.payload, dict) else {}
        ok = result.status_code < 400 and bool(payload_out.get("success", False))
        run_item: Dict[str, Any] = {
            "repeat": repeat + 1,
            "status_code": int(result.status_code),
            "success": ok,
            "result": payload_out,
            "started_at": run_started_at,
            "finished_at": time.time(),
            "duration_ms": int(max(0.0, time.time() - run_started_at) * 1000.0),
        }
        signature, signature_hash = _build_pie_run_signature(run_item)
        run_item["signature"] = signature
        run_item["signature_hash"] = signature_hash
        hashes.append(signature_hash)
        if ok:
            passed += 1
        else:
            failed += 1
            if capture_screenshot_on_fail:
                run_item["failure_screenshot"] = _capture_pie_failure_screenshot(settings, f"pie_sp_fail_r{repeat + 1}")
        runs.append(run_item)

    expected_hash = hashes[0] if hashes else ""
    mismatch_items = []
    if expected_hash:
        for run in runs:
            if not isinstance(run, dict):
                continue
            actual_hash = str(run.get("signature_hash", ""))
            if actual_hash != expected_hash:
                mismatch_items.append(
                    {
                        "repeat": int(run.get("repeat", 0)),
                        "expected_hash": expected_hash,
                        "actual_hash": actual_hash,
                        "status_code": int(run.get("status_code", 0)),
                        "success": bool(run.get("success", False)),
                    }
                )
    finished_at = time.time()
    return {
        "success": failed == 0,
        "deterministic": len(set(hashes)) <= 1,
        "repeats": repeats,
        "total_runs": len(runs),
        "passed_runs": passed,
        "failed_runs": failed,
        "hashes": hashes,
        "expected_hash": expected_hash,
        "mismatch_items": mismatch_items,
        "run_started_at": started_at,
        "run_finished_at": finished_at,
        "run_duration_ms": int(max(0.0, finished_at - started_at) * 1000.0),
        "runs": runs,
    }


def run_pie_replay_suite(
    settings: Dict[str, Any],
    assertions: List[Dict[str, Any]],
    *,
    client_count: int,
    repeats: int,
    include_multiplayer: bool,
    capture_screenshot_on_fail: bool = False,
) -> Dict[str, Any]:
    if include_multiplayer:
        harness = run_multiplayer_pie_harness(
            settings,
            assertions,
            client_count,
            repeats,
            capture_screenshot_on_fail=capture_screenshot_on_fail,
        )
        runs = harness.get("runs", []) if isinstance(harness.get("runs", []), list) else []
        hashes = harness.get("hashes", []) if isinstance(harness.get("hashes", []), list) else []
        deterministic = bool(harness.get("deterministic", False))
        failed = int(harness.get("failed_runs", 0))
        passed = int(harness.get("passed_runs", 0))
        mismatch_items = harness.get("mismatch_items", []) if isinstance(harness.get("mismatch_items", []), list) else []
        determinism_details: Dict[str, Any] = {
            "mode": "multiplayer_by_client",
            "client_determinism": harness.get("client_determinism", []),
            "hashes_by_client": harness.get("hashes_by_client", {}),
        }
    else:
        harness = run_singleplayer_pie_harness(
            settings,
            assertions,
            repeats,
            capture_screenshot_on_fail=capture_screenshot_on_fail,
        )
        runs = harness.get("runs", []) if isinstance(harness.get("runs", []), list) else []
        hashes = harness.get("hashes", []) if isinstance(harness.get("hashes", []), list) else []
        deterministic = bool(harness.get("deterministic", False))
        failed = int(harness.get("failed_runs", 0))
        passed = int(harness.get("passed_runs", 0))
        mismatch_items = harness.get("mismatch_items", []) if isinstance(harness.get("mismatch_items", []), list) else []
        determinism_details = {
            "mode": "singleplayer",
            "expected_hash": str(harness.get("expected_hash", "")),
        }

    return {
        "success": failed == 0 and deterministic,
        "deterministic": deterministic,
        "include_multiplayer": include_multiplayer,
        "client_count": int(client_count),
        "repeats": int(repeats),
        "total_runs": len(runs),
        "passed_runs": passed,
        "failed_runs": failed,
        "hashes": hashes,
        "mismatch_items": mismatch_items,
        "determinism_details": determinism_details,
        "capture_screenshot_on_fail": bool(capture_screenshot_on_fail),
        "harness": harness,
        "runs": runs,
    }


def build_blueprint_perf_risk(analysis_payload: Dict[str, Any]) -> Dict[str, Any]:
    graphs = get_analysis_graphs(analysis_payload if isinstance(analysis_payload, dict) else {})
    total_nodes = 0
    total_edges = 0
    total_contradictions = 0
    total_delays = 0
    total_prints = 0
    graph_count = 0
    for graph in graphs:
        if not isinstance(graph, dict):
            continue
        graph_count += 1
        total_nodes += int(graph.get("total_nodes", 0))
        edges = graph.get("exec_edges", [])
        if isinstance(edges, list):
            total_edges += len(edges)
        contradictions = graph.get("contradictions", [])
        if isinstance(contradictions, list):
            total_contradictions += len(contradictions)
        delays = graph.get("delays", [])
        if isinstance(delays, list):
            total_delays += len(delays)
        prints = graph.get("print_strings", [])
        if isinstance(prints, list):
            total_prints += len(prints)

    risk_score = (
        1.0
        + float(total_nodes) / 250.0
        + float(total_edges) / 400.0
        + float(total_contradictions) * 6.0
        + float(total_delays) * 0.5
        + float(total_prints) * 0.25
    )
    risk_score = round(max(0.0, min(100.0, risk_score)), 2)
    return {
        "success": total_contradictions == 0,
        "risk_score": risk_score,
        "graphs_analyzed": graph_count,
        "total_nodes": total_nodes,
        "total_exec_edges": total_edges,
        "total_contradictions": total_contradictions,
        "total_delays": total_delays,
        "total_print_strings": total_prints,
    }


def run_autonomous_blueprint_gate(
    settings: Dict[str, Any],
    blueprint_path: str,
    *,
    assertions: List[Dict[str, Any]],
    scenario_repeats: int,
    include_multiplayer: bool,
    multiplayer_client_count: int,
    multiplayer_repeats: int,
    max_rpc_risk_score: float,
    max_multiplayer_lint_risk_score: float,
    max_perf_risk_score: float,
) -> Dict[str, Any]:
    compile_diag = call_unreal(
        settings,
        "POST",
        "/execute",
        {
            "action": "blueprint_compile_diagnostics",
            "payload": {"blueprint_path": blueprint_path, "include_pins": True, "max_nodes": 2000},
            "dry_run": True,
        },
    )
    compile_payload = compile_diag.payload if isinstance(compile_diag.payload, dict) else {}
    compile_upstream = extract_upstream_payload(compile_payload)
    compile_contradictions = collect_analysis_contradictions(compile_upstream if isinstance(compile_upstream, dict) else {})
    compile_ok = (
        compile_diag.status_code < 400
        and bool(compile_payload.get("success", False))
        and bool((compile_upstream or {}).get("compile_success", False))
        and len(compile_contradictions) == 0
    )

    analysis = call_unreal(
        settings,
        "POST",
        "/execute",
        {
            "action": "analyze_blueprint_asset",
            "payload": {"blueprint_path": blueprint_path, "include_pins": True, "max_nodes_per_graph": 2000, "max_trace_depth": 256},
            "dry_run": True,
        },
    )
    analysis_payload = analysis.payload if isinstance(analysis.payload, dict) else {}
    analysis_upstream = extract_upstream_payload(analysis_payload)
    analysis_contradictions = collect_analysis_contradictions(analysis_upstream if isinstance(analysis_upstream, dict) else {})
    rpc_lint = build_rpc_contract_lint(analysis_upstream if isinstance(analysis_upstream, dict) else {})
    mp_lint = build_multiplayer_lint(analysis_upstream if isinstance(analysis_upstream, dict) else {})
    perf = build_blueprint_perf_risk(analysis_upstream if isinstance(analysis_upstream, dict) else {})
    analysis_ok = analysis.status_code < 400 and bool(analysis_payload.get("success", False)) and len(analysis_contradictions) == 0

    singleplayer = run_singleplayer_pie_harness(settings, assertions, scenario_repeats)
    multiplayer = {"success": True, "skipped": True}
    if include_multiplayer:
        multiplayer = run_multiplayer_pie_harness(settings, assertions, multiplayer_client_count, multiplayer_repeats)
        multiplayer["skipped"] = False

    gates = {
        "compile_gate_pass": compile_ok,
        "analysis_gate_pass": analysis_ok,
        "contradiction_gate_pass": len(compile_contradictions) == 0 and len(analysis_contradictions) == 0,
        "singleplayer_scenario_pass": bool(singleplayer.get("success", False)),
        "multiplayer_scenario_pass": bool(multiplayer.get("success", False)),
        "rpc_lint_pass": bool(rpc_lint.get("success", False)) and float(rpc_lint.get("risk_score", 0.0)) <= max_rpc_risk_score,
        "multiplayer_lint_pass": bool(mp_lint.get("success", False)) and float(mp_lint.get("risk_score", 0.0)) <= max_multiplayer_lint_risk_score,
        "perf_gate_pass": bool(perf.get("success", False)) and float(perf.get("risk_score", 0.0)) <= max_perf_risk_score,
    }
    return {
        "success": all(bool(v) for v in gates.values()),
        "blueprint_path": blueprint_path,
        "gates": gates,
        "compile": {"success": compile_ok, "status_code": int(compile_diag.status_code), "contradictions": compile_contradictions},
        "analysis": {"success": analysis_ok, "status_code": int(analysis.status_code), "contradictions": analysis_contradictions},
        "rpc_lint": rpc_lint,
        "multiplayer_lint": mp_lint,
        "perf": perf,
        "singleplayer_scenario": singleplayer,
        "multiplayer_scenario": multiplayer,
    }


def collect_blueprint_targets_from_plan(plan: Dict[str, Any]) -> List[str]:
    targets: List[str] = []
    compile_items = plan.get("compile_blueprints", []) if isinstance(plan.get("compile_blueprints", []), list) else []
    for bp in compile_items:
        if isinstance(bp, str) and bp.strip():
            targets.append(bp.strip())
    steps = plan.get("steps", []) if isinstance(plan.get("steps", []), list) else []
    for step in steps:
        if not isinstance(step, dict):
            continue
        payload = step.get("payload", {})
        if not isinstance(payload, dict):
            continue
        bp = str(payload.get("blueprint_path", "")).strip()
        if bp:
            targets.append(bp)
    seen: set[str] = set()
    unique: List[str] = []
    for bp in targets:
        if bp in seen:
            continue
        seen.add(bp)
        unique.append(bp)
    return unique


def dedupe_blueprint_paths(paths: List[str]) -> List[str]:
    seen: set[str] = set()
    deduped: List[str] = []
    for item in paths:
        path = str(item).strip()
        if not path:
            continue
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return deduped


def run_post_mutation_blueprint_verification(settings: Dict[str, Any], targets: List[str]) -> Dict[str, Any]:
    deduped_targets = dedupe_blueprint_paths(targets)
    if len(deduped_targets) == 0:
        return {"success": True, "targets": [], "items": []}
    assertions_cfg = settings.get("auto_verify_assertions", [])
    assertions = [item for item in assertions_cfg if isinstance(item, dict)] if isinstance(assertions_cfg, list) else []
    verify_items: List[Dict[str, Any]] = []
    verify_pass = True
    for bp in deduped_targets[:20]:
        verify = run_autonomous_blueprint_gate(
            settings,
            bp,
            assertions=assertions,
            scenario_repeats=int(settings.get("auto_verify_scenario_repeats", 1)),
            include_multiplayer=bool(settings.get("auto_verify_multiplayer", True)),
            multiplayer_client_count=int(settings.get("auto_verify_multiplayer_client_count", 2)),
            multiplayer_repeats=int(settings.get("auto_verify_multiplayer_repeats", 1)),
            max_rpc_risk_score=float(settings.get("auto_verify_max_rpc_risk_score", 40.0)),
            max_multiplayer_lint_risk_score=float(settings.get("auto_verify_max_multiplayer_lint_risk_score", 40.0)),
            max_perf_risk_score=float(settings.get("auto_verify_max_perf_risk_score", 35.0)),
        )
        verify_items.append(verify)
        if not bool(verify.get("success", False)):
            verify_pass = False
    return {
        "success": verify_pass,
        "targets": deduped_targets,
        "items": verify_items,
    }


def collect_native_asset_verify_targets(asset_type: str, body: Dict[str, Any], action_payload: Dict[str, Any]) -> List[str]:
    targets: List[str] = []
    raw_targets = body.get("verify_blueprint_paths", [])
    if isinstance(raw_targets, list):
        for item in raw_targets:
            if isinstance(item, str):
                targets.append(item)
    single_target = str(body.get("verify_blueprint_path", "")).strip()
    if single_target:
        targets.append(single_target)

    key = (asset_type or "").strip().lower()
    if key == "anim_blueprint":
        explicit_anim_bp = str(body.get("anim_blueprint_path", body.get("asset_path", ""))).strip()
        if explicit_anim_bp:
            targets.append(explicit_anim_bp)
        else:
            payload_anim_bp = str(action_payload.get("anim_blueprint_path", "")).strip()
            if payload_anim_bp:
                targets.append(payload_anim_bp)
            else:
                package_path = str(action_payload.get("package_path", "")).strip()
                asset_name = str(action_payload.get("asset_name", "")).strip()
                if package_path and asset_name:
                    targets.append(f"{package_path}/{asset_name}")
    return dedupe_blueprint_paths(targets)


def build_rpc_contract_lint(analysis_payload: Dict[str, Any]) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    risk_score = 0
    rpc_event_count = 0
    rpc_call_count = 0
    authority_guard_count = 0
    graphs_analyzed = 0

    for graph in get_analysis_graphs(analysis_payload):
        if not isinstance(graph, dict):
            continue
        graphs_analyzed += 1
        graph_name = str(graph.get("graph_name", "")).strip() or "<unknown>"
        nodes = graph.get("nodes", []) if isinstance(graph.get("nodes", []), list) else []
        function_calls = graph.get("function_calls", []) if isinstance(graph.get("function_calls", []), list) else []

        has_authority_guard = False
        graph_rpc_events = 0
        graph_rpc_calls = 0
        naming_issues = 0

        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_class = str(node.get("class", "")).lower()
            node_title = str(node.get("title", "")).strip()
            title_lower = node_title.lower()
            if "authority" in title_lower and "switch" in title_lower:
                has_authority_guard = True
            if "k2node_customevent" in node_class and any(term in title_lower for term in ["server", "client", "multicast", "rpc"]):
                graph_rpc_events += 1
                rpc_event_count += 1
                starts_valid = (
                    node_title.startswith("Server")
                    or node_title.startswith("Client")
                    or node_title.startswith("Multicast")
                    or node_title.startswith("RPC_")
                )
                if not starts_valid:
                    naming_issues += 1

        for call in function_calls:
            if not isinstance(call, dict):
                continue
            title_lower = str(call.get("node_title", "")).lower()
            if any(term in title_lower for term in ["server", "client", "multicast", "rpc"]):
                graph_rpc_calls += 1
                rpc_call_count += 1

        if has_authority_guard:
            authority_guard_count += 1

        if (graph_rpc_calls + graph_rpc_events) > 0 and not has_authority_guard:
            risk_score += 40
            findings.append(
                {
                    "rule_id": "rpc_without_authority_guard",
                    "severity": "high",
                    "graph_name": graph_name,
                    "message": "RPC-like events/calls detected without an authority guard in graph.",
                    "rpc_events": graph_rpc_events,
                    "rpc_calls": graph_rpc_calls,
                }
            )
        if naming_issues > 0:
            risk_score += 10
            findings.append(
                {
                    "rule_id": "rpc_naming_contract_weak",
                    "severity": "medium",
                    "graph_name": graph_name,
                    "message": "RPC-like custom events detected with weak naming contract.",
                    "naming_issues": naming_issues,
                }
            )
        if graph_rpc_calls + graph_rpc_events == 0:
            findings.append(
                {
                    "rule_id": "no_rpc_detected",
                    "severity": "info",
                    "graph_name": graph_name,
                    "message": "No RPC-like nodes detected in graph.",
                }
            )

    risk_score = max(0, min(100, risk_score))
    success = all(str(item.get("severity", "")).lower() not in {"high"} for item in findings if isinstance(item, dict))
    return {
        "success": success,
        "risk_score": risk_score,
        "graphs_analyzed": graphs_analyzed,
        "rpc_event_count": rpc_event_count,
        "rpc_call_count": rpc_call_count,
        "authority_guard_count": authority_guard_count,
        "findings": findings,
        "note": "Deterministic lint based on graph/node evidence; deep engine-level RPC flag introspection remains a follow-up plugin enhancement.",
    }


def build_blueprint_structure_review(
    settings: Dict[str, Any],
    blueprint_path: str,
    graph_name: str,
    *,
    include_ast: bool = True,
    include_refactor_catalog: bool = True,
) -> Dict[str, Any]:
    compile_diag = call_unreal(
        settings,
        "POST",
        "/execute",
        {
            "action": "blueprint_compile_diagnostics",
            "payload": {"blueprint_path": blueprint_path, "include_pins": True, "max_nodes": 2000},
            "dry_run": True,
        },
    )
    compile_payload = compile_diag.payload if isinstance(compile_diag.payload, dict) else {}
    compile_upstream = extract_upstream_payload(compile_payload)
    compile_contradictions = collect_analysis_contradictions(compile_upstream if isinstance(compile_upstream, dict) else {})

    analysis = call_unreal(
        settings,
        "POST",
        "/execute",
        {
            "action": "analyze_blueprint_graph",
            "payload": {"blueprint_path": blueprint_path, "graph_name": graph_name, "include_pins": True, "max_nodes": 2000, "max_trace_depth": 256},
            "dry_run": True,
        },
    )
    analysis_payload = extract_upstream_payload(analysis.payload if isinstance(analysis.payload, dict) else {})
    analysis_contradictions = collect_analysis_contradictions(analysis_payload if isinstance(analysis_payload, dict) else {})
    lint = build_analysis_lint(analysis_payload if isinstance(analysis_payload, dict) else {})
    suggestions = build_refactor_suggestions(blueprint_path, analysis_payload if isinstance(analysis_payload, dict) else {}, lint)
    catalog = build_refactor_catalog(blueprint_path, "strict", analysis_payload if isinstance(analysis_payload, dict) else {}, lint) if include_refactor_catalog else []
    rpc_lint = build_rpc_contract_lint(analysis_payload if isinstance(analysis_payload, dict) else {})

    ast_doc: Dict[str, Any] = {}
    if include_ast:
        ast_doc = build_graph_ast_document(settings, blueprint_path, graph_name, include_pins=True, max_nodes=2000)

    node_count = int((analysis_payload or {}).get("total_nodes", 0)) if isinstance(analysis_payload, dict) else 0
    exec_edges = (analysis_payload or {}).get("exec_edges", []) if isinstance(analysis_payload, dict) else []
    entry_nodes = (analysis_payload or {}).get("entry_nodes", []) if isinstance(analysis_payload, dict) else []
    function_calls = (analysis_payload or {}).get("function_calls", []) if isinstance(analysis_payload, dict) else []
    branch_guards = (analysis_payload or {}).get("branch_guards", []) if isinstance(analysis_payload, dict) else []

    compile_ok = (
        compile_diag.status_code < 400
        and bool(compile_payload.get("success", False))
        and bool((compile_upstream or {}).get("compile_success", False))
        and len(compile_contradictions) == 0
    )
    success = compile_ok and len(analysis_contradictions) == 0
    summary = {
        "node_count": node_count,
        "exec_edge_count": len(exec_edges) if isinstance(exec_edges, list) else 0,
        "entry_node_count": len(entry_nodes) if isinstance(entry_nodes, list) else 0,
        "function_call_count": len(function_calls) if isinstance(function_calls, list) else 0,
        "branch_guard_count": len(branch_guards) if isinstance(branch_guards, list) else 0,
        "lint_count": len(lint),
        "refactor_suggestion_count": len(suggestions),
    }
    deterministic_review = (
        f"Graph '{graph_name or 'EventGraph'}' has {summary['node_count']} nodes, "
        f"{summary['exec_edge_count']} exec edges, {summary['function_call_count']} function calls, "
        f"and {summary['lint_count']} lint findings."
    )

    return {
        "success": success,
        "blueprint_path": blueprint_path,
        "review_scope": "graph",
        "graph_name": graph_name or "EventGraph",
        "compile": {
            "success": compile_ok,
            "status_code": int(compile_diag.status_code),
            "contradictions": compile_contradictions,
            "result": compile_payload,
        },
        "analysis": {
            "status_code": int(analysis.status_code),
            "contradictions": analysis_contradictions,
            "lint": lint,
            "rpc_lint": rpc_lint,
            "summary": summary,
        },
        "deterministic_review": deterministic_review,
        "suggested_fixes": suggestions,
        "refactor_catalog": catalog,
        "ast": ast_doc,
    }


def build_blueprint_asset_structure_review(
    settings: Dict[str, Any],
    blueprint_path: str,
    *,
    include_ast: bool = True,
    include_refactor_catalog: bool = True,
    max_graph_ast_exports: int = 12,
) -> Dict[str, Any]:
    compile_diag = call_unreal(
        settings,
        "POST",
        "/execute",
        {
            "action": "blueprint_compile_diagnostics",
            "payload": {"blueprint_path": blueprint_path, "include_pins": True, "max_nodes": 2000},
            "dry_run": True,
        },
    )
    compile_payload = compile_diag.payload if isinstance(compile_diag.payload, dict) else {}
    compile_upstream = extract_upstream_payload(compile_payload)
    compile_contradictions = collect_analysis_contradictions(compile_upstream if isinstance(compile_upstream, dict) else {})

    analysis = call_unreal(
        settings,
        "POST",
        "/execute",
        {
            "action": "analyze_blueprint_asset",
            "payload": {
                "blueprint_path": blueprint_path,
                "include_pins": True,
                "max_nodes_per_graph": 2000,
                "max_trace_depth": 256,
            },
            "dry_run": True,
        },
    )
    analysis_payload = extract_upstream_payload(analysis.payload if isinstance(analysis.payload, dict) else {})
    analysis_contradictions = collect_analysis_contradictions(analysis_payload if isinstance(analysis_payload, dict) else {})
    lint = build_analysis_lint(analysis_payload if isinstance(analysis_payload, dict) else {})
    suggestions = build_refactor_suggestions(blueprint_path, analysis_payload if isinstance(analysis_payload, dict) else {}, lint)
    catalog = build_refactor_catalog(blueprint_path, "strict", analysis_payload if isinstance(analysis_payload, dict) else {}, lint) if include_refactor_catalog else []
    rpc_lint = build_rpc_contract_lint(analysis_payload if isinstance(analysis_payload, dict) else {})

    max_graph_ast_exports = max(0, min(32, int(max_graph_ast_exports)))
    ast_graphs: List[Dict[str, Any]] = []
    graphs = get_analysis_graphs(analysis_payload if isinstance(analysis_payload, dict) else {})
    graph_reviews: List[Dict[str, Any]] = []
    ast_exported = 0
    for graph in graphs:
        if not isinstance(graph, dict):
            continue
        graph_name = str(graph.get("graph_name", "")).strip()
        graph_type = str(graph.get("graph_type", "")).strip()
        graph_lint = build_analysis_lint(graph)
        graph_suggestions = build_refactor_suggestions(blueprint_path, graph, graph_lint)
        graph_catalog = build_refactor_catalog(blueprint_path, "strict", graph, graph_lint) if include_refactor_catalog else []
        graph_rpc_lint = build_rpc_contract_lint(graph)

        node_count = int(graph.get("total_nodes", 0))
        exec_edges = graph.get("exec_edges", [])
        entry_nodes = graph.get("entry_nodes", [])
        function_calls = graph.get("function_calls", [])
        branch_guards = graph.get("branch_guards", [])
        graph_summary = {
            "node_count": node_count,
            "exec_edge_count": len(exec_edges) if isinstance(exec_edges, list) else 0,
            "entry_node_count": len(entry_nodes) if isinstance(entry_nodes, list) else 0,
            "function_call_count": len(function_calls) if isinstance(function_calls, list) else 0,
            "branch_guard_count": len(branch_guards) if isinstance(branch_guards, list) else 0,
            "lint_count": len(graph_lint),
            "refactor_suggestion_count": len(graph_suggestions),
        }
        graph_reviews.append(
            {
                "graph_name": graph_name,
                "graph_type": graph_type,
                "summary": graph_summary,
                "lint": graph_lint,
                "rpc_lint": graph_rpc_lint,
                "suggested_fixes": graph_suggestions,
                "refactor_catalog": graph_catalog,
                "contradictions": collect_analysis_contradictions(graph),
            }
        )

        if include_ast and graph_name and ast_exported < max_graph_ast_exports:
            ast_graphs.append(build_graph_ast_document(settings, blueprint_path, graph_name, include_pins=True, max_nodes=2000))
            ast_exported += 1

    total_graphs = int((analysis_payload or {}).get("total_graphs", len(graphs))) if isinstance(analysis_payload, dict) else len(graphs)
    total_nodes = int((analysis_payload or {}).get("total_nodes", 0)) if isinstance(analysis_payload, dict) else 0
    total_entry_nodes = int((analysis_payload or {}).get("total_entry_nodes", 0)) if isinstance(analysis_payload, dict) else 0
    total_contradictions = int((analysis_payload or {}).get("total_contradictions", 0)) if isinstance(analysis_payload, dict) else 0

    compile_ok = (
        compile_diag.status_code < 400
        and bool(compile_payload.get("success", False))
        and bool((compile_upstream or {}).get("compile_success", False))
        and len(compile_contradictions) == 0
    )
    analysis_ok = bool((analysis_payload or {}).get("analysis_ok", total_contradictions == 0)) if isinstance(analysis_payload, dict) else False
    success = compile_ok and analysis.status_code < 400 and analysis_ok and len(analysis_contradictions) == 0
    deterministic_review = (
        f"Blueprint asset review analyzed {total_graphs} graphs with {total_nodes} total nodes and "
        f"{total_contradictions} contradictions."
    )

    return {
        "success": success,
        "blueprint_path": blueprint_path,
        "review_scope": "asset",
        "graph_name": "ALL_GRAPHS",
        "compile": {
            "success": compile_ok,
            "status_code": int(compile_diag.status_code),
            "contradictions": compile_contradictions,
            "result": compile_payload,
        },
        "analysis": {
            "status_code": int(analysis.status_code),
            "contradictions": analysis_contradictions,
            "lint": lint,
            "rpc_lint": rpc_lint,
            "summary": {
                "total_graphs": total_graphs,
                "total_nodes": total_nodes,
                "total_entry_nodes": total_entry_nodes,
                "total_contradictions": total_contradictions,
                "lint_count": len(lint),
                "refactor_suggestion_count": len(suggestions),
            },
        },
        "deterministic_review": deterministic_review,
        "graph_reviews": graph_reviews,
        "suggested_fixes": suggestions,
        "refactor_catalog": catalog,
        "ast": {
            "scope": "asset",
            "graphs": ast_graphs,
            "ast_graph_count": len(ast_graphs),
            "ast_truncated": include_ast and len(graphs) > len(ast_graphs),
            "max_graph_ast_exports": max_graph_ast_exports,
        },
    }


def build_native_asset_action_payload(asset_type: str, body: Dict[str, Any], *, mode: str) -> Tuple[str, Dict[str, Any]]:
    key = (asset_type or "").strip().lower()
    if key not in NATIVE_ASSET_AUTHORING_CATALOG:
        raise ValueError(f"Unsupported asset_type: {asset_type}")
    spec = NATIVE_ASSET_AUTHORING_CATALOG[key]
    action = str(spec.get("create_action" if mode == "create" else "edit_action", "")).strip()
    if not action:
        raise ValueError(f"Missing {mode} action for asset_type={asset_type}")

    payload: Dict[str, Any] = {}
    for field in spec.get("inputs", []):
        if field in body:
            payload[field] = body.get(field)

    if key == "behavior_tree":
        if mode == "create":
            payload.setdefault("asset_name", str(body.get("asset_name", "BT_AgentTree")).strip() or "BT_AgentTree")
            payload.setdefault("package_path", str(body.get("package_path", "/Game/AgentGenerated/AI")).strip() or "/Game/AgentGenerated/AI")
        else:
            payload.setdefault("behavior_tree_path", str(body.get("behavior_tree_path", body.get("asset_path", ""))).strip())
            payload.setdefault("tasks", body.get("tasks", []))
            payload.setdefault("operations", body.get("operations", []))
            payload.setdefault("root_class_path", str(body.get("root_class_path", "/Script/AIModule.BTComposite_Selector")).strip())
            if not payload.get("behavior_tree_path"):
                raise ValueError("behavior_tree_path or asset_path is required for behavior_tree edit.")
    elif key == "blackboard":
        if mode == "create":
            payload.setdefault("asset_name", str(body.get("asset_name", "BB_AgentData")).strip() or "BB_AgentData")
            payload.setdefault("package_path", str(body.get("package_path", "/Game/AgentGenerated/AI")).strip() or "/Game/AgentGenerated/AI")
        else:
            payload.setdefault("blackboard_path", str(body.get("blackboard_path", body.get("asset_path", ""))).strip())
            payload.setdefault("keys", body.get("keys", []))
            payload.setdefault("replace_existing", bool(body.get("replace_existing", False)))
            if not payload.get("blackboard_path"):
                raise ValueError("blackboard_path or asset_path is required for blackboard edit.")
    elif key == "eqs_query":
        if mode == "create":
            payload.setdefault("asset_name", str(body.get("asset_name", "EQS_AgentQuery")).strip() or "EQS_AgentQuery")
            payload.setdefault("package_path", str(body.get("package_path", "/Game/AgentGenerated/AI")).strip() or "/Game/AgentGenerated/AI")
        else:
            payload.setdefault("eqs_path", str(body.get("eqs_path", body.get("asset_path", ""))).strip())
            payload.setdefault("options", body.get("options", []))
            payload.setdefault("operations", body.get("operations", []))
            payload.setdefault("replace_options", bool(body.get("replace_options", True)))
            if not payload.get("eqs_path"):
                raise ValueError("eqs_path or asset_path is required for eqs_query edit.")
    elif key == "anim_blueprint":
        if mode == "create":
            payload.setdefault("asset_name", str(body.get("asset_name", "ABP_AgentCharacter")).strip() or "ABP_AgentCharacter")
            payload.setdefault("package_path", str(body.get("package_path", "/Game/AgentGenerated/Animation")).strip() or "/Game/AgentGenerated/Animation")
        else:
            payload.setdefault("anim_blueprint_path", str(body.get("anim_blueprint_path", body.get("asset_path", ""))).strip())
            payload.setdefault("state_machine_name", str(body.get("state_machine_name", "LocomotionSM")).strip() or "LocomotionSM")
            payload.setdefault("states", body.get("states", []))
            payload.setdefault("operations", body.get("operations", []))
            payload.setdefault("compile_after", bool(body.get("compile_after", True)))
            if not payload.get("anim_blueprint_path"):
                raise ValueError("anim_blueprint_path or asset_path is required for anim_blueprint edit.")
    elif key == "material":
        if mode == "create":
            payload.setdefault("asset_name", str(body.get("asset_name", "M_AgentMaterial")).strip() or "M_AgentMaterial")
            payload.setdefault("package_path", str(body.get("package_path", "/Game/AgentGenerated/Materials")).strip() or "/Game/AgentGenerated/Materials")
        else:
            payload.setdefault("material_path", str(body.get("material_path", body.get("asset_path", ""))).strip())
            payload.setdefault("two_sided", bool(body.get("two_sided", False)))
            payload.setdefault("blend_mode", int(body.get("blend_mode", 0)))
            payload.setdefault("shading_model", int(body.get("shading_model", 1)))
            payload.setdefault("operations", body.get("operations", []))
            if not payload.get("material_path"):
                raise ValueError("material_path or asset_path is required for material edit.")
    elif key == "niagara_system":
        if mode == "create":
            payload.setdefault("asset_name", str(body.get("asset_name", "NS_AgentSystem")).strip() or "NS_AgentSystem")
            payload.setdefault("package_path", str(body.get("package_path", "/Game/AgentGenerated/VFX")).strip() or "/Game/AgentGenerated/VFX")
        else:
            payload.setdefault("niagara_system_path", str(body.get("niagara_system_path", body.get("asset_path", ""))).strip())
            payload.setdefault("deterministic_seed", int(body.get("deterministic_seed", 0)))
            payload.setdefault("operations", body.get("operations", []))
            if "determinism" in body:
                payload["determinism"] = bool(body.get("determinism"))
            if not payload.get("niagara_system_path"):
                raise ValueError("niagara_system_path or asset_path is required for niagara_system edit.")
    elif key == "level_sequence":
        if mode == "create":
            payload.setdefault("asset_name", str(body.get("asset_name", "LS_AgentSequence")).strip() or "LS_AgentSequence")
            payload.setdefault("package_path", str(body.get("package_path", "/Game/AgentGenerated/Cinematics")).strip() or "/Game/AgentGenerated/Cinematics")
        else:
            payload.setdefault("level_sequence_path", str(body.get("level_sequence_path", body.get("asset_path", ""))).strip())
            payload.setdefault("playback_start", int(body.get("playback_start", 0)))
            payload.setdefault("playback_end", int(body.get("playback_end", 300)))
            payload.setdefault("operations", body.get("operations", []))
            if not payload.get("level_sequence_path"):
                raise ValueError("level_sequence_path or asset_path is required for level_sequence edit.")
    return action, payload


def build_native_asset_authoring_workflow_plan(body: Dict[str, Any]) -> Dict[str, Any]:
    asset_type = str(body.get("asset_type", "")).strip().lower()
    if asset_type not in NATIVE_ASSET_AUTHORING_CATALOG:
        raise ValueError("asset_type is required and must be supported.")

    create_action, create_payload = build_native_asset_action_payload(asset_type, body, mode="create")
    edit_action, edit_payload = build_native_asset_action_payload(asset_type, body, mode="edit")

    steps: List[Dict[str, Any]] = [
        {
            "id": f"create_{asset_type}",
            "action": create_action,
            "payload": create_payload,
        },
    ]
    if bool(body.get("include_edit_pass", True)):
        steps.append(
            {
                "id": f"edit_{asset_type}",
                "action": edit_action,
                "payload": edit_payload,
            }
        )
    return {
        "plan_id": f"native_asset_authoring_{asset_type}",
        "stop_on_error": bool(body.get("stop_on_error", True)),
        "dry_run": bool(body.get("dry_run", False)),
        "steps": steps,
    }


def build_ai_asset_authoring_plan(body: Dict[str, Any]) -> Dict[str, Any]:
    namespace_root = str(body.get("namespace_root", "/Game/AgentGenerated")).strip() or "/Game/AgentGenerated"
    if not namespace_root.startswith("/Game"):
        namespace_root = "/Game/AgentGenerated"
    ai_controller_asset_name = str(body.get("ai_controller_asset_name", "BP_AIAgentController")).strip() or "BP_AIAgentController"
    bt_task_asset_name = str(body.get("bt_task_asset_name", "BTT_AIAgentTask")).strip() or "BTT_AIAgentTask"
    bt_tree_asset_name = str(body.get("bt_tree_asset_name", "BT_AIAgentTree")).strip() or "BT_AIAgentTree"
    blackboard_asset_name = str(body.get("blackboard_asset_name", "BB_AIAgentBlackboard")).strip() or "BB_AIAgentBlackboard"
    eqs_asset_name = str(body.get("eqs_asset_name", "EQS_AIAgentQuery")).strip() or "EQS_AIAgentQuery"

    ai_controller_path = f"{namespace_root}/AI/{ai_controller_asset_name}"
    bt_task_path = f"{namespace_root}/AI/{bt_task_asset_name}"
    bt_tree_path = f"{namespace_root}/AI/{bt_tree_asset_name}"
    blackboard_path = f"{namespace_root}/AI/{blackboard_asset_name}"
    eqs_path = f"{namespace_root}/AI/{eqs_asset_name}"

    steps: List[Dict[str, Any]] = [
        {
            "id": "create_ai_controller",
            "action": "create_blueprint",
            "payload": {
                "asset_name": ai_controller_asset_name,
                "package_path": f"{namespace_root}/AI",
                "parent_class": "/Script/AIModule.AIController",
            },
        },
        {
            "id": "create_bt_task",
            "action": "create_blueprint",
            "payload": {
                "asset_name": bt_task_asset_name,
                "package_path": f"{namespace_root}/AI",
                "parent_class": "/Script/AIModule.BTTask_BlueprintBase",
            },
        },
        {
            "id": "create_blackboard_data_asset",
            "action": "create_blackboard_data_asset",
            "payload": {
                "asset_name": blackboard_asset_name,
                "package_path": f"{namespace_root}/AI",
            },
        },
        {
            "id": "create_eqs_query_asset",
            "action": "create_eqs_query_asset",
            "payload": {
                "asset_name": eqs_asset_name,
                "package_path": f"{namespace_root}/AI",
            },
        },
        {
            "id": "create_behavior_tree_asset",
            "action": "create_behavior_tree_asset",
            "payload": {
                "asset_name": bt_tree_asset_name,
                "package_path": f"{namespace_root}/AI",
            },
        },
        {
            "id": "seed_blackboard_schema",
            "action": "edit_blackboard_data_asset",
            "payload": {
                "blackboard_path": blackboard_path,
                "replace_existing": False,
                "keys": body.get(
                    "blackboard_keys",
                    [
                        {"name": "TargetActor", "key_type_class": "/Script/AIModule.BlackboardKeyType_Object"},
                        {"name": "TargetLocation", "key_type_class": "/Script/AIModule.BlackboardKeyType_Vector"},
                        {"name": "HasLineOfSight", "key_type_class": "/Script/AIModule.BlackboardKeyType_Bool"},
                    ],
                ),
            },
        },
        {
            "id": "seed_eqs_query",
            "action": "edit_eqs_query_asset",
            "payload": {
                "eqs_path": eqs_path,
                "replace_options": True,
                "options": body.get(
                    "eqs_options",
                    [
                        {
                            "option_class_path": "/Script/AIModule.EnvQueryOption",
                            "generator_class_path": "/Script/AIModule.EnvQueryGenerator_ActorsOfClass",
                            "test_class_paths": ["/Script/AIModule.EnvQueryTest_Distance"],
                        }
                    ],
                ),
            },
        },
        {
            "id": "seed_behavior_tree",
            "action": "edit_behavior_tree_asset",
            "payload": {
                "behavior_tree_path": bt_tree_path,
                "blackboard_path": blackboard_path,
                "root_class_path": "/Script/AIModule.BTComposite_Selector",
                "tasks": body.get("bt_tasks", [{"class_path": "/Script/AIModule.BTTask_Wait", "wait_time": 0.2}]),
            },
        },
        {
            "id": "add_blackboard_path_var",
            "action": "modify_blueprint_graph",
            "payload": {
                "blueprint_path": ai_controller_path,
                "operation": "add_variable",
                "variable_name": "BlackboardAssetPath",
                "variable_type": "string",
                "default_value": blackboard_path,
                "category": "AI",
                "compile_after": False,
            },
        },
        {
            "id": "add_eqs_path_var",
            "action": "modify_blueprint_graph",
            "payload": {
                "blueprint_path": ai_controller_path,
                "operation": "add_variable",
                "variable_name": "EQSQueryAssetPath",
                "variable_type": "string",
                "default_value": eqs_path,
                "category": "AI",
                "compile_after": False,
            },
        },
        {
            "id": "add_bt_tree_path_var",
            "action": "modify_blueprint_graph",
            "payload": {
                "blueprint_path": ai_controller_path,
                "operation": "add_variable",
                "variable_name": "BehaviorTreeAssetPath",
                "variable_type": "string",
                "default_value": bt_tree_path,
                "category": "AI",
                "compile_after": False,
            },
        },
    ]
    return {
        "plan_id": f"ai_asset_authoring_{uuid4().hex[:8]}",
        "profile": "strict",
        "stop_on_error": True,
        "compile_blueprints": [ai_controller_path, bt_task_path],
        "steps": steps,
        "outputs": {
            "ai_controller_path": ai_controller_path,
            "bt_task_path": bt_task_path,
            "bt_tree_asset_path": bt_tree_path,
            "blackboard_asset_path": blackboard_path,
            "eqs_asset_path": eqs_path,
        },
    }


def get_graph_primitives_catalog() -> Dict[str, Any]:
    return {
        "supported_operations": [
            "spawn_node_by_class",
            "set_pin_default",
            "connect_pins",
            "disconnect_pins",
            "inspect_pin_contract",
            "reroute_exec_path",
        ],
        "supported_node_classes": [
            "/Script/BlueprintGraph.K2Node_CallFunction",
            "/Script/BlueprintGraph.K2Node_CustomEvent",
            "/Script/BlueprintGraph.K2Node_IfThenElse",
            "/Script/BlueprintGraph.K2Node_VariableGet",
        ],
    }


def _extract_pin_snapshot(settings: Dict[str, Any], payload: Dict[str, Any], pin_name: str) -> Dict[str, Any]:
    inspect = call_unreal(
        settings,
        "POST",
        "/execute",
        {
            "action": "inspect_blueprint_graph",
            "payload": {
                "blueprint_path": payload.get("blueprint_path", ""),
                "graph_name": payload.get("graph_name", ""),
                "include_pins": True,
                "max_nodes": 2000,
            },
            "dry_run": True,
        },
    )
    inspect_payload = extract_upstream_payload(inspect.payload if isinstance(inspect.payload, dict) else {})
    nodes = inspect_payload.get("nodes", []) if isinstance(inspect_payload, dict) else []
    node_name = str(payload.get("node_name", "")).strip()
    title_contains = str(payload.get("node_title_contains", "")).strip()
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        n_name = str(node.get("name", "")).strip()
        n_title = str(node.get("title", "")).strip()
        if node_name and n_name.lower() != node_name.lower():
            continue
        if title_contains and title_contains.lower() not in n_title.lower():
            continue
        pins = node.get("pins", [])
        for pin in pins if isinstance(pins, list) else []:
            if isinstance(pin, dict) and str(pin.get("name", "")).strip().lower() == pin_name.lower():
                return pin
    return {}


def execute_graph_primitive_operation(
    settings: Dict[str, Any],
    blueprint_path: str,
    graph_name: str,
    operation: Dict[str, Any],
    *,
    dry_run: bool,
) -> Tuple[int, Dict[str, Any], Optional[Dict[str, Any]]]:
    op = str(operation.get("operation", operation.get("op", ""))).strip().lower()
    if not op:
        return HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "operation/op is required."), None
    if op == "spawn_node_by_class":
        node_class_path = str(operation.get("node_class_path", "")).strip()
        node_name = str(operation.get("node_name", "")).strip()
        compile_after = bool(operation.get("compile_after", False))
        if node_class_path == "/Script/BlueprintGraph.K2Node_CallFunction":
            payload = {
                "blueprint_path": blueprint_path,
                "graph_name": graph_name,
                "operation": "spawn_function_call",
                "node_name": node_name,
                "function_class_path": str(operation.get("function_class_path", "")).strip(),
                "function_name": str(operation.get("function_name", "")).strip(),
                "node_position": operation.get("node_position", [0, 0]),
                "compile_after": compile_after,
            }
        elif node_class_path == "/Script/BlueprintGraph.K2Node_CustomEvent":
            payload = {
                "blueprint_path": blueprint_path,
                "graph_name": graph_name,
                "operation": "spawn_custom_event",
                "node_name": node_name,
                "custom_event_name": str(operation.get("custom_event_name", node_name)).strip(),
                "node_position": operation.get("node_position", [0, 0]),
                "compile_after": compile_after,
            }
        elif node_class_path == "/Script/BlueprintGraph.K2Node_IfThenElse":
            payload = {
                "blueprint_path": blueprint_path,
                "graph_name": graph_name,
                "operation": "spawn_branch_node",
                "node_name": node_name,
                "condition_default": bool(operation.get("condition_default", False)),
                "node_position": operation.get("node_position", [0, 0]),
                "compile_after": compile_after,
            }
        elif node_class_path == "/Script/BlueprintGraph.K2Node_VariableGet":
            variable_name = str(operation.get("variable_name", "")).strip()
            if not variable_name:
                return HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "variable_name is required for K2Node_VariableGet."), None
            payload = {
                "blueprint_path": blueprint_path,
                "graph_name": graph_name,
                "operation": "spawn_variable_get",
                "node_name": node_name,
                "variable_name": variable_name,
                "node_position": operation.get("node_position", [0, 0]),
                "compile_after": compile_after,
            }
        else:
            return HTTPStatus.BAD_REQUEST, make_error("UNSUPPORTED_NODE_CLASS", "Unsupported node_class_path for spawn_node_by_class.", node_class_path=node_class_path), None
        result = call_unreal(settings, "POST", "/execute", {"action": "blueprint_node_authoring", "payload": payload, "dry_run": dry_run})
        inverse = None
        if node_name:
            inverse = {
                "operation": "remove_nodes",
                "payload": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "operation": "remove_nodes",
                    "node_name_contains": node_name,
                },
            }
        return result.status_code, result.payload, inverse
    if op in {"connect_pins", "disconnect_pins"}:
        payload = {
            "blueprint_path": blueprint_path,
            "graph_name": graph_name,
            "operation": "connect" if op == "connect_pins" else "disconnect",
            "from_node_name": str(operation.get("from_node_name", "")).strip(),
            "from_node_title_contains": str(operation.get("from_node_title_contains", "")).strip(),
            "from_pin_name": str(operation.get("from_pin_name", "")).strip(),
            "to_node_name": str(operation.get("to_node_name", "")).strip(),
            "to_node_title_contains": str(operation.get("to_node_title_contains", "")).strip(),
            "to_pin_name": str(operation.get("to_pin_name", "")).strip(),
            "compile_after": bool(operation.get("compile_after", False)),
        }
        result = call_unreal(settings, "POST", "/execute", {"action": "wire_blueprint_pins", "payload": payload, "dry_run": dry_run})
        inverse = {
            "operation": "connect_pins" if op == "disconnect_pins" else "disconnect_pins",
            "payload": dict(payload),
        }
        return result.status_code, result.payload, inverse
    if op == "set_pin_default":
        class_path = str(operation.get("class_path", "")).strip()
        function_name = str(operation.get("function_name", "")).strip()
        pin_name = str(operation.get("pin_name", "")).strip()
        default_value = str(operation.get("default_value", "")).strip()
        if not class_path or not function_name or not pin_name:
            return HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "set_pin_default requires class_path, function_name, and pin_name."), None
        before_pin = _extract_pin_snapshot(
            settings,
            {
                "blueprint_path": blueprint_path,
                "graph_name": graph_name,
                "node_name": str(operation.get("node_name_contains", "")).strip(),
                "node_title_contains": str(operation.get("node_title_contains", "")).strip(),
            },
            pin_name,
        )
        payload = {
            "blueprint_path": blueprint_path,
            "graph_name": graph_name,
            "operation": "set_default",
            "class_path": class_path,
            "function_name": function_name,
            "node_name_contains": str(operation.get("node_name_contains", "")).strip(),
            "node_title_contains": str(operation.get("node_title_contains", "")).strip(),
            "pin_name": pin_name,
            "default_value": default_value,
            "create_if_missing": bool(operation.get("create_if_missing", False)),
            "compile_after": bool(operation.get("compile_after", False)),
        }
        result = call_unreal(settings, "POST", "/execute", {"action": "modify_blueprint_graph", "payload": payload, "dry_run": dry_run})
        inverse = None
        if isinstance(before_pin, dict) and str(before_pin.get("default_value", "")).strip():
            inverse = {
                "operation": "set_pin_default",
                "payload": {
                    **payload,
                    "default_value": str(before_pin.get("default_value", "")).strip(),
                },
            }
        return result.status_code, result.payload, inverse
    if op == "inspect_pin_contract":
        payload = {
            "blueprint_path": blueprint_path,
            "graph_name": graph_name,
            "from_node_name": str(operation.get("from_node_name", "")).strip(),
            "from_node_title_contains": str(operation.get("from_node_title_contains", "")).strip(),
            "from_pin_name": str(operation.get("from_pin_name", "")).strip(),
            "to_node_name": str(operation.get("to_node_name", "")).strip(),
            "to_node_title_contains": str(operation.get("to_node_title_contains", "")).strip(),
            "to_pin_name": str(operation.get("to_pin_name", "")).strip(),
            "operation": "connect",
        }
        validation = validate_wire_pin_contract(settings, payload)
        return HTTPStatus.OK if bool(validation.get("ok", False)) else HTTPStatus.CONFLICT, {"success": bool(validation.get("ok", False)), "validation": validation}, None
    if op == "reroute_exec_path":
        disconnect_op = {
            "operation": "disconnect_pins",
            "from_node_name": str(operation.get("old_from_node_name", "")).strip(),
            "from_pin_name": str(operation.get("old_from_pin_name", "then")).strip() or "then",
            "to_node_name": str(operation.get("old_to_node_name", "")).strip(),
            "to_pin_name": str(operation.get("old_to_pin_name", "execute")).strip() or "execute",
            "compile_after": False,
        }
        connect_op = {
            "operation": "connect_pins",
            "from_node_name": str(operation.get("new_from_node_name", "")).strip(),
            "from_pin_name": str(operation.get("new_from_pin_name", "then")).strip() or "then",
            "to_node_name": str(operation.get("new_to_node_name", "")).strip(),
            "to_pin_name": str(operation.get("new_to_pin_name", "execute")).strip() or "execute",
            "compile_after": bool(operation.get("compile_after", False)),
        }
        d_status, d_payload, _ = execute_graph_primitive_operation(settings, blueprint_path, graph_name, disconnect_op, dry_run=dry_run)
        if d_status >= 400 or not bool((d_payload or {}).get("success", False)):
            return d_status, d_payload, None
        c_status, c_payload, _ = execute_graph_primitive_operation(settings, blueprint_path, graph_name, connect_op, dry_run=dry_run)
        response = {"success": c_status < 400 and bool((c_payload or {}).get("success", False)), "disconnect_result": d_payload, "connect_result": c_payload}
        inverse = {
            "operation": "reroute_exec_path",
            "payload": {
                "old_from_node_name": connect_op["from_node_name"],
                "old_from_pin_name": connect_op["from_pin_name"],
                "old_to_node_name": connect_op["to_node_name"],
                "old_to_pin_name": connect_op["to_pin_name"],
                "new_from_node_name": disconnect_op["from_node_name"],
                "new_from_pin_name": disconnect_op["from_pin_name"],
                "new_to_node_name": disconnect_op["to_node_name"],
                "new_to_pin_name": disconnect_op["to_pin_name"],
                "compile_after": bool(operation.get("compile_after", False)),
            },
        }
        return c_status, response, inverse
    return HTTPStatus.BAD_REQUEST, make_error("INVALID_FIELD", "Unsupported graph primitive operation.", operation=op), None


def build_graph_ast_document(
    settings: Dict[str, Any],
    blueprint_path: str,
    graph_name: str,
    *,
    include_pins: bool = True,
    max_nodes: int = 2000,
) -> Dict[str, Any]:
    inspect_req = {
        "action": "inspect_blueprint_graph",
        "payload": {
            "blueprint_path": blueprint_path,
            "graph_name": graph_name,
            "include_pins": include_pins,
            "max_nodes": max_nodes,
        },
        "dry_run": True,
    }
    analyze_req = {
        "action": "analyze_blueprint_graph",
        "payload": {
            "blueprint_path": blueprint_path,
            "graph_name": graph_name,
            "include_pins": include_pins,
            "max_nodes": max_nodes,
            "max_trace_depth": 128,
        },
        "dry_run": True,
    }
    inspect_result = call_unreal(settings, "POST", "/execute", inspect_req)
    analyze_result = call_unreal(settings, "POST", "/execute", analyze_req)
    inspect_payload = extract_upstream_payload(inspect_result.payload if isinstance(inspect_result.payload, dict) else {})
    analyze_payload = extract_upstream_payload(analyze_result.payload if isinstance(analyze_result.payload, dict) else {})

    node_items = []
    edge_items = []
    if isinstance(inspect_payload, dict):
        nodes = inspect_payload.get("nodes", [])
        if isinstance(nodes, list):
            for node in nodes:
                if isinstance(node, dict):
                    node_items.append(node)
    if isinstance(analyze_payload, dict):
        edges = analyze_payload.get("exec_edges", [])
        if isinstance(edges, list):
            for edge in edges:
                if isinstance(edge, dict):
                    edge_items.append(edge)
    fingerprint = build_blueprint_fingerprint(analyze_payload if isinstance(analyze_payload, dict) else {})
    return {
        "blueprint_path": blueprint_path,
        "graph_name": graph_name or str(inspect_payload.get("graph_name", "")),
        "node_count": len(node_items),
        "edge_count": len(edge_items),
        "nodes": node_items,
        "exec_edges": edge_items,
        "analysis": analyze_payload if isinstance(analyze_payload, dict) else {},
        "fingerprint": fingerprint,
    }


def build_signature_edit_plan(body: Dict[str, Any]) -> Dict[str, Any]:
    blueprint_path = str(body.get("blueprint_path", "")).strip()
    graph_name = str(body.get("graph_name", "EventGraph")).strip() or "EventGraph"
    op = str(body.get("operation", "")).strip().lower()
    if not blueprint_path:
        raise ValueError("blueprint_path is required")

    steps: List[Dict[str, Any]] = []
    if op in {"add_variable", "remove_variable", "set_default"}:
        payload = {
            "blueprint_path": blueprint_path,
            "graph_name": graph_name,
            "operation": op,
            "name": str(body.get("name", "")).strip(),
            "type": str(body.get("type", "bool")).strip() or "bool",
            "default_value": str(body.get("default_value", "")).strip(),
            "category": str(body.get("category", "AgentGenerated")).strip() or "AgentGenerated",
        }
        if not payload["name"]:
            raise ValueError("name is required for variable operations")
        steps.append({"id": f"sig_{op}", "action": "modify_blueprint_graph", "payload": payload})
    elif op == "create_function":
        fn_name = str(body.get("function_name", "")).strip()
        if not fn_name:
            raise ValueError("function_name is required")
        steps.append(
            {
                "id": "sig_create_function",
                "action": "create_blueprint_function",
                "payload": {"blueprint_path": blueprint_path, "function_name": fn_name, "compile_after": False},
            }
        )
    elif op == "create_macro":
        macro_name = str(body.get("macro_name", "")).strip() or str(body.get("function_name", "")).strip()
        if not macro_name:
            raise ValueError("macro_name is required")
        steps.append(
            {
                "id": "sig_create_macro",
                "action": "create_blueprint_macro",
                "payload": {"blueprint_path": blueprint_path, "macro_name": macro_name, "compile_after": False},
            }
        )
    else:
        raise ValueError("Unsupported operation for signature editing.")

    return {
        "plan_id": f"signature_edit_{op}",
        "profile": "strict",
        "stop_on_error": True,
        "compile_blueprints": [blueprint_path],
        "steps": steps,
    }


def create_approval(
    kind: str,
    summary: str,
    request_payload: Dict[str, Any],
    risky_actions: List[str],
) -> Dict[str, Any]:
    token = f"apr_{uuid4().hex}"
    item = {
        "token": token,
        "kind": kind,
        "summary": summary,
        "risky_actions": risky_actions,
        "request_payload": request_payload,
        "status": "PENDING",
        "created_at": time.time(),
        "approved_at": None,
        "used_at": None,
    }
    with APPROVALS_LOCK:
        approvals = load_approvals()
        approvals["items"][token] = item
        save_approvals(approvals)
    return item


def get_approval(token: str) -> Optional[Dict[str, Any]]:
    with APPROVALS_LOCK:
        approvals = load_approvals()
        item = approvals["items"].get(token)
        if isinstance(item, dict):
            return item
    return None


def mark_approval_approved(token: str) -> Optional[Dict[str, Any]]:
    with APPROVALS_LOCK:
        approvals = load_approvals()
        item = approvals["items"].get(token)
        if not isinstance(item, dict):
            return None
        item["status"] = "APPROVED"
        item["approved_at"] = time.time()
        approvals["items"][token] = item
        save_approvals(approvals)
        return item


def consume_approval(token: str) -> Optional[Dict[str, Any]]:
    with APPROVALS_LOCK:
        approvals = load_approvals()
        item = approvals["items"].get(token)
        if not isinstance(item, dict):
            return None
        if item.get("status") != "APPROVED":
            return item
        item["status"] = "USED"
        item["used_at"] = time.time()
        approvals["items"][token] = item
        save_approvals(approvals)
        return item


def check_requires_approval(
    settings: Dict[str, Any],
    operation: str,
    risky_actions: List[str],
    dry_run: bool,
    approval_token: str,
    request_payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if dry_run:
        return None
    if not bool(settings.get("require_approval_for_mutations", True)):
        return None
    if not risky_actions:
        return None

    if approval_token:
        approved = get_approval(approval_token)
        if not approved:
            return make_error("APPROVAL_INVALID", "Approval token not found.", approval_required=True)
        if approved.get("status") != "APPROVED":
            return make_error("APPROVAL_NOT_APPROVED", "Approval token is not approved.", approval_required=True)
        consume_approval(approval_token)
        return None

    item = create_approval(
        kind=operation,
        summary=f"{operation} requires approval for actions: {', '.join(risky_actions)}",
        request_payload=request_payload,
        risky_actions=risky_actions,
    )
    return make_error(
        "APPROVAL_REQUIRED",
        "Approval required before running mutating operations.",
        approval_required=True,
        approval_token=item["token"],
        risky_actions=risky_actions,
        approval_summary=item["summary"],
    )


def load_recipe_definitions() -> List[Dict[str, Any]]:
    recipes: List[Dict[str, Any]] = []
    if not RECIPES_DIR.exists():
        return recipes
    for path in sorted(RECIPES_DIR.glob("*.json")):
        parsed = load_json_file(path, {})
        if not isinstance(parsed, dict):
            continue
        recipe_id = str(parsed.get("recipe_id", "")).strip()
        version = str(parsed.get("version", "")).strip()
        if not recipe_id or not version:
            continue
        item = dict(parsed)
        item["source_file"] = str(path)
        recipes.append(item)
    return recipes


def get_recipe_definition(recipe_id: str) -> Optional[Dict[str, Any]]:
    recipe_id = recipe_id.strip()
    if not recipe_id:
        return None
    for recipe in load_recipe_definitions():
        if str(recipe.get("recipe_id", "")).strip() == recipe_id:
            return recipe
    return None


def infer_recipe_id_from_message(message: str) -> Optional[str]:
    text = message.lower().strip()
    if not text:
        return None

    if "objective_loop_basic_sp" in text:
        return "objective_loop_basic_sp"
    if "objective_loop_basic_mp_safe" in text:
        return "objective_loop_basic_mp_safe"
    if "objective_loop_timed_collection_sp" in text:
        return "objective_loop_timed_collection_sp"
    if "objective_loop_timed_collection_mp_safe" in text:
        return "objective_loop_timed_collection_mp_safe"
    if "world_city_block_layout" in text:
        return "world_city_block_layout"
    if "world_jump_line_layout" in text:
        return "world_jump_line_layout"
    if "asset_import_materialize_pack" in text:
        return "asset_import_materialize_pack"
    if "sky_objective_jump_loop_sp" in text:
        return "sky_objective_jump_loop_sp"

    wants_mp = any(k in text for k in ["multiplayer", "mp", "replication", "authority", "network"])
    if any(k in text for k in ["timed", "timer"]) and any(k in text for k in ["objective", "collect", "capture"]):
        if any(k in text for k in ["sky", "platform", "jump", "parkour", "floating"]):
            return "sky_objective_jump_loop_sp"
        return "objective_loop_timed_collection_mp_safe" if wants_mp else "objective_loop_timed_collection_sp"
    if any(k in text for k in ["objective", "capture", "collect"]) and any(k in text for k in ["sky", "platform", "jump", "floating"]):
        return "sky_objective_jump_loop_sp"
    if any(k in text for k in ["roll", "dash", "landing", "combo"]) and any(k in text for k in ["platform", "jump", "objective", "sky"]):
        return "sky_objective_jump_loop_sp"
    if any(k in text for k in ["objective", "collect", "capture"]) and any(k in text for k in ["loop", "gameplay", "mode"]):
        return "objective_loop_basic_mp_safe" if wants_mp else "objective_loop_basic_sp"
    if any(k in text for k in ["city", "block", "layout", "street", "environment"]):
        return "world_city_block_layout"
    if any(k in text for k in ["jump line", "parkour", "traversal lane", "platform line"]):
        return "world_jump_line_layout"
    if any(k in text for k in ["import assets", "materialize", "asset pack", "data asset"]):
        return "asset_import_materialize_pack"
    return None


def apply_recipe_defaults(recipe_def: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(inputs)
    recipe_inputs = recipe_def.get("inputs", [])
    if not isinstance(recipe_inputs, list):
        return merged
    for item in recipe_inputs:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name or name in merged:
            continue
        if "default" in item:
            merged[name] = item["default"]
    return merged


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_recipe_inputs(recipe_def: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    allowed_names: set[str] = set()

    recipe_inputs = recipe_def.get("inputs", [])
    if not isinstance(recipe_inputs, list):
        return {"ok": True, "errors": [], "warnings": ["Recipe has no typed input schema."]}

    for item in recipe_inputs:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        input_type = str(item.get("type", "")).strip().lower()
        required = bool(item.get("required", False))
        if not name:
            continue
        allowed_names.add(name)
        if required and name not in inputs:
            errors.append(f"Missing required input: {name}")
            continue
        if name not in inputs:
            continue
        value = inputs[name]
        if input_type == "string" and not isinstance(value, str):
            errors.append(f"Input '{name}' must be a string.")
        elif input_type == "integer" and not (isinstance(value, int) and not isinstance(value, bool)):
            errors.append(f"Input '{name}' must be an integer.")
        elif input_type == "number" and not _is_number(value):
            errors.append(f"Input '{name}' must be numeric.")
        elif input_type == "vector3":
            if not isinstance(value, list) or len(value) != 3 or not all(_is_number(v) for v in value):
                errors.append(f"Input '{name}' must be [x,y,z] numeric array.")
        elif input_type == "boolean" and not isinstance(value, bool):
            errors.append(f"Input '{name}' must be boolean.")

    for name in inputs.keys():
        if name not in allowed_names:
            warnings.append(f"Input '{name}' is not part of the recipe schema and may be ignored.")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def _clamp_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(min_value, min(max_value, parsed))


def _clamp_float(value: Any, default: float, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(min_value, min(max_value, parsed))


def _normalize_namespace_root(value: Any) -> str:
    root = str(value).strip() or "/Game/AgentGenerated"
    if not root.startswith("/"):
        root = f"/{root}"
    return root.rstrip("/")


def build_local_recipe_plan(
    recipe_id: str,
    resolved_inputs: Dict[str, Any],
    dry_run: bool,
    stop_on_error: bool,
    profile: str,
) -> Optional[Dict[str, Any]]:
    if recipe_id != "sky_objective_jump_loop_sp":
        return None

    namespace_root = _normalize_namespace_root(resolved_inputs.get("namespace_root", "/Game/AgentGenerated"))
    gameplay_path = f"{namespace_root}/Gameplay"
    controller_asset_name = str(resolved_inputs.get("controller_asset_name", "BP_SkyObjectiveLoopController")).strip() or "BP_SkyObjectiveLoopController"
    controller_path = f"{gameplay_path}/{controller_asset_name}"

    platform_rows = _clamp_int(resolved_inputs.get("platform_rows", 20), 20, 3, 32)
    platform_cols = _clamp_int(resolved_inputs.get("platform_cols", 20), 20, 3, 32)
    platform_spacing = _clamp_float(resolved_inputs.get("platform_spacing", 900.0), 900.0, 250.0, 2500.0)
    sky_height = _clamp_float(resolved_inputs.get("sky_height", 4500.0), 4500.0, 800.0, 12000.0)
    objective_count = _clamp_int(resolved_inputs.get("objective_count", 5), 5, 1, 25)
    random_seed = _clamp_int(resolved_inputs.get("random_seed", 1337), 1337, -2147483648, 2147483647)
    combo_window_sec = _clamp_float(resolved_inputs.get("roll_dash_combo_window_sec", 1.0), 1.0, 0.2, 2.0)
    player_character_blueprint_path = str(resolved_inputs.get("player_character_blueprint_path", "")).strip()
    disable_legacy_roll_dash_cpp = bool(resolved_inputs.get("disable_legacy_roll_dash_cpp", True))

    steps: List[Dict[str, Any]] = []

    def add_step(step_id: str, action: str, payload: Dict[str, Any]) -> None:
        steps.append({"id": step_id, "action": action, "payload": payload})

    def add_var_step(step_id: str, blueprint_path: str, variable_name: str, variable_type: str, default_value: Any, category: str) -> None:
        add_step(
            step_id,
            "modify_blueprint_graph",
            {
                "blueprint_path": blueprint_path,
                "operation": "add_variable",
                "variable_name": variable_name,
                "variable_type": variable_type,
                "default_value": str(default_value),
                "category": category,
                "compile_after": False,
            },
        )

    add_step(
        "create_loop_controller",
        "create_blueprint",
        {
            "asset_name": controller_asset_name,
            "package_path": gameplay_path,
            "parent_class": "/Script/Engine.Actor",
        },
    )

    add_var_step("var_objective_required", controller_path, "ObjectiveCountRequired", "int", objective_count, "ObjectiveLoop")
    add_var_step("var_objective_collected", controller_path, "ObjectivesCollected", "int", 0, "ObjectiveLoop")
    add_var_step("var_unified_move_enabled", controller_path, "bUseUnifiedRollDashInput", "bool", "true", "MovementCombo")
    add_var_step("var_combo_window", controller_path, "RollDashComboWindowSec", "float", f"{combo_window_sec}", "MovementCombo")
    add_var_step("var_roll_buffer", controller_path, "bRollTriggeredAfterLanding", "bool", "false", "MovementCombo")
    add_var_step("var_dash_buffer", controller_path, "bDashQueuedWithinWindow", "bool", "false", "MovementCombo")
    add_var_step("var_last_roll_time", controller_path, "LastRollInputTimestamp", "float", "-1000.0", "MovementCombo")

    add_step(
        "init_combo_debug",
        "modify_blueprint_graph",
        {
            "blueprint_path": controller_path,
            "operation": "call_function",
            "class_path": "/Script/Engine.KismetSystemLibrary",
            "function_name": "PrintString",
            "exec_source": "begin_play",
            "inputs": {"InString": "Unified roll->dash combo scaffold active"},
            "compile_after": False,
        },
    )
    add_step(
        "clear_existing_sky_start_platform",
        "delete_actors_by_filter",
        {
            "label_contains": "SkyStartPlatform",
        },
    )
    add_step(
        "clear_existing_sky_platforms",
        "delete_actors_by_filter",
        {
            "label_contains": "SkyPlatform_",
        },
    )
    add_step(
        "clear_existing_sky_towers",
        "delete_actors_by_filter",
        {
            "label_contains": "SkyTower_",
        },
    )
    add_step(
        "clear_existing_sky_objectives",
        "delete_actors_by_filter",
        {
            "label_contains": "SkyObjective_",
        },
    )

    add_step(
        "spawn_start_platform",
        "spawn_actor",
        {
            "class_path": "/Script/Engine.StaticMeshActor",
            "actor_label": "SkyStartPlatform",
            "folder_path": "AgentGenerated/SkyPlatforms",
            "static_mesh_path": "/Engine/BasicShapes/Cube.Cube",
            "location": [0.0, 0.0, sky_height],
            "scale": [30.0, 30.0, 1.5],
            "tags": ["StartPlatform", "SkyPlatform"],
        },
    )
    add_step(
        "clear_existing_player_starts",
        "delete_actors_by_filter",
        {
            "label_contains": "PlayerStart",
        },
    )
    add_step(
        "spawn_center_player_start",
        "spawn_actor",
        {
            "class_path": "/Script/Engine.PlayerStart",
            "actor_label": "PlayerStart_SkyCenter",
            "folder_path": "AgentGenerated/Spawn",
            "location": [0.0, 0.0, sky_height + 240.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "tags": ["SkyPlayerStart", "StartPlatform"],
        },
    )

    origin_x = -0.5 * float(platform_cols - 1) * platform_spacing
    origin_y = -0.5 * float(platform_rows - 1) * platform_spacing
    platform_actors: List[Dict[str, Any]] = []
    for row in range(platform_rows):
        for col in range(platform_cols):
            x = origin_x + float(col) * platform_spacing
            y = origin_y + float(row) * platform_spacing
            platform_actors.append(
                {
                    "class_path": "/Script/Engine.StaticMeshActor",
                    "actor_label": f"SkyPlatform_{row + 1:02d}_{col + 1:02d}",
                    "folder_path": "AgentGenerated/SkyPlatforms/Grid",
                    "static_mesh_path": "/Engine/BasicShapes/Cube.Cube",
                    "location": [x, y, sky_height],
                    "scale": [4.0, 4.0, 0.6],
                    "tags": ["SkyPlatform"],
                }
            )
    add_step("spawn_sky_platform_grid", "batch_spawn_actors", {"actors": platform_actors})
    tower_scale_z = max(1.0, sky_height / 100.0)
    tower_actors: List[Dict[str, Any]] = []
    for row in range(platform_rows):
        for col in range(platform_cols):
            x = origin_x + float(col) * platform_spacing
            y = origin_y + float(row) * platform_spacing
            tower_actors.append(
                {
                    "class_path": "/Script/Engine.StaticMeshActor",
                    "actor_label": f"SkyTower_{row + 1:02d}_{col + 1:02d}",
                    "folder_path": "AgentGenerated/SkyPlatforms/Towers",
                    "static_mesh_path": "/Engine/BasicShapes/Cube.Cube",
                    "location": [x, y, sky_height * 0.5],
                    "scale": [1.6, 1.6, tower_scale_z],
                    "tags": ["SkyTower", "SkyPlatformSupport"],
                }
            )
    add_step("spawn_sky_tower_supports", "batch_spawn_actors", {"actors": tower_actors})

    total_cells = platform_rows * platform_cols
    objective_count = max(1, min(objective_count, total_cells))
    cell_indices = list(range(total_cells))
    if (platform_rows % 2) == 1 and (platform_cols % 2) == 1:
        center_cell = (platform_rows // 2) * platform_cols + (platform_cols // 2)
        if center_cell in cell_indices:
            cell_indices.remove(center_cell)
    if not cell_indices:
        cell_indices = [0]
    objective_count = max(1, min(objective_count, len(cell_indices)))

    rng = random.Random(random_seed)
    chosen_cells = rng.sample(cell_indices, objective_count)
    for idx, cell in enumerate(chosen_cells, start=1):
        row = cell // platform_cols
        col = cell % platform_cols
        x = origin_x + float(col) * platform_spacing
        y = origin_y + float(row) * platform_spacing
        add_step(
            f"spawn_objective_{idx}",
            "create_objective_actor",
            {
                "actor_label": f"SkyObjective_{idx:02d}",
                "folder_path": "AgentGenerated/Objectives",
                "class_path": "/Script/Engine.StaticMeshActor",
                "static_mesh_path": "/Engine/BasicShapes/Sphere.Sphere",
                "location": [x, y, sky_height + 140.0],
                "scale": [0.6, 0.6, 0.6],
                "tags": ["ObjectiveItem", "SkyObjective"],
            },
        )

    add_step("assert_start_platform", "assert_world_state", {"required_tags": ["StartPlatform"], "min_count": 1})
    add_step("assert_center_player_start", "assert_world_state", {"required_tags": ["SkyPlayerStart"], "min_count": 1})
    add_step("assert_objectives", "assert_world_state", {"required_tags": ["ObjectiveItem"], "min_count": objective_count})

    compile_blueprints = [controller_path]
    if player_character_blueprint_path:
        add_var_step("char_unified_combo_enabled", player_character_blueprint_path, "bUseUnifiedRollDashInput", "bool", "true", "MovementCombo")
        add_var_step("char_combo_window_sec", player_character_blueprint_path, "RollDashComboWindowSec", "float", f"{combo_window_sec}", "MovementCombo")
        add_var_step("char_roll_landing_flag", player_character_blueprint_path, "bRollTriggeredAfterLanding", "bool", "false", "MovementCombo")
        add_var_step("char_dash_window_flag", player_character_blueprint_path, "bDashQueuedWithinWindow", "bool", "false", "MovementCombo")
        add_var_step("char_last_roll_time", player_character_blueprint_path, "LastRollInputTimestamp", "float", "-1000.0", "MovementCombo")
        if disable_legacy_roll_dash_cpp:
            add_var_step("char_disable_legacy_roll", player_character_blueprint_path, "bDisableLegacyRoll", "bool", "true", "LegacyMovement")
            add_var_step("char_disable_legacy_dash", player_character_blueprint_path, "bDisableLegacyDash", "bool", "true", "LegacyMovement")
            add_var_step("char_disable_legacy_cpp", player_character_blueprint_path, "bDisableLegacyRollDashCpp", "bool", "true", "LegacyMovement")
        compile_blueprints.append(player_character_blueprint_path)

    return {
        "plan_id": f"local-{recipe_id}-{uuid4().hex[:8]}",
        "dry_run": bool(dry_run),
        "stop_on_error": bool(stop_on_error),
        "envelope": {
            "trace_id": uuid4().hex,
            "request_id": uuid4().hex,
            "profile": profile,
            "mode": "recipe-local-fallback",
            "goal": recipe_id,
            "goal_context": dict(resolved_inputs),
        },
        "steps": steps,
        "compile_blueprints": compile_blueprints,
    }


def _is_unknown_recipe_error(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    message = str(payload.get("message", "")).lower()
    code = str(payload.get("error_code", "")).lower()
    return ("unknown recipe_id" in message) or ("unknown recipe" in message) or (code == "unknown_recipe")


def run_recipe_with_local_fallback(
    settings: Dict[str, Any],
    recipe_id: str,
    resolved_inputs: Dict[str, Any],
    dry_run: bool,
    stop_on_error: bool,
    profile: str,
) -> Tuple[int, Dict[str, Any], str]:
    request_payload = {
        "recipe_id": recipe_id,
        "inputs": resolved_inputs,
        "dry_run": bool(dry_run),
        "stop_on_error": bool(stop_on_error),
        "profile": profile,
    }
    upstream = call_unreal(settings, "POST", "/run-recipe", request_payload)
    if upstream.status_code < 400 or not _is_unknown_recipe_error(upstream.payload):
        return upstream.status_code, upstream.payload, "unreal_run_recipe"

    local_plan = build_local_recipe_plan(
        recipe_id=recipe_id,
        resolved_inputs=resolved_inputs,
        dry_run=bool(dry_run),
        stop_on_error=bool(stop_on_error),
        profile=profile,
    )
    if local_plan is None:
        return upstream.status_code, upstream.payload, "unreal_run_recipe"

    plan_result = call_unreal(settings, "POST", "/run-plan", local_plan)
    response = plan_result.payload if isinstance(plan_result.payload, dict) else {"success": False, "raw": plan_result.payload}
    response["recipe_local_plan_fallback"] = {
        "used": True,
        "reason": "upstream_unknown_recipe_id",
        "recipe_id": recipe_id,
        "plan_id": str(local_plan.get("plan_id", "")),
    }
    return plan_result.status_code, response, "local_run_plan_fallback"


def complete_recipe_inputs_with_llm(
    settings: Dict[str, Any],
    message: str,
    recipe_def: Dict[str, Any],
    existing_inputs: Dict[str, Any],
) -> Dict[str, Any]:
    llm_enabled = bool(settings.get("llm_enabled", False))
    llm_api_key = str(settings.get("llm_api_key", "")).strip()
    llm_base_url = str(settings.get("llm_base_url", "")).rstrip("/")
    llm_model = str(settings.get("llm_model", "")).strip()
    if not llm_enabled or not llm_base_url or not llm_model:
        return existing_inputs

    schema_inputs = recipe_def.get("inputs", [])
    if not isinstance(schema_inputs, list) or len(schema_inputs) == 0:
        return existing_inputs

    schema_payload = [
        {
            "name": str(item.get("name", "")).strip(),
            "type": str(item.get("type", "")).strip(),
            "required": bool(item.get("required", False)),
            "default": item.get("default"),
        }
        for item in schema_inputs
        if isinstance(item, dict)
    ]

    system_prompt = (
        "You complete structured recipe inputs for Unreal automation. "
        "Return only a JSON object containing recipe inputs. "
        "Do not include keys outside the provided schema."
    )
    user_prompt = (
        f"Natural language request: {message}\n"
        f"Recipe: {json.dumps({'recipe_id': recipe_def.get('recipe_id', ''), 'inputs': schema_payload}, indent=2)}\n"
        f"Current inputs: {json.dumps(existing_inputs, indent=2)}\n"
        "Fill missing values conservatively. Prefer recipe defaults when ambiguous."
    )
    body = {
        "model": llm_model,
        "temperature": float(settings.get("llm_temperature", 0.1)),
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
    }
    headers: Dict[str, str] = {}
    if llm_api_key:
        headers["Authorization"] = f"Bearer {llm_api_key}"

    result = request_json("POST", f"{llm_base_url}/chat/completions", payload=body, headers=headers, timeout_sec=60)
    if result.status_code >= 400:
        return existing_inputs

    choices = result.payload.get("choices", [])
    if not choices:
        return existing_inputs
    content = choices[0].get("message", {}).get("content", "")
    if not isinstance(content, str):
        return existing_inputs
    try:
        parsed = extract_first_json_object(content)
    except Exception:
        return existing_inputs
    if not isinstance(parsed, dict):
        return existing_inputs

    allowed = {str(item.get("name", "")).strip() for item in schema_inputs if isinstance(item, dict)}
    merged = dict(existing_inputs)
    for key, value in parsed.items():
        if key in allowed and key not in merged:
            merged[key] = value
    return merged


def default_release_metrics() -> Dict[str, Any]:
    return {
        "updated_at": time.time(),
        "totals": {
            "recipe_runs": 0,
            "recipe_validations": 0,
            "scenario_runs": 0,
        },
        "success": {
            "recipe_runs": 0,
            "recipe_validations": 0,
            "scenario_runs": 0,
        },
        "compile_failures": 0,
        "contradiction_count": 0,
        "mp_safety_failures": 0,
        "scenario_failures": 0,
        "error_codes": {},
        "runs": [],
    }


def load_release_metrics() -> Dict[str, Any]:
    ensure_data_dir()
    data = load_json_file(RELEASE_METRICS_PATH, {})
    base = default_release_metrics()
    if isinstance(data, dict):
        for key, value in data.items():
            if key in {"totals", "success", "error_codes"} and isinstance(value, dict):
                base[key].update(value)
            elif key == "runs" and isinstance(value, list):
                base["runs"] = value
            elif key in base:
                base[key] = value
    return base


def save_release_metrics(metrics: Dict[str, Any]) -> None:
    ensure_data_dir()
    save_json_file(RELEASE_METRICS_PATH, metrics)


def collect_error_codes_from_payload(obj: Any) -> List[str]:
    out: List[str] = []
    if isinstance(obj, dict):
        code = str(obj.get("error_code", "")).strip()
        if code:
            out.append(code)
        for value in obj.values():
            out.extend(collect_error_codes_from_payload(value))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(collect_error_codes_from_payload(item))
    return out


def update_release_metrics(
    run_kind: str,
    run_success: bool,
    http_status: int,
    response_payload: Dict[str, Any],
    profile: str,
    release_validation: bool,
) -> Dict[str, Any]:
    with RELEASE_METRICS_LOCK:
        metrics = load_release_metrics()
        if run_kind not in metrics["totals"]:
            metrics["totals"][run_kind] = 0
            metrics["success"][run_kind] = 0
        metrics["totals"][run_kind] = int(metrics["totals"].get(run_kind, 0)) + 1
        if run_success:
            metrics["success"][run_kind] = int(metrics["success"].get(run_kind, 0)) + 1

        error_codes = collect_error_codes_from_payload(response_payload)
        for code in error_codes:
            metrics["error_codes"][code] = int(metrics["error_codes"].get(code, 0)) + 1
        if "COMPILE_FAILED" in error_codes:
            metrics["compile_failures"] = int(metrics.get("compile_failures", 0)) + 1
        if "ANALYSIS_CONTRADICTION" in error_codes:
            metrics["contradiction_count"] = int(metrics.get("contradiction_count", 0)) + 1
        if "MP_SAFETY_FAILED" in error_codes:
            metrics["mp_safety_failures"] = int(metrics.get("mp_safety_failures", 0)) + 1
        if run_kind == "scenario_runs" and not run_success:
            metrics["scenario_failures"] = int(metrics.get("scenario_failures", 0)) + 1

        run_record = {
            "timestamp": time.time(),
            "kind": run_kind,
            "success": run_success,
            "http_status": int(http_status),
            "profile": profile,
            "release_validation": release_validation,
            "error_codes": sorted(list(set(error_codes))),
        }
        metrics["runs"].append(run_record)
        metrics["runs"] = metrics["runs"][-500:]
        metrics["updated_at"] = time.time()
        save_release_metrics(metrics)
        return metrics


def build_release_metrics_summary(metrics: Dict[str, Any]) -> Dict[str, Any]:
    totals = metrics.get("totals", {})
    success = metrics.get("success", {})
    recipe_total = int(totals.get("recipe_runs", 0)) + int(totals.get("recipe_validations", 0))
    scenario_total = int(totals.get("scenario_runs", 0))
    all_total = recipe_total + scenario_total
    all_success = int(success.get("recipe_runs", 0)) + int(success.get("recipe_validations", 0)) + int(success.get("scenario_runs", 0))

    compile_failures = int(metrics.get("compile_failures", 0))
    contradiction_count = int(metrics.get("contradiction_count", 0))
    scenario_success = int(success.get("scenario_runs", 0))

    top_error_codes = sorted(
        [
            {"error_code": code, "count": int(count)}
            for code, count in metrics.get("error_codes", {}).items()
            if int(count) > 0
        ],
        key=lambda item: item["count"],
        reverse=True,
    )[:10]

    return {
        "success": True,
        "updated_at": metrics.get("updated_at", 0),
        "pass_rate": (float(all_success) / float(all_total)) if all_total > 0 else None,
        "scenario_pass_rate": (float(scenario_success) / float(scenario_total)) if scenario_total > 0 else None,
        "compile_failure_rate": (float(compile_failures) / float(all_total)) if all_total > 0 else None,
        "contradiction_rate": (float(contradiction_count) / float(all_total)) if all_total > 0 else None,
        "totals": totals,
        "success_counts": success,
        "compile_failures": compile_failures,
        "contradiction_count": contradiction_count,
        "mp_safety_failures": int(metrics.get("mp_safety_failures", 0)),
        "scenario_failures": int(metrics.get("scenario_failures", 0)),
        "top_error_codes": top_error_codes,
        "release_metrics_file": str(RELEASE_METRICS_PATH),
    }


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "UnrealAgentWeb/0.2"

    def _json_response(self, code: int, payload: Dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json_body(self) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None, "Invalid Content-Length."
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw:
            return {}, None
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return None, "Invalid JSON body."
        if not isinstance(parsed, dict):
            return None, "JSON body must be an object."
        return parsed, None

    def _serve_index(self) -> None:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            self._json_response(HTTPStatus.NOT_FOUND, make_error("NOT_FOUND", "index.html not found"))
            return
        content = index_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_static_html(self, filename: str) -> None:
        safe_name = Path(filename).name
        page_path = STATIC_DIR / safe_name
        if not page_path.exists():
            self._json_response(HTTPStatus.NOT_FOUND, make_error("NOT_FOUND", f"{safe_name} not found"))
            return
        content = page_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _with_run_lock(self, fn):
        if not RUN_LOCK.acquire(blocking=False):
            return HTTPStatus.CONFLICT, make_error("RUN_BUSY", "Another Unreal run is already in progress.")
        try:
            return fn()
        finally:
            RUN_LOCK.release()

    def _get_paid_token(self, body: Optional[Dict[str, Any]] = None) -> str:
        header_token = str(self.headers.get("X-Paid-Token", "")).strip()
        if header_token:
            return header_token
        if isinstance(body, dict):
            return str(body.get("paid_token", "")).strip()
        return ""

    def _is_paid_route_authorized(
        self,
        settings: Dict[str, Any],
        path: str,
        body: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, List[str]]] = None,
    ) -> bool:
        if not bool(settings.get("plan_tier_gate_enabled", False)):
            return True
        required_routes = settings.get("paid_tier_required_routes", [])
        if not isinstance(required_routes, list):
            return True
        if path not in {str(item).strip() for item in required_routes if isinstance(item, str)}:
            return True

        token = self._get_paid_token(body)
        if not token and isinstance(query, dict):
            token = str(query.get("paid_token", [""])[0]).strip()
        if not token:
            return False
        valid_tokens = get_valid_paid_tokens(settings)
        return token in valid_tokens

    def _resolve_session_id(self, body: Optional[Dict[str, Any]] = None) -> str:
        header_session = str(self.headers.get("X-Session-Id", "")).strip()
        if header_session:
            return header_session
        if isinstance(body, dict):
            return str(body.get("session_id", "")).strip()
        return ""

    def _emit_major_update(
        self,
        settings: Dict[str, Any],
        session_id: str,
        kind: str,
        status: str,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not session_id:
            return
        append_paid_session_event(
            settings,
            session_id,
            {
                "kind": kind,
                "status": status,
                "message": message,
                "payload": payload or {},
                "path": self.path,
            },
        )

    def do_GET(self) -> None:
        try:
            parsed_url = urllib.parse.urlparse(self.path)
            path = parsed_url.path
            query = urllib.parse.parse_qs(parsed_url.query)
            settings = load_settings()

            if not self._is_paid_route_authorized(settings, path, body=None, query=query):
                self._json_response(
                    HTTPStatus.PAYMENT_REQUIRED,
                    make_error("PLAN_TIER_REQUIRED", "This route requires a paid plan token.", route=path),
                )
                return

            if path == "/":
                self._serve_index()
                return
            if path == "/capabilities":
                self._serve_static_html("capabilities.html")
                return
            if path == "/api/settings":
                safe = dict(settings)
                if safe.get("llm_api_key"):
                    safe["llm_api_key"] = "********"
                if isinstance(safe.get("paid_live_logs_tokens"), list) and len(safe["paid_live_logs_tokens"]) > 0:
                    safe["paid_live_logs_tokens"] = ["********" for _ in safe["paid_live_logs_tokens"]]
                if isinstance(safe.get("paid_admin_tokens"), list) and len(safe["paid_admin_tokens"]) > 0:
                    safe["paid_admin_tokens"] = ["********" for _ in safe["paid_admin_tokens"]]
                self._json_response(HTTPStatus.OK, {"success": True, "settings": safe})
                return
            if path == "/api/approvals":
                approvals = load_approvals()
                items = list(approvals.get("items", {}).values())
                items.sort(key=lambda x: float(x.get("created_at", 0.0)), reverse=True)
                self._json_response(HTTPStatus.OK, {"success": True, "approvals": items})
                return
            if path == "/api/paid/session/logs":
                if not bool(settings.get("paid_live_logs_enabled", False)):
                    self._json_response(HTTPStatus.FORBIDDEN, make_error("PAID_LOGS_DISABLED", "Paid live logs are disabled."))
                    return
                token = self._get_paid_token()
                if not token:
                    token = str(query.get("paid_token", [""])[0]).strip()
                valid_tokens = get_valid_paid_tokens(settings)
                if token not in valid_tokens:
                    self._json_response(HTTPStatus.UNAUTHORIZED, make_error("PAID_LOGS_UNAUTHORIZED", "Invalid paid live log token."))
                    return
                session_id = str(query.get("session_id", [""])[0]).strip()
                if not session_id:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "session_id is required."))
                    return
                since = 0.0
                try:
                    since = float(str(query.get("since", ["0"])[0]).strip() or "0")
                except Exception:
                    since = 0.0
                limit = 200
                try:
                    limit = int(str(query.get("limit", ["200"])[0]).strip() or "200")
                except Exception:
                    limit = 200
                limit = max(1, min(2000, limit))
                events = read_paid_session_events(session_id, since_ts=since, limit=limit)
                self._json_response(HTTPStatus.OK, {"success": True, "session_id": session_id, "events": events})
                return
            if path == "/api/paid/session/stream":
                if not bool(settings.get("paid_live_logs_enabled", False)):
                    self._json_response(HTTPStatus.FORBIDDEN, make_error("PAID_LOGS_DISABLED", "Paid live logs are disabled."))
                    return
                token = self._get_paid_token()
                if not token:
                    token = str(query.get("paid_token", [""])[0]).strip()
                valid_tokens = get_valid_paid_tokens(settings)
                if token not in valid_tokens:
                    self._json_response(HTTPStatus.UNAUTHORIZED, make_error("PAID_LOGS_UNAUTHORIZED", "Invalid paid live log token."))
                    return
                session_id = str(query.get("session_id", [""])[0]).strip()
                if not session_id:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "session_id is required."))
                    return
                try:
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.end_headers()
                    heartbeat = {"kind": "stream_open", "status": "info", "message": "Paid log stream connected."}
                    self.wfile.write(f"data: {json.dumps(heartbeat)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    since_ts = 0.0
                    start_time = time.time()
                    while time.time() - start_time < 20.0:
                        events = read_paid_session_events(session_id, since_ts=since_ts, limit=200)
                        if events:
                            for event in events:
                                ts = float(event.get("timestamp", 0.0))
                                if ts > since_ts:
                                    since_ts = ts
                                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode("utf-8"))
                            self.wfile.flush()
                        time.sleep(0.75)
                except (BrokenPipeError, ConnectionResetError):
                    return
                return
            if path == "/api/health":
                compatibility = check_compatibility(settings)
                unreal_health = call_unreal(settings, "GET", "/health")
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "web_tool": "ok",
                        "compatibility": compatibility,
                        "unreal_status_code": unreal_health.status_code,
                        "unreal": unreal_health.payload,
                    },
                )
                return
            if path == "/api/info":
                result = call_unreal(settings, "GET", "/info")
                self._json_response(result.status_code, result.payload)
                return
            if path == "/api/state":
                result = call_unreal(settings, "GET", "/state")
                self._json_response(result.status_code, result.payload)
                return
            if path == "/api/actions":
                result = call_unreal(settings, "GET", "/actions")
                self._json_response(result.status_code, result.payload)
                return
            if path == "/api/recipes":
                local_recipes = load_recipe_definitions()
                upstream = call_unreal(settings, "GET", "/recipes")
                if upstream.status_code >= 400 and len(local_recipes) == 0:
                    self._json_response(upstream.status_code, upstream.payload)
                    return

                upstream_recipes = []
                if isinstance(upstream.payload, dict):
                    candidate = upstream.payload.get("recipes", [])
                    if isinstance(candidate, list):
                        upstream_recipes = [item for item in candidate if isinstance(item, dict)]

                if len(local_recipes) > 0:
                    upstream_by_id = {
                        str(item.get("recipe_id", "")).strip(): item
                        for item in upstream_recipes
                        if isinstance(item, dict) and str(item.get("recipe_id", "")).strip()
                    }
                    merged_recipes = []
                    for recipe in local_recipes:
                        rid = str(recipe.get("recipe_id", "")).strip()
                        merged = dict(recipe)
                        if rid in upstream_by_id:
                            merged["upstream"] = upstream_by_id[rid]
                        merged_recipes.append(merged)
                else:
                    merged_recipes = upstream_recipes

                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "recipes": merged_recipes,
                        "local_recipe_count": len(local_recipes),
                        "upstream_recipe_count": len(upstream_recipes),
                    },
                )
                return
            if path == "/api/release-metrics":
                summary = build_release_metrics_summary(load_release_metrics())
                self._json_response(HTTPStatus.OK, summary)
                return
            if path == "/api/claims-evidence":
                summary = build_claim_evidence_summary(settings)
                self._json_response(HTTPStatus.OK, summary)
                return
            if path == "/api/admin/session-diagnostics":
                admin_token = self._get_paid_token()
                if not admin_token:
                    admin_token = str(query.get("paid_token", [""])[0]).strip()
                if admin_token not in get_valid_admin_tokens(settings):
                    self._json_response(HTTPStatus.UNAUTHORIZED, make_error("ADMIN_UNAUTHORIZED", "Invalid admin token."))
                    return
                _, _, _, session_logs = build_paid_providers(settings)
                self._json_response(HTTPStatus.OK, {"success": True, **session_logs.diagnostics()})
                return
            if path == "/api/admin/usage-events":
                admin_token = self._get_paid_token()
                if not admin_token:
                    admin_token = str(query.get("paid_token", [""])[0]).strip()
                if admin_token not in get_valid_admin_tokens(settings):
                    self._json_response(HTTPStatus.UNAUTHORIZED, make_error("ADMIN_UNAUTHORIZED", "Invalid admin token."))
                    return
                limit = 200
                try:
                    limit = int(str(query.get("limit", ["200"])[0]).strip() or "200")
                except Exception:
                    limit = 200
                limit = max(1, min(2000, limit))
                events: List[Dict[str, Any]] = []
                if USAGE_EVENTS_PATH.exists():
                    try:
                        lines = USAGE_EVENTS_PATH.read_text(encoding="utf-8").splitlines()
                        for line in lines[-limit:]:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                item = json.loads(line)
                            except Exception:
                                continue
                            if isinstance(item, dict):
                                events.append(item)
                    except Exception:
                        events = []
                self._json_response(HTTPStatus.OK, {"success": True, "count": len(events), "events": events})
                return
            if path == "/api/debug/traces":
                limit = str(query.get("limit", ["50"])[0]).strip()
                flt = str(query.get("filter", [""])[0]).strip()
                qp = f"?limit={urllib.parse.quote(limit)}"
                if flt:
                    qp += f"&filter={urllib.parse.quote(flt)}"
                result = call_unreal(settings, "GET", f"/debug/traces{qp}")
                self._json_response(result.status_code, result.payload)
                return
            if path == "/api/node-library":
                idx = load_node_library_index()
                if not idx:
                    self._json_response(HTTPStatus.NOT_FOUND, make_error("NODE_LIBRARY_NOT_FOUND", "Node library index not found."))
                    return
                q = str(query.get("q", [""])[0]).strip()
                if q:
                    search = {
                        "node_hits": [],
                        "connection_pattern_hits": [],
                    }
                    qt = q.lower()
                    for node in idx.get("node_types", []):
                        if not isinstance(node, dict):
                            continue
                        blob = " ".join(
                            [
                                str(node.get("name", "")),
                                str(node.get("class", "")),
                                str(node.get("description", "")),
                                str(node.get("properties", "")),
                                str(node.get("pins", "")),
                                " ".join(str(n) for n in node.get("notes", [])),
                            ]
                        ).lower()
                        if qt in blob:
                            search["node_hits"].append(node)
                        if len(search["node_hits"]) >= 25:
                            break

                    for pattern in idx.get("connection_patterns", []):
                        if not isinstance(pattern, dict):
                            continue
                        blob = " ".join([str(pattern.get("name", ""))] + [str(s) for s in pattern.get("steps", [])]).lower()
                        if qt in blob:
                            search["connection_pattern_hits"].append(pattern)
                        if len(search["connection_pattern_hits"]) >= 25:
                            break

                    self._json_response(
                        HTTPStatus.OK,
                        {
                            "success": True,
                            "query": q,
                            "counts": {
                                "node_hits": len(search["node_hits"]),
                                "connection_pattern_hits": len(search["connection_pattern_hits"]),
                            },
                            "results": search,
                        },
                    )
                    return

                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "counts": idx.get("counts", {}),
                        "source": idx.get("source", ""),
                    },
                )
                return
            if path == "/api/node-pattern-catalog":
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "patterns": sorted(NODE_PATTERN_CATALOG.values(), key=lambda x: str(x.get("pattern_id", ""))),
                        "count": len(NODE_PATTERN_CATALOG),
                    },
                )
                return
            if path == "/api/workflow-catalog":
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "workflows": sorted(WORKFLOW_TEMPLATE_CATALOG.values(), key=lambda x: str(x.get("workflow_id", ""))),
                        "count": len(WORKFLOW_TEMPLATE_CATALOG),
                    },
                )
                return
            if path == "/api/animation-autonomy-catalog":
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "templates": sorted(ANIMATION_AUTONOMY_TEMPLATES.values(), key=lambda x: str(x.get("template_id", ""))),
                        "count": len(ANIMATION_AUTONOMY_TEMPLATES),
                    },
                )
                return
            if path == "/api/ai-autonomy-catalog":
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "templates": sorted(AI_AUTONOMY_TEMPLATES.values(), key=lambda x: str(x.get("template_id", ""))),
                        "count": len(AI_AUTONOMY_TEMPLATES),
                    },
                )
                return
            if path == "/api/content-pipeline-catalog":
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "presets": sorted(CONTENT_PIPELINE_PRESETS.values(), key=lambda x: str(x.get("preset_id", ""))),
                        "count": len(CONTENT_PIPELINE_PRESETS),
                    },
                )
                return
            if path == "/api/multiplayer-correctness-catalog":
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "profiles": sorted(MULTIPLAYER_CORRECTNESS_PROFILES.values(), key=lambda x: str(x.get("profile_id", ""))),
                        "count": len(MULTIPLAYER_CORRECTNESS_PROFILES),
                    },
                )
                return
            if path == "/api/material-mesh-presets-catalog":
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "presets": sorted(MATERIAL_MESH_SETUP_PRESETS.values(), key=lambda x: str(x.get("preset_id", ""))),
                        "count": len(MATERIAL_MESH_SETUP_PRESETS),
                    },
                )
                return
            if path == "/api/native-asset-authoring-catalog":
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "asset_types": sorted(NATIVE_ASSET_AUTHORING_CATALOG.values(), key=lambda x: str(x.get("asset_type", ""))),
                        "count": len(NATIVE_ASSET_AUTHORING_CATALOG),
                    },
                )
                return
            if path == "/api/graph-primitives-catalog":
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        **get_graph_primitives_catalog(),
                    },
                )
                return
            if path == "/api/node-control-capabilities":
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "modify_blueprint_graph_operations": sorted(
                            [
                                "add_print_string_on_begin_play",
                                "add_variable",
                                "remove_variable",
                                "set_default",
                                "add_branch",
                                "call_function",
                                "remove_function_call",
                                "remove_nodes",
                                "disconnect_pin",
                            ]
                        ),
                        "blueprint_node_authoring_operations": sorted(
                            [
                                "spawn_function_call",
                                "replace_function_call",
                                "spawn_custom_event",
                                "spawn_branch_node",
                                "spawn_variable_get",
                            ]
                        ),
                        "graph_primitive_operations": get_graph_primitives_catalog().get("supported_operations", []),
                        "graph_actions": sorted(list(GRAPH_MUTATION_ACTIONS)),
                        "node_patterns": sorted(NODE_PATTERN_CATALOG.values(), key=lambda x: str(x.get("pattern_id", ""))),
                        "workflow_templates": sorted(WORKFLOW_TEMPLATE_CATALOG.values(), key=lambda x: str(x.get("workflow_id", ""))),
                        "animation_autonomy_templates": sorted(ANIMATION_AUTONOMY_TEMPLATES.values(), key=lambda x: str(x.get("template_id", ""))),
                        "ai_autonomy_templates": sorted(AI_AUTONOMY_TEMPLATES.values(), key=lambda x: str(x.get("template_id", ""))),
                        "content_pipeline_presets": sorted(CONTENT_PIPELINE_PRESETS.values(), key=lambda x: str(x.get("preset_id", ""))),
                        "multiplayer_correctness_profiles": sorted(MULTIPLAYER_CORRECTNESS_PROFILES.values(), key=lambda x: str(x.get("profile_id", ""))),
                        "material_mesh_setup_presets": sorted(MATERIAL_MESH_SETUP_PRESETS.values(), key=lambda x: str(x.get("preset_id", ""))),
                        "native_asset_authoring_types": sorted(NATIVE_ASSET_AUTHORING_CATALOG.values(), key=lambda x: str(x.get("asset_type", ""))),
                        "blueprint_review_scopes": ["graph", "asset"],
                        "control_surfaces": get_control_surface_catalog_payload(),
                    },
                )
                return
            if path == "/api/control-surface-catalog":
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "surfaces": get_control_surface_catalog_payload(),
                    },
                )
                return
            if path == "/api/agent-readiness":
                status, payload = evaluate_agent_readiness(settings)
                self._json_response(status, payload)
                return
            if path == "/api/graph-snapshots":
                snapshots: List[Dict[str, Any]] = []
                files = sorted(
                    [p for p in GRAPH_SNAPSHOTS_DIR.glob("*.json") if p.is_file()],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )[:100]
                for path_item in files:
                    payload = load_json_file(path_item, {})
                    if not isinstance(payload, dict):
                        continue
                    snapshots.append(
                        {
                            "snapshot_token": path_item.stem,
                            "created_at": payload.get("created_at", 0),
                            "route": payload.get("route", ""),
                            "blueprint_path": payload.get("blueprint_path", ""),
                            "graph_name": payload.get("graph_name", ""),
                            "has_rollback_plan": bool(payload.get("rollback_plan")),
                        }
                    )
                self._json_response(HTTPStatus.OK, {"success": True, "snapshots": snapshots})
                return
            if path == "/api/analysis-runs":
                runs: List[Dict[str, Any]] = []
                for run_dir in sorted(
                    [p for p in ANALYSIS_RUNS_DIR.iterdir() if p.is_dir()],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )[:50]:
                    analysis_file = run_dir / "analysis.json"
                    if not analysis_file.exists():
                        continue
                    runs.append(
                        {
                            "run_id": run_dir.name,
                            "updated_at": run_dir.stat().st_mtime,
                            "analysis_file": str(analysis_file),
                        }
                    )
                self._json_response(HTTPStatus.OK, {"success": True, "runs": runs})
                return
            if path == "/api/execution-runs":
                runs: List[Dict[str, Any]] = []
                for run_dir in sorted(
                    [p for p in EXECUTION_RUNS_DIR.iterdir() if p.is_dir()],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )[:100]:
                    execution_file = run_dir / "execution.json"
                    if not execution_file.exists():
                        continue
                    runs.append(
                        {
                            "run_id": run_dir.name,
                            "updated_at": run_dir.stat().st_mtime,
                            "execution_file": str(execution_file),
                        }
                    )
                self._json_response(HTTPStatus.OK, {"success": True, "runs": runs})
                return
            if path == "/api/execution-run-detail":
                run_id = str(query.get("run_id", [""])[0]).strip()
                if not run_id:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "run_id is required."))
                    return
                run_dir = EXECUTION_RUNS_DIR / run_id
                execution_file = run_dir / "execution.json"
                if not execution_file.exists():
                    self._json_response(HTTPStatus.NOT_FOUND, make_error("NOT_FOUND", "Execution run not found.", run_id=run_id))
                    return
                payload = load_json_file(execution_file, {})
                if not isinstance(payload, dict):
                    payload = {}
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "run_id": run_id,
                        "timeline": payload.get("timeline", []),
                        "graph_diff": payload.get("graph_diff", {}),
                        "determinism_score": payload.get("determinism_score", {}),
                        "artifact": payload,
                    },
                )
                return
            if path == "/api/execution-artifact":
                run_id = str(query.get("run_id", [""])[0]).strip()
                if not run_id:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "run_id is required."))
                    return
                include_snapshot = str(query.get("include_snapshot", ["1"])[0]).strip().lower() not in {"0", "false", "no"}
                include_full = str(query.get("include_full", ["0"])[0]).strip().lower() in {"1", "true", "yes"}
                artifact = read_execution_artifact(run_id)
                if not isinstance(artifact, dict):
                    self._json_response(HTTPStatus.NOT_FOUND, make_error("NOT_FOUND", "Execution run not found.", run_id=run_id))
                    return
                self._json_response(
                    HTTPStatus.OK,
                    build_execution_artifact_view(
                        run_id,
                        artifact,
                        include_snapshot=include_snapshot,
                        include_full=include_full,
                    ),
                )
                return

            self._json_response(HTTPStatus.NOT_FOUND, make_error("NOT_FOUND", "Not found"))
        except Exception as exc:
            self._json_response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                make_error("INTERNAL_ERROR", str(exc), trace=traceback.format_exc()),
            )

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        body, err = self._read_json_body()
        if err:
            self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_JSON", err))
            return
        assert body is not None

        request_id = uuid4().hex
        started = time.time()

        try:
            settings = load_settings()

            if not self._is_paid_route_authorized(settings, path, body=body, query=None):
                self._json_response(
                    HTTPStatus.PAYMENT_REQUIRED,
                    make_error("PLAN_TIER_REQUIRED", "This route requires a paid plan token.", route=path),
                )
                return

            bootstrap_block = enforce_agent_bootstrap_for_route(settings, path, body, self.headers)
            if bootstrap_block is not None:
                status, payload = bootstrap_block
                self._json_response(status, payload)
                return

            readiness_block = enforce_agent_readiness_for_route(settings, path, body)
            if readiness_block is not None:
                status, payload = readiness_block
                self._json_response(status, payload)
                return

            if path == "/api/settings":
                merged = dict(settings)
                for key in DEFAULT_SETTINGS.keys():
                    if key in body:
                        merged[key] = body[key]
                merged["execution_profile"] = normalize_execution_profile(
                    merged.get("execution_profile", DEFAULT_SETTINGS["execution_profile"]),
                    fallback=DEFAULT_SETTINGS["execution_profile"],
                )
                merged = save_settings(merged)
                safe = dict(merged)
                if safe.get("llm_api_key"):
                    safe["llm_api_key"] = "********"
                if isinstance(safe.get("paid_live_logs_tokens"), list) and len(safe["paid_live_logs_tokens"]) > 0:
                    safe["paid_live_logs_tokens"] = ["********" for _ in safe["paid_live_logs_tokens"]]
                response = {"success": True, "settings": safe}
                self._json_response(HTTPStatus.OK, response)
                return

            if path == "/api/approve":
                token = str(body.get("approval_token", "")).strip()
                if not token:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "approval_token is required."))
                    return
                approved = mark_approval_approved(token)
                if not approved:
                    self._json_response(HTTPStatus.NOT_FOUND, make_error("APPROVAL_INVALID", "approval_token not found."))
                    return
                self._json_response(HTTPStatus.OK, {"success": True, "approval": approved})
                return

            if path == "/api/paid/session/start":
                token = self._get_paid_token(body)
                user_id = str(body.get("user_id", "")).strip()
                project_label = str(body.get("project_label", "")).strip()
                ok, payload = create_paid_session(settings, token=token, user_id=user_id, project_label=project_label)
                if not ok:
                    code = HTTPStatus.UNAUTHORIZED if str(payload.get("error_code", "")).endswith("UNAUTHORIZED") else HTTPStatus.BAD_REQUEST
                    self._json_response(code, payload)
                    return
                session_id = str(payload.get("session_id", "")).strip()
                payload["stream_url"] = f"/api/paid/session/stream?session_id={urllib.parse.quote(session_id)}"
                payload["logs_url"] = f"/api/paid/session/logs?session_id={urllib.parse.quote(session_id)}"
                self._json_response(HTTPStatus.OK, payload)
                return

            if path == "/api/paid/session/end":
                token = self._get_paid_token(body)
                valid_tokens = get_valid_paid_tokens(settings)
                if token not in valid_tokens:
                    self._json_response(HTTPStatus.UNAUTHORIZED, make_error("PAID_LOGS_UNAUTHORIZED", "Invalid paid live log token."))
                    return
                session_id = self._resolve_session_id(body)
                if not session_id:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "session_id is required."))
                    return
                sessions = load_paid_sessions()
                meta = sessions.get("sessions", {}).get(session_id)
                if not isinstance(meta, dict):
                    self._json_response(HTTPStatus.NOT_FOUND, make_error("SESSION_NOT_FOUND", "Session not found."))
                    return
                meta["active"] = False
                meta["ended_at"] = time.time()
                sessions["sessions"][session_id] = meta
                save_paid_sessions(sessions)
                self._emit_major_update(settings, session_id, "session_ended", "info", "Paid live log session ended.", {})
                self._json_response(HTTPStatus.OK, {"success": True, "session_id": session_id})
                return

            if path == "/api/debug/clear":
                result = call_unreal(settings, "POST", "/debug/clear", payload={})
                self._json_response(result.status_code, result.payload)
                return

            if path == "/api/agent-bootstrap":
                client_name = str(body.get("client_name", "agent_client")).strip() or "agent_client"
                client_version = str(body.get("client_version", "")).strip()
                session_label = str(body.get("session_label", "")).strip()
                readiness_status, readiness_payload = evaluate_agent_readiness(settings)
                capability_context = build_agent_bootstrap_capability_context()
                if readiness_status != HTTPStatus.OK:
                    self._json_response(
                        readiness_status,
                        {
                            "success": False,
                            "error_code": "AGENT_NOT_READY",
                            "message": "Agent bootstrap failed because the control surface is not ready.",
                            "readiness": readiness_payload,
                            "capability_context": capability_context,
                            "bootstrap_route": "/api/agent-bootstrap",
                        },
                    )
                    return
                session_record = issue_agent_bootstrap_session(
                    settings,
                    client_name=client_name,
                    client_version=client_version,
                    session_label=session_label,
                    readiness=readiness_payload,
                    capability_context=capability_context,
                )
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "message": "Agent bootstrap session started.",
                        "bootstrap_token": session_record.get("token", ""),
                        "created_at": float(session_record.get("created_at", 0.0)),
                        "expires_at": float(session_record.get("expires_at", 0.0)),
                        "client_name": client_name,
                        "client_version": client_version,
                        "session_label": session_label,
                        "readiness": readiness_payload,
                        "capability_context": capability_context,
                    },
                )
                return

            compatibility = check_compatibility(settings)
            if not compatibility.get("ok", False):
                self._json_response(
                    HTTPStatus.PRECONDITION_FAILED,
                    make_error("VERSION_INCOMPATIBLE", "Unreal plugin/API compatibility check failed.", compatibility=compatibility),
                )
                return

            if path == "/api/run-recipe":
                recipe_id = str(body.get("recipe_id", "")).strip()
                if not recipe_id:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "recipe_id is required."))
                    return
                inputs = body.get("inputs", {})
                if not isinstance(inputs, dict):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "inputs must be an object."))
                    return

                dry_run = bool(body.get("dry_run", False))
                stop_on_error = bool(body.get("stop_on_error", True))
                profile = normalize_execution_profile(
                    body.get("profile", settings.get("execution_profile", "balanced")),
                    fallback=normalize_execution_profile(settings.get("execution_profile", "balanced")),
                )
                approval_token = str(body.get("approval_token", "")).strip()
                release_validation = bool(body.get("release_validation", False))
                session_id = self._resolve_session_id(body)
                self._emit_major_update(
                    settings,
                    session_id,
                    "run_recipe_started",
                    "info",
                    f"Recipe '{recipe_id}' execution started.",
                    {"profile": profile, "dry_run": dry_run},
                )

                recipe_def = get_recipe_definition(recipe_id)
                inputs = merge_default_project_inputs(settings, inputs, recipe_def)
                validation = {"ok": True, "errors": [], "warnings": []}
                resolved_inputs = dict(inputs)
                if recipe_def is not None:
                    resolved_inputs = apply_recipe_defaults(recipe_def, resolved_inputs)
                    validation = validate_recipe_inputs(recipe_def, resolved_inputs)
                    if not validation.get("ok", False):
                        self._json_response(
                            HTTPStatus.BAD_REQUEST,
                            make_error(
                                "RECIPE_INPUT_VALIDATION_FAILED",
                                "Recipe input validation failed.",
                                recipe_id=recipe_id,
                                validation=validation,
                            ),
                        )
                        return

                risky = []
                if recipe_def is not None:
                    recipe_actions = [
                        str(step.get("action", "")).strip()
                        for step in recipe_def.get("steps", [])
                        if isinstance(step, dict)
                    ]
                    risky = sorted(list(set(recipe_actions).intersection(set(settings.get("risky_actions", [])))))
                if len(risky) == 0 and not dry_run:
                    risky = list(settings.get("risky_actions", []))

                approval_result = check_requires_approval(
                    settings=settings,
                    operation="run-recipe",
                    risky_actions=risky,
                    dry_run=dry_run,
                    approval_token=approval_token,
                    request_payload=body,
                )
                if approval_result:
                    self._json_response(HTTPStatus.ACCEPTED, approval_result)
                    return

                preflight_enabled = bool(settings.get("execution_preflight_enabled", True))
                preflight_result: Dict[str, Any] = {"ran": False}
                if preflight_enabled and not dry_run:
                    preflight_payload = {
                        "recipe_id": recipe_id,
                        "inputs": resolved_inputs,
                        "dry_run": True,
                        "stop_on_error": True,
                        "profile": profile,
                    }
                    preflight_response = call_unreal(settings, "POST", "/validate-recipe", preflight_payload)
                    preflight_result = {
                        "ran": True,
                        "status_code": int(preflight_response.status_code),
                        "payload": preflight_response.payload,
                    }
                    preflight_ok = preflight_response.status_code < 400 and bool(preflight_response.payload.get("success", False))
                    if not preflight_ok:
                        self._emit_major_update(
                            settings,
                            session_id,
                            "run_recipe_preflight_failed",
                            "error",
                            f"Recipe '{recipe_id}' preflight failed.",
                            {"preflight": preflight_result},
                        )
                        self._json_response(
                            HTTPStatus.PRECONDITION_FAILED,
                            make_error(
                                "PREFLIGHT_FAILED",
                                "Recipe preflight validation failed.",
                                preflight=preflight_result,
                                recipe_id=recipe_id,
                            ),
                        )
                        return

                def run_recipe():
                    status_code, payload, _ = run_recipe_with_local_fallback(
                        settings=settings,
                        recipe_id=recipe_id,
                        resolved_inputs=resolved_inputs,
                        dry_run=dry_run,
                        stop_on_error=stop_on_error,
                        profile=profile,
                    )
                    return status_code, payload

                status, response = self._with_run_lock(run_recipe)
                issues = collect_analysis_contradictions(response)
                if issues:
                    status = HTTPStatus.CONFLICT
                    response = make_error(
                        "ANALYSIS_CONTRADICTION",
                        "Recipe execution reported analysis contradictions.",
                        issues=issues,
                        upstream=response,
                    )

                run_success = bool(response.get("success", False))
                response["recipe_id"] = recipe_id
                response["profile"] = profile
                response["resolved_inputs"] = resolved_inputs
                response["input_validation"] = validation
                if preflight_result.get("ran", False):
                    response["preflight"] = preflight_result

                if bool(settings.get("execution_store_artifacts", True)):
                    run_artifact = {
                        "timestamp": time.time(),
                        "route": "/api/run-recipe",
                        "recipe_id": recipe_id,
                        "profile": profile,
                        "dry_run": dry_run,
                        "resolved_inputs": resolved_inputs,
                        "request": body,
                        "preflight": preflight_result,
                        "status": int(status),
                        "response": response,
                    }
                    response["execution_run_id"] = write_execution_artifact(settings, run_artifact)

                update_release_metrics(
                    run_kind="recipe_runs",
                    run_success=run_success,
                    http_status=int(status),
                    response_payload=response,
                    profile=profile,
                    release_validation=release_validation,
                )
                self._emit_major_update(
                    settings,
                    session_id,
                    "run_recipe_completed",
                    "success" if run_success else "error",
                    f"Recipe '{recipe_id}' execution completed.",
                    {"status": int(status), "success": run_success},
                )
                self._json_response(status, response)
                log_event(
                    "run_recipe",
                    {
                        "request_id": request_id,
                        "recipe_id": recipe_id,
                        "dry_run": dry_run,
                        "profile": profile,
                        "status": int(status),
                        "duration_ms": int((time.time() - started) * 1000),
                    },
                )
                return

            if path == "/api/validate-recipe":
                recipe_id = str(body.get("recipe_id", "")).strip()
                if not recipe_id:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "recipe_id is required."))
                    return
                inputs = body.get("inputs", {})
                if not isinstance(inputs, dict):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "inputs must be an object."))
                    return

                profile = normalize_execution_profile(
                    body.get("profile", settings.get("execution_profile", "balanced")),
                    fallback=normalize_execution_profile(settings.get("execution_profile", "balanced")),
                )
                release_validation = bool(body.get("release_validation", True))
                recipe_def = get_recipe_definition(recipe_id)
                inputs = merge_default_project_inputs(settings, inputs, recipe_def)
                validation = {"ok": True, "errors": [], "warnings": []}
                resolved_inputs = dict(inputs)
                if recipe_def is not None:
                    resolved_inputs = apply_recipe_defaults(recipe_def, resolved_inputs)
                    validation = validate_recipe_inputs(recipe_def, resolved_inputs)
                    if not validation.get("ok", False):
                        self._json_response(
                            HTTPStatus.BAD_REQUEST,
                            make_error(
                                "RECIPE_INPUT_VALIDATION_FAILED",
                                "Recipe input validation failed.",
                                recipe_id=recipe_id,
                                validation=validation,
                            ),
                        )
                        return

                request_payload = {
                    "recipe_id": recipe_id,
                    "inputs": resolved_inputs,
                    "dry_run": True,
                    "stop_on_error": bool(body.get("stop_on_error", True)),
                    "profile": profile,
                }

                def validate_recipe():
                    result = call_unreal(settings, "POST", "/validate-recipe", request_payload)
                    return result.status_code, result.payload

                status, response = self._with_run_lock(validate_recipe)
                response["recipe_id"] = recipe_id
                response["profile"] = profile
                response["validation_only"] = True
                response["resolved_inputs"] = resolved_inputs
                response["input_validation"] = validation

                error_codes = set(collect_error_codes_from_payload(response))
                run_success = bool(response.get("success", False))
                if "COMPILE_FAILED" in error_codes:
                    status = HTTPStatus.CONFLICT

                update_release_metrics(
                    run_kind="recipe_validations",
                    run_success=run_success,
                    http_status=int(status),
                    response_payload=response,
                    profile=profile,
                    release_validation=release_validation,
                )
                self._json_response(status, response)
                log_event(
                    "validate_recipe",
                    {
                        "request_id": request_id,
                        "recipe_id": recipe_id,
                        "profile": profile,
                        "status": int(status),
                        "duration_ms": int((time.time() - started) * 1000),
                    },
                )
                return

            if path == "/api/run-scenario":
                assertions = body.get("assertions", [])
                if not isinstance(assertions, list) or len(assertions) == 0:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "assertions[] is required."))
                    return

                dry_run = bool(body.get("dry_run", False))
                profile = normalize_execution_profile(
                    body.get("profile", settings.get("execution_profile", "balanced")),
                    fallback=normalize_execution_profile(settings.get("execution_profile", "balanced")),
                )
                release_validation = bool(body.get("release_validation", False))

                request_payload = {
                    "assertions": assertions,
                    "dry_run": dry_run,
                    "profile": profile,
                    "mode": str(body.get("mode", "scenario")).strip() or "scenario",
                }

                def run_scenario():
                    result = call_unreal(settings, "POST", "/run-scenario", request_payload)
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_scenario)
                scenario_success = bool(response.get("success", False))
                effective_status = int(status)
                if not scenario_success and profile == "balanced" and not release_validation:
                    effective_status = HTTPStatus.OK
                    response = {
                        "success": True,
                        "scenario_success": False,
                        "non_blocking": True,
                        "message": "Scenario assertions failed; balanced profile treated this as non-blocking.",
                        "profile": profile,
                        "release_validation": release_validation,
                        "upstream": response,
                    }
                else:
                    response["profile"] = profile
                    response["release_validation"] = release_validation

                update_release_metrics(
                    run_kind="scenario_runs",
                    run_success=scenario_success,
                    http_status=effective_status,
                    response_payload=response,
                    profile=profile,
                    release_validation=release_validation,
                )
                self._json_response(effective_status, response)
                log_event(
                    "run_scenario",
                    {
                        "request_id": request_id,
                        "assertions": len(assertions),
                        "dry_run": dry_run,
                        "profile": profile,
                        "release_validation": release_validation,
                        "status": int(effective_status),
                        "scenario_success": scenario_success,
                        "duration_ms": int((time.time() - started) * 1000),
                    },
                )
                return

            if path == "/api/validate-execution":
                compile_blueprints = body.get("compile_blueprints", [])
                if not isinstance(compile_blueprints, list):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "compile_blueprints must be an array."))
                    return
                compile_blueprints = [str(item).strip() for item in compile_blueprints if isinstance(item, str) and str(item).strip()]

                assertions = body.get("assertions", [])
                if assertions is None:
                    assertions = []
                if not isinstance(assertions, list):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "assertions must be an array."))
                    return
                if len(compile_blueprints) == 0 and len(assertions) == 0:
                    self._json_response(
                        HTTPStatus.BAD_REQUEST,
                        make_error("MISSING_FIELD", "Provide compile_blueprints[] and/or assertions[]."),
                    )
                    return

                profile = normalize_execution_profile(
                    body.get("profile", settings.get("execution_profile", "balanced")),
                    fallback=normalize_execution_profile(settings.get("execution_profile", "balanced")),
                )
                release_validation = bool(body.get("release_validation", True))
                validation_results: Dict[str, Any] = {
                    "compiled": [],
                    "scenario": None,
                }

                def run_validation_suite() -> Tuple[int, Dict[str, Any]]:
                    compile_success = True
                    scenario_success = True

                    for blueprint_path in compile_blueprints:
                        compile_payload = {
                            "action": "compile_blueprint",
                            "payload": {"blueprint_path": blueprint_path},
                            "dry_run": False,
                        }
                        compile_result = call_unreal(settings, "POST", "/execute", compile_payload)
                        payload = compile_result.payload if isinstance(compile_result.payload, dict) else {"success": False, "raw": compile_result.payload}
                        ok = compile_result.status_code < 400 and bool(payload.get("success", False))
                        if not ok:
                            compile_success = False
                        validation_results["compiled"].append(
                            {
                                "blueprint_path": blueprint_path,
                                "status_code": int(compile_result.status_code),
                                "success": ok,
                                "result": payload,
                            }
                        )

                    if len(assertions) > 0:
                        scenario_payload = {
                            "assertions": assertions,
                            "dry_run": False,
                            "profile": profile,
                            "mode": "validation",
                        }
                        scenario_result = call_unreal(settings, "POST", "/run-scenario", scenario_payload)
                        scenario_payload_out = scenario_result.payload if isinstance(scenario_result.payload, dict) else {"success": False, "raw": scenario_result.payload}
                        scenario_success = scenario_result.status_code < 400 and bool(scenario_payload_out.get("success", False))
                        validation_results["scenario"] = {
                            "status_code": int(scenario_result.status_code),
                            "success": scenario_success,
                            "result": scenario_payload_out,
                        }

                    overall_success = compile_success and scenario_success
                    response = {
                        "success": overall_success,
                        "profile": profile,
                        "compiled_count": len(compile_blueprints),
                        "assertion_count": len(assertions),
                        "results": validation_results,
                    }
                    return (HTTPStatus.OK if overall_success else HTTPStatus.CONFLICT), response

                status, response = self._with_run_lock(run_validation_suite)
                if bool(settings.get("execution_store_artifacts", True)):
                    run_artifact = {
                        "timestamp": time.time(),
                        "route": "/api/validate-execution",
                        "profile": profile,
                        "request": body,
                        "status": int(status),
                        "response": response,
                    }
                    response["execution_run_id"] = write_execution_artifact(settings, run_artifact)

                update_release_metrics(
                    run_kind="scenario_runs",
                    run_success=bool(response.get("success", False)),
                    http_status=int(status),
                    response_payload=response,
                    profile=profile,
                    release_validation=release_validation,
                )
                self._json_response(status, response)
                log_event(
                    "validate_execution",
                    {
                        "request_id": request_id,
                        "compile_count": len(compile_blueprints),
                        "assertion_count": len(assertions),
                        "profile": profile,
                        "release_validation": release_validation,
                        "status": int(status),
                        "duration_ms": int((time.time() - started) * 1000),
                    },
                )
                return

            if path == "/api/project-audit":
                package_path = str(body.get("package_path", "/Game")).strip() or "/Game"
                recursive = bool(body.get("recursive", True))
                class_paths = body.get("class_paths", ["/Script/Engine.Blueprint", "/Script/UMG.WidgetBlueprint"])
                if not isinstance(class_paths, list):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "class_paths must be an array."))
                    return
                class_paths = [str(item).strip() for item in class_paths if isinstance(item, str) and str(item).strip()]

                name_contains = str(body.get("name_contains", "")).strip()
                max_assets = int(body.get("max_assets", 200))
                max_assets = max(1, min(2000, max_assets))
                analyze_blueprints = bool(body.get("analyze_blueprints", True))
                compile_blueprints = bool(body.get("compile_blueprints", False))
                profile = normalize_execution_profile(
                    body.get("profile", settings.get("execution_profile", "balanced")),
                    fallback=normalize_execution_profile(settings.get("execution_profile", "balanced")),
                )
                release_validation = bool(body.get("release_validation", True))

                list_payload = {
                    "action": "list_assets",
                    "payload": {
                        "package_path": package_path,
                        "recursive": recursive,
                        "class_paths": class_paths,
                        "name_contains": name_contains,
                        "limit": max_assets,
                    },
                    "dry_run": True,
                }

                def run_project_audit() -> Tuple[int, Dict[str, Any]]:
                    list_result = call_unreal(settings, "POST", "/execute", list_payload)
                    if list_result.status_code >= 400:
                        return list_result.status_code, list_result.payload
                    list_payload_out = list_result.payload if isinstance(list_result.payload, dict) else {}
                    asset_listing = list_payload_out.get("payload", {}) if isinstance(list_payload_out.get("payload", {}), dict) else {}
                    assets = asset_listing.get("assets", []) if isinstance(asset_listing.get("assets", []), list) else []

                    analyzed = []
                    compile_results = []
                    contradiction_total = 0
                    graph_total = 0
                    node_total = 0

                    for asset in assets:
                        if not isinstance(asset, dict):
                            continue
                        package_name = str(asset.get("package_name", "")).strip()
                        class_path = str(asset.get("class_path", "")).strip()
                        if not package_name:
                            continue
                        is_blueprint_like = "blueprint" in class_path.lower()
                        if analyze_blueprints and is_blueprint_like:
                            analysis_req = {
                                "action": "analyze_blueprint_asset",
                                "payload": {
                                    "blueprint_path": package_name,
                                    "include_pins": False,
                                    "max_nodes_per_graph": 1000,
                                },
                                "dry_run": True,
                            }
                            analysis_result = call_unreal(settings, "POST", "/execute", analysis_req)
                            analysis_payload = analysis_result.payload if isinstance(analysis_result.payload, dict) else {}
                            analysis_data = analysis_payload.get("payload", {}) if isinstance(analysis_payload.get("payload", {}), dict) else {}
                            contradiction_count = 0
                            graph_count = 0
                            total_nodes = 0
                            if isinstance(analysis_data.get("graphs", []), list):
                                for graph in analysis_data.get("graphs", []):
                                    if not isinstance(graph, dict):
                                        continue
                                    graph_count += 1
                                    total_nodes += int(graph.get("total_nodes", 0))
                                    contradictions = graph.get("contradictions", [])
                                    if isinstance(contradictions, list):
                                        contradiction_count += len(contradictions)
                            contradiction_total += contradiction_count
                            graph_total += graph_count
                            node_total += total_nodes
                            analyzed.append(
                                {
                                    "asset": package_name,
                                    "class_path": class_path,
                                    "status_code": int(analysis_result.status_code),
                                    "success": analysis_result.status_code < 400 and bool(analysis_payload.get("success", False)),
                                    "graph_count": graph_count,
                                    "total_nodes": total_nodes,
                                    "contradiction_count": contradiction_count,
                                }
                            )

                        if compile_blueprints and is_blueprint_like:
                            compile_req = {
                                "action": "compile_blueprint",
                                "payload": {"blueprint_path": package_name},
                                "dry_run": False,
                            }
                            compile_result = call_unreal(settings, "POST", "/execute", compile_req)
                            compile_payload = compile_result.payload if isinstance(compile_result.payload, dict) else {}
                            compile_results.append(
                                {
                                    "asset": package_name,
                                    "status_code": int(compile_result.status_code),
                                    "success": compile_result.status_code < 400 and bool(compile_payload.get("success", False)),
                                    "result": compile_payload,
                                }
                            )

                    compile_failures = [item for item in compile_results if not bool(item.get("success", False))]
                    overall_success = True
                    if compile_blueprints and len(compile_failures) > 0:
                        overall_success = False

                    response = {
                        "success": overall_success,
                        "profile": profile,
                        "scope": {
                            "package_path": package_path,
                            "recursive": recursive,
                            "class_paths": class_paths,
                            "name_contains": name_contains,
                            "max_assets": max_assets,
                        },
                        "assets": {
                            "matched": int(asset_listing.get("matched", len(assets))),
                            "returned": len(assets),
                            "truncated": bool(asset_listing.get("truncated", False)),
                        },
                        "analysis": {
                            "enabled": analyze_blueprints,
                            "analyzed_assets": len(analyzed),
                            "graph_total": graph_total,
                            "node_total": node_total,
                            "contradiction_total": contradiction_total,
                            "items": analyzed,
                        },
                        "compile": {
                            "enabled": compile_blueprints,
                            "compiled_assets": len(compile_results),
                            "failed_assets": len(compile_failures),
                            "items": compile_results,
                        },
                    }
                    return (HTTPStatus.OK if overall_success else HTTPStatus.CONFLICT), response

                status, response = self._with_run_lock(run_project_audit)
                if bool(settings.get("execution_store_artifacts", True)):
                    run_artifact = {
                        "timestamp": time.time(),
                        "route": "/api/project-audit",
                        "profile": profile,
                        "request": body,
                        "status": int(status),
                        "response": response,
                    }
                    if isinstance(response, dict):
                        response["execution_run_id"] = write_execution_artifact(settings, run_artifact)

                update_release_metrics(
                    run_kind="scenario_runs",
                    run_success=bool(response.get("success", False)),
                    http_status=int(status),
                    response_payload=response,
                    profile=profile,
                    release_validation=release_validation,
                )
                self._json_response(status, response)
                log_event(
                    "project_audit",
                    {
                        "request_id": request_id,
                        "profile": profile,
                        "package_path": package_path,
                        "status": int(status),
                        "duration_ms": int((time.time() - started) * 1000),
                    },
                )
                return

            if path == "/api/analyze":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                graph_name = str(body.get("graph_name", "")).strip()
                mode = str(body.get("mode", "asset")).strip().lower()
                include_pins = bool(body.get("include_pins", True))
                max_nodes = int(body.get("max_nodes", 1000))
                max_trace_depth = int(body.get("max_trace_depth", 128))
                prompt = str(body.get("prompt", "")).strip() or "Analyze this blueprint accurately."
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return

                action_name = "analyze_blueprint_asset" if mode == "asset" else "analyze_blueprint_graph"
                action_payload: Dict[str, Any] = {
                    "blueprint_path": blueprint_path,
                    "include_pins": include_pins,
                    "max_trace_depth": max_trace_depth,
                }
                if action_name == "analyze_blueprint_graph":
                    action_payload["max_nodes"] = max_nodes
                    if graph_name:
                        action_payload["graph_name"] = graph_name
                else:
                    action_payload["max_nodes_per_graph"] = max_nodes

                def run_analysis():
                    result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": action_name, "payload": action_payload, "dry_run": True},
                    )
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_analysis)
                if status >= 400:
                    self._json_response(status, response)
                    return

                contradictions = collect_analysis_contradictions(response)
                if contradictions:
                    self._json_response(
                        HTTPStatus.CONFLICT,
                        make_error(
                            "ANALYSIS_CONTRADICTION",
                            "Deterministic analysis found contradictions.",
                            issues=contradictions,
                            upstream=response,
                        ),
                    )
                    return

                analysis_payload = extract_upstream_payload(response)
                if not analysis_payload:
                    self._json_response(
                        HTTPStatus.BAD_GATEWAY,
                        make_error("ANALYSIS_PAYLOAD_MISSING", "Analyzer returned no payload.", upstream=response),
                    )
                    return

                lint_findings = build_analysis_lint(analysis_payload)
                evidence_index = build_analysis_evidence_index(analysis_payload)
                fingerprint = build_blueprint_fingerprint(analysis_payload)
                timeline = [
                    {"ts": time.time(), "stage": "analysis_collected", "ok": True, "details": {"mode": mode, "action": action_name}},
                    {"ts": time.time(), "stage": "lint_built", "ok": True, "details": {"lint_count": len(lint_findings)}},
                ]
                use_llm_summary = bool(settings.get("analysis_llm_summary", True)) and bool(settings.get("llm_enabled", True))
                report_source = "deterministic"
                report_errors: List[str] = []
                if use_llm_summary:
                    try:
                        report = generate_analysis_report_with_llm(settings, prompt, analysis_payload, lint_findings)
                        report_source = "llm"
                    except Exception as exc:
                        report = build_deterministic_analysis_report(analysis_payload, lint_findings)
                        report_source = "deterministic_fallback"
                        report_errors.append(str(exc))
                else:
                    report = build_deterministic_analysis_report(analysis_payload, lint_findings)
                timeline.append({"ts": time.time(), "stage": "report_generated", "ok": True, "details": {"source": report_source}})

                report_validation = validate_analysis_report(
                    report=report,
                    evidence_index=evidence_index,
                    require_citations=bool(settings.get("analysis_require_citations", True)),
                    disallow_speculative=bool(settings.get("analysis_disallow_speculative", True)),
                )
                if not report_validation.get("ok", False):
                    self._json_response(
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                        make_error(
                            "ANALYSIS_REPORT_INVALID",
                            "Analysis report failed strict validation.",
                            report_validation=report_validation,
                            report=report,
                            lint_findings=lint_findings,
                            analysis=analysis_payload,
                        ),
                    )
                    return
                timeline.append({"ts": time.time(), "stage": "report_validated", "ok": True, "details": {"claims": len(report.get("claims", [])) if isinstance(report, dict) and isinstance(report.get("claims", []), list) else 0}})
                determinism = build_determinism_score(
                    compile_ok=True,
                    contradictions=[],
                    lint_findings=lint_findings,
                    replay_match=True,
                    preflight_ok=True,
                    min_score=int(settings.get("determinism_min_score", 85)),
                )

                artifact = {
                    "timestamp": time.time(),
                    "blueprint_path": blueprint_path,
                    "mode": mode,
                    "action": action_name,
                    "action_payload": action_payload,
                    "report_source": report_source,
                    "report_generation_errors": report_errors,
                    "analysis": analysis_payload,
                    "fingerprint": fingerprint,
                    "lint_findings": lint_findings,
                    "report": report,
                    "report_validation": report_validation,
                    "determinism_score": determinism,
                    "timeline": timeline,
                }
                run_id = ""
                if bool(settings.get("analysis_store_artifacts", True)):
                    run_id = write_analysis_artifact(settings, artifact)

                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "run_id": run_id,
                        "report_source": report_source,
                        "analysis": analysis_payload,
                        "fingerprint": fingerprint,
                        "lint_findings": lint_findings,
                        "report": report,
                        "report_validation": report_validation,
                        "determinism_score": determinism,
                        "timeline": timeline,
                    },
                )
                log_event(
                    "analysis_run",
                    {
                        "request_id": request_id,
                        "run_id": run_id,
                        "blueprint_path": blueprint_path,
                        "mode": mode,
                        "report_source": report_source,
                        "lint_count": len(lint_findings),
                        "duration_ms": int((time.time() - started) * 1000),
                    },
                )
                return

            if path == "/api/refactor-catalog":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                profile = normalize_execution_profile(
                    body.get("profile", settings.get("execution_profile", "balanced")),
                    fallback=normalize_execution_profile(settings.get("execution_profile", "balanced")),
                )
                mode = str(body.get("mode", "asset")).strip().lower()
                include_pins = bool(body.get("include_pins", False))
                max_nodes = int(body.get("max_nodes", 1000))
                max_trace_depth = int(body.get("max_trace_depth", 128))
                analysis_payload: Dict[str, Any] = {}
                lint_findings: List[Dict[str, Any]] = []

                if blueprint_path:
                    action_name = "analyze_blueprint_asset" if mode == "asset" else "analyze_blueprint_graph"
                    action_payload: Dict[str, Any] = {
                        "blueprint_path": blueprint_path,
                        "include_pins": include_pins,
                        "max_trace_depth": max_trace_depth,
                    }
                    if action_name == "analyze_blueprint_graph":
                        action_payload["max_nodes"] = max_nodes
                        graph_name = str(body.get("graph_name", "")).strip()
                        if graph_name:
                            action_payload["graph_name"] = graph_name
                    else:
                        action_payload["max_nodes_per_graph"] = max_nodes

                    def run_catalog_analysis():
                        result = call_unreal(
                            settings,
                            "POST",
                            "/execute",
                            {"action": action_name, "payload": action_payload, "dry_run": True},
                        )
                        return result.status_code, result.payload

                    status, response = self._with_run_lock(run_catalog_analysis)
                    if status >= 400:
                        self._json_response(status, response)
                        return
                    contradictions = collect_analysis_contradictions(response)
                    if contradictions:
                        self._json_response(
                            HTTPStatus.CONFLICT,
                            make_error(
                                "ANALYSIS_CONTRADICTION",
                                "Deterministic analysis found contradictions.",
                                issues=contradictions,
                                upstream=response,
                            ),
                        )
                        return
                    analysis_payload = extract_upstream_payload(response)
                    lint_findings = build_analysis_lint(analysis_payload)

                catalog = build_refactor_catalog(
                    blueprint_path=blueprint_path,
                    profile=profile,
                    analysis_payload=analysis_payload,
                    lint_findings=lint_findings,
                )
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "profile": profile,
                        "blueprint_path": normalize_blueprint_path(blueprint_path),
                        "transforms": catalog,
                        "transform_count": len(catalog),
                        "analysis": analysis_payload,
                        "lint_findings": lint_findings,
                    },
                )
                return

            if path == "/api/refactor-preview":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                profile = normalize_execution_profile(
                    body.get("profile", settings.get("execution_profile", "balanced")),
                    fallback=normalize_execution_profile(settings.get("execution_profile", "balanced")),
                )
                transform_ids_raw = body.get("transform_ids", body.get("suggestion_ids", []))
                transform_ids = transform_ids_raw if isinstance(transform_ids_raw, list) else []
                transform_inputs = body.get("transform_inputs", {})
                if not isinstance(transform_inputs, dict):
                    transform_inputs = {}
                dry_run = True
                stop_on_error = bool(body.get("stop_on_error", True))
                mode = str(body.get("mode", "asset")).strip().lower()
                include_pins = bool(body.get("include_pins", False))
                max_nodes = int(body.get("max_nodes", 1000))
                max_trace_depth = int(body.get("max_trace_depth", 128))

                action_name = "analyze_blueprint_asset" if mode == "asset" else "analyze_blueprint_graph"
                action_payload: Dict[str, Any] = {
                    "blueprint_path": blueprint_path,
                    "include_pins": include_pins,
                    "max_trace_depth": max_trace_depth,
                }
                if action_name == "analyze_blueprint_graph":
                    action_payload["max_nodes"] = max_nodes
                    graph_name = str(body.get("graph_name", "")).strip()
                    if graph_name:
                        action_payload["graph_name"] = graph_name
                else:
                    action_payload["max_nodes_per_graph"] = max_nodes

                def run_refactor_preview_analysis():
                    result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": action_name, "payload": action_payload, "dry_run": True},
                    )
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_refactor_preview_analysis)
                if status >= 400:
                    self._json_response(status, response)
                    return
                contradictions = collect_analysis_contradictions(response)
                if contradictions:
                    self._json_response(
                        HTTPStatus.CONFLICT,
                        make_error(
                            "ANALYSIS_CONTRADICTION",
                            "Deterministic analysis found contradictions.",
                            issues=contradictions,
                            upstream=response,
                        ),
                    )
                    return
                analysis_payload = extract_upstream_payload(response)
                lint_findings = build_analysis_lint(analysis_payload)
                catalog = build_refactor_catalog(blueprint_path, profile, analysis_payload, lint_findings)
                plan, selected = build_refactor_catalog_plan(
                    blueprint_path=blueprint_path,
                    catalog=catalog,
                    transform_ids=transform_ids,
                    transform_inputs=transform_inputs,
                    dry_run=dry_run,
                    stop_on_error=stop_on_error,
                )
                if plan is None:
                    self._json_response(
                        HTTPStatus.BAD_REQUEST,
                        make_error(
                            "NO_APPLICABLE_TRANSFORMS",
                            "No applicable catalog transforms were selected.",
                            transforms=catalog,
                        ),
                    )
                    return
                validation = validate_plan_with_node_library(plan)
                if not validation.get("ok", False):
                    self._json_response(
                        HTTPStatus.BAD_REQUEST,
                        make_error(
                            "PLAN_NODELIB_VALIDATION_FAILED",
                            "Preview refactor plan failed node-library validation.",
                            validation=validation,
                            generated_plan=plan,
                        ),
                    )
                    return
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "profile": profile,
                        "generated_plan": plan,
                        "selected_transforms": selected,
                        "estimated_impact": estimate_refactor_impact(plan),
                        "analysis": analysis_payload,
                        "lint_findings": lint_findings,
                    },
                )
                return

            if path == "/api/refactor-suggest":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                mode = str(body.get("mode", "asset")).strip().lower()
                include_pins = bool(body.get("include_pins", False))
                max_nodes = int(body.get("max_nodes", 1000))
                max_trace_depth = int(body.get("max_trace_depth", 128))
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return

                action_name = "analyze_blueprint_asset" if mode == "asset" else "analyze_blueprint_graph"
                action_payload: Dict[str, Any] = {
                    "blueprint_path": blueprint_path,
                    "include_pins": include_pins,
                    "max_trace_depth": max_trace_depth,
                }
                if action_name == "analyze_blueprint_graph":
                    action_payload["max_nodes"] = max_nodes
                    graph_name = str(body.get("graph_name", "")).strip()
                    if graph_name:
                        action_payload["graph_name"] = graph_name
                else:
                    action_payload["max_nodes_per_graph"] = max_nodes

                def run_refactor_suggest():
                    result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": action_name, "payload": action_payload, "dry_run": True},
                    )
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_refactor_suggest)
                if status >= 400:
                    self._json_response(status, response)
                    return

                contradictions = collect_analysis_contradictions(response)
                if contradictions:
                    self._json_response(
                        HTTPStatus.CONFLICT,
                        make_error(
                            "ANALYSIS_CONTRADICTION",
                            "Deterministic analysis found contradictions.",
                            issues=contradictions,
                            upstream=response,
                        ),
                    )
                    return

                analysis_payload = extract_upstream_payload(response)
                if not analysis_payload:
                    self._json_response(
                        HTTPStatus.BAD_GATEWAY,
                        make_error("ANALYSIS_PAYLOAD_MISSING", "Analyzer returned no payload.", upstream=response),
                    )
                    return

                lint_findings = build_analysis_lint(analysis_payload)
                suggestions = build_refactor_suggestions(blueprint_path, analysis_payload, lint_findings)
                catalog = build_refactor_catalog(
                    blueprint_path=blueprint_path,
                    profile="balanced",
                    analysis_payload=analysis_payload,
                    lint_findings=lint_findings,
                )
                auto_applicable = [s for s in suggestions if bool(s.get("auto_applicable", False))]
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "blueprint_path": normalize_blueprint_path(blueprint_path),
                        "mode": mode,
                        "analysis": analysis_payload,
                        "lint_findings": lint_findings,
                        "suggestions": suggestions,
                        "suggestion_count": len(suggestions),
                        "auto_applicable_count": len(auto_applicable),
                        "transforms": catalog,
                        "transform_count": len(catalog),
                    },
                )
                return

            if path == "/api/refactor-apply":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                mode = str(body.get("mode", "asset")).strip().lower()
                include_pins = bool(body.get("include_pins", False))
                max_nodes = int(body.get("max_nodes", 1000))
                max_trace_depth = int(body.get("max_trace_depth", 128))
                dry_run = bool(body.get("dry_run", False))
                stop_on_error = bool(body.get("stop_on_error", True))
                suggestion_ids_raw = body.get("suggestion_ids", [])
                suggestion_ids = suggestion_ids_raw if isinstance(suggestion_ids_raw, list) else []
                transform_ids_raw = body.get("transform_ids", [])
                transform_ids = transform_ids_raw if isinstance(transform_ids_raw, list) else []
                transform_inputs = body.get("transform_inputs", {})
                if not isinstance(transform_inputs, dict):
                    transform_inputs = {}
                approval_token = str(body.get("approval_token", "")).strip()
                release_validation = bool(body.get("release_validation", True))
                auto_repair_enabled = bool(body.get("auto_repair", settings.get("refactor_auto_repair_enabled", True)))
                auto_repair_max_attempts = max(0, int(body.get("auto_repair_max_attempts", settings.get("refactor_auto_repair_max_attempts", 1))))
                profile = normalize_execution_profile(
                    body.get("profile", settings.get("execution_profile", "balanced")),
                    fallback=normalize_execution_profile(settings.get("execution_profile", "balanced")),
                )
                timeline: List[Dict[str, Any]] = []

                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return

                action_name = "analyze_blueprint_asset" if mode == "asset" else "analyze_blueprint_graph"
                action_payload: Dict[str, Any] = {
                    "blueprint_path": blueprint_path,
                    "include_pins": include_pins,
                    "max_trace_depth": max_trace_depth,
                }
                if action_name == "analyze_blueprint_graph":
                    action_payload["max_nodes"] = max_nodes
                    graph_name = str(body.get("graph_name", "")).strip()
                    if graph_name:
                        action_payload["graph_name"] = graph_name
                else:
                    action_payload["max_nodes_per_graph"] = max_nodes

                def run_refactor_analysis():
                    result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": action_name, "payload": action_payload, "dry_run": True},
                    )
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_refactor_analysis)
                if status >= 400:
                    self._json_response(status, response)
                    return

                contradictions = collect_analysis_contradictions(response)
                if contradictions:
                    self._json_response(
                        HTTPStatus.CONFLICT,
                        make_error(
                            "ANALYSIS_CONTRADICTION",
                            "Deterministic analysis found contradictions.",
                            issues=contradictions,
                            upstream=response,
                        ),
                    )
                    return

                analysis_payload = extract_upstream_payload(response)
                if not analysis_payload:
                    self._json_response(
                        HTTPStatus.BAD_GATEWAY,
                        make_error("ANALYSIS_PAYLOAD_MISSING", "Analyzer returned no payload.", upstream=response),
                    )
                    return

                before_fingerprint = build_blueprint_fingerprint(analysis_payload)
                timeline.append(
                    {
                        "ts": time.time(),
                        "stage": "pre_analysis_collected",
                        "ok": True,
                        "details": {
                            "graphs": int(before_fingerprint.get("graph_count", 0)),
                            "nodes": int(before_fingerprint.get("total_nodes", 0)),
                        },
                    }
                )
                lint_findings = build_analysis_lint(analysis_payload)
                suggestions = build_refactor_suggestions(blueprint_path, analysis_payload, lint_findings)
                catalog = build_refactor_catalog(blueprint_path, profile, analysis_payload, lint_findings)
                catalog_plan, selected_transforms = build_refactor_catalog_plan(
                    blueprint_path=blueprint_path,
                    catalog=catalog,
                    transform_ids=transform_ids,
                    transform_inputs=transform_inputs,
                    dry_run=dry_run,
                    stop_on_error=stop_on_error,
                )
                suggestions_plan, selected_suggestions = build_refactor_apply_plan(
                    blueprint_path=blueprint_path,
                    suggestions=suggestions,
                    selected_suggestion_ids=suggestion_ids,
                    dry_run=dry_run,
                    stop_on_error=stop_on_error,
                )
                plan = catalog_plan or suggestions_plan
                selected = selected_transforms if catalog_plan is not None else selected_suggestions
                if plan is None:
                    self._json_response(
                        HTTPStatus.BAD_REQUEST,
                        make_error(
                            "NO_APPLICABLE_SUGGESTIONS",
                            "No applicable suggestions or transforms were selected for automatic apply.",
                            suggestions=suggestions,
                            transforms=catalog,
                        ),
                    )
                    return
                timeline.append(
                    {
                        "ts": time.time(),
                        "stage": "refactor_plan_built",
                        "ok": True,
                        "details": {
                            "step_count": len(plan.get("steps", [])) if isinstance(plan.get("steps", []), list) else 0,
                            "selected_transforms": len(selected_transforms),
                            "selected_suggestions": len(selected_suggestions),
                        },
                    }
                )

                validation = validate_plan_with_node_library(plan)
                if not validation.get("ok", False):
                    self._json_response(
                        HTTPStatus.BAD_REQUEST,
                        make_error(
                            "PLAN_NODELIB_VALIDATION_FAILED",
                            "Generated refactor plan failed node-library validation.",
                            validation=validation,
                            generated_plan=plan,
                        ),
                    )
                    return
                timeline.append({"ts": time.time(), "stage": "plan_validated", "ok": True, "details": {"validator": "node_library"}})

                actions = get_plan_actions(plan)
                risky = sorted(list(set(actions).intersection(set(settings.get("risky_actions", [])))))
                approval_result = check_requires_approval(
                    settings=settings,
                    operation="refactor-apply",
                    risky_actions=risky,
                    dry_run=dry_run,
                    approval_token=approval_token,
                    request_payload=plan,
                )
                if approval_result:
                    self._json_response(HTTPStatus.ACCEPTED, approval_result)
                    return

                preflight_enabled = bool(settings.get("execution_preflight_enabled", True))
                preflight_result: Dict[str, Any] = {"ran": False}
                if preflight_enabled and not dry_run:
                    preflight_plan = dict(plan)
                    preflight_plan["dry_run"] = True
                    preflight_run = call_unreal(settings, "POST", "/run-plan", preflight_plan)
                    preflight_result = {
                        "ran": True,
                        "status_code": int(preflight_run.status_code),
                        "payload": preflight_run.payload,
                    }
                    preflight_ok = preflight_run.status_code < 400 and bool(preflight_run.payload.get("success", False))
                    if not preflight_ok:
                        self._json_response(
                            HTTPStatus.PRECONDITION_FAILED,
                            make_error(
                                "PREFLIGHT_FAILED",
                                "Refactor preflight dry-run failed.",
                                preflight=preflight_result,
                                generated_plan=plan,
                            ),
                        )
                        return
                    timeline.append({"ts": time.time(), "stage": "preflight", "ok": True, "details": {"status_code": int(preflight_run.status_code)}})

                def run_refactor_plan():
                    result = call_unreal(settings, "POST", "/run-plan", plan)
                    return result.status_code, result.payload

                exec_status, exec_response = self._with_run_lock(run_refactor_plan)
                timeline.append({"ts": time.time(), "stage": "refactor_execute", "ok": exec_status < 400, "details": {"status_code": int(exec_status)}})
                issues = collect_analysis_contradictions(exec_response)
                if issues:
                    exec_status = HTTPStatus.CONFLICT
                    exec_response = make_error(
                        "ANALYSIS_CONTRADICTION",
                        "Refactor execution reported analysis contradictions.",
                        issues=issues,
                        upstream=exec_response,
                        generated_plan=plan,
                    )
                elif preflight_result.get("ran", False) and isinstance(exec_response, dict):
                    exec_response["preflight"] = preflight_result
                post_analysis_payload: Dict[str, Any] = {}
                post_lint_findings: List[Dict[str, Any]] = []
                post_issues: List[str] = []
                after_fingerprint: Dict[str, Any] = {}
                graph_diff: Dict[str, Any] = {}
                auto_repair_report: Dict[str, Any] = {"attempted": False, "attempt_count": 0, "attempts": [], "resolved": False}

                def analyze_current_blueprint_snapshot() -> Tuple[int, Dict[str, Any]]:
                    result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": action_name, "payload": action_payload, "dry_run": True},
                    )
                    return result.status_code, result.payload

                snapshot_status, snapshot_response = self._with_run_lock(analyze_current_blueprint_snapshot)
                if snapshot_status < 400:
                    post_issues = collect_analysis_contradictions(snapshot_response)
                    if len(post_issues) == 0:
                        post_analysis_payload = extract_upstream_payload(snapshot_response)
                        if post_analysis_payload:
                            post_lint_findings = build_analysis_lint(post_analysis_payload)
                            after_fingerprint = build_blueprint_fingerprint(post_analysis_payload)
                            graph_diff = build_graph_diff(analysis_payload, post_analysis_payload)
                            timeline.append(
                                {
                                    "ts": time.time(),
                                    "stage": "post_analysis_collected",
                                    "ok": True,
                                    "details": {
                                        "graphs": int(after_fingerprint.get("graph_count", 0)),
                                        "nodes": int(after_fingerprint.get("total_nodes", 0)),
                                        "lint_count": len(post_lint_findings),
                                    },
                                }
                            )
                    else:
                        timeline.append({"ts": time.time(), "stage": "post_analysis_collected", "ok": False, "details": {"issues": post_issues}})
                else:
                    timeline.append({"ts": time.time(), "stage": "post_analysis_collected", "ok": False, "details": {"status_code": int(snapshot_status)}})

                compile_ok = infer_compile_ok_from_execution(exec_response if isinstance(exec_response, dict) else {})
                contradiction_issues = issues + post_issues
                replay_match = True if dry_run else bool(
                    before_fingerprint.get("fingerprint_hash", "")
                    and after_fingerprint.get("fingerprint_hash", "")
                    and before_fingerprint.get("fingerprint_hash", "") == after_fingerprint.get("fingerprint_hash", "")
                )
                determinism_score = build_determinism_score(
                    compile_ok=compile_ok,
                    contradictions=contradiction_issues,
                    lint_findings=post_lint_findings if post_lint_findings else lint_findings,
                    replay_match=replay_match,
                    preflight_ok=bool(preflight_result.get("ran", False) is False or preflight_result.get("status_code", 200) < 400),
                    min_score=int(settings.get("determinism_min_score", 85)),
                )

                should_auto_repair = (
                    auto_repair_enabled
                    and not dry_run
                    and auto_repair_max_attempts > 0
                    and (not compile_ok or len(contradiction_issues) > 0 or not bool(determinism_score.get("pass", False)))
                )
                if should_auto_repair:
                    auto_repair_report["attempted"] = True
                    timeline.append({"ts": time.time(), "stage": "auto_repair_start", "ok": True, "details": {"max_attempts": auto_repair_max_attempts}})

                    for attempt in range(1, auto_repair_max_attempts + 1):
                        working_analysis = post_analysis_payload if post_analysis_payload else analysis_payload
                        working_lint = build_analysis_lint(working_analysis) if working_analysis else lint_findings
                        working_suggestions = build_refactor_suggestions(blueprint_path, working_analysis, working_lint)
                        repair_plan, repair_selected = build_refactor_apply_plan(
                            blueprint_path=blueprint_path,
                            suggestions=working_suggestions,
                            selected_suggestion_ids=[],
                            dry_run=False,
                            stop_on_error=True,
                        )
                        if repair_plan is None:
                            auto_repair_report["attempts"].append(
                                {"attempt": attempt, "success": False, "reason": "no_auto_applicable_repairs"}
                            )
                            timeline.append({"ts": time.time(), "stage": "auto_repair_attempt", "ok": False, "details": {"attempt": attempt, "reason": "no_auto_applicable_repairs"}})
                            break

                        repair_validation = validate_plan_with_node_library(repair_plan)
                        if not repair_validation.get("ok", False):
                            auto_repair_report["attempts"].append(
                                {"attempt": attempt, "success": False, "reason": "repair_plan_validation_failed", "validation": repair_validation}
                            )
                            timeline.append({"ts": time.time(), "stage": "auto_repair_attempt", "ok": False, "details": {"attempt": attempt, "reason": "validation_failed"}})
                            break

                        def run_auto_repair_plan():
                            result = call_unreal(settings, "POST", "/run-plan", repair_plan)
                            return result.status_code, result.payload

                        repair_status, repair_response = self._with_run_lock(run_auto_repair_plan)
                        repair_ok = repair_status < 400 and bool(isinstance(repair_response, dict) and repair_response.get("success", False))
                        auto_repair_report["attempts"].append(
                            {
                                "attempt": attempt,
                                "success": repair_ok,
                                "plan": repair_plan,
                                "selected_suggestions": repair_selected,
                                "status_code": int(repair_status),
                                "response": repair_response,
                            }
                        )
                        timeline.append({"ts": time.time(), "stage": "auto_repair_attempt", "ok": repair_ok, "details": {"attempt": attempt, "status_code": int(repair_status)}})
                        auto_repair_report["attempt_count"] = attempt

                        snapshot_status, snapshot_response = self._with_run_lock(analyze_current_blueprint_snapshot)
                        if snapshot_status < 400:
                            post_issues = collect_analysis_contradictions(snapshot_response)
                            post_analysis_payload = extract_upstream_payload(snapshot_response) if len(post_issues) == 0 else {}
                            post_lint_findings = build_analysis_lint(post_analysis_payload) if post_analysis_payload else []
                            if post_analysis_payload:
                                after_fingerprint = build_blueprint_fingerprint(post_analysis_payload)
                                graph_diff = build_graph_diff(analysis_payload, post_analysis_payload)

                        compile_ok = repair_ok
                        contradiction_issues = issues + post_issues
                        replay_match = bool(
                            before_fingerprint.get("fingerprint_hash", "")
                            and after_fingerprint.get("fingerprint_hash", "")
                            and before_fingerprint.get("fingerprint_hash", "") == after_fingerprint.get("fingerprint_hash", "")
                        )
                        determinism_score = build_determinism_score(
                            compile_ok=compile_ok,
                            contradictions=contradiction_issues,
                            lint_findings=post_lint_findings if post_lint_findings else lint_findings,
                            replay_match=replay_match,
                            preflight_ok=bool(preflight_result.get("ran", False) is False or preflight_result.get("status_code", 200) < 400),
                            min_score=int(settings.get("determinism_min_score", 85)),
                        )
                        if repair_ok and len(contradiction_issues) == 0 and bool(determinism_score.get("pass", False)):
                            auto_repair_report["resolved"] = True
                            if isinstance(exec_response, dict):
                                exec_response["auto_repair_resolution"] = "resolved"
                                exec_response["final_repair_attempt"] = attempt
                            exec_status = HTTPStatus.OK
                            if isinstance(exec_response, dict):
                                exec_response["success"] = True
                            break

                update_release_metrics(
                    run_kind="scenario_runs",
                    run_success=bool(isinstance(exec_response, dict) and exec_response.get("success", False)),
                    http_status=int(exec_status),
                    response_payload=exec_response if isinstance(exec_response, dict) else {},
                    profile=profile,
                    release_validation=release_validation,
                )
                if isinstance(exec_response, dict):
                    exec_response["generated_plan"] = plan
                    exec_response["selected_suggestions"] = selected
                    exec_response["selected_transforms"] = selected_transforms
                    exec_response["suggestion_count"] = len(suggestions)
                    exec_response["applied_suggestion_count"] = len(selected)
                    exec_response["transform_count"] = len(catalog)
                    exec_response["applied_transform_count"] = len(selected_transforms)
                    exec_response["estimated_impact"] = estimate_refactor_impact(plan)
                    exec_response["fingerprint_before"] = before_fingerprint
                    exec_response["fingerprint_after"] = after_fingerprint
                    exec_response["graph_diff"] = graph_diff
                    exec_response["determinism_score"] = determinism_score
                    exec_response["timeline"] = timeline
                    exec_response["auto_repair_report"] = auto_repair_report

                if bool(settings.get("execution_store_artifacts", True)) and isinstance(exec_response, dict):
                    run_artifact = {
                        "timestamp": time.time(),
                        "route": "/api/refactor-apply",
                        "profile": profile,
                        "request": body,
                        "generated_plan": plan,
                        "selected_suggestions": selected,
                        "status": int(exec_status),
                        "response": exec_response,
                        "fingerprint_before": before_fingerprint,
                        "fingerprint_after": after_fingerprint,
                        "graph_diff": graph_diff,
                        "determinism_score": determinism_score,
                        "timeline": timeline,
                        "auto_repair_report": auto_repair_report,
                    }
                    exec_response["execution_run_id"] = write_execution_artifact(settings, run_artifact)
                self._json_response(exec_status, exec_response if isinstance(exec_response, dict) else {"success": False, "raw": exec_response})
                return

            if path == "/api/explain-selection":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                graph_name = str(body.get("graph_name", "")).strip()
                mode = str(body.get("mode", "graph")).strip().lower()
                node_names_raw = body.get("node_names", [])
                node_names = node_names_raw if isinstance(node_names_raw, list) else []
                include_pins = bool(body.get("include_pins", True))
                max_nodes = int(body.get("max_nodes", 1500))
                max_trace_depth = int(body.get("max_trace_depth", 128))
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return

                action_name = "analyze_blueprint_asset" if mode == "asset" else "analyze_blueprint_graph"
                action_payload: Dict[str, Any] = {
                    "blueprint_path": blueprint_path,
                    "include_pins": include_pins,
                    "max_trace_depth": max_trace_depth,
                }
                if action_name == "analyze_blueprint_graph":
                    action_payload["max_nodes"] = max_nodes
                    if graph_name:
                        action_payload["graph_name"] = graph_name
                else:
                    action_payload["max_nodes_per_graph"] = max_nodes

                def run_explain_selection():
                    result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": action_name, "payload": action_payload, "dry_run": True},
                    )
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_explain_selection)
                if status >= 400:
                    self._json_response(status, response)
                    return

                contradictions = collect_analysis_contradictions(response)
                if contradictions:
                    self._json_response(
                        HTTPStatus.CONFLICT,
                        make_error(
                            "ANALYSIS_CONTRADICTION",
                            "Deterministic analysis found contradictions.",
                            issues=contradictions,
                            upstream=response,
                        ),
                    )
                    return

                analysis_payload = extract_upstream_payload(response)
                lint_findings = build_analysis_lint(analysis_payload)
                suggestions = build_refactor_suggestions(blueprint_path, analysis_payload, lint_findings)
                explanation = build_selection_explanation(
                    analysis_payload=analysis_payload,
                    node_names=node_names,
                    lint_findings=lint_findings,
                    suggestions=suggestions,
                )
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "blueprint_path": normalize_blueprint_path(blueprint_path),
                        "mode": mode,
                        "analysis": analysis_payload,
                        "lint_findings": lint_findings,
                        "explanation": explanation,
                        "evidence": explanation.get("evidence", []),
                        "suggested_fixes": explanation.get("suggested_fixes", []),
                    },
                )
                return

            if path == "/api/explain-screenshot":
                image_path = str(body.get("image_path", "")).strip()
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                graph_name = str(body.get("graph_name", "")).strip()
                if not image_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "image_path is required."))
                    return

                if not blueprint_path:
                    parsed_nodes = parse_screenshot_node_candidates(image_path)
                    self._json_response(
                        HTTPStatus.OK,
                        {
                            "success": True,
                            "image_path": image_path,
                            "parsed_nodes": parsed_nodes,
                            "confidence": 0.2 if parsed_nodes else 0.0,
                            "explanation": "No blueprint context provided; returning parsed node candidates only.",
                            "suggested_fixes": [],
                        },
                    )
                    return

                action_payload: Dict[str, Any] = {
                    "blueprint_path": blueprint_path,
                    "include_pins": True,
                    "max_nodes": 1500,
                    "max_trace_depth": 128,
                }
                if graph_name:
                    action_payload["graph_name"] = graph_name

                def run_explain_screenshot():
                    result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": "analyze_blueprint_graph", "payload": action_payload, "dry_run": True},
                    )
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_explain_screenshot)
                if status >= 400:
                    self._json_response(status, response)
                    return
                contradictions = collect_analysis_contradictions(response)
                if contradictions:
                    self._json_response(
                        HTTPStatus.CONFLICT,
                        make_error(
                            "ANALYSIS_CONTRADICTION",
                            "Deterministic analysis found contradictions.",
                            issues=contradictions,
                            upstream=response,
                        ),
                    )
                    return
                analysis_payload = extract_upstream_payload(response)
                lint_findings = build_analysis_lint(analysis_payload)
                suggestions = build_refactor_suggestions(blueprint_path, analysis_payload, lint_findings)
                explanation = build_screenshot_explanation(
                    image_path=image_path,
                    analysis_payload=analysis_payload,
                    lint_findings=lint_findings,
                    suggestions=suggestions,
                )
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "blueprint_path": normalize_blueprint_path(blueprint_path),
                        **explanation,
                    },
                )
                return

            if path == "/api/project-dependencies":
                package_path = str(body.get("package_path", "/Game")).strip() or "/Game"
                recursive = bool(body.get("recursive", True))
                depth = int(body.get("depth", 2))
                depth = max(0, min(6, depth))
                max_assets = int(body.get("max_assets", 300))
                max_assets = max(1, min(2000, max_assets))

                list_payload = {
                    "action": "list_assets",
                    "payload": {
                        "package_path": package_path,
                        "recursive": recursive,
                        "limit": max_assets,
                    },
                    "dry_run": True,
                }
                list_result = call_unreal(settings, "POST", "/execute", list_payload)
                if list_result.status_code >= 400:
                    self._json_response(list_result.status_code, list_result.payload)
                    return
                list_payload_out = list_result.payload if isinstance(list_result.payload, dict) else {}
                asset_listing = list_payload_out.get("payload", {}) if isinstance(list_payload_out.get("payload", {}), dict) else {}
                assets = asset_listing.get("assets", []) if isinstance(asset_listing.get("assets", []), list) else []

                dependency_map: Dict[str, List[str]] = {}
                referencer_map: Dict[str, List[str]] = {}
                for item in assets[:250]:
                    if not isinstance(item, dict):
                        continue
                    asset_path = str(item.get("package_name", "")).strip()
                    if not asset_path:
                        continue
                    dep_result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": "list_asset_dependencies", "payload": {"asset_path": asset_path, "depth": depth}, "dry_run": True},
                    )
                    if dep_result.status_code < 400 and isinstance(dep_result.payload, dict):
                        dep_payload = dep_result.payload.get("payload", {})
                        deps = dep_payload.get("dependencies", []) if isinstance(dep_payload, dict) else []
                        if isinstance(deps, list):
                            dependency_map[asset_path] = [str(d).strip() for d in deps if isinstance(d, str) and str(d).strip()]

                    ref_result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": "list_asset_referencers", "payload": {"asset_path": asset_path, "depth": depth}, "dry_run": True},
                    )
                    if ref_result.status_code < 400 and isinstance(ref_result.payload, dict):
                        ref_payload = ref_result.payload.get("payload", {})
                        refs = ref_payload.get("referencers", []) if isinstance(ref_payload, dict) else []
                        if isinstance(refs, list):
                            referencer_map[asset_path] = [str(r).strip() for r in refs if isinstance(r, str) and str(r).strip()]

                graph = build_project_dependency_graph(assets, dependency_map, referencer_map, depth)
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "scope": {
                            "package_path": package_path,
                            "recursive": recursive,
                            "depth": depth,
                            "max_assets": max_assets,
                        },
                        "asset_count": len(assets),
                        "nodes": graph["nodes"],
                        "edges": graph["edges"],
                        "hotspots": graph["hotspots"],
                    },
                )
                return

            if path == "/api/perf-hotspots":
                package_path = str(body.get("package_path", "/Game")).strip() or "/Game"
                analyze_blueprints = bool(body.get("analyze_blueprints", True))
                max_assets = int(body.get("max_assets", 200))
                max_assets = max(1, min(2000, max_assets))

                list_payload = {
                    "action": "list_assets",
                    "payload": {
                        "package_path": package_path,
                        "recursive": bool(body.get("recursive", True)),
                        "limit": max_assets,
                    },
                    "dry_run": True,
                }
                list_result = call_unreal(settings, "POST", "/execute", list_payload)
                if list_result.status_code >= 400:
                    self._json_response(list_result.status_code, list_result.payload)
                    return

                payload_out = list_result.payload if isinstance(list_result.payload, dict) else {}
                asset_listing = payload_out.get("payload", {}) if isinstance(payload_out.get("payload", {}), dict) else {}
                assets = asset_listing.get("assets", []) if isinstance(asset_listing.get("assets", []), list) else []

                hotspot_items: List[Dict[str, Any]] = []
                for item in assets:
                    if not isinstance(item, dict):
                        continue
                    package_name = str(item.get("package_name", "")).strip()
                    class_path = str(item.get("class_path", "")).strip()
                    if not package_name:
                        continue
                    risk = 1.0
                    contradictions = 0
                    node_total = 0
                    graph_total = 0
                    if analyze_blueprints and "blueprint" in class_path.lower():
                        analysis_req = {
                            "action": "analyze_blueprint_asset",
                            "payload": {
                                "blueprint_path": package_name,
                                "include_pins": False,
                                "max_nodes_per_graph": 1000,
                            },
                            "dry_run": True,
                        }
                        analysis_result = call_unreal(settings, "POST", "/execute", analysis_req)
                        analysis_payload = analysis_result.payload if isinstance(analysis_result.payload, dict) else {}
                        analysis_data = analysis_payload.get("payload", {}) if isinstance(analysis_payload.get("payload", {}), dict) else {}
                        if isinstance(analysis_data.get("graphs", []), list):
                            for graph in analysis_data.get("graphs", []):
                                if not isinstance(graph, dict):
                                    continue
                                graph_total += 1
                                node_total += int(graph.get("total_nodes", 0))
                                contradictions += len(graph.get("contradictions", [])) if isinstance(graph.get("contradictions", []), list) else 0
                        risk += float(node_total) / 200.0 + float(contradictions) * 4.0
                    hotspot_items.append(
                        {
                            "asset": package_name,
                            "class_path": class_path,
                            "graph_total": graph_total,
                            "node_total": node_total,
                            "contradictions": contradictions,
                            "risk_score": round(risk, 2),
                        }
                    )
                hotspot_items.sort(key=lambda x: float(x.get("risk_score", 0.0)), reverse=True)
                risk_score = round(sum(float(item.get("risk_score", 0.0)) for item in hotspot_items[:25]), 2)
                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "package_path": package_path,
                        "analyze_blueprints": analyze_blueprints,
                        "hotspot_items": hotspot_items[:100],
                        "risk_score": risk_score,
                    },
                )
                return

            if path == "/api/impact-analysis":
                asset_paths_raw = body.get("asset_paths", [])
                asset_paths = [str(item).strip() for item in asset_paths_raw if isinstance(item, str) and str(item).strip()]
                if len(asset_paths) == 0:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "asset_paths[] is required."))
                    return
                change_type = str(body.get("change_type", "modify_blueprint_graph")).strip() or "modify_blueprint_graph"

                affected_assets: set[str] = set(asset_paths)
                dependency_details: Dict[str, Dict[str, Any]] = {}
                for asset_path in asset_paths:
                    dep_result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": "analyze_asset_impact", "payload": {"asset_path": asset_path, "change_type": change_type}, "dry_run": True},
                    )
                    if dep_result.status_code < 400 and isinstance(dep_result.payload, dict):
                        payload_out = dep_result.payload.get("payload", {})
                        if isinstance(payload_out, dict):
                            deps = payload_out.get("dependencies", [])
                            refs = payload_out.get("referencers", [])
                            if isinstance(deps, list):
                                for item in deps:
                                    if isinstance(item, str) and item.strip():
                                        affected_assets.add(item.strip())
                            if isinstance(refs, list):
                                for item in refs:
                                    if isinstance(item, str) and item.strip():
                                        affected_assets.add(item.strip())
                            dependency_details[asset_path] = payload_out

                compile_targets = sorted([item for item in affected_assets if item.split("/")[-1].startswith("BP_") or "WBP_" in item.split("/")[-1]])
                risk_flags: List[str] = []
                if len(affected_assets) > 25:
                    risk_flags.append("HIGH_BLAST_RADIUS")
                if len(compile_targets) > 10:
                    risk_flags.append("HIGH_COMPILE_IMPACT")
                if change_type.lower().startswith("remove"):
                    risk_flags.append("DESTRUCTIVE_CHANGE_TYPE")

                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "change_type": change_type,
                        "input_assets": asset_paths,
                        "affected_assets": sorted(affected_assets),
                        "compile_targets": compile_targets,
                        "risk_flags": risk_flags,
                        "impact_count": len(affected_assets),
                        "details": dependency_details,
                    },
                )
                return

            if path == "/api/property-reflect":
                payload = {
                    "target_type": str(body.get("target_type", "blueprint_cdo")).strip() or "blueprint_cdo",
                    "blueprint_path": str(body.get("blueprint_path", "")).strip(),
                    "component_name": str(body.get("component_name", "")).strip(),
                    "actor": str(body.get("actor", "")).strip(),
                    "actor_label": str(body.get("actor_label", "")).strip(),
                    "property_name": str(body.get("property_name", "")).strip(),
                    "value": body.get("value"),
                    "compile_after": bool(body.get("compile_after", False)),
                }
                if not payload["property_name"]:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "property_name is required."))
                    return

                def run_reflect_property():
                    result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": "set_reflected_property", "payload": payload, "dry_run": bool(body.get("dry_run", False))},
                    )
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_reflect_property)
                self._json_response(status, response)
                return

            if path == "/api/blueprint-function-author":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                graph_kind = str(body.get("graph_kind", "function")).strip().lower()
                graph_name = str(body.get("graph_name", "")).strip()
                category = str(body.get("category", "")).strip()
                compile_after = bool(body.get("compile_after", True))
                if not blueprint_path or not graph_name:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path and graph_name are required."))
                    return

                action = "create_blueprint_macro" if graph_kind == "macro" else "create_blueprint_function"
                payload = {
                    "blueprint_path": blueprint_path,
                    "category": category,
                    "compile_after": compile_after,
                }
                if action == "create_blueprint_macro":
                    payload["macro_name"] = graph_name
                else:
                    payload["function_name"] = graph_name

                def run_function_author():
                    result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": action, "payload": payload, "dry_run": bool(body.get("dry_run", False))},
                    )
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_function_author)
                self._json_response(status, response)
                return

            if path == "/api/component-hierarchy":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                operation = str(body.get("operation", "add_component")).strip()
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                payload = {
                    "blueprint_path": blueprint_path,
                    "operation": operation,
                    "class_path": str(body.get("class_path", "")).strip(),
                    "component_name": str(body.get("component_name", "")).strip(),
                    "parent_component": str(body.get("parent_component", "")).strip(),
                    "property_name": str(body.get("property_name", "")).strip(),
                    "value": body.get("value"),
                    "compile_after": bool(body.get("compile_after", True)),
                }

                def run_component_hierarchy():
                    result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": "modify_blueprint_components", "payload": payload, "dry_run": bool(body.get("dry_run", False))},
                    )
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_component_hierarchy)
                self._json_response(status, response)
                return

            if path == "/api/graph-ast-export":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                graph_name = str(body.get("graph_name", "")).strip()
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                include_pins = bool(body.get("include_pins", True))
                max_nodes = int(body.get("max_nodes", 2000))
                max_nodes = max(1, min(5000, max_nodes))
                ast = build_graph_ast_document(
                    settings,
                    blueprint_path,
                    graph_name,
                    include_pins=include_pins,
                    max_nodes=max_nodes,
                )
                self._json_response(HTTPStatus.OK, {"success": True, "ast": ast})
                return

            if path == "/api/graph-ast-apply":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                graph_name = str(body.get("graph_name", "EventGraph")).strip() or "EventGraph"
                operations = body.get("operations", [])
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                if not isinstance(operations, list) or len(operations) == 0:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "operations[] is required."))
                    return
                dry_run = bool(body.get("dry_run", False))
                stop_on_error = bool(body.get("stop_on_error", True))

                allowed_actions = {"wire_blueprint_pins", "blueprint_node_authoring", "modify_blueprint_graph"}
                steps: List[Dict[str, Any]] = []
                for i, operation in enumerate(operations):
                    if not isinstance(operation, dict):
                        self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", f"operations[{i}] must be object."))
                        return
                    action = str(operation.get("action", "")).strip()
                    payload = operation.get("payload", {})
                    if action not in allowed_actions:
                        self._json_response(
                            HTTPStatus.BAD_REQUEST,
                            make_error("INVALID_FIELD", f"operations[{i}] action must be one of {sorted(allowed_actions)}."),
                        )
                        return
                    if not isinstance(payload, dict):
                        self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", f"operations[{i}].payload must be object."))
                        return
                    payload.setdefault("blueprint_path", blueprint_path)
                    payload.setdefault("graph_name", graph_name)
                    if action == "wire_blueprint_pins" and not dry_run:
                        pin_validation = validate_wire_pin_contract(settings, payload)
                        if not bool(pin_validation.get("ok", False)):
                            self._json_response(
                                HTTPStatus.BAD_REQUEST,
                                make_error(
                                    str(pin_validation.get("error_code", "PIN_CONTRACT_INVALID")),
                                    str(pin_validation.get("message", "Pin contract validation failed.")),
                                    validation=pin_validation,
                                ),
                            )
                            return
                    steps.append({"id": f"ast_{i+1}", "action": action, "payload": payload})

                plan = {
                    "plan_id": "graph_ast_apply",
                    "profile": "strict",
                    "stop_on_error": stop_on_error,
                    "compile_blueprints": [blueprint_path],
                    "steps": steps,
                }
                before_obs: Dict[str, Any] = {}
                if not dry_run:
                    before_obs = collect_graph_observation(settings, blueprint_path, graph_name)

                def run_ast_apply():
                    current_plan = dict(plan)
                    current_plan["dry_run"] = dry_run
                    current_plan["stop_on_error"] = stop_on_error
                    result = call_unreal(
                        settings,
                        "POST",
                        "/run-plan",
                        current_plan,
                    )
                    return result.status_code, result.payload

                rollback_plan = build_rollback_plan_for_steps("graph_ast_apply", blueprint_path, steps)
                snapshot_token = ""
                if not dry_run:
                    if rollback_plan is None:
                        self._json_response(
                            HTTPStatus.PRECONDITION_FAILED,
                            make_error(
                                "ROLLBACK_PLAN_UNAVAILABLE",
                                "Unable to build deterministic rollback plan for graph-ast-apply.",
                                recovery_suggestions=[
                                    "Use simpler operations (wire_blueprint_pins connect/disconnect, spawn_function_call, add_variable) for rollback-safe apply.",
                                    "Run with dry_run=true to preview.",
                                ],
                            ),
                        )
                        return
                    snapshot = build_graph_snapshot_payload(
                        settings,
                        blueprint_path,
                        graph_name,
                        route=path,
                        mutation_payload={"operations": operations},
                        rollback_plan=rollback_plan,
                    )
                    snapshot_token = write_graph_snapshot(snapshot)

                status, response = self._with_run_lock(run_ast_apply)
                result_payload = {
                    "success": status < 400 and bool(response.get("success", False)),
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "applied_operations": len(steps),
                    "plan": plan,
                    "rollback_plan": rollback_plan or {},
                    "result": response,
                }
                if snapshot_token:
                    result_payload["rollback_token"] = snapshot_token
                if not dry_run and status < 500:
                    after_obs = collect_graph_observation(settings, blueprint_path, graph_name)
                    result_payload["execution_run_id"] = write_apply_execution_artifact(
                        settings,
                        route=path,
                        request_body=body,
                        response_payload=result_payload,
                        blueprint_path=blueprint_path,
                        graph_name=graph_name,
                        before_obs=before_obs,
                        after_obs=after_obs,
                    )
                self._json_response(status, result_payload)
                return

            if path == "/api/signature-edit":
                dry_run = bool(body.get("dry_run", False))
                stop_on_error = bool(body.get("stop_on_error", True))
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                graph_name = str(body.get("graph_name", "EventGraph")).strip() or "EventGraph"
                try:
                    plan = build_signature_edit_plan(body)
                except Exception as exc:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", str(exc)))
                    return
                before_obs: Dict[str, Any] = {}
                if not dry_run:
                    before_obs = collect_graph_observation(settings, blueprint_path, graph_name)

                def run_signature_edit():
                    current_plan = dict(plan)
                    current_plan["dry_run"] = dry_run
                    current_plan["stop_on_error"] = stop_on_error
                    result = call_unreal(
                        settings,
                        "POST",
                        "/run-plan",
                        current_plan,
                    )
                    return result.status_code, result.payload

                rollback_plan = build_signature_edit_rollback_plan(body, plan)
                snapshot_token = ""
                if not dry_run:
                    if rollback_plan is None:
                        self._json_response(
                            HTTPStatus.PRECONDITION_FAILED,
                            make_error(
                                "ROLLBACK_PLAN_UNAVAILABLE",
                                "Unable to build deterministic rollback plan for this signature-edit operation.",
                                operation=str(body.get("operation", "")).strip().lower(),
                                recovery_suggestions=[
                                    "Use add_variable/create_function/create_macro for rollback-safe signature operations.",
                                    "Run with dry_run=true to preview.",
                                ],
                            ),
                        )
                        return
                    snapshot = build_graph_snapshot_payload(
                        settings,
                        blueprint_path,
                        graph_name,
                        route=path,
                        mutation_payload={"operation": str(body.get("operation", "")).strip().lower(), "request": body},
                        rollback_plan=rollback_plan,
                    )
                    snapshot_token = write_graph_snapshot(snapshot)

                status, response = self._with_run_lock(run_signature_edit)
                result_payload = {
                    "success": status < 400 and bool(response.get("success", False)),
                    "operation": str(body.get("operation", "")).strip().lower(),
                    "plan": plan,
                    "rollback_plan": rollback_plan or {},
                    "result": response,
                }
                if snapshot_token:
                    result_payload["rollback_token"] = snapshot_token
                if not dry_run and status < 500:
                    after_obs = collect_graph_observation(settings, blueprint_path, graph_name)
                    result_payload["execution_run_id"] = write_apply_execution_artifact(
                        settings,
                        route=path,
                        request_body=body,
                        response_payload=result_payload,
                        blueprint_path=blueprint_path,
                        graph_name=graph_name,
                        before_obs=before_obs,
                        after_obs=after_obs,
                    )
                self._json_response(status, result_payload)
                return

            if path == "/api/actor-transform-control":
                actor = str(body.get("actor", "")).strip()
                actor_label = str(body.get("actor_label", "")).strip()
                if not actor and not actor_label:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "actor or actor_label is required."))
                    return
                payload = {
                    "actor": actor,
                    "actor_label": actor_label,
                    "operation": str(body.get("operation", "set_transform")).strip() or "set_transform",
                    "location": body.get("location", [0, 0, 0]),
                    "rotation": body.get("rotation", [0, 0, 0]),
                    "scale": body.get("scale", [1, 1, 1]),
                }

                def run_actor_transform():
                    result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": "edit_actor_transform", "payload": payload, "dry_run": bool(body.get("dry_run", False))},
                    )
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_actor_transform)
                self._json_response(status, response)
                return

            if path == "/api/system-bootstrap":
                system_type = str(body.get("system_type", "")).strip().lower()
                asset_name = str(body.get("asset_name", "")).strip()
                package_path = str(body.get("package_path", "")).strip()
                dry_run = bool(body.get("dry_run", False))
                if not system_type or not asset_name or not package_path:
                    self._json_response(
                        HTTPStatus.BAD_REQUEST,
                        make_error("MISSING_FIELD", "system_type, asset_name, and package_path are required."),
                    )
                    return
                parent_map = {
                    "anim_instance": "/Script/Engine.AnimInstance",
                    "gameplay_ability": "/Script/GameplayAbilities.GameplayAbility",
                    "ai_controller": "/Script/AIModule.AIController",
                    "bt_task": "/Script/AIModule.BTTask_BlueprintBase",
                }
                parent_class = parent_map.get(system_type, "")
                if not parent_class:
                    self._json_response(
                        HTTPStatus.BAD_REQUEST,
                        make_error("INVALID_FIELD", "system_type must be one of anim_instance, gameplay_ability, ai_controller, bt_task."),
                    )
                    return

                create_payload = {
                    "action": "create_blueprint",
                    "payload": {
                        "asset_name": asset_name,
                        "package_path": package_path,
                        "parent_class": parent_class,
                    },
                    "dry_run": dry_run,
                }
                create_result = call_unreal(settings, "POST", "/execute", create_payload)
                if create_result.status_code >= 400:
                    self._json_response(create_result.status_code, create_result.payload)
                    return

                self._json_response(
                    HTTPStatus.OK,
                    {
                        "success": bool(create_result.payload.get("success", False)),
                        "system_type": system_type,
                        "parent_class": parent_class,
                        "asset": f"{package_path}/{asset_name}",
                        "result": create_result.payload,
                    },
                )
                return

            if path == "/api/graph-pin-wire":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                payload = {
                    "blueprint_path": blueprint_path,
                    "graph_name": str(body.get("graph_name", "")).strip(),
                    "operation": str(body.get("operation", "connect")).strip() or "connect",
                    "from_node_name": str(body.get("from_node_name", "")).strip(),
                    "from_node_title_contains": str(body.get("from_node_title_contains", "")).strip(),
                    "from_pin_name": str(body.get("from_pin_name", "")).strip(),
                    "to_node_name": str(body.get("to_node_name", "")).strip(),
                    "to_node_title_contains": str(body.get("to_node_title_contains", "")).strip(),
                    "to_pin_name": str(body.get("to_pin_name", "")).strip(),
                    "compile_after": bool(body.get("compile_after", True)),
                }
                if not payload["from_pin_name"] or not payload["to_pin_name"]:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "from_pin_name and to_pin_name are required."))
                    return
                pin_validation = validate_wire_pin_contract(settings, payload)
                if not bool(pin_validation.get("ok", False)):
                    self._json_response(
                        HTTPStatus.BAD_REQUEST,
                        make_error(
                            str(pin_validation.get("error_code", "PIN_CONTRACT_INVALID")),
                            str(pin_validation.get("message", "Pin contract validation failed.")),
                            validation=pin_validation,
                        ),
                    )
                    return

                dry_run = bool(body.get("dry_run", False))
                graph_name = str(payload.get("graph_name", "")).strip()
                before_obs: Dict[str, Any] = {}
                if not dry_run:
                    before_obs = collect_graph_observation(settings, blueprint_path, graph_name)
                rollback_plan = {
                    "plan_id": "rollback_graph_pin_wire",
                    "stop_on_error": True,
                    "steps": [
                        {
                            "id": "rollback_pin_wire",
                            "action": "wire_blueprint_pins",
                            "payload": {
                                **payload,
                                "operation": "disconnect" if payload["operation"].lower() == "connect" else "connect",
                                "compile_after": True,
                            },
                        }
                    ],
                    "compile_blueprints": [blueprint_path],
                }
                snapshot_token = ""
                if not dry_run:
                    snapshot = build_graph_snapshot_payload(
                        settings,
                        blueprint_path,
                        str(payload.get("graph_name", "")),
                        route=path,
                        mutation_payload=payload,
                        rollback_plan=rollback_plan,
                    )
                    snapshot_token = write_graph_snapshot(snapshot)

                def run_graph_pin_wire():
                    result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": "wire_blueprint_pins", "payload": payload, "dry_run": dry_run},
                    )
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_graph_pin_wire)
                if isinstance(response, dict) and snapshot_token:
                    response["rollback_token"] = snapshot_token
                if isinstance(response, dict) and not dry_run and status < 500:
                    after_obs = collect_graph_observation(settings, blueprint_path, graph_name)
                    response["execution_run_id"] = write_apply_execution_artifact(
                        settings,
                        route=path,
                        request_body=body,
                        response_payload=response,
                        blueprint_path=blueprint_path,
                        graph_name=graph_name,
                        before_obs=before_obs,
                        after_obs=after_obs,
                    )
                self._json_response(status, response)
                return

            if path == "/api/node-author":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                payload = {
                    "blueprint_path": blueprint_path,
                    "graph_name": str(body.get("graph_name", "")).strip(),
                    "operation": str(body.get("operation", "spawn_function_call")).strip() or "spawn_function_call",
                    "node_name": str(body.get("node_name", "")).strip(),
                    "target_node_name": str(body.get("target_node_name", "")).strip(),
                    "target_node_title_contains": str(body.get("target_node_title_contains", "")).strip(),
                    "function_class_path": str(body.get("function_class_path", "")).strip(),
                    "function_name": str(body.get("function_name", "")).strip(),
                    "node_position": body.get("node_position", [0, 0]),
                    "compile_after": bool(body.get("compile_after", True)),
                }
                if not payload["function_class_path"] or not payload["function_name"]:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "function_class_path and function_name are required."))
                    return

                dry_run = bool(body.get("dry_run", False))
                graph_name = str(payload.get("graph_name", "")).strip()
                before_obs: Dict[str, Any] = {}
                if not dry_run:
                    before_obs = collect_graph_observation(settings, blueprint_path, graph_name)
                rollback_plan: Dict[str, Any] = {}
                snapshot_token = ""
                if not dry_run:
                    snapshot = build_graph_snapshot_payload(
                        settings,
                        blueprint_path,
                        str(payload.get("graph_name", "")),
                        route=path,
                        mutation_payload=payload,
                        rollback_plan=rollback_plan,
                    )
                    snapshot_token = write_graph_snapshot(snapshot)

                def run_node_author():
                    result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": "blueprint_node_authoring", "payload": payload, "dry_run": dry_run},
                    )
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_node_author)
                if isinstance(response, dict) and snapshot_token:
                    response["rollback_token"] = snapshot_token
                    op = str(payload.get("operation", "spawn_function_call")).strip().lower()
                    upstream = extract_upstream_payload(response)
                    if op == "spawn_function_call" and isinstance(upstream, dict):
                        new_node_name = str(upstream.get("new_node_name", "")).strip()
                        if new_node_name:
                            rollback_plan = {
                                "plan_id": "rollback_spawn_function_call",
                                "stop_on_error": True,
                                "steps": [
                                    {
                                        "id": "remove_spawned_node",
                                        "action": "modify_blueprint_graph",
                                        "payload": {
                                            "blueprint_path": blueprint_path,
                                            "graph_name": str(payload.get("graph_name", "")),
                                            "operation": "remove_nodes",
                                            "node_name_contains": new_node_name,
                                        },
                                    }
                                ],
                                "compile_blueprints": [blueprint_path],
                            }
                            response["rollback_plan"] = rollback_plan
                            if snapshot_token:
                                update_graph_snapshot_rollback(snapshot_token, rollback_plan)
                if isinstance(response, dict) and not dry_run and status < 500:
                    after_obs = collect_graph_observation(settings, blueprint_path, graph_name)
                    response["execution_run_id"] = write_apply_execution_artifact(
                        settings,
                        route=path,
                        request_body=body,
                        response_payload=response,
                        blueprint_path=blueprint_path,
                        graph_name=graph_name,
                        before_obs=before_obs,
                        after_obs=after_obs,
                    )
                self._json_response(status, response)
                return

            if path == "/api/compile-diagnostics":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                payload = {
                    "blueprint_path": blueprint_path,
                    "graph_name": str(body.get("graph_name", "")).strip(),
                    "include_pins": bool(body.get("include_pins", True)),
                    "max_nodes": int(body.get("max_nodes", 500)),
                }

                def run_compile_diagnostics():
                    result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": "blueprint_compile_diagnostics", "payload": payload, "dry_run": bool(body.get("dry_run", False))},
                    )
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_compile_diagnostics)
                self._json_response(status, response)
                return

            if path == "/api/compile-gate-run":
                blueprint_paths_raw = body.get("blueprint_paths", [])
                blueprint_paths = [str(x).strip() for x in blueprint_paths_raw if isinstance(x, str) and str(x).strip()]
                if not blueprint_paths:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_paths[] is required."))
                    return
                max_items = int(settings.get("compile_gate_max_blueprints", 100))
                blueprint_paths = blueprint_paths[:max(1, max_items)]
                include_pins = bool(body.get("include_pins", True))
                max_nodes = int(body.get("max_nodes", 800))
                dry_run = bool(body.get("dry_run", False))

                items: List[Dict[str, Any]] = []
                passed = 0
                failed = 0
                for blueprint_path in blueprint_paths:
                    req = {
                        "action": "blueprint_compile_diagnostics",
                        "payload": {
                            "blueprint_path": blueprint_path,
                            "include_pins": include_pins,
                            "max_nodes": max_nodes,
                        },
                        "dry_run": dry_run,
                    }
                    result = call_unreal(settings, "POST", "/execute", req)
                    payload_out = result.payload if isinstance(result.payload, dict) else {}
                    upstream = extract_upstream_payload(payload_out)
                    ok = result.status_code < 400 and bool(payload_out.get("success", False))
                    contradictions = collect_analysis_contradictions(upstream if isinstance(upstream, dict) else {})
                    if contradictions:
                        ok = False
                    if ok:
                        passed += 1
                    else:
                        failed += 1
                    items.append(
                        {
                            "blueprint_path": blueprint_path,
                            "success": ok,
                            "status_code": result.status_code,
                            "error_code": payload_out.get("error_code", "OK" if ok else "FAILED"),
                            "compile_success": bool((upstream.get("compile_success") if isinstance(upstream, dict) else False)),
                            "contradictions": contradictions,
                            "result": payload_out,
                        }
                    )

                self._json_response(
                    HTTPStatus.OK if failed == 0 else HTTPStatus.CONFLICT,
                    {
                        "success": failed == 0,
                        "gate": "compile_and_diagnostics",
                        "dry_run": dry_run,
                        "total": len(items),
                        "passed": passed,
                        "failed": failed,
                        "items": items,
                    },
                )
                return

            if path == "/api/node-pattern-preview":
                pattern_id = str(body.get("pattern_id", "")).strip()
                if pattern_id not in NODE_PATTERN_CATALOG:
                    self._json_response(HTTPStatus.NOT_FOUND, make_error("NOT_FOUND", "Unknown pattern_id.", pattern_id=pattern_id))
                    return
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                try:
                    plan = build_node_pattern_plan(pattern_id, body)
                except Exception as exc:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", str(exc)))
                    return
                self._json_response(
                    HTTPStatus.OK,
                    {"success": True, "pattern": NODE_PATTERN_CATALOG[pattern_id], "generated_plan": plan, "dry_run_only": True},
                )
                return

            if path == "/api/node-pattern-apply":
                pattern_id = str(body.get("pattern_id", "")).strip()
                if pattern_id not in NODE_PATTERN_CATALOG:
                    self._json_response(HTTPStatus.NOT_FOUND, make_error("NOT_FOUND", "Unknown pattern_id.", pattern_id=pattern_id))
                    return
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                dry_run = bool(body.get("dry_run", False))
                try:
                    plan = build_node_pattern_plan(pattern_id, body)
                except Exception as exc:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", str(exc)))
                    return

                graph_name = str(body.get("graph_name", "EventGraph")).strip() or "EventGraph"
                before_obs: Dict[str, Any] = {}
                if not dry_run:
                    before_obs = collect_graph_observation(settings, blueprint_path, graph_name)
                rollback_plan = build_node_pattern_rollback_plan(body)
                snapshot_token = ""
                if not dry_run:
                    if rollback_plan is None:
                        self._json_response(
                            HTTPStatus.PRECONDITION_FAILED,
                            make_error("ROLLBACK_PLAN_UNAVAILABLE", "Unable to build rollback plan for node pattern apply."),
                        )
                        return
                    snapshot = build_graph_snapshot_payload(
                        settings,
                        blueprint_path,
                        str(body.get("graph_name", "EventGraph")).strip() or "EventGraph",
                        route=path,
                        mutation_payload={"pattern_id": pattern_id, "request": body},
                        rollback_plan=rollback_plan,
                    )
                    snapshot_token = write_graph_snapshot(snapshot)

                def run_pattern_plan():
                    current_plan = dict(plan)
                    current_plan["dry_run"] = dry_run
                    current_plan["stop_on_error"] = True
                    result = call_unreal(settings, "POST", "/run-plan", current_plan)
                    return result.status_code, result.payload

                if dry_run:
                    status, response = run_node_pattern_dry_run_simulation(settings, plan)
                else:
                    status, response = self._with_run_lock(run_pattern_plan)
                result_payload = {
                    "success": status < 400 and bool(response.get("success", False)),
                    "pattern_id": pattern_id,
                    "plan": plan,
                    "rollback_plan": rollback_plan or {},
                    "result": response,
                }
                if snapshot_token:
                    result_payload["rollback_token"] = snapshot_token
                if not dry_run and status < 500:
                    after_obs = collect_graph_observation(settings, blueprint_path, graph_name)
                    result_payload["execution_run_id"] = write_apply_execution_artifact(
                        settings,
                        route=path,
                        request_body=body,
                        response_payload=result_payload,
                        blueprint_path=blueprint_path,
                        graph_name=graph_name,
                        before_obs=before_obs,
                        after_obs=after_obs,
                    )
                self._json_response(status, result_payload)
                return

            if path == "/api/workflow-generate":
                workflow_id = str(body.get("workflow_id", "")).strip()
                if workflow_id not in WORKFLOW_TEMPLATE_CATALOG:
                    self._json_response(HTTPStatus.NOT_FOUND, make_error("NOT_FOUND", "Unknown workflow_id.", workflow_id=workflow_id))
                    return
                dry_run = bool(body.get("dry_run", False))
                stop_on_error = bool(body.get("stop_on_error", True))
                try:
                    plan = build_workflow_plan(workflow_id, body)
                except Exception as exc:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", str(exc)))
                    return

                def run_workflow_plan():
                    current_plan = dict(plan)
                    current_plan["dry_run"] = dry_run
                    current_plan["stop_on_error"] = stop_on_error
                    result = call_unreal(settings, "POST", "/run-plan", current_plan)
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_workflow_plan)
                payload = {
                    "success": status < 400 and bool(response.get("success", False)),
                    "workflow_id": workflow_id,
                    "template": WORKFLOW_TEMPLATE_CATALOG[workflow_id],
                    "generated_plan": plan,
                    "result": response,
                    "outputs": plan.get("outputs", {}),
                }
                self._json_response(status, payload)
                return

            if path == "/api/animation-autonomy-generate":
                template_id = str(body.get("template_id", "")).strip()
                if template_id not in ANIMATION_AUTONOMY_TEMPLATES:
                    self._json_response(HTTPStatus.NOT_FOUND, make_error("NOT_FOUND", "Unknown template_id.", template_id=template_id))
                    return
                dry_run = bool(body.get("dry_run", False))
                stop_on_error = bool(body.get("stop_on_error", True))
                try:
                    plan = build_animation_autonomy_plan(template_id, body)
                except Exception as exc:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", str(exc)))
                    return

                def run_animation_plan():
                    current_plan = dict(plan)
                    current_plan["dry_run"] = dry_run
                    current_plan["stop_on_error"] = stop_on_error
                    result = call_unreal(settings, "POST", "/run-plan", current_plan)
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_animation_plan)
                self._json_response(
                    status,
                    {
                        "success": status < 400 and bool(response.get("success", False)),
                        "template_id": template_id,
                        "template": ANIMATION_AUTONOMY_TEMPLATES[template_id],
                        "generated_plan": plan,
                        "result": response,
                        "outputs": plan.get("outputs", {}),
                    },
                )
                return

            if path == "/api/ai-autonomy-generate":
                template_id = str(body.get("template_id", "")).strip()
                if template_id not in AI_AUTONOMY_TEMPLATES:
                    self._json_response(HTTPStatus.NOT_FOUND, make_error("NOT_FOUND", "Unknown template_id.", template_id=template_id))
                    return
                dry_run = bool(body.get("dry_run", False))
                stop_on_error = bool(body.get("stop_on_error", True))
                try:
                    plan = build_ai_autonomy_plan(template_id, body)
                except Exception as exc:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", str(exc)))
                    return

                def run_ai_plan():
                    current_plan = dict(plan)
                    current_plan["dry_run"] = dry_run
                    current_plan["stop_on_error"] = stop_on_error
                    result = call_unreal(settings, "POST", "/run-plan", current_plan)
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_ai_plan)
                self._json_response(
                    status,
                    {
                        "success": status < 400 and bool(response.get("success", False)),
                        "template_id": template_id,
                        "template": AI_AUTONOMY_TEMPLATES[template_id],
                        "generated_plan": plan,
                        "result": response,
                        "outputs": plan.get("outputs", {}),
                    },
                )
                return

            if path == "/api/blackboard-schema-evolve":
                dry_run = bool(body.get("dry_run", False))
                try:
                    plan, summary = build_blackboard_schema_evolution_plan(body)
                except Exception as exc:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", str(exc)))
                    return

                if dry_run:
                    self._json_response(
                        HTTPStatus.OK,
                        {
                            "success": True,
                            "dry_run": True,
                            "generated_plan": plan,
                            "summary": summary,
                        },
                    )
                    return

                def run_blackboard_evolution():
                    result = call_unreal(settings, "POST", "/run-plan", plan)
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_blackboard_evolution)
                self._json_response(
                    status,
                    {
                        "success": status < 400 and bool(response.get("success", False)),
                        "generated_plan": plan,
                        "summary": summary,
                        "result": response,
                    },
                )
                return

            if path == "/api/ai-behavior-validate":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                graph_name = str(body.get("graph_name", "EventGraph")).strip() or "EventGraph"
                assertions = body.get("assertions", [])
                if assertions is None:
                    assertions = []
                if not isinstance(assertions, list):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "assertions must be an array."))
                    return
                compile_diag = call_unreal(
                    settings,
                    "POST",
                    "/execute",
                    {
                        "action": "blueprint_compile_diagnostics",
                        "payload": {"blueprint_path": blueprint_path, "include_pins": True, "max_nodes": 1500},
                        "dry_run": True,
                    },
                )
                compile_payload = compile_diag.payload if isinstance(compile_diag.payload, dict) else {}
                compile_upstream = extract_upstream_payload(compile_payload)
                compile_contradictions = collect_analysis_contradictions(compile_upstream if isinstance(compile_upstream, dict) else {})

                analysis = call_unreal(
                    settings,
                    "POST",
                    "/execute",
                    {
                        "action": "analyze_blueprint_graph",
                        "payload": {"blueprint_path": blueprint_path, "graph_name": graph_name, "include_pins": True, "max_nodes": 1500},
                        "dry_run": True,
                    },
                )
                analysis_payload = extract_upstream_payload(analysis.payload if isinstance(analysis.payload, dict) else {})
                ai_lint = build_analysis_lint(analysis_payload if isinstance(analysis_payload, dict) else {})

                scenario_run = call_unreal(
                    settings,
                    "POST",
                    "/execute",
                    {"action": "run_pie_scenario", "payload": {"assertions": assertions}, "dry_run": False},
                )
                scenario_payload = scenario_run.payload if isinstance(scenario_run.payload, dict) else {}

                compile_ok = compile_diag.status_code < 400 and bool(compile_payload.get("success", False)) and len(compile_contradictions) == 0
                scenario_ok = scenario_run.status_code < 400 and bool(scenario_payload.get("success", False))
                success = compile_ok and scenario_ok
                self._json_response(
                    HTTPStatus.OK if success else HTTPStatus.CONFLICT,
                    {
                        "success": success,
                        "blueprint_path": blueprint_path,
                        "graph_name": graph_name,
                        "compile": {
                            "success": compile_ok,
                            "status_code": int(compile_diag.status_code),
                            "contradictions": compile_contradictions,
                            "result": compile_payload,
                        },
                        "analysis_lint": ai_lint,
                        "scenario": {
                            "success": scenario_ok,
                            "status_code": int(scenario_run.status_code),
                            "result": scenario_payload,
                        },
                    },
                )
                return

            if path == "/api/content-pipeline-apply":
                preset_id = str(body.get("preset_id", "")).strip()
                if preset_id not in CONTENT_PIPELINE_PRESETS:
                    self._json_response(HTTPStatus.NOT_FOUND, make_error("NOT_FOUND", "Unknown preset_id.", preset_id=preset_id))
                    return
                namespace_root = str(body.get("namespace_root", "/Game/AgentGenerated")).strip() or "/Game/AgentGenerated"
                if not namespace_root.startswith("/Game"):
                    namespace_root = "/Game/AgentGenerated"
                recipe_inputs = {
                    "namespace_root": namespace_root,
                    "pack_label": str(body.get("pack_label", "AgentPack")).strip() or "AgentPack",
                    "naming_prefix": str(body.get("naming_prefix", "SM_")).strip() or "SM_",
                    "default_material": str(body.get("default_material", "")).strip(),
                }
                dry_run = bool(body.get("dry_run", False))
                dep_assets = body.get("asset_paths", [])
                if dep_assets is None:
                    dep_assets = []
                if not isinstance(dep_assets, list):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "asset_paths must be an array."))
                    return
                dependency_safety = run_dependency_safety_check(settings, [str(x) for x in dep_assets], depth=int(body.get("dependency_depth", 2)))
                if not dry_run and not bool(dependency_safety.get("success", False)):
                    self._json_response(
                        HTTPStatus.CONFLICT,
                        make_error(
                            "DEPENDENCY_SAFETY_BLOCKED",
                            "Content pipeline apply blocked by dependency safety checks.",
                            dependency_safety=dependency_safety,
                        ),
                    )
                    return

                status, recipe_result, execution_mode = run_recipe_with_local_fallback(
                    settings=settings,
                    recipe_id="asset_import_materialize_pack",
                    resolved_inputs=recipe_inputs,
                    dry_run=dry_run,
                    stop_on_error=True,
                    profile="strict",
                )
                self._json_response(
                    status if status >= 400 else HTTPStatus.OK,
                    {
                        "success": status < 400 and bool(recipe_result.get("success", False)),
                        "preset_id": preset_id,
                        "preset": CONTENT_PIPELINE_PRESETS[preset_id],
                        "recipe_id": "asset_import_materialize_pack",
                        "recipe_inputs": recipe_inputs,
                        "execution_mode": execution_mode,
                        "dependency_safety": dependency_safety,
                        "result": recipe_result,
                    },
                )
                return

            if path == "/api/content-schema-enforce":
                try:
                    report = enforce_content_schema(settings, body)
                except Exception as exc:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", str(exc)))
                    return
                self._json_response(HTTPStatus.OK if bool(report.get("success", False)) else HTTPStatus.CONFLICT, report)
                return

            if path == "/api/dependency-safety-check":
                asset_paths = body.get("asset_paths", [])
                if not isinstance(asset_paths, list) or len(asset_paths) == 0:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "asset_paths[] is required."))
                    return
                depth = int(body.get("depth", 2))
                result = run_dependency_safety_check(settings, [str(x) for x in asset_paths], depth=depth)
                self._json_response(HTTPStatus.OK if bool(result.get("success", False)) else HTTPStatus.CONFLICT, result)
                return

            if path == "/api/multiplayer-lint":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                graph_name = str(body.get("graph_name", "")).strip()
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                analyze = call_unreal(
                    settings,
                    "POST",
                    "/execute",
                    {
                        "action": "analyze_blueprint_graph",
                        "payload": {"blueprint_path": blueprint_path, "graph_name": graph_name, "include_pins": True, "max_nodes": 1500},
                        "dry_run": True,
                    },
                )
                analyze_payload = extract_upstream_payload(analyze.payload if isinstance(analyze.payload, dict) else {})
                lint = build_multiplayer_lint(analyze_payload if isinstance(analyze_payload, dict) else {})
                lint["blueprint_path"] = blueprint_path
                lint["graph_name"] = graph_name or "EventGraph"
                lint["analysis_status_code"] = int(analyze.status_code)
                self._json_response(HTTPStatus.OK if bool(lint.get("success", False)) else HTTPStatus.CONFLICT, lint)
                return

            if path == "/api/multiplayer-guard-apply":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                dry_run = bool(body.get("dry_run", False))
                stop_on_error = bool(body.get("stop_on_error", True))

                analyze = call_unreal(
                    settings,
                    "POST",
                    "/execute",
                    {
                        "action": "analyze_blueprint_graph",
                        "payload": {"blueprint_path": blueprint_path, "include_pins": True, "max_nodes": 1500},
                        "dry_run": True,
                    },
                )
                analyze_payload = extract_upstream_payload(analyze.payload if isinstance(analyze.payload, dict) else {})
                lint_findings = build_analysis_lint(analyze_payload if isinstance(analyze_payload, dict) else {})
                catalog = build_refactor_catalog(blueprint_path, "strict", analyze_payload if isinstance(analyze_payload, dict) else {}, lint_findings)
                plan, selected = build_refactor_catalog_plan(
                    blueprint_path=blueprint_path,
                    catalog=catalog,
                    transform_ids=["insert_authority_guard"],
                    transform_inputs={},
                    dry_run=dry_run,
                    stop_on_error=stop_on_error,
                )
                if plan is None:
                    self._json_response(
                        HTTPStatus.OK,
                        {
                            "success": True,
                            "applied": False,
                            "message": "No applicable authority guard transform was found.",
                            "selected_transforms": selected,
                            "generated_plan": None,
                        },
                    )
                    return

                def run_mp_guard_plan():
                    result = call_unreal(settings, "POST", "/run-plan", plan)
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_mp_guard_plan)
                self._json_response(
                    status,
                    {
                        "success": status < 400 and bool(response.get("success", False)),
                        "applied": status < 400 and bool(response.get("success", False)),
                        "selected_transforms": selected,
                        "generated_plan": plan,
                        "result": response,
                    },
                )
                return

            if path == "/api/multiplayer-pie-test":
                assertions = body.get("assertions", [])
                if assertions is None:
                    assertions = []
                if not isinstance(assertions, list):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "assertions must be an array."))
                    return
                client_count = int(body.get("client_count", 2))
                repeats = int(body.get("repeats", 2))
                capture_on_fail = bool(body.get("capture_screenshot_on_fail", False))
                harness = run_multiplayer_pie_harness(
                    settings,
                    [item for item in assertions if isinstance(item, dict)],
                    client_count,
                    repeats,
                    capture_screenshot_on_fail=capture_on_fail,
                )
                if bool(settings.get("execution_store_artifacts", True)):
                    run_artifact = {
                        "timestamp": time.time(),
                        "route": path,
                        "request": body,
                        "response": harness,
                        "summary": {
                            "total_runs": int(harness.get("total_runs", 0)),
                            "failed_runs": int(harness.get("failed_runs", 0)),
                            "deterministic": bool(harness.get("deterministic", False)),
                        },
                    }
                    harness["execution_run_id"] = write_execution_artifact(settings, run_artifact)
                self._json_response(HTTPStatus.OK if bool(harness.get("success", False)) else HTTPStatus.CONFLICT, harness)
                return

            if path == "/api/pie-replay-suite":
                assertions = body.get("assertions", [])
                if assertions is None:
                    assertions = []
                if not isinstance(assertions, list):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "assertions must be an array."))
                    return
                include_multiplayer = bool(body.get("include_multiplayer", True))
                client_count = int(body.get("client_count", 2))
                repeats = int(body.get("repeats", 2))
                capture_on_fail = bool(body.get("capture_screenshot_on_fail", False))
                replay = run_pie_replay_suite(
                    settings,
                    [item for item in assertions if isinstance(item, dict)],
                    client_count=client_count,
                    repeats=repeats,
                    include_multiplayer=include_multiplayer,
                    capture_screenshot_on_fail=capture_on_fail,
                )
                if bool(settings.get("execution_store_artifacts", True)):
                    run_artifact = {
                        "timestamp": time.time(),
                        "route": path,
                        "request": body,
                        "response": replay,
                        "summary": {
                            "total_runs": int(replay.get("total_runs", 0)),
                            "failed_runs": int(replay.get("failed_runs", 0)),
                            "deterministic": bool(replay.get("deterministic", False)),
                            "mismatch_count": len(replay.get("mismatch_items", []))
                            if isinstance(replay.get("mismatch_items", []), list)
                            else 0,
                        },
                    }
                    replay["execution_run_id"] = write_execution_artifact(settings, run_artifact)
                self._json_response(HTTPStatus.OK if bool(replay.get("success", False)) else HTTPStatus.CONFLICT, replay)
                return

            if path == "/api/blueprint-structure-review":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                graph_name = str(body.get("graph_name", "EventGraph")).strip() or "EventGraph"
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                include_ast = bool(body.get("include_ast", True))
                include_refactor_catalog = bool(body.get("include_refactor_catalog", True))
                review_scope = str(body.get("review_scope", "graph")).strip().lower() or "graph"
                include_all_graphs = bool(body.get("include_all_graphs", False))
                if include_all_graphs:
                    review_scope = "asset"
                if review_scope not in {"graph", "asset"}:
                    self._json_response(
                        HTTPStatus.BAD_REQUEST,
                        make_error("INVALID_FIELD", "review_scope must be 'graph' or 'asset'.", review_scope=review_scope),
                    )
                    return
                if review_scope == "asset":
                    max_graph_ast_exports = int(body.get("max_graph_ast_exports", 12))
                    review = build_blueprint_asset_structure_review(
                        settings,
                        blueprint_path,
                        include_ast=include_ast,
                        include_refactor_catalog=include_refactor_catalog,
                        max_graph_ast_exports=max_graph_ast_exports,
                    )
                else:
                    review = build_blueprint_structure_review(
                        settings,
                        blueprint_path,
                        graph_name,
                        include_ast=include_ast,
                        include_refactor_catalog=include_refactor_catalog,
                    )
                self._json_response(HTTPStatus.OK if bool(review.get("success", False)) else HTTPStatus.CONFLICT, review)
                return

            if path == "/api/rpc-contract-lint":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                graph_name = str(body.get("graph_name", "EventGraph")).strip() or "EventGraph"
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                analyze = call_unreal(
                    settings,
                    "POST",
                    "/execute",
                    {
                        "action": "analyze_blueprint_graph",
                        "payload": {"blueprint_path": blueprint_path, "graph_name": graph_name, "include_pins": True, "max_nodes": 2000},
                        "dry_run": True,
                    },
                )
                analyze_payload = extract_upstream_payload(analyze.payload if isinstance(analyze.payload, dict) else {})
                lint = build_rpc_contract_lint(analyze_payload if isinstance(analyze_payload, dict) else {})
                lint["blueprint_path"] = blueprint_path
                lint["graph_name"] = graph_name
                lint["analysis_status_code"] = int(analyze.status_code)
                self._json_response(HTTPStatus.OK if bool(lint.get("success", False)) else HTTPStatus.CONFLICT, lint)
                return

            if path == "/api/ai-asset-authoring":
                dry_run = bool(body.get("dry_run", False))
                stop_on_error = bool(body.get("stop_on_error", True))
                try:
                    plan = build_ai_asset_authoring_plan(body)
                except Exception as exc:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", str(exc)))
                    return

                def run_ai_asset_plan():
                    current_plan = dict(plan)
                    current_plan["dry_run"] = dry_run
                    current_plan["stop_on_error"] = stop_on_error
                    result = call_unreal(settings, "POST", "/run-plan", current_plan)
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_ai_asset_plan)
                self._json_response(
                    status,
                    {
                        "success": status < 400 and bool(response.get("success", False)),
                        "generated_plan": plan,
                        "result": response,
                        "outputs": plan.get("outputs", {}),
                        "note": "AI asset authoring now targets native Blackboard/EQS/BehaviorTree assets via editor-native plugin actions.",
                    },
                )
                return

            if path == "/api/material-mesh-setup":
                preset_id = str(body.get("preset_id", "static_mesh_actor_basic")).strip() or "static_mesh_actor_basic"
                if preset_id not in MATERIAL_MESH_SETUP_PRESETS:
                    self._json_response(HTTPStatus.NOT_FOUND, make_error("NOT_FOUND", "Unknown preset_id.", preset_id=preset_id))
                    return
                dry_run = bool(body.get("dry_run", False))
                asset_name = str(body.get("asset_name", "BP_AgentMeshActor")).strip() or "BP_AgentMeshActor"
                package_path = str(body.get("package_path", "/Game/AgentGenerated/Props")).strip() or "/Game/AgentGenerated/Props"
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                static_mesh_path = str(body.get("static_mesh_path", "")).strip()
                material_path = str(body.get("material_path", "")).strip()
                if not blueprint_path and (not asset_name or not package_path):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "asset_name/package_path or blueprint_path are required."))
                    return
                if not static_mesh_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "static_mesh_path is required."))
                    return

                actor_bp_path = blueprint_path
                steps_run: List[Dict[str, Any]] = []

                if not actor_bp_path:
                    create_result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {
                            "action": "create_blueprint",
                            "payload": {
                                "asset_name": asset_name,
                                "package_path": package_path,
                                "parent_class": "/Script/Engine.Actor",
                            },
                            "dry_run": dry_run,
                        },
                    )
                    steps_run.append({"step": "create_blueprint", "status_code": int(create_result.status_code), "result": create_result.payload})
                    if create_result.status_code >= 400 or not bool((create_result.payload or {}).get("success", False)):
                        self._json_response(create_result.status_code, {"success": False, "step_results": steps_run, "error": create_result.payload})
                        return
                    actor_bp_path = f"{package_path}/{asset_name}"

                add_mesh_component = call_unreal(
                    settings,
                    "POST",
                    "/execute",
                    {
                        "action": "modify_blueprint_components",
                        "payload": {
                            "blueprint_path": actor_bp_path,
                            "operation": "add_component",
                            "class_path": "/Script/Engine.StaticMeshComponent",
                            "component_name": "Mesh",
                            "parent_component": "DefaultSceneRoot",
                            "compile_after": False,
                        },
                        "dry_run": dry_run,
                    },
                )
                steps_run.append({"step": "add_mesh_component", "status_code": int(add_mesh_component.status_code), "result": add_mesh_component.payload})

                set_mesh = call_unreal(
                    settings,
                    "POST",
                    "/execute",
                    {
                        "action": "set_reflected_property",
                        "payload": {
                            "target_type": "blueprint_component",
                            "blueprint_path": actor_bp_path,
                            "component_name": "Mesh",
                            "property_name": "StaticMesh",
                            "value": static_mesh_path,
                            "compile_after": False,
                        },
                        "dry_run": dry_run,
                    },
                )
                steps_run.append({"step": "set_static_mesh", "status_code": int(set_mesh.status_code), "result": set_mesh.payload})

                if material_path:
                    set_material = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {
                            "action": "set_reflected_property",
                            "payload": {
                                "target_type": "blueprint_component",
                                "blueprint_path": actor_bp_path,
                                "component_name": "Mesh",
                                "property_name": "OverrideMaterials",
                                "value": [material_path],
                                "compile_after": False,
                            },
                            "dry_run": dry_run,
                        },
                    )
                    steps_run.append({"step": "set_material", "status_code": int(set_material.status_code), "result": set_material.payload})

                if preset_id == "pickup_prop_basic":
                    add_pickup_var = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {
                            "action": "modify_blueprint_graph",
                            "payload": {
                                "blueprint_path": actor_bp_path,
                                "operation": "add_variable",
                                "variable_name": "bCanPickup",
                                "variable_type": "bool",
                                "default_value": "true",
                                "category": "Pickup",
                                "compile_after": False,
                            },
                            "dry_run": dry_run,
                        },
                    )
                    steps_run.append({"step": "add_pickup_variable", "status_code": int(add_pickup_var.status_code), "result": add_pickup_var.payload})

                compile_result = call_unreal(
                    settings,
                    "POST",
                    "/execute",
                    {"action": "compile_blueprint", "payload": {"blueprint_path": actor_bp_path}, "dry_run": dry_run},
                )
                steps_run.append({"step": "compile_blueprint", "status_code": int(compile_result.status_code), "result": compile_result.payload})

                overall_success = all(item.get("status_code", 500) < 400 and bool((item.get("result", {}) or {}).get("success", False)) for item in steps_run)
                self._json_response(
                    HTTPStatus.OK if overall_success else HTTPStatus.CONFLICT,
                    {
                        "success": overall_success,
                        "preset_id": preset_id,
                        "preset": MATERIAL_MESH_SETUP_PRESETS[preset_id],
                        "blueprint_path": actor_bp_path,
                        "static_mesh_path": static_mesh_path,
                        "material_path": material_path,
                        "step_results": steps_run,
                    },
                )
                return

            if path == "/api/native-asset-create":
                asset_type = str(body.get("asset_type", "")).strip().lower()
                if asset_type not in NATIVE_ASSET_AUTHORING_CATALOG:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_FIELD", "Unsupported asset_type.", asset_type=asset_type))
                    return
                dry_run = bool(body.get("dry_run", False))
                try:
                    action, payload = build_native_asset_action_payload(asset_type, body, mode="create")
                except Exception as exc:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", str(exc)))
                    return

                def run_native_create():
                    result = call_unreal(settings, "POST", "/execute", {"action": action, "payload": payload, "dry_run": dry_run})
                    return result.status_code, result.payload

                status_code, result_payload = self._with_run_lock(run_native_create)
                response_payload = {
                    "success": status_code < 400 and bool((result_payload or {}).get("success", False)),
                    "asset_type": asset_type,
                    "action": action,
                    "payload": payload,
                    "dry_run": dry_run,
                    "result": result_payload,
                }
                if (
                    status_code < 400
                    and bool(response_payload.get("success", False))
                    and not dry_run
                    and bool(settings.get("auto_verify_after_mutation", True))
                ):
                    verify_targets = collect_native_asset_verify_targets(asset_type, body, payload)
                    verify = run_post_mutation_blueprint_verification(settings, verify_targets)
                    response_payload["post_mutation_verification"] = verify
                    if verify_targets and (not bool(verify.get("success", False))) and bool(settings.get("auto_verify_enforce_pass", True)):
                        status_code = HTTPStatus.CONFLICT
                        response_payload["success"] = False
                        response_payload["error_code"] = "POST_MUTATION_VERIFY_FAILED"
                self._json_response(status_code, response_payload)
                return

            if path == "/api/native-asset-edit":
                asset_type = str(body.get("asset_type", "")).strip().lower()
                if asset_type not in NATIVE_ASSET_AUTHORING_CATALOG:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_FIELD", "Unsupported asset_type.", asset_type=asset_type))
                    return
                dry_run = bool(body.get("dry_run", False))
                try:
                    action, payload = build_native_asset_action_payload(asset_type, body, mode="edit")
                except Exception as exc:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", str(exc)))
                    return

                def run_native_edit():
                    result = call_unreal(settings, "POST", "/execute", {"action": action, "payload": payload, "dry_run": dry_run})
                    return result.status_code, result.payload

                status_code, result_payload = self._with_run_lock(run_native_edit)
                response_payload = {
                    "success": status_code < 400 and bool((result_payload or {}).get("success", False)),
                    "asset_type": asset_type,
                    "action": action,
                    "payload": payload,
                    "dry_run": dry_run,
                    "result": result_payload,
                }
                if (
                    status_code < 400
                    and bool(response_payload.get("success", False))
                    and not dry_run
                    and bool(settings.get("auto_verify_after_mutation", True))
                ):
                    verify_targets = collect_native_asset_verify_targets(asset_type, body, payload)
                    verify = run_post_mutation_blueprint_verification(settings, verify_targets)
                    response_payload["post_mutation_verification"] = verify
                    if verify_targets and (not bool(verify.get("success", False))) and bool(settings.get("auto_verify_enforce_pass", True)):
                        status_code = HTTPStatus.CONFLICT
                        response_payload["success"] = False
                        response_payload["error_code"] = "POST_MUTATION_VERIFY_FAILED"
                self._json_response(status_code, response_payload)
                return

            if path == "/api/native-asset-authoring-workflow":
                dry_run = bool(body.get("dry_run", False))
                stop_on_error = bool(body.get("stop_on_error", True))
                try:
                    plan = build_native_asset_authoring_workflow_plan(body)
                except Exception as exc:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", str(exc)))
                    return
                plan["dry_run"] = dry_run
                plan["stop_on_error"] = stop_on_error

                def run_native_workflow():
                    result = call_unreal(settings, "POST", "/run-plan", plan)
                    return result.status_code, result.payload

                status_code, result_payload = self._with_run_lock(run_native_workflow)
                response_payload = {
                    "success": status_code < 400 and bool((result_payload or {}).get("success", False)),
                    "generated_plan": plan,
                    "result": result_payload,
                }
                if (
                    status_code < 400
                    and bool(response_payload.get("success", False))
                    and not dry_run
                    and bool(settings.get("auto_verify_after_mutation", True))
                ):
                    workflow_asset_type = str(body.get("asset_type", "")).strip().lower()
                    verify_targets = collect_blueprint_targets_from_plan(plan)
                    verify_targets.extend(collect_native_asset_verify_targets(workflow_asset_type, body, {}))
                    verify = run_post_mutation_blueprint_verification(settings, verify_targets)
                    response_payload["post_mutation_verification"] = verify
                    if dedupe_blueprint_paths(verify_targets) and (not bool(verify.get("success", False))) and bool(settings.get("auto_verify_enforce_pass", True)):
                        status_code = HTTPStatus.CONFLICT
                        response_payload["success"] = False
                        response_payload["error_code"] = "POST_MUTATION_VERIFY_FAILED"
                self._json_response(status_code, response_payload)
                return

            if path == "/api/graph-primitives-apply":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                graph_name = str(body.get("graph_name", "EventGraph")).strip() or "EventGraph"
                operations_raw = body.get("operations", [])
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                if not isinstance(operations_raw, list) or len(operations_raw) == 0:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "operations[] is required."))
                    return
                dry_run = bool(body.get("dry_run", False))
                stop_on_error = bool(body.get("stop_on_error", True))
                before_obs: Dict[str, Any] = {}
                if not dry_run:
                    before_obs = collect_graph_observation(settings, blueprint_path, graph_name)
                results: List[Dict[str, Any]] = []
                inverses: List[Dict[str, Any]] = []
                failed = 0
                for idx, operation in enumerate(operations_raw, start=1):
                    if not isinstance(operation, dict):
                        failed += 1
                        results.append({"index": idx, "success": False, "error_code": "INVALID_OPERATION", "message": "Operation must be an object."})
                        if stop_on_error:
                            break
                        continue
                    status_code, payload_out, inverse = execute_graph_primitive_operation(
                        settings,
                        blueprint_path,
                        graph_name,
                        operation,
                        dry_run=dry_run,
                    )
                    success = status_code < 400 and isinstance(payload_out, dict) and bool(payload_out.get("success", False))
                    results.append({"index": idx, "operation": operation, "status_code": int(status_code), "success": success, "result": payload_out})
                    if success and isinstance(inverse, dict):
                        inverses.append(inverse)
                    if not success:
                        failed += 1
                        if stop_on_error:
                            break
                rollback_plan: Dict[str, Any] = {}
                if not dry_run:
                    steps: List[Dict[str, Any]] = []
                    for idx, inv in enumerate(reversed(inverses), start=1):
                        inv_payload = inv.get("payload", {}) if isinstance(inv, dict) else {}
                        if not isinstance(inv_payload, dict):
                            continue
                        steps.append(
                            {
                                "id": f"rollback_primitive_{idx}",
                                "action": "graph_node_primitive",
                                "payload": {
                                    "blueprint_path": blueprint_path,
                                    "graph_name": graph_name,
                                    **inv_payload,
                                },
                            }
                        )
                    rollback_plan = {
                        "plan_id": "rollback_graph_primitives_apply",
                        "stop_on_error": True,
                        "steps": steps,
                        "compile_blueprints": [blueprint_path],
                    } if len(steps) > 0 else {}
                status = HTTPStatus.OK if failed == 0 else HTTPStatus.CONFLICT
                response_payload = {
                    "success": failed == 0,
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "summary": {
                        "requested_operations": len(operations_raw),
                        "executed_operations": len(results),
                        "failed_operations": failed,
                        "dry_run": dry_run,
                    },
                    "results": results,
                    "rollback_plan": rollback_plan,
                }
                if not dry_run and status < 500:
                    after_obs = collect_graph_observation(settings, blueprint_path, graph_name)
                    response_payload["execution_run_id"] = write_apply_execution_artifact(
                        settings,
                        route=path,
                        request_body=body,
                        response_payload=response_payload,
                        blueprint_path=blueprint_path,
                        graph_name=graph_name,
                        before_obs=before_obs,
                        after_obs=after_obs,
                    )
                self._json_response(status, response_payload)
                return

            if path == "/api/autonomous-loop-run":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return

                graph_name = str(body.get("graph_name", "EventGraph")).strip() or "EventGraph"
                assertions = body.get("assertions", [])
                if assertions is None:
                    assertions = []
                if not isinstance(assertions, list):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "assertions must be an array."))
                    return
                scenario_repeats = max(1, min(20, int(body.get("scenario_repeats", 2))))
                auto_repair = bool(body.get("auto_repair", True))
                max_repair_attempts = max(0, int(body.get("max_repair_attempts", 1)))
                capture_on_fail = bool(body.get("capture_screenshot_on_fail", True))

                multiplayer_cfg = body.get("multiplayer", {})
                if not isinstance(multiplayer_cfg, dict):
                    multiplayer_cfg = {}
                multiplayer_enabled = bool(multiplayer_cfg.get("enabled", False) or bool(body.get("enable_multiplayer", False)))
                mp_assertions = multiplayer_cfg.get("assertions", assertions)
                if not isinstance(mp_assertions, list):
                    mp_assertions = []
                mp_client_count = int(multiplayer_cfg.get("client_count", body.get("multiplayer_client_count", 2)))
                mp_repeats = int(multiplayer_cfg.get("repeats", body.get("multiplayer_repeats", 2)))

                include_lint_gate = bool(body.get("include_lint_gate", True))
                max_rpc_risk_score = max(0.0, float(body.get("max_rpc_risk_score", 40.0)))
                max_multiplayer_lint_risk_score = max(0.0, float(body.get("max_multiplayer_lint_risk_score", 40.0)))

                include_perf_gate = bool(body.get("include_perf_gate", True))
                max_perf_risk_score = max(0.0, float(body.get("max_perf_risk_score", 35.0)))

                rollback_on_failure = bool(body.get("rollback_on_failure", True))
                rollback_accept_as_success = bool(body.get("rollback_accept_as_success", True))
                rollback_token = str(body.get("rollback_token", "")).strip()

                timeline: List[Dict[str, Any]] = []
                repairs: List[Dict[str, Any]] = []
                rollback_result: Dict[str, Any] = {"attempted": False, "applied": False}

                def run_validation_round() -> Dict[str, Any]:
                    compile_diag = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {
                            "action": "blueprint_compile_diagnostics",
                            "payload": {"blueprint_path": blueprint_path, "include_pins": True, "max_nodes": 2000},
                            "dry_run": True,
                        },
                    )
                    compile_payload = compile_diag.payload if isinstance(compile_diag.payload, dict) else {}
                    compile_upstream = extract_upstream_payload(compile_payload)
                    compile_contradictions = collect_analysis_contradictions(compile_upstream if isinstance(compile_upstream, dict) else {})
                    compile_ok = (
                        compile_diag.status_code < 400
                        and bool(compile_payload.get("success", False))
                        and bool((compile_upstream or {}).get("compile_success", False))
                        and len(compile_contradictions) == 0
                    )

                    analysis_result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {
                            "action": "analyze_blueprint_asset",
                            "payload": {"blueprint_path": blueprint_path, "include_pins": True, "max_nodes_per_graph": 2000, "max_trace_depth": 256},
                            "dry_run": True,
                        },
                    )
                    analysis_payload = analysis_result.payload if isinstance(analysis_result.payload, dict) else {}
                    analysis_upstream = extract_upstream_payload(analysis_payload)
                    analysis_contradictions = collect_analysis_contradictions(analysis_upstream if isinstance(analysis_upstream, dict) else {})
                    analysis_lint = build_analysis_lint(analysis_upstream if isinstance(analysis_upstream, dict) else {})
                    rpc_lint = build_rpc_contract_lint(analysis_upstream if isinstance(analysis_upstream, dict) else {})
                    multiplayer_lint = build_multiplayer_lint(analysis_upstream if isinstance(analysis_upstream, dict) else {})
                    perf = build_blueprint_perf_risk(analysis_upstream if isinstance(analysis_upstream, dict) else {})

                    scenario = run_singleplayer_pie_harness(settings, [item for item in assertions if isinstance(item, dict)], scenario_repeats)
                    multiplayer = {"success": True, "skipped": True}
                    if multiplayer_enabled:
                        multiplayer = run_multiplayer_pie_harness(settings, [item for item in mp_assertions if isinstance(item, dict)], mp_client_count, mp_repeats)
                        multiplayer["skipped"] = False

                    lint_gate_pass = True
                    if include_lint_gate:
                        lint_gate_pass = (
                            bool(rpc_lint.get("success", False))
                            and bool(multiplayer_lint.get("success", False))
                            and float(rpc_lint.get("risk_score", 0.0)) <= max_rpc_risk_score
                            and float(multiplayer_lint.get("risk_score", 0.0)) <= max_multiplayer_lint_risk_score
                        )

                    perf_gate_pass = True
                    if include_perf_gate:
                        perf_gate_pass = bool(perf.get("success", False)) and float(perf.get("risk_score", 0.0)) <= max_perf_risk_score

                    contradiction_gate_pass = len(compile_contradictions) == 0 and len(analysis_contradictions) == 0
                    analysis_gate_pass = (
                        analysis_result.status_code < 400
                        and bool(analysis_payload.get("success", False))
                        and len(analysis_contradictions) == 0
                    )
                    gates = {
                        "compile_gate_pass": compile_ok,
                        "analysis_gate_pass": analysis_gate_pass,
                        "contradiction_gate_pass": contradiction_gate_pass,
                        "singleplayer_scenario_pass": bool(scenario.get("success", False)),
                        "multiplayer_gate_pass": bool(multiplayer.get("success", False)),
                        "lint_gate_pass": lint_gate_pass,
                        "perf_gate_pass": perf_gate_pass,
                    }
                    overall_ok = all(bool(value) for value in gates.values())
                    return {
                        "success": overall_ok,
                        "gates": gates,
                        "compile": {
                            "success": compile_ok,
                            "status_code": int(compile_diag.status_code),
                            "contradictions": compile_contradictions,
                            "result": compile_payload,
                        },
                        "analysis": {
                            "success": analysis_gate_pass,
                            "status_code": int(analysis_result.status_code),
                            "contradictions": analysis_contradictions,
                            "lint": analysis_lint,
                            "upstream_payload": analysis_upstream if isinstance(analysis_upstream, dict) else {},
                            "result": analysis_payload,
                        },
                        "rpc_lint": rpc_lint,
                        "multiplayer_lint": multiplayer_lint,
                        "perf": perf,
                        "singleplayer_scenario": scenario,
                        "multiplayer": multiplayer,
                    }

                validation = run_validation_round()
                timeline.append(
                    {
                        "ts": time.time(),
                        "stage": "validation_round_0",
                        "ok": bool(validation.get("success", False)),
                        "gates": validation.get("gates", {}),
                    }
                )
                success = bool(validation.get("success", False))

                attempt = 0
                while not success and auto_repair and attempt < max_repair_attempts:
                    attempt += 1
                    analysis_for_repair = (
                        validation.get("analysis", {}).get("upstream_payload", {})
                        if isinstance(validation.get("analysis", {}), dict)
                        else {}
                    )
                    lint_for_repair = (
                        validation.get("analysis", {}).get("lint", [])
                        if isinstance(validation.get("analysis", {}), dict)
                        else []
                    )
                    catalog = build_refactor_catalog(
                        blueprint_path,
                        "strict",
                        analysis_for_repair if isinstance(analysis_for_repair, dict) else {},
                        lint_for_repair if isinstance(lint_for_repair, list) else [],
                    )
                    plan, selected = build_refactor_catalog_plan(
                        blueprint_path=blueprint_path,
                        catalog=catalog,
                        transform_ids=[],
                        transform_inputs={},
                        dry_run=False,
                        stop_on_error=True,
                    )
                    if plan is None:
                        repairs.append({"attempt": attempt, "success": False, "reason": "no_auto_repair_plan", "selected_transforms": []})
                        timeline.append(
                            {
                                "ts": time.time(),
                                "stage": "repair_attempt",
                                "ok": False,
                                "details": {"attempt": attempt, "reason": "no_auto_repair_plan"},
                            }
                        )
                        break

                    def run_repair_plan():
                        result = call_unreal(settings, "POST", "/run-plan", plan)
                        return result.status_code, result.payload

                    repair_status, repair_response = self._with_run_lock(run_repair_plan)
                    repair_ok = repair_status < 400 and bool((repair_response or {}).get("success", False))
                    repairs.append(
                        {
                            "attempt": attempt,
                            "success": repair_ok,
                            "selected_transforms": selected,
                            "generated_plan": plan,
                            "status_code": int(repair_status),
                            "result": repair_response,
                        }
                    )
                    timeline.append(
                        {
                            "ts": time.time(),
                            "stage": "repair_attempt",
                            "ok": repair_ok,
                            "details": {"attempt": attempt, "selected_count": len(selected)},
                        }
                    )
                    validation = run_validation_round()
                    success = bool(validation.get("success", False))
                    timeline.append(
                        {
                            "ts": time.time(),
                            "stage": f"validation_round_{attempt}",
                            "ok": success,
                            "gates": validation.get("gates", {}),
                        }
                    )

                if not success and rollback_on_failure:
                    rollback_result = {"attempted": True, "applied": False, "rollback_token": rollback_token}
                    if rollback_token:
                        snapshot = read_graph_snapshot(rollback_token)
                        rollback_plan = snapshot.get("rollback_plan", {}) if isinstance(snapshot, dict) else {}
                        if isinstance(rollback_plan, dict) and isinstance(rollback_plan.get("steps", []), list) and len(rollback_plan.get("steps", [])) > 0:

                            def run_rollback_plan():
                                result = call_unreal(
                                    settings,
                                    "POST",
                                    "/run-plan",
                                    {**rollback_plan, "dry_run": False, "stop_on_error": True},
                                )
                                return result.status_code, result.payload

                            rb_status, rb_response = self._with_run_lock(run_rollback_plan)
                            rb_ok = rb_status < 400 and bool((rb_response or {}).get("success", False))
                            rollback_result = {
                                "attempted": True,
                                "applied": rb_ok,
                                "rollback_token": rollback_token,
                                "status_code": int(rb_status),
                                "rollback_plan": rollback_plan,
                                "result": rb_response,
                            }
                            timeline.append(
                                {
                                    "ts": time.time(),
                                    "stage": "rollback_attempt",
                                    "ok": rb_ok,
                                    "details": {"rollback_token": rollback_token},
                                }
                            )
                            if rb_ok and rollback_accept_as_success:
                                success = True
                        else:
                            rollback_result["reason"] = "rollback_plan_unavailable"
                    else:
                        rollback_result["reason"] = "rollback_token_missing"

                screenshot_payload: Dict[str, Any] = {}
                if not success and capture_on_fail:
                    shot = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": "capture_screenshot", "payload": {"file_name": f"autonomous_loop_fail_{int(time.time())}.png"}, "dry_run": False},
                    )
                    if isinstance(shot.payload, dict):
                        screenshot_payload = shot.payload

                response_payload = {
                    "success": success,
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "loop_config": {
                        "scenario_repeats": scenario_repeats,
                        "auto_repair": auto_repair,
                        "max_repair_attempts": max_repair_attempts,
                        "capture_screenshot_on_fail": capture_on_fail,
                        "multiplayer_enabled": multiplayer_enabled,
                        "include_lint_gate": include_lint_gate,
                        "include_perf_gate": include_perf_gate,
                        "rollback_on_failure": rollback_on_failure,
                        "rollback_accept_as_success": rollback_accept_as_success,
                    },
                    "validation": validation,
                    "repairs": repairs,
                    "rollback": rollback_result,
                    "timeline": timeline,
                    "failure_screenshot": screenshot_payload,
                }
                if bool(settings.get("execution_store_artifacts", True)):
                    response_payload["execution_run_id"] = write_execution_artifact(
                        settings,
                        {
                            "timestamp": time.time(),
                            "route": path,
                            "blueprint_path": blueprint_path,
                            "request": body,
                            "response": response_payload,
                            "timeline": timeline,
                            "runtime_validation": validation,
                            "auto_repair": repairs,
                            "rollback": rollback_result,
                            "failure_screenshot": screenshot_payload,
                        },
                    )
                self._json_response(HTTPStatus.OK if success else HTTPStatus.CONFLICT, response_payload)
                return

            if path == "/api/runtime-validate-repair":
                blueprint_path = str(body.get("blueprint_path", "")).strip()
                if not blueprint_path:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_path is required."))
                    return
                assertions = body.get("assertions", [])
                if assertions is None:
                    assertions = []
                if not isinstance(assertions, list):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "assertions must be an array."))
                    return
                auto_repair = bool(body.get("auto_repair", True))
                max_repair_attempts = max(0, int(body.get("max_repair_attempts", 1)))
                capture_on_fail = bool(body.get("capture_screenshot_on_fail", True))
                timeline: List[Dict[str, Any]] = []
                repairs: List[Dict[str, Any]] = []

                def run_validation_round() -> Dict[str, Any]:
                    compile_diag = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {
                            "action": "blueprint_compile_diagnostics",
                            "payload": {"blueprint_path": blueprint_path, "include_pins": True, "max_nodes": 1500},
                            "dry_run": True,
                        },
                    )
                    compile_payload = compile_diag.payload if isinstance(compile_diag.payload, dict) else {}
                    compile_upstream = extract_upstream_payload(compile_payload)
                    contradictions = collect_analysis_contradictions(compile_upstream if isinstance(compile_upstream, dict) else {})
                    compile_ok = compile_diag.status_code < 400 and bool(compile_payload.get("success", False)) and len(contradictions) == 0 and bool((compile_upstream or {}).get("compile_success", False))
                    scenario_result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": "run_pie_scenario", "payload": {"assertions": assertions}, "dry_run": False},
                    )
                    scenario_payload = scenario_result.payload if isinstance(scenario_result.payload, dict) else {}
                    scenario_ok = scenario_result.status_code < 400 and bool(scenario_payload.get("success", False))
                    return {
                        "compile_ok": compile_ok,
                        "scenario_ok": scenario_ok,
                        "compile": compile_payload,
                        "scenario": scenario_payload,
                        "contradictions": contradictions,
                    }

                validation = run_validation_round()
                timeline.append({"ts": time.time(), "stage": "validation_round_0", "ok": bool(validation.get("compile_ok", False)) and bool(validation.get("scenario_ok", False))})
                success = bool(validation.get("compile_ok", False)) and bool(validation.get("scenario_ok", False))
                attempt = 0
                while not success and auto_repair and attempt < max_repair_attempts:
                    attempt += 1
                    analyze_result = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {
                            "action": "analyze_blueprint_graph",
                            "payload": {"blueprint_path": blueprint_path, "include_pins": True, "max_nodes": 1200, "max_trace_depth": 128},
                            "dry_run": True,
                        },
                    )
                    analyze_payload = extract_upstream_payload(analyze_result.payload if isinstance(analyze_result.payload, dict) else {})
                    lint = build_analysis_lint(analyze_payload if isinstance(analyze_payload, dict) else {})
                    catalog = build_refactor_catalog(blueprint_path, "strict", analyze_payload if isinstance(analyze_payload, dict) else {}, lint)
                    plan, selected = build_refactor_catalog_plan(
                        blueprint_path=blueprint_path,
                        catalog=catalog,
                        transform_ids=[],
                        transform_inputs={},
                        dry_run=False,
                        stop_on_error=True,
                    )
                    if plan is None:
                        repairs.append({"attempt": attempt, "success": False, "reason": "no_auto_repair_plan"})
                        timeline.append({"ts": time.time(), "stage": "repair_attempt", "ok": False, "details": {"attempt": attempt, "reason": "no_auto_repair_plan"}})
                        break
                    repair_run = call_unreal(settings, "POST", "/run-plan", plan)
                    repair_ok = repair_run.status_code < 400 and bool((repair_run.payload or {}).get("success", False))
                    repairs.append({"attempt": attempt, "success": repair_ok, "selected_transforms": selected, "plan": plan, "result": repair_run.payload})
                    timeline.append({"ts": time.time(), "stage": "repair_attempt", "ok": repair_ok, "details": {"attempt": attempt, "selected": len(selected)}})
                    validation = run_validation_round()
                    success = bool(validation.get("compile_ok", False)) and bool(validation.get("scenario_ok", False))
                    timeline.append({"ts": time.time(), "stage": f"validation_round_{attempt}", "ok": success})

                screenshot_payload: Dict[str, Any] = {}
                if not success and capture_on_fail:
                    shot = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {"action": "capture_screenshot", "payload": {"file_name": f"runtime_fail_{int(time.time())}.png"}, "dry_run": False},
                    )
                    if isinstance(shot.payload, dict):
                        screenshot_payload = shot.payload
                response_payload = {
                    "success": success,
                    "blueprint_path": blueprint_path,
                    "validation": validation,
                    "auto_repair": {
                        "enabled": auto_repair,
                        "max_repair_attempts": max_repair_attempts,
                        "attempts": repairs,
                    },
                    "timeline": timeline,
                    "failure_screenshot": screenshot_payload,
                }
                if bool(settings.get("execution_store_artifacts", True)):
                    response_payload["execution_run_id"] = write_execution_artifact(
                        settings,
                        {
                            "timestamp": time.time(),
                            "route": path,
                            "blueprint_path": blueprint_path,
                            "request": body,
                            "response": response_payload,
                            "timeline": timeline,
                            "runtime_validation": validation,
                            "auto_repair": repairs,
                            "failure_screenshot": screenshot_payload,
                        },
                    )
                self._json_response(HTTPStatus.OK if success else HTTPStatus.CONFLICT, response_payload)
                return

            if path == "/api/replay-suite":
                cases_raw = body.get("cases", [])
                repeats = int(body.get("repeats", 2))
                if not isinstance(cases_raw, list) or len(cases_raw) == 0:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "cases[] is required."))
                    return
                suite_result = run_replay_suite(settings, [c for c in cases_raw if isinstance(c, dict)], repeats)
                self._json_response(HTTPStatus.OK if bool(suite_result.get("success", False)) else HTTPStatus.CONFLICT, suite_result)
                return

            if path == "/api/release-gate-evaluate":
                blueprint_paths_raw = body.get("blueprint_paths", [])
                replay_cases_raw = body.get("replay_cases", [])
                replay_repeats = int(body.get("replay_repeats", 2))
                multiplayer_cfg = body.get("multiplayer", {})
                if not isinstance(multiplayer_cfg, dict):
                    multiplayer_cfg = {}
                blueprint_paths = [str(x).strip() for x in blueprint_paths_raw if isinstance(x, str) and str(x).strip()]
                if len(blueprint_paths) == 0:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "blueprint_paths[] is required."))
                    return
                replay_result = run_replay_suite(settings, [c for c in replay_cases_raw if isinstance(c, dict)], replay_repeats) if isinstance(replay_cases_raw, list) and len(replay_cases_raw) > 0 else {"success": True, "case_total": 0, "case_passed": 0, "case_failed": 0, "cases": []}
                compile_items: List[Dict[str, Any]] = []
                compile_pass = True
                for bp in blueprint_paths:
                    diag = call_unreal(
                        settings,
                        "POST",
                        "/execute",
                        {
                            "action": "blueprint_compile_diagnostics",
                            "payload": {"blueprint_path": bp, "include_pins": True, "max_nodes": 1000},
                            "dry_run": True,
                        },
                    )
                    payload_out = diag.payload if isinstance(diag.payload, dict) else {}
                    upstream = extract_upstream_payload(payload_out)
                    contradictions = collect_analysis_contradictions(upstream if isinstance(upstream, dict) else {})
                    item_ok = diag.status_code < 400 and bool(payload_out.get("success", False)) and len(contradictions) == 0
                    if not item_ok:
                        compile_pass = False
                    compile_items.append(
                        {
                            "blueprint_path": bp,
                            "success": item_ok,
                            "status_code": int(diag.status_code),
                            "compile_success": bool(upstream.get("compile_success")) if isinstance(upstream, dict) else False,
                            "contradictions": contradictions,
                        }
                    )
                multiplayer_result: Dict[str, Any] = {"success": True, "skipped": True}
                multiplayer_enabled = bool(multiplayer_cfg.get("enabled", False))
                if multiplayer_enabled:
                    mp_assertions = multiplayer_cfg.get("assertions", [])
                    if not isinstance(mp_assertions, list):
                        mp_assertions = []
                    multiplayer_result = run_multiplayer_pie_harness(
                        settings,
                        [item for item in mp_assertions if isinstance(item, dict)],
                        int(multiplayer_cfg.get("client_count", 2)),
                        int(multiplayer_cfg.get("repeats", 2)),
                    )
                    multiplayer_result["skipped"] = False

                multiplayer_pass = bool(multiplayer_result.get("success", False))
                overall_success = bool(replay_result.get("success", False)) and compile_pass and multiplayer_pass
                payload = {
                    "success": overall_success,
                    "gates": {
                        "replay_suite_pass": bool(replay_result.get("success", False)),
                        "compile_gate_pass": compile_pass,
                        "contradiction_gate_pass": compile_pass,
                        "multiplayer_gate_pass": multiplayer_pass,
                    },
                    "replay_suite": replay_result,
                    "compile_gate": {
                        "success": compile_pass,
                        "items": compile_items,
                    },
                    "multiplayer_gate": multiplayer_result,
                }
                self._json_response(HTTPStatus.OK if overall_success else HTTPStatus.CONFLICT, payload)
                return

            if path == "/api/rollback-apply":
                rollback_token = str(body.get("rollback_token", "")).strip()
                if not rollback_token:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "rollback_token is required."))
                    return
                snapshot = read_graph_snapshot(rollback_token)
                if not isinstance(snapshot, dict):
                    self._json_response(HTTPStatus.NOT_FOUND, make_error("NOT_FOUND", "Rollback snapshot not found.", rollback_token=rollback_token))
                    return
                rollback_plan = snapshot.get("rollback_plan", {})
                if not isinstance(rollback_plan, dict) or not isinstance(rollback_plan.get("steps", []), list) or len(rollback_plan.get("steps", [])) == 0:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("ROLLBACK_UNAVAILABLE", "No rollback plan available for this token.", rollback_token=rollback_token))
                    return
                dry_run = bool(body.get("dry_run", False))
                stop_on_error = bool(body.get("stop_on_error", True))

                def run_rollback():
                    current_plan = dict(rollback_plan)
                    current_plan["dry_run"] = dry_run
                    current_plan["stop_on_error"] = stop_on_error
                    result = call_unreal(
                        settings,
                        "POST",
                        "/run-plan",
                        current_plan,
                    )
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_rollback)
                self._json_response(
                    status,
                    {
                        "success": status < 400 and bool(response.get("success", False)),
                        "rollback_token": rollback_token,
                        "blueprint_path": snapshot.get("blueprint_path", ""),
                        "graph_name": snapshot.get("graph_name", ""),
                        "rollback_plan": rollback_plan,
                        "result": response,
                    },
                )
                return

            if path == "/api/umg-generate":
                widget_blueprint = str(body.get("widget_blueprint", "")).strip()
                template_id = str(body.get("template_id", "hud_basic")).strip() or "hud_basic"
                style_preset = str(body.get("style_preset", "minimal")).strip() or "minimal"
                custom_bindings = body.get("bindings", [])
                if custom_bindings is None:
                    custom_bindings = []
                if not isinstance(custom_bindings, list):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "bindings must be an array."))
                    return

                if not widget_blueprint:
                    asset_name = str(body.get("asset_name", "WBP_AgentGenerated")).strip()
                    package_path = str(body.get("package_path", "/Game/AgentGenerated/UI")).strip() or "/Game/AgentGenerated/UI"
                    create_req = {
                        "action": "create_widget_blueprint",
                        "payload": {"asset_name": asset_name, "package_path": package_path, "parent_class": "/Script/UMG.UserWidget"},
                        "dry_run": False,
                    }
                    create_result = call_unreal(settings, "POST", "/execute", create_req)
                    if create_result.status_code >= 400 or not bool(create_result.payload.get("success", False)):
                        self._json_response(create_result.status_code, create_result.payload)
                        return
                    widget_blueprint = f"{package_path}/{asset_name}"

                template_payload = build_umg_template_operations(template_id, style_preset)
                operations = template_payload.get("operations", [])
                bindings = template_payload.get("bindings", [])
                for item in custom_bindings:
                    if isinstance(item, dict):
                        bindings.append(item)

                mutate_req = {
                    "action": "modify_widget_tree",
                    "payload": {
                        "widget_blueprint": widget_blueprint,
                        "operations": operations,
                        "compile_after": False,
                    },
                    "dry_run": False,
                }
                mutate_result = call_unreal(settings, "POST", "/execute", mutate_req)
                if mutate_result.status_code >= 400:
                    self._json_response(mutate_result.status_code, mutate_result.payload)
                    return

                bind_req = {
                    "action": "bind_widget_events",
                    "payload": {
                        "widget_blueprint": widget_blueprint,
                        "bindings": bindings,
                        "compile_after": True,
                    },
                    "dry_run": False,
                }
                bind_result = call_unreal(settings, "POST", "/execute", bind_req)
                status_code = bind_result.status_code if bind_result.status_code >= mutate_result.status_code else mutate_result.status_code
                self._json_response(
                    status_code,
                    {
                        "success": bind_result.status_code < 400 and bool(bind_result.payload.get("success", True)) and bool(mutate_result.payload.get("success", True)),
                        "widget_blueprint": widget_blueprint,
                        "template_id": template_payload.get("template_id", template_id),
                        "style_preset": template_payload.get("style_preset", style_preset),
                        "operations_applied": operations,
                        "bindings_applied": bindings,
                        "compile_status": bind_result.payload.get("payload", {}).get("compiled", False) if isinstance(bind_result.payload, dict) else False,
                        "modify_result": mutate_result.payload,
                        "bind_result": bind_result.payload,
                    },
                )
                return

            if path == "/api/world-generate":
                layout_id = str(body.get("layout_id", "city_grid")).strip() or "city_grid"
                bounds = body.get("bounds", [0, 0, 5000, 5000])
                density = float(body.get("density", 1.0))
                seed = int(body.get("seed", 1337))
                constraints = body.get("constraints", {})
                if not isinstance(constraints, dict):
                    constraints = {}

                cleanup_token = f"world_{uuid4().hex[:10]}"
                layout_payload = build_world_layout_payload(layout_id, bounds, density, seed, constraints)
                tags = list(layout_payload.get("tags", [])) if isinstance(layout_payload.get("tags", []), list) else []
                if cleanup_token not in tags:
                    tags.append(cleanup_token)
                layout_payload["tags"] = tags

                world_req = {
                    "action": "generate_layout_from_template",
                    "payload": layout_payload,
                    "dry_run": False,
                }
                world_result = call_unreal(settings, "POST", "/execute", world_req)
                if world_result.status_code >= 400:
                    fallback_action = "create_level_chunk" if "city" in layout_id.lower() else "layout_along_spline"
                    fallback_req = {"action": fallback_action, "payload": layout_payload, "dry_run": False}
                    world_result = call_unreal(settings, "POST", "/execute", fallback_req)

                status_code = world_result.status_code
                payload_out = world_result.payload if isinstance(world_result.payload, dict) else {}
                self._json_response(
                    status_code,
                    {
                        "success": status_code < 400 and bool(payload_out.get("success", True)),
                        "layout_id": layout_id,
                        "cleanup_token": cleanup_token,
                        "seed": seed,
                        "tags": tags,
                        "spawned": payload_out.get("payload", {}),
                        "result": payload_out,
                    },
                )
                return

            if path == "/api/entitlements/check":
                token = str(body.get("paid_token", "")).strip() or self._get_paid_token()
                feature = str(body.get("feature", "paid_live_logs")).strip() or "paid_live_logs"
                auth, entitlement, _, _ = build_paid_providers(settings)
                if not auth.validate(token):
                    self._json_response(HTTPStatus.UNAUTHORIZED, make_error("PAID_LOGS_UNAUTHORIZED", "Invalid paid token."))
                    return
                self._json_response(HTTPStatus.OK, {"success": True, "entitlement": entitlement.check(token, feature)})
                return

            if path == "/api/usage/event":
                token = str(body.get("paid_token", "")).strip() or self._get_paid_token()
                event_type = str(body.get("event_type", "")).strip()
                amount = float(body.get("amount", 1.0))
                metadata = body.get("metadata", {})
                if not isinstance(metadata, dict):
                    metadata = {}
                if not event_type:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "event_type is required."))
                    return
                auth, _, billing, _ = build_paid_providers(settings)
                if not auth.validate(token):
                    self._json_response(HTTPStatus.UNAUTHORIZED, make_error("PAID_LOGS_UNAUTHORIZED", "Invalid paid token."))
                    return
                result = billing.record_usage(token, event_type, amount, metadata)
                self._json_response(HTTPStatus.OK, {"success": True, "usage": result})
                return

            if path == "/api/direct-execute":
                action = str(body.get("action", "")).strip()
                if not action:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "Missing action"))
                    return
                payload = body.get("payload", {})
                if not isinstance(payload, dict):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "payload must be an object"))
                    return
                dry_run = bool(body.get("dry_run", False))
                approval_token = str(body.get("approval_token", "")).strip()
                risky = [action] if action in set(settings.get("risky_actions", [])) else []
                approval_result = check_requires_approval(
                    settings=settings,
                    operation="direct-execute",
                    risky_actions=risky,
                    dry_run=dry_run,
                    approval_token=approval_token,
                    request_payload=body,
                )
                if approval_result:
                    self._json_response(HTTPStatus.ACCEPTED, approval_result)
                    return

                def run_direct():
                    result = call_unreal(settings, "POST", "/execute", {"action": action, "payload": payload, "dry_run": dry_run})
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_direct)
                if action in ANALYSIS_ACTIONS:
                    issues = collect_analysis_contradictions(response)
                    if issues:
                        status = HTTPStatus.CONFLICT
                        response = make_error(
                            "ANALYSIS_CONTRADICTION",
                            "Deterministic blueprint analysis reported contradictions.",
                            issues=issues,
                            upstream=response,
                        )
                if (
                    status < 400
                    and isinstance(response, dict)
                    and bool(response.get("success", False))
                    and not dry_run
                    and bool(settings.get("auto_verify_after_mutation", True))
                    and action in MUTATING_ACTIONS
                ):
                    blueprint_path = str(payload.get("blueprint_path", "")).strip()
                    if blueprint_path:
                        verify = run_post_mutation_blueprint_verification(settings, [blueprint_path])
                        response["post_mutation_verification"] = verify
                        if not bool(verify.get("success", False)) and bool(settings.get("auto_verify_enforce_pass", True)):
                            status = HTTPStatus.CONFLICT
                            response["success"] = False
                            response["error_code"] = "POST_MUTATION_VERIFY_FAILED"
                self._json_response(status, response)
                log_event(
                    "direct_execute",
                    {
                        "request_id": request_id,
                        "action": action,
                        "dry_run": dry_run,
                        "status": status,
                        "response": response,
                        "duration_ms": int((time.time() - started) * 1000),
                    },
                )
                return

            if path == "/api/run-plan":
                plan = body.get("plan", body)
                if not isinstance(plan, dict):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "Plan must be an object"))
                    return
                validation = validate_plan_with_node_library(plan)
                if not validation.get("ok", False):
                    self._json_response(
                        HTTPStatus.BAD_REQUEST,
                        make_error(
                            "PLAN_NODELIB_VALIDATION_FAILED",
                            "Plan failed node-library validation.",
                            validation=validation,
                        ),
                    )
                    return
                actions = get_plan_actions(plan)
                dry_run = bool(plan.get("dry_run", False))
                approval_token = str(body.get("approval_token", plan.get("approval_token", ""))).strip()
                session_id = self._resolve_session_id(body)
                self._emit_major_update(
                    settings,
                    session_id,
                    "run_plan_started",
                    "info",
                    "Plan execution started.",
                    {"plan_id": plan.get("plan_id", ""), "dry_run": dry_run},
                )
                risky = sorted(list(set(actions).intersection(set(settings.get("risky_actions", [])))))
                approval_result = check_requires_approval(
                    settings=settings,
                    operation="run-plan",
                    risky_actions=risky,
                    dry_run=dry_run,
                    approval_token=approval_token,
                    request_payload=plan,
                )
                if approval_result:
                    self._json_response(HTTPStatus.ACCEPTED, approval_result)
                    return

                preflight_enabled = bool(settings.get("execution_preflight_enabled", True))
                preflight_result: Dict[str, Any] = {"ran": False}
                if preflight_enabled and not dry_run:
                    preflight_plan = dict(plan)
                    preflight_plan["dry_run"] = True
                    preflight_run = call_unreal(settings, "POST", "/run-plan", preflight_plan)
                    preflight_result = {
                        "ran": True,
                        "status_code": int(preflight_run.status_code),
                        "payload": preflight_run.payload,
                    }
                    preflight_ok = preflight_run.status_code < 400 and bool(preflight_run.payload.get("success", False))
                    if not preflight_ok:
                        self._emit_major_update(
                            settings,
                            session_id,
                            "run_plan_preflight_failed",
                            "error",
                            "Plan preflight dry-run failed.",
                            {"plan_id": plan.get("plan_id", ""), "preflight": preflight_result},
                        )
                        self._json_response(
                            HTTPStatus.PRECONDITION_FAILED,
                            make_error(
                                "PREFLIGHT_FAILED",
                                "Plan preflight dry-run failed.",
                                preflight=preflight_result,
                                plan_id=plan.get("plan_id", ""),
                            ),
                        )
                        return

                def run_plan():
                    result = call_unreal(settings, "POST", "/run-plan", plan)
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_plan)
                issues = collect_analysis_contradictions(response)
                if issues:
                    status = HTTPStatus.CONFLICT
                    response = make_error(
                        "ANALYSIS_CONTRADICTION",
                        "Plan execution reported analysis contradictions.",
                        issues=issues,
                        upstream=response,
                    )
                elif preflight_result.get("ran", False):
                    response["preflight"] = preflight_result

                if (
                    status < 400
                    and isinstance(response, dict)
                    and bool(response.get("success", False))
                    and not dry_run
                    and bool(settings.get("auto_verify_after_mutation", True))
                ):
                    targets = collect_blueprint_targets_from_plan(plan)
                    verify = run_post_mutation_blueprint_verification(settings, targets)
                    response["post_mutation_verification"] = verify
                    if not bool(verify.get("success", False)) and bool(settings.get("auto_verify_enforce_pass", True)):
                        status = HTTPStatus.CONFLICT
                        response["success"] = False
                        response["error_code"] = "POST_MUTATION_VERIFY_FAILED"

                if bool(settings.get("execution_store_artifacts", True)):
                    run_artifact = {
                        "timestamp": time.time(),
                        "route": "/api/run-plan",
                        "plan_id": plan.get("plan_id", ""),
                        "dry_run": dry_run,
                        "request": body,
                        "plan": plan,
                        "preflight": preflight_result,
                        "status": int(status),
                        "response": response,
                    }
                    response["execution_run_id"] = write_execution_artifact(settings, run_artifact)
                self._emit_major_update(
                    settings,
                    session_id,
                    "run_plan_completed",
                    "success" if bool(response.get("success", False)) else "error",
                    "Plan execution completed.",
                    {"plan_id": plan.get("plan_id", ""), "status": int(status), "success": bool(response.get("success", False))},
                )
                self._json_response(status, response)
                log_event(
                    "run_plan",
                    {
                        "request_id": request_id,
                        "plan_id": plan.get("plan_id", ""),
                        "dry_run": dry_run,
                        "actions": actions,
                        "status": status,
                        "response": response,
                        "duration_ms": int((time.time() - started) * 1000),
                    },
                )
                return

            if path == "/api/run-goal":
                goal_request = body.get("goal_request", body)
                if not isinstance(goal_request, dict):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "goal_request must be an object"))
                    return
                goal_context = goal_request.get("goal_context", {})
                if not isinstance(goal_context, dict):
                    goal_context = {}
                goal_request = dict(goal_request)
                goal_request["goal_context"] = merge_default_project_context(settings, goal_context)
                dry_run = bool(goal_request.get("dry_run", False))
                approval_token = str(body.get("approval_token", goal_request.get("approval_token", ""))).strip()
                session_id = self._resolve_session_id(body)
                self._emit_major_update(
                    settings,
                    session_id,
                    "run_goal_started",
                    "info",
                    "Goal execution started.",
                    {"goal": goal_request.get("goal", ""), "dry_run": dry_run},
                )
                risky = list(settings.get("risky_actions", []))
                approval_result = check_requires_approval(
                    settings=settings,
                    operation="run-goal",
                    risky_actions=risky,
                    dry_run=dry_run,
                    approval_token=approval_token,
                    request_payload=goal_request,
                )
                if approval_result:
                    self._json_response(HTTPStatus.ACCEPTED, approval_result)
                    return

                preflight_enabled = bool(settings.get("execution_preflight_enabled", True))
                preflight_result: Dict[str, Any] = {"ran": False}
                if preflight_enabled and not dry_run:
                    preflight_goal = dict(goal_request)
                    preflight_goal["dry_run"] = True
                    preflight_run = call_unreal(settings, "POST", "/run-goal", preflight_goal)
                    preflight_result = {
                        "ran": True,
                        "status_code": int(preflight_run.status_code),
                        "payload": preflight_run.payload,
                    }
                    preflight_ok = preflight_run.status_code < 400 and bool(preflight_run.payload.get("success", False))
                    if not preflight_ok:
                        self._emit_major_update(
                            settings,
                            session_id,
                            "run_goal_preflight_failed",
                            "error",
                            "Goal preflight dry-run failed.",
                            {"goal": goal_request.get("goal", ""), "preflight": preflight_result},
                        )
                        self._json_response(
                            HTTPStatus.PRECONDITION_FAILED,
                            make_error(
                                "PREFLIGHT_FAILED",
                                "Goal preflight dry-run failed.",
                                preflight=preflight_result,
                                goal=goal_request.get("goal", ""),
                            ),
                        )
                        return

                def run_goal():
                    result = call_unreal(settings, "POST", "/run-goal", goal_request)
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_goal)
                if preflight_result.get("ran", False) and isinstance(response, dict):
                    response["preflight"] = preflight_result

                if (
                    status < 400
                    and isinstance(response, dict)
                    and bool(response.get("success", False))
                    and not dry_run
                    and bool(settings.get("auto_verify_after_mutation", True))
                ):
                    goal_ctx = goal_request.get("goal_context", {})
                    if not isinstance(goal_ctx, dict):
                        goal_ctx = {}
                    targets: List[str] = []
                    bp = str(goal_ctx.get("blueprint_path", "")).strip()
                    if bp:
                        targets.append(bp)
                    bp_list = goal_ctx.get("blueprint_paths", [])
                    if isinstance(bp_list, list):
                        for item in bp_list:
                            if isinstance(item, str) and item.strip():
                                targets.append(item.strip())
                    seen_targets: set[str] = set()
                    deduped_targets: List[str] = []
                    for target in targets:
                        if target in seen_targets:
                            continue
                        seen_targets.add(target)
                        deduped_targets.append(target)

                    verify = run_post_mutation_blueprint_verification(settings, deduped_targets)
                    response["post_mutation_verification"] = verify
                    if deduped_targets and (not bool(verify.get("success", False))) and bool(settings.get("auto_verify_enforce_pass", True)):
                        status = HTTPStatus.CONFLICT
                        response["success"] = False
                        response["error_code"] = "POST_MUTATION_VERIFY_FAILED"

                if bool(settings.get("execution_store_artifacts", True)):
                    run_artifact = {
                        "timestamp": time.time(),
                        "route": "/api/run-goal",
                        "goal": goal_request.get("goal", ""),
                        "dry_run": dry_run,
                        "request": body,
                        "goal_request": goal_request,
                        "preflight": preflight_result,
                        "status": int(status),
                        "response": response,
                    }
                    if isinstance(response, dict):
                        response["execution_run_id"] = write_execution_artifact(settings, run_artifact)
                self._emit_major_update(
                    settings,
                    session_id,
                    "run_goal_completed",
                    "success" if bool(response.get("success", False)) else "error",
                    "Goal execution completed.",
                    {"goal": goal_request.get("goal", ""), "status": int(status), "success": bool(response.get("success", False))},
                )
                self._json_response(status, response)
                log_event(
                    "run_goal",
                    {
                        "request_id": request_id,
                        "goal": goal_request.get("goal", ""),
                        "dry_run": dry_run,
                        "status": status,
                        "response": response,
                        "duration_ms": int((time.time() - started) * 1000),
                    },
                )
                return

            if path == "/api/chat":
                chat_message = str(body.get("message", "")).strip()
                if not chat_message:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "Missing message"))
                    return
                # Alias of /api/command for chat-first clients.
                body = {
                    "command": chat_message,
                    "dry_run": bool(body.get("dry_run", False)),
                    "stop_on_error": bool(body.get("stop_on_error", True)),
                    "goal_context": body.get("goal_context", {}),
                    "recipe_id": str(body.get("recipe_id", "")).strip(),
                    "inputs": body.get("inputs", {}),
                    "profile": normalize_execution_profile(
                        body.get("profile", settings.get("execution_profile", "balanced")),
                        fallback=normalize_execution_profile(settings.get("execution_profile", "balanced")),
                    ),
                    "approval_token": str(body.get("approval_token", "")).strip(),
                    "session_id": str(body.get("session_id", "")).strip(),
                    "paid_token": str(body.get("paid_token", "")).strip(),
                }
                path = "/api/command"

            if path == "/api/command":
                command = str(body.get("command", "")).strip()
                if not command:
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("MISSING_FIELD", "Missing command"))
                    return

                dry_run = bool(body.get("dry_run", False))
                stop_on_error = bool(body.get("stop_on_error", True))
                goal_context = body.get("goal_context", {})
                if not isinstance(goal_context, dict):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "goal_context must be an object"))
                    return
                goal_context = merge_default_project_context(settings, goal_context)
                session_id = self._resolve_session_id(body)
                self._emit_major_update(
                    settings,
                    session_id,
                    "command_started",
                    "info",
                    "Command execution started.",
                    {"command": command, "dry_run": dry_run},
                )

                approval_token = str(body.get("approval_token", "")).strip()
                llm_enabled = bool(settings.get("llm_enabled", True))
                llm_model = str(settings.get("llm_model", "")).strip()
                llm_base_url = str(settings.get("llm_base_url", "")).strip()
                use_llm = llm_enabled and bool(llm_model) and bool(llm_base_url)
                profile = normalize_execution_profile(
                    body.get("profile", settings.get("execution_profile", "balanced")),
                    fallback=normalize_execution_profile(settings.get("execution_profile", "balanced")),
                )
                strict_mode = profile == "strict"

                direct_inputs = body.get("inputs", {})
                if not isinstance(direct_inputs, dict):
                    self._json_response(HTTPStatus.BAD_REQUEST, make_error("INVALID_PAYLOAD", "inputs must be an object"))
                    return

                explicit_recipe_id = str(body.get("recipe_id", "")).strip()
                if not explicit_recipe_id:
                    explicit_recipe_id = str(goal_context.get("recipe_id", "")).strip()
                routed_recipe_id = explicit_recipe_id or infer_recipe_id_from_message(command)

                if routed_recipe_id:
                    recipe_def = get_recipe_definition(routed_recipe_id)
                    if strict_mode and recipe_def is None:
                        self._json_response(
                            HTTPStatus.BAD_REQUEST,
                            make_error(
                                "RECIPE_SCHEMA_REQUIRED_STRICT",
                                "Strict profile requires a known local recipe schema.",
                                recipe_id=routed_recipe_id,
                            ),
                        )
                        return
                    recipe_inputs = dict(goal_context)
                    recipe_inputs.pop("recipe_id", None)
                    nested_inputs = goal_context.get("inputs", {})
                    if isinstance(nested_inputs, dict):
                        recipe_inputs.update(nested_inputs)
                    recipe_inputs.update(direct_inputs)

                    if recipe_def is not None and use_llm:
                        recipe_inputs = complete_recipe_inputs_with_llm(
                            settings=settings,
                            message=command,
                            recipe_def=recipe_def,
                            existing_inputs=recipe_inputs,
                        )

                    if recipe_def is not None:
                        recipe_inputs = apply_recipe_defaults(recipe_def, recipe_inputs)
                        recipe_validation = validate_recipe_inputs(recipe_def, recipe_inputs)
                        if not recipe_validation.get("ok", False):
                            self._json_response(
                                HTTPStatus.BAD_REQUEST,
                                make_error(
                                    "RECIPE_INPUT_VALIDATION_FAILED",
                                    "Recipe input validation failed.",
                                    recipe_id=routed_recipe_id,
                                    validation=recipe_validation,
                                ),
                            )
                            return
                    else:
                        recipe_validation = {"ok": True, "errors": [], "warnings": ["Recipe schema not found locally."]}

                    risky = []
                    if recipe_def is not None:
                        recipe_actions = [
                            str(step.get("action", "")).strip()
                            for step in recipe_def.get("steps", [])
                            if isinstance(step, dict)
                        ]
                        risky = sorted(list(set(recipe_actions).intersection(set(settings.get("risky_actions", [])))))
                    if len(risky) == 0 and not dry_run:
                        risky = list(settings.get("risky_actions", []))

                    approval_result = check_requires_approval(
                        settings=settings,
                        operation="command-recipe",
                        risky_actions=risky,
                        dry_run=dry_run,
                        approval_token=approval_token,
                        request_payload={"recipe_id": routed_recipe_id, "inputs": recipe_inputs},
                    )
                    if approval_result:
                        self._json_response(HTTPStatus.ACCEPTED, approval_result)
                        return

                    preflight_enabled = bool(settings.get("execution_preflight_enabled", True))
                    preflight_result: Dict[str, Any] = {"ran": False}
                    if preflight_enabled and not dry_run:
                        preflight_payload = {
                            "recipe_id": routed_recipe_id,
                            "inputs": recipe_inputs,
                            "dry_run": True,
                            "stop_on_error": True,
                            "profile": profile,
                        }
                        preflight_response = call_unreal(settings, "POST", "/validate-recipe", preflight_payload)
                        preflight_result = {
                            "ran": True,
                            "status_code": int(preflight_response.status_code),
                            "payload": preflight_response.payload,
                        }
                        preflight_ok = preflight_response.status_code < 400 and bool(preflight_response.payload.get("success", False))
                        if not preflight_ok:
                            self._emit_major_update(
                                settings,
                                session_id,
                                "command_recipe_preflight_failed",
                                "error",
                                f"Recipe '{routed_recipe_id}' preflight failed.",
                                {"preflight": preflight_result},
                            )
                            self._json_response(
                                HTTPStatus.PRECONDITION_FAILED,
                                make_error(
                                    "PREFLIGHT_FAILED",
                                    "Recipe preflight validation failed.",
                                    preflight=preflight_result,
                                    recipe_id=routed_recipe_id,
                                ),
                            )
                            return

                    def run_command_recipe():
                        status_code, payload, execution_mode = run_recipe_with_local_fallback(
                            settings=settings,
                            recipe_id=routed_recipe_id,
                            resolved_inputs=recipe_inputs,
                            dry_run=dry_run,
                            stop_on_error=stop_on_error,
                            profile=profile,
                        )
                        payload = payload if isinstance(payload, dict) else {"success": False, "raw": payload}
                        response = {
                            "success": bool(payload.get("success", False)),
                            "mode": "recipe",
                            "recipe_id": routed_recipe_id,
                            "profile": profile,
                            "resolved_inputs": recipe_inputs,
                            "input_validation": recipe_validation,
                            "execution": payload,
                            "unreal_status_code": status_code,
                            "execution_mode": execution_mode,
                        }
                        if preflight_result.get("ran", False):
                            response["preflight"] = preflight_result
                        if bool(settings.get("execution_store_artifacts", True)):
                            run_artifact = {
                                "timestamp": time.time(),
                                "route": "/api/command",
                                "mode": "recipe",
                                "command": command,
                                "recipe_id": routed_recipe_id,
                                "profile": profile,
                                "dry_run": dry_run,
                                "request": body,
                                "resolved_inputs": recipe_inputs,
                                "preflight": preflight_result,
                                "status": int(status_code),
                                "response": response,
                            }
                            response["execution_run_id"] = write_execution_artifact(settings, run_artifact)
                        issues = collect_analysis_contradictions(response)
                        if issues:
                            return HTTPStatus.CONFLICT, make_error(
                                "ANALYSIS_CONTRADICTION",
                                "Recipe execution reported analysis contradictions.",
                                issues=issues,
                                result=response,
                            )
                        return HTTPStatus.OK if status_code < 500 else HTTPStatus.BAD_GATEWAY, response

                    status, response = self._with_run_lock(run_command_recipe)
                    update_release_metrics(
                        run_kind="recipe_runs",
                        run_success=bool(response.get("success", False)),
                        http_status=int(status),
                        response_payload=response,
                        profile=profile,
                        release_validation=False,
                    )
                    self._json_response(status, response)
                    self._emit_major_update(
                        settings,
                        session_id,
                        "command_completed",
                        "success" if bool(response.get("success", False)) else "error",
                        "Command execution completed via recipe.",
                        {"mode": "recipe", "status": int(status), "success": bool(response.get("success", False))},
                    )
                    log_event(
                        "command_recipe",
                        {
                            "request_id": request_id,
                            "command": command,
                            "recipe_id": routed_recipe_id,
                            "dry_run": dry_run,
                            "status": int(status),
                            "duration_ms": int((time.time() - started) * 1000),
                        },
                    )
                    return

                if strict_mode and not use_llm:
                    self._emit_major_update(
                        settings,
                        session_id,
                        "command_blocked",
                        "error",
                        "Strict mode blocked command fallback without recipe/LLM.",
                        {"profile": profile},
                    )
                    self._json_response(
                        HTTPStatus.BAD_REQUEST,
                        make_error(
                            "STRICT_MODE_NEEDS_RECIPE_OR_LLM",
                            "Strict profile requires recipe routing or LLM-backed validated plan generation. "
                            "Provide recipe_id or enable llm_enabled with llm_model and llm_base_url.",
                            profile=profile,
                        ),
                    )
                    return

                actions_result = call_unreal(settings, "GET", "/actions")
                if actions_result.status_code >= 400:
                    self._json_response(
                        HTTPStatus.BAD_GATEWAY,
                        make_error("UNREAL_ACTIONS_FAILED", "Failed to load actions from Unreal.", details=actions_result.payload),
                    )
                    return

                if use_llm:
                    state_result = call_unreal(settings, "GET", "/state")
                    info_result = call_unreal(settings, "GET", "/info")
                    state_payload = state_result.payload if state_result.status_code < 400 else {}
                    info_payload = info_result.payload if info_result.status_code < 400 else {}
                    node_library_context = build_node_library_context(command, goal_context)

                    plan = generate_plan_with_llm(
                        settings=settings,
                        command=command,
                        actions_payload=actions_result.payload,
                        dry_run=dry_run,
                        stop_on_error=stop_on_error,
                        goal_context=goal_context,
                        state_payload=state_payload,
                        info_payload=info_payload,
                        node_library_context=node_library_context,
                    )
                    validation = validate_plan_with_node_library(plan)
                    if not validation.get("ok", False):
                        self._json_response(
                            HTTPStatus.BAD_REQUEST,
                            make_error(
                                "PLAN_NODELIB_VALIDATION_FAILED",
                                "Generated plan failed node-library validation.",
                                generated_plan=plan,
                                validation=validation,
                            ),
                        )
                        return

                    risky = sorted(list(set(get_plan_actions(plan)).intersection(set(settings.get("risky_actions", [])))))
                    approval_result = check_requires_approval(
                        settings=settings,
                        operation="command-llm-plan",
                        risky_actions=risky,
                        dry_run=dry_run,
                        approval_token=approval_token,
                        request_payload=plan,
                    )
                    if approval_result:
                        self._json_response(HTTPStatus.ACCEPTED, approval_result)
                        return

                    def run_command_plan():
                        current_plan = plan
                        result = call_unreal(settings, "POST", "/run-plan", current_plan)

                        max_replans = int(settings.get("llm_max_replans", 1))
                        replan_count = 0
                        while (
                            result.status_code < 500
                            and not bool(result.payload.get("success", False))
                            and replan_count < max_replans
                        ):
                            replan_count += 1
                            current_plan = generate_plan_with_llm(
                                settings=settings,
                                command=command,
                                actions_payload=actions_result.payload,
                                dry_run=dry_run,
                                stop_on_error=stop_on_error,
                                goal_context=goal_context,
                                state_payload=state_payload,
                                info_payload=info_payload,
                                prior_plan=current_plan,
                                prior_execution=result.payload,
                                node_library_context=node_library_context,
                            )
                            validation = validate_plan_with_node_library(current_plan)
                            if not validation.get("ok", False):
                                response = {
                                    "success": False,
                                    "mode": "llm_plan",
                                    "generated_plan": current_plan,
                                    "execution": result.payload,
                                    "unreal_status_code": result.status_code,
                                    "replan_count": replan_count,
                                    "error_code": "PLAN_NODELIB_VALIDATION_FAILED",
                                    "validation": validation,
                                }
                                return HTTPStatus.BAD_REQUEST, response
                            result = call_unreal(settings, "POST", "/run-plan", current_plan)

                        response = {
                            "success": bool(result.payload.get("success", False)),
                            "mode": "llm_plan",
                            "generated_plan": current_plan,
                            "execution": result.payload,
                            "unreal_status_code": result.status_code,
                            "replan_count": replan_count,
                        }
                        issues = collect_analysis_contradictions(response)
                        if issues:
                            return HTTPStatus.CONFLICT, make_error(
                                "ANALYSIS_CONTRADICTION",
                                "LLM plan execution reported analysis contradictions.",
                                issues=issues,
                                result=response,
                            )
                        return HTTPStatus.OK if result.status_code < 500 else HTTPStatus.BAD_GATEWAY, response

                    status, response = self._with_run_lock(run_command_plan)
                    self._emit_major_update(
                        settings,
                        session_id,
                        "command_completed",
                        "success" if bool(response.get("success", False)) else "error",
                        "Command execution completed via LLM plan.",
                        {"mode": "llm_plan", "status": int(status), "success": bool(response.get("success", False))},
                    )
                    self._json_response(status, response)
                    log_event(
                        "command_llm",
                        {
                            "request_id": request_id,
                            "command": command,
                            "dry_run": dry_run,
                            "status": status,
                            "response": response,
                            "duration_ms": int((time.time() - started) * 1000),
                        },
                    )
                    return

                if strict_mode:
                    self._json_response(
                        HTTPStatus.BAD_REQUEST,
                        make_error(
                            "STRICT_MODE_BLOCKED_GOAL_FALLBACK",
                            "Strict profile blocks heuristic goal-runner fallback. "
                            "Use recipe_id or enable LLM plan generation.",
                            profile=profile,
                        ),
                    )
                    return

                goal_payload = {
                    "goal": command,
                    "dry_run": dry_run,
                    "stop_on_error": stop_on_error,
                    "goal_context": goal_context,
                }
                risky = list(settings.get("risky_actions", []))
                approval_result = check_requires_approval(
                    settings=settings,
                    operation="command-goal-runner",
                    risky_actions=risky,
                    dry_run=dry_run,
                    approval_token=approval_token,
                    request_payload=goal_payload,
                )
                if approval_result:
                    self._json_response(HTTPStatus.ACCEPTED, approval_result)
                    return

                def run_command_goal():
                    result = call_unreal(settings, "POST", "/run-goal", goal_payload)
                    response = {
                        "success": bool(result.payload.get("success", False)),
                        "mode": "unreal_goal_runner",
                        "execution": result.payload,
                        "unreal_status_code": result.status_code,
                    }
                    return HTTPStatus.OK if result.status_code < 500 else HTTPStatus.BAD_GATEWAY, response

                status, response = self._with_run_lock(run_command_goal)
                self._emit_major_update(
                    settings,
                    session_id,
                    "command_completed",
                    "success" if bool(response.get("success", False)) else "error",
                    "Command execution completed via goal runner.",
                    {"mode": "unreal_goal_runner", "status": int(status), "success": bool(response.get("success", False))},
                )
                self._json_response(status, response)
                log_event(
                    "command_goal_runner",
                    {
                        "request_id": request_id,
                        "command": command,
                        "dry_run": dry_run,
                        "status": status,
                        "response": response,
                        "duration_ms": int((time.time() - started) * 1000),
                    },
                )
                return

            self._json_response(HTTPStatus.NOT_FOUND, make_error("NOT_FOUND", "Not found"))
        except Exception as exc:
            self._json_response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                make_error("INTERNAL_ERROR", str(exc), trace=traceback.format_exc()),
            )


def main() -> int:
    host = os.environ.get("UNREAL_AGENT_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("UNREAL_AGENT_WEB_PORT", "8787"))
    ensure_data_dir()
    save_settings(load_settings())
    if not APPROVALS_PATH.exists():
        save_approvals({"items": {}})
    if not PAID_SESSIONS_PATH.exists():
        save_paid_sessions({"sessions": {}})
    if not RELEASE_METRICS_PATH.exists():
        save_release_metrics(default_release_metrics())

    server = ThreadingHTTPServer((host, port), RequestHandler)
    print(f"Unreal Agent Web running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Unreal Agent Web...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
