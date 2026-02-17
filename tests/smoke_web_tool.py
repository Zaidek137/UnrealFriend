#!/usr/bin/env python3
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
WEB_SERVER = ROOT / "apps" / "unreal-agent-web" / "server.py"
SETTINGS_FILE = ROOT / "apps" / "unreal-agent-web" / ".data" / "settings.json"
APPROVALS_FILE = ROOT / "apps" / "unreal-agent-web" / ".data" / "approvals.json"
PAID_SESSIONS_FILE = ROOT / "apps" / "unreal-agent-web" / ".data" / "paid_sessions.json"
AUDIT_LOG = ROOT / "apps" / "unreal-agent-web" / ".data" / "audit.log.jsonl"
REQUEST_DEFAULT_HEADERS: Dict[str, str] = {}


class StubUnrealHandler(BaseHTTPRequestHandler):
    delay_run_goal_sec = 0.0

    def _send(self, code: int, payload: Dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/unreal-agent/v1/health":
            self._send(HTTPStatus.OK, {"success": True, "message": "ok"})
            return
        if self.path == "/unreal-agent/v1/info":
            self._send(
                HTTPStatus.OK,
                {
                    "success": True,
                    "plugin_name": "UnrealAgent",
                    "plugin_version": "0.1.0",
                    "api_version": "v1",
                    "engine_version": "5.4.0",
                    "engine_branch": "++UE5+Release-5.4",
                },
            )
            return
        if self.path == "/unreal-agent/v1/actions":
            self._send(
                HTTPStatus.OK,
                {
                    "success": True,
                    "actions": [
                        {"name": "create_blueprint", "description": "Creates BP."},
                        {"name": "spawn_actor", "description": "Spawns actor."},
                        {"name": "modify_blueprint_graph", "description": "Edits BP graph."},
                        {"name": "compile_blueprint", "description": "Compiles BP."},
                        {"name": "wire_blueprint_pins", "description": "Connects/disconnects blueprint graph pins."},
                        {"name": "blueprint_node_authoring", "description": "Creates/replaces blueprint nodes."},
                        {"name": "blueprint_compile_diagnostics", "description": "Compiles and analyzes blueprint graph."},
                        {"name": "edit_actor_transform", "description": "Edits actor transform deterministically."},
                        {"name": "inspect_asset", "description": "Checks if asset exists."},
                        {"name": "inspect_blueprint_graph", "description": "Returns graph node inventory."},
                        {"name": "analyze_blueprint_graph", "description": "Returns deterministic graph analysis."},
                        {"name": "analyze_blueprint_asset", "description": "Returns deterministic asset analysis."},
                    ],
                },
            )
            return
        if self.path == "/unreal-agent/v1/recipes":
            self._send(
                HTTPStatus.OK,
                {
                    "success": True,
                    "recipes": [
                        {
                            "recipe_id": "objective_loop_basic_sp",
                            "version": "1.0.0",
                            "description": "basic objective loop",
                        }
                    ],
                },
            )
            return
        if self.path == "/unreal-agent/v1/state":
            self._send(
                HTTPStatus.OK,
                {
                    "success": True,
                    "is_pie": False,
                    "editor_world": "/Engine/Transient.World_0",
                    "current_level": "/Game/Maps/TestMap",
                    "selected_actors": [],
                },
            )
            return
        if self.path.startswith("/unreal-agent/v1/debug/traces"):
            self._send(
                HTTPStatus.OK,
                {
                    "success": True,
                    "count": 1,
                    "limit": 50,
                    "trace_file": "/tmp/debug_trace.jsonl",
                    "traces": [
                        {
                            "trace_id": "t1",
                            "route": "/unreal-agent/v1/execute",
                            "success": True,
                            "message": "ok",
                        }
                    ],
                },
            )
            return
        self._send(HTTPStatus.NOT_FOUND, {"success": False, "message": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {}

        if self.path == "/unreal-agent/v1/execute":
            action = str(payload.get("action", "")).strip()
            action_payload = payload.get("payload", {}) if isinstance(payload.get("payload", {}), dict) else {}
            if action == "list_assets":
                package_path = str(action_payload.get("package_path", "/Game"))
                self._send(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "message": "assets listed",
                        "payload": {
                            "package_path": package_path,
                            "matched": 2,
                            "returned": 2,
                            "truncated": False,
                            "assets": [
                                {
                                    "asset_name": "BP_Example",
                                    "package_name": "/Game/Test/BP_Example",
                                    "object_path": "/Game/Test/BP_Example.BP_Example",
                                    "class_path": "/Script/Engine.Blueprint",
                                },
                                {
                                    "asset_name": "WBP_Menu",
                                    "package_name": "/Game/UI/WBP_Menu",
                                    "object_path": "/Game/UI/WBP_Menu.WBP_Menu",
                                    "class_path": "/Script/UMG.WidgetBlueprint",
                                },
                            ],
                        },
                    },
                )
                return
            if action == "analyze_blueprint_asset":
                blueprint_path = str(action_payload.get("blueprint_path", ""))
                self._send(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "message": "asset analysis ok",
                        "payload": {
                            "blueprint": blueprint_path,
                            "graphs": [
                                {
                                    "graph_name": "EventGraph",
                                    "total_nodes": 10,
                                    "contradictions": [],
                                    "dead_exec_outputs": [{"node_name": "K2Node_CallFunction_PrintString", "pin_name": "then"}],
                                },
                                {"graph_name": "FunctionGraph", "total_nodes": 5, "contradictions": []},
                            ],
                        },
                    },
                )
                return
            if action == "analyze_blueprint_graph":
                blueprint_path = str(action_payload.get("blueprint_path", ""))
                contradiction_mode = blueprint_path.endswith("BP_Bad")
                graph_payload = {
                    "blueprint": blueprint_path,
                    "graph_name": "EventGraph",
                    "total_nodes": 3,
                    "returned_nodes": 3,
                    "truncated": False,
                    "nodes": [
                        {
                            "name": "K2Node_Event_BeginPlay",
                            "title": "Event BeginPlay",
                            "class": "/Script/BlueprintGraph.K2Node_Event",
                            "pins": [
                                {"name": "then", "direction": "output", "category": "exec", "links": 1},
                            ],
                        },
                        {
                            "name": "K2Node_CallFunction_PrintString",
                            "title": "Print String",
                            "class": "/Script/BlueprintGraph.K2Node_CallFunction",
                            "pins": [
                                {"name": "execute", "direction": "input", "category": "exec", "links": 1},
                                {"name": "then", "direction": "output", "category": "exec", "links": 0},
                                {"name": "In String", "direction": "input", "category": "string", "links": 0, "default_value": "Hi"},
                            ],
                        },
                        {
                            "name": "K2Node_IfThenElse_0",
                            "title": "Branch",
                            "class": "/Script/BlueprintGraph.K2Node_IfThenElse",
                            "pins": [
                                {"name": "Condition", "direction": "input", "category": "bool", "links": 1},
                                {"name": "Then", "direction": "output", "category": "exec", "links": 1},
                                {"name": "Else", "direction": "output", "category": "exec", "links": 1},
                            ],
                        },
                    ],
                    "entry_nodes": [{"node_name": "K2Node_Event_BeginPlay", "node_title": "Event BeginPlay"}],
                    "exec_edges": [
                        {"from_node": "K2Node_Event_BeginPlay", "from_pin": "then", "to_node": "K2Node_CallFunction_PrintString", "to_pin": "execute"},
                    ],
                    "path_traces": [],
                    "dead_exec_outputs": [] if not contradiction_mode else [{"node_name": "K2Node_Event_BeginPlay", "pin_name": "then"}],
                    "branch_guards": [{"node_name": "K2Node_IfThenElse_0", "then_links": 1, "else_links": 1}],
                    "function_calls": [{"node_name": "K2Node_CallFunction_PrintString", "node_title": "Print String", "target": "self"}],
                    "delays": [],
                    "print_strings": [{"node_name": "K2Node_CallFunction_PrintString", "message": "Hi", "duration": "2.0"}],
                    "enum_values": [],
                    "constants": [],
                    "contradictions": [] if not contradiction_mode else [{"type": "dead_exec_pin_has_outgoing_edge"}],
                    "analysis_ok": not contradiction_mode,
                }
                self._send(
                    HTTPStatus.OK,
                    {
                        "success": not contradiction_mode,
                        "error_code": "OK" if not contradiction_mode else "ANALYSIS_CONTRADICTION",
                        "message": "analysis ok" if not contradiction_mode else "analysis contradiction",
                        "payload": graph_payload,
                    },
                )
                return
            self._send(HTTPStatus.OK, {"success": True, "message": "execute ok", "payload": payload})
            return
        if self.path == "/unreal-agent/v1/run-plan":
            self._send(HTTPStatus.OK, {"success": True, "message": "plan ok", "payload": payload})
            return
        if self.path == "/unreal-agent/v1/run-goal":
            if StubUnrealHandler.delay_run_goal_sec > 0:
                time.sleep(StubUnrealHandler.delay_run_goal_sec)
            self._send(HTTPStatus.OK, {"success": True, "message": "goal ok", "payload": payload})
            return
        if self.path == "/unreal-agent/v1/run-recipe":
            recipe_id = str(payload.get("recipe_id", ""))
            self._send(
                HTTPStatus.OK,
                {
                    "success": recipe_id != "force_recipe_fail",
                    "message": "recipe ok" if recipe_id != "force_recipe_fail" else "recipe failed",
                    "recipe_id": recipe_id,
                    "execution": {"success": recipe_id != "force_recipe_fail"},
                },
            )
            return
        if self.path == "/unreal-agent/v1/validate-recipe":
            recipe_id = str(payload.get("recipe_id", ""))
            self._send(
                HTTPStatus.OK,
                {
                    "success": recipe_id != "force_compile_fail",
                    "message": "validation ok" if recipe_id != "force_compile_fail" else "compile failed",
                    "error_code": "OK" if recipe_id != "force_compile_fail" else "COMPILE_FAILED",
                    "validation_only": True,
                    "recipe_id": recipe_id,
                },
            )
            return
        if self.path == "/unreal-agent/v1/run-scenario":
            assertions = payload.get("assertions", [])
            force_fail = False
            if isinstance(assertions, list):
                for item in assertions:
                    if isinstance(item, dict) and bool(item.get("force_fail", False)):
                        force_fail = True
                        break
            self._send(
                HTTPStatus.OK if not force_fail else HTTPStatus.BAD_REQUEST,
                {
                    "success": not force_fail,
                    "message": "scenario pass" if not force_fail else "scenario fail",
                    "error_code": "OK" if not force_fail else "SCENARIO_FAILED",
                },
            )
            return
        if self.path == "/unreal-agent/v1/debug/clear":
            self._send(HTTPStatus.OK, {"success": True, "message": "cleared"})
            return

        self._send(HTTPStatus.NOT_FOUND, {"success": False, "message": "not found"})


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def request_json(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, Dict[str, Any]]:
    data = None
    request_headers = {"Content-Type": "application/json"}
    if REQUEST_DEFAULT_HEADERS:
        request_headers.update(REQUEST_DEFAULT_HEADERS)
    if isinstance(headers, dict):
        request_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url=url, method=method, data=data, headers=request_headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        parsed: Dict[str, Any]
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"success": False, "raw": body}
        return exc.code, parsed


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def wait_for(url: str, timeout_sec: float = 20.0) -> None:
    started = time.time()
    last_error = ""
    while time.time() - started < timeout_sec:
        try:
            status, _ = request_json("GET", url)
            if status < 500:
                return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {url}. Last error: {last_error}")


def run() -> None:
    stub_port = free_port()
    web_port = free_port()
    managed_files = [SETTINGS_FILE, APPROVALS_FILE, PAID_SESSIONS_FILE, AUDIT_LOG]
    backups: Dict[Path, Optional[bytes]] = {}
    for file_path in managed_files:
        backups[file_path] = file_path.read_bytes() if file_path.exists() else None

    stub_server = ThreadingHTTPServer(("127.0.0.1", stub_port), StubUnrealHandler)
    stub_thread = threading.Thread(target=stub_server.serve_forever, daemon=True)
    stub_thread.start()

    env = dict(os.environ)
    env["UNREAL_AGENT_WEB_HOST"] = "127.0.0.1"
    env["UNREAL_AGENT_WEB_PORT"] = str(web_port)
    web_proc = subprocess.Popen([sys.executable, str(WEB_SERVER)], cwd=str(ROOT), env=env)

    try:
        base = f"http://127.0.0.1:{web_port}"
        wait_for(f"{base}/api/health")

        status, settings = request_json(
            "POST",
            f"{base}/api/settings",
            {
                "unreal_base_url": f"http://127.0.0.1:{stub_port}/unreal-agent/v1",
                "llm_enabled": False,
                "require_approval_for_mutations": True,
                "min_api_version": "v1",
                "min_plugin_version": "0.1.0",
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/settings to succeed")
        assert_true(settings.get("success", False), "Expected settings update success")

        status, paid_settings = request_json(
            "POST",
            f"{base}/api/settings",
            {
                "paid_live_logs_enabled": True,
                "paid_live_logs_tokens": ["test-paid-token"],
                "paid_admin_tokens": ["test-admin-token"],
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected paid settings update success")
        assert_true(paid_settings.get("success", False), "Expected paid settings success")

        status, prebootstrap_block = request_json(
            "POST",
            f"{base}/api/run-goal",
            {"goal": "pre-bootstrap smoke check", "dry_run": True},
        )
        assert_true(status == HTTPStatus.PRECONDITION_REQUIRED, "Expected bootstrap precondition on /api/run-goal")
        assert_true(
            str(prebootstrap_block.get("error_code", "")) == "AGENT_BOOTSTRAP_REQUIRED",
            "Expected AGENT_BOOTSTRAP_REQUIRED before bootstrap",
        )

        status, bootstrap = request_json(
            "POST",
            f"{base}/api/agent-bootstrap",
            {
                "client_name": "smoke_test",
                "client_version": "0.1.0",
                "session_label": "smoke_suite",
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/agent-bootstrap success")
        assert_true(bootstrap.get("success", False), "Expected agent bootstrap success")
        bootstrap_token = str(bootstrap.get("bootstrap_token", "")).strip()
        assert_true(bool(bootstrap_token), "Expected bootstrap token")
        REQUEST_DEFAULT_HEADERS["X-Agent-Bootstrap-Token"] = bootstrap_token

        status, paid_start = request_json(
            "POST",
            f"{base}/api/paid/session/start",
            {
                "paid_token": "test-paid-token",
                "user_id": "smoke",
                "project_label": "SmokeProject",
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected paid session start success")
        assert_true(paid_start.get("success", False), "Expected paid session start payload success")
        paid_session_id = str(paid_start.get("session_id", ""))
        assert_true(bool(paid_session_id), "Expected paid session id")

        status, paid_goal = request_json(
            "POST",
            f"{base}/api/run-goal",
            {
                "goal": "Smoke paid-session run-goal",
                "dry_run": True,
                "session_id": paid_session_id,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected run-goal success with paid session id")
        assert_true(paid_goal.get("success", False), "Expected paid run-goal success")

        status, paid_logs = request_json(
            "GET",
            f"{base}/api/paid/session/logs?session_id={paid_session_id}&limit=50",
            headers={"X-Paid-Token": "test-paid-token"},
        )
        assert_true(status == HTTPStatus.OK, "Expected paid session logs success")
        assert_true(paid_logs.get("success", False), "Expected paid session logs payload success")
        assert_true(len(paid_logs.get("events", [])) >= 2, "Expected paid session major update events")

        status, paid_end = request_json(
            "POST",
            f"{base}/api/paid/session/end",
            {"paid_token": "test-paid-token", "session_id": paid_session_id},
        )
        assert_true(status == HTTPStatus.OK, "Expected paid session end success")
        assert_true(paid_end.get("success", False), "Expected paid session end payload success")

        status, _ = request_json(
            "POST",
            f"{base}/api/settings",
            {
                "plan_tier_gate_enabled": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected tier-gate settings update success")

        status, tier_blocked = request_json(
            "POST",
            f"{base}/api/project-audit",
            {
                "package_path": "/Game",
                "recursive": True,
                "max_assets": 10,
                "analyze_blueprints": False,
            },
        )
        assert_true(status == HTTPStatus.PAYMENT_REQUIRED, "Expected paid-tier route to require token")
        assert_true(tier_blocked.get("error_code") == "PLAN_TIER_REQUIRED", "Expected PLAN_TIER_REQUIRED")

        status, _ = request_json(
            "POST",
            f"{base}/api/settings",
            {
                "plan_tier_gate_enabled": False,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected tier-gate reset settings update success")

        status, _ = request_json("GET", f"{base}/api/info")
        assert_true(status == HTTPStatus.OK, "Expected /api/info to proxy correctly")

        status, _ = request_json("GET", f"{base}/api/state")
        assert_true(status == HTTPStatus.OK, "Expected /api/state to proxy correctly")

        status, recipes = request_json("GET", f"{base}/api/recipes")
        assert_true(status == HTTPStatus.OK, "Expected /api/recipes to succeed")
        assert_true(recipes.get("success", False), "Expected /api/recipes success")
        assert_true(int(recipes.get("local_recipe_count", 0)) >= 1, "Expected local recipe catalog")
        recipe_ids = {str(item.get("recipe_id", "")) for item in recipes.get("recipes", []) if isinstance(item, dict)}
        assert_true("sky_objective_jump_loop_sp" in recipe_ids, "Expected sky objective jump recipe to be listed")

        status, approval_required = request_json(
            "POST",
            f"{base}/api/direct-execute",
            {
                "action": "create_blueprint",
                "payload": {"asset_name": "BP_Test", "package_path": "/Game/Test"},
                "dry_run": False,
            },
        )
        assert_true(status == HTTPStatus.ACCEPTED, "Expected approval-required response")
        assert_true(approval_required.get("error_code") == "APPROVAL_REQUIRED", "Expected APPROVAL_REQUIRED")
        token = str(approval_required.get("approval_token", ""))
        assert_true(bool(token), "Expected approval token")

        status, approved = request_json("POST", f"{base}/api/approve", {"approval_token": token})
        assert_true(status == HTTPStatus.OK, "Expected approval endpoint to succeed")
        assert_true(approved.get("success", False), "Expected approval success")

        status, direct_run = request_json(
            "POST",
            f"{base}/api/direct-execute",
            {
                "action": "create_blueprint",
                "payload": {"asset_name": "BP_Test", "package_path": "/Game/Test"},
                "dry_run": False,
                "approval_token": token,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected direct execute to run after approval")
        assert_true(direct_run.get("success", False), "Expected direct execute success")

        status, _ = request_json("POST", f"{base}/api/settings", {"min_api_version": "v9"})
        assert_true(status == HTTPStatus.OK, "Expected settings update for compatibility test")
        status, incompatible = request_json(
            "POST",
            f"{base}/api/run-plan",
            {
                "plan": {
                    "plan_id": "compat-test",
                    "dry_run": True,
                    "steps": [
                        {"id": "s1", "action": "inspect_asset", "payload": {"asset_path": "/Game/Test/BP_Test"}}
                    ],
                }
            },
        )
        assert_true(status == HTTPStatus.PRECONDITION_FAILED, "Expected compatibility precondition failure")
        assert_true(incompatible.get("error_code") == "VERSION_INCOMPATIBLE", "Expected VERSION_INCOMPATIBLE")

        status, _ = request_json(
            "POST",
            f"{base}/api/settings",
            {"min_api_version": "v1", "require_approval_for_mutations": False},
        )
        assert_true(status == HTTPStatus.OK, "Expected lock test settings update")

        status, run_recipe = request_json(
            "POST",
            f"{base}/api/run-recipe",
            {
                "recipe_id": "objective_loop_basic_sp",
                "inputs": {"objective_count": 2},
                "dry_run": True,
                "profile": "balanced",
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/run-recipe success")
        assert_true(run_recipe.get("success", False), "Expected recipe run success")

        status, chat_recipe = request_json(
            "POST",
            f"{base}/api/chat",
            {
                "message": "Create a timed objective collection loop for parkour.",
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/chat recipe-first success")
        assert_true(str(chat_recipe.get("mode", "")) == "recipe", "Expected chat recipe-first routing")

        status, strict_unknown_recipe = request_json(
            "POST",
            f"{base}/api/command",
            {
                "command": "Build me a custom loop",
                "dry_run": True,
                "profile": "strict",
                "recipe_id": "unknown_recipe",
            },
        )
        assert_true(status == HTTPStatus.BAD_REQUEST, "Expected strict unknown recipe to fail")
        assert_true(
            strict_unknown_recipe.get("error_code") == "RECIPE_SCHEMA_REQUIRED_STRICT",
            "Expected RECIPE_SCHEMA_REQUIRED_STRICT",
        )

        status, strict_no_fallback = request_json(
            "POST",
            f"{base}/api/command",
            {
                "command": "Create BP_StrictMode and print on begin play",
                "dry_run": True,
                "profile": "strict",
            },
        )
        assert_true(status == HTTPStatus.BAD_REQUEST, "Expected strict mode to block run-goal fallback")
        assert_true(
            strict_no_fallback.get("error_code") == "STRICT_MODE_NEEDS_RECIPE_OR_LLM",
            "Expected STRICT_MODE_NEEDS_RECIPE_OR_LLM",
        )

        status, strict_recipe = request_json(
            "POST",
            f"{base}/api/command",
            {
                "command": "Create a timed objective collection loop for parkour.",
                "dry_run": True,
                "profile": "strict",
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected strict profile to allow recipe path")
        assert_true(strict_recipe.get("success", False), "Expected strict recipe command success")
        assert_true(str(strict_recipe.get("mode", "")) == "recipe", "Expected strict recipe routing")

        status, strict_sky_recipe = request_json(
            "POST",
            f"{base}/api/command",
            {
                "command": "Create a sky platform environment with jump platforms and 5 objectives to capture.",
                "dry_run": True,
                "profile": "strict",
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected strict profile sky recipe routing")
        assert_true(strict_sky_recipe.get("success", False), "Expected strict sky recipe success")
        assert_true(
            str(strict_sky_recipe.get("recipe_id", "")) == "sky_objective_jump_loop_sp",
            "Expected sky objective jump recipe id",
        )

        status, validate_recipe = request_json(
            "POST",
            f"{base}/api/validate-recipe",
            {
                "recipe_id": "objective_loop_basic_sp",
                "inputs": {"objective_count": 2},
                "profile": "balanced",
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/validate-recipe success")
        assert_true(validate_recipe.get("success", False), "Expected recipe validation success")

        status, scenario_non_blocking = request_json(
            "POST",
            f"{base}/api/run-scenario",
            {
                "assertions": [{"label_contains": "Objective", "force_fail": True}],
                "profile": "balanced",
                "release_validation": False,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected balanced scenario failure to be non-blocking")
        assert_true(scenario_non_blocking.get("success", False), "Expected non-blocking wrapper success")
        assert_true(not scenario_non_blocking.get("scenario_success", True), "Expected scenario_success false")

        status, scenario_blocking = request_json(
            "POST",
            f"{base}/api/run-scenario",
            {
                "assertions": [{"label_contains": "Objective", "force_fail": True}],
                "profile": "balanced",
                "release_validation": True,
            },
        )
        assert_true(status == HTTPStatus.BAD_REQUEST, "Expected release validation scenario failure to block")
        assert_true(not scenario_blocking.get("success", True), "Expected scenario blocking failure")

        status, validation_suite = request_json(
            "POST",
            f"{base}/api/validate-execution",
            {
                "compile_blueprints": ["/Game/Test/BP_Example"],
                "assertions": [{"label_contains": "Objective"}],
                "profile": "strict",
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/validate-execution success")
        assert_true(validation_suite.get("success", False), "Expected validation suite success")
        assert_true(bool(validation_suite.get("execution_run_id", "")), "Expected execution_run_id in validate-execution response")

        status, execution_runs = request_json("GET", f"{base}/api/execution-runs")
        assert_true(status == HTTPStatus.OK, "Expected /api/execution-runs success")
        assert_true(execution_runs.get("success", False), "Expected execution-runs success payload")
        assert_true(isinstance(execution_runs.get("runs", []), list), "Expected runs list from /api/execution-runs")

        status, project_audit = request_json(
            "POST",
            f"{base}/api/project-audit",
            {
                "package_path": "/Game",
                "recursive": True,
                "max_assets": 50,
                "analyze_blueprints": True,
                "compile_blueprints": True,
                "profile": "strict",
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/project-audit success")
        assert_true(project_audit.get("success", False), "Expected project audit success")
        assert_true(project_audit.get("assets", {}).get("returned", 0) >= 1, "Expected at least one audited asset")

        status, metrics = request_json("GET", f"{base}/api/release-metrics")
        assert_true(status == HTTPStatus.OK, "Expected /api/release-metrics success")
        assert_true(metrics.get("success", False), "Expected release metrics success")
        assert_true(metrics.get("scenario_pass_rate") is not None, "Expected scenario pass rate")

        StubUnrealHandler.delay_run_goal_sec = 1.0
        first_result: Dict[str, Any] = {}

        def run_goal() -> None:
            status_code, payload = request_json(
                "POST",
                f"{base}/api/run-goal",
                {"goal": "Long running goal", "dry_run": True},
            )
            first_result["status"] = status_code
            first_result["payload"] = payload

        thread = threading.Thread(target=run_goal, daemon=True)
        thread.start()
        time.sleep(0.15)

        status, busy = request_json(
            "POST",
            f"{base}/api/run-plan",
            {
                "plan": {
                    "plan_id": "lock-test",
                    "dry_run": True,
                    "steps": [
                        {"id": "s1", "action": "inspect_asset", "payload": {"asset_path": "/Game/Test/BP_Test"}}
                    ],
                }
            },
        )
        assert_true(status == HTTPStatus.CONFLICT, "Expected RUN_BUSY conflict")
        assert_true(busy.get("error_code") == "RUN_BUSY", "Expected RUN_BUSY error_code")

        thread.join(timeout=3.0)
        assert_true(first_result.get("status") == HTTPStatus.OK, "Expected first run-goal request to complete")

        assert_true(AUDIT_LOG.exists(), "Expected audit log file")
        assert_true(AUDIT_LOG.read_text(encoding="utf-8").strip() != "", "Expected audit log to contain events")

        status, traces = request_json("GET", f"{base}/api/debug/traces?limit=10")
        assert_true(status == HTTPStatus.OK, "Expected /api/debug/traces to proxy")
        assert_true(traces.get("success", False), "Expected debug traces success")
        assert_true(int(traces.get("count", 0)) >= 1, "Expected at least one trace from stub")

        status, cleared = request_json("POST", f"{base}/api/debug/clear", {})
        assert_true(status == HTTPStatus.OK, "Expected /api/debug/clear to proxy")
        assert_true(cleared.get("success", False), "Expected debug clear success")

        status, analyzed = request_json(
            "POST",
            f"{base}/api/analyze",
            {
                "blueprint_path": "/Game/Test/BP_Good",
                "mode": "graph",
                "prompt": "Analyze this blueprint",
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/analyze success for good graph")
        assert_true(analyzed.get("success", False), "Expected analysis success")
        report = analyzed.get("report", {})
        claims = report.get("claims", []) if isinstance(report, dict) else []
        assert_true(isinstance(claims, list) and len(claims) > 0, "Expected evidence-backed claims in report")
        run_id = str(analyzed.get("run_id", ""))
        assert_true(bool(run_id), "Expected analysis run_id artifact")

        status, refactor_suggest = request_json(
            "POST",
            f"{base}/api/refactor-suggest",
            {
                "blueprint_path": "/Game/Test/BP_Good",
                "mode": "asset",
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/refactor-suggest success")
        assert_true(refactor_suggest.get("success", False), "Expected refactor suggest success")
        assert_true(int(refactor_suggest.get("auto_applicable_count", 0)) >= 1, "Expected auto-applicable suggestions")

        status, refactor_apply = request_json(
            "POST",
            f"{base}/api/refactor-apply",
            {
                "blueprint_path": "/Game/Test/BP_Good",
                "mode": "asset",
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/refactor-apply success")
        assert_true(refactor_apply.get("success", False), "Expected refactor apply success")
        generated_plan = refactor_apply.get("generated_plan", {})
        assert_true(isinstance(generated_plan, dict) and len(generated_plan.get("steps", [])) >= 1, "Expected generated refactor plan steps")
        assert_true(isinstance(refactor_apply.get("determinism_score", {}), dict), "Expected refactor determinism score payload")
        assert_true(isinstance(refactor_apply.get("timeline", []), list), "Expected refactor timeline payload")
        assert_true(isinstance(refactor_apply.get("graph_diff", {}), dict), "Expected refactor graph diff payload")
        refactor_run_id = str(refactor_apply.get("execution_run_id", ""))
        assert_true(bool(refactor_run_id), "Expected refactor execution run id")

        status, refactor_run_detail = request_json("GET", f"{base}/api/execution-run-detail?run_id={refactor_run_id}")
        assert_true(status == HTTPStatus.OK, "Expected /api/execution-run-detail success")
        assert_true(refactor_run_detail.get("success", False), "Expected execution-run-detail success")
        assert_true(isinstance(refactor_run_detail.get("timeline", []), list), "Expected execution-run-detail timeline list")
        status, refactor_artifact = request_json(
            "GET",
            f"{base}/api/execution-artifact?run_id={refactor_run_id}&include_snapshot=1&include_full=0",
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/execution-artifact success")
        assert_true(refactor_artifact.get("success", False), "Expected execution-artifact success")
        assert_true(isinstance(refactor_artifact.get("summary", {}), dict), "Expected execution-artifact summary object")
        assert_true(isinstance(refactor_artifact.get("graph_diff", {}), dict), "Expected execution-artifact graph diff")
        assert_true(isinstance(refactor_artifact.get("pin_diff", {}), dict), "Expected execution-artifact pin diff")

        status, refactor_catalog = request_json(
            "POST",
            f"{base}/api/refactor-catalog",
            {"blueprint_path": "/Game/Test/BP_Good", "profile": "balanced"},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/refactor-catalog success")
        assert_true(refactor_catalog.get("success", False), "Expected refactor catalog success")
        assert_true(int(refactor_catalog.get("transform_count", 0)) >= 1, "Expected catalog transforms")

        status, refactor_preview = request_json(
            "POST",
            f"{base}/api/refactor-preview",
            {"blueprint_path": "/Game/Test/BP_Good", "dry_run": True},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/refactor-preview success")
        assert_true(refactor_preview.get("success", False), "Expected refactor preview success")

        status, explain_selection = request_json(
            "POST",
            f"{base}/api/explain-selection",
            {"blueprint_path": "/Game/Test/BP_Good", "graph_name": "EventGraph", "node_names": ["K2Node_CallFunction_PrintString"]},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/explain-selection success")
        assert_true(explain_selection.get("success", False), "Expected explain-selection success")
        assert_true(isinstance(explain_selection.get("evidence", []), list), "Expected explain-selection evidence list")

        status, explain_screenshot = request_json(
            "POST",
            f"{base}/api/explain-screenshot",
            {"image_path": "/tmp/K2Node_CallFunction_PrintString.png", "blueprint_path": "/Game/Test/BP_Good", "graph_name": "EventGraph"},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/explain-screenshot success")
        assert_true(explain_screenshot.get("success", False), "Expected explain-screenshot success")

        status, project_dependencies = request_json(
            "POST",
            f"{base}/api/project-dependencies",
            {"package_path": "/Game", "recursive": True, "depth": 2},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/project-dependencies success")
        assert_true(project_dependencies.get("success", False), "Expected project-dependencies success")
        assert_true(isinstance(project_dependencies.get("nodes", []), list), "Expected dependency graph nodes")

        status, perf_hotspots = request_json(
            "POST",
            f"{base}/api/perf-hotspots",
            {"package_path": "/Game", "analyze_blueprints": True},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/perf-hotspots success")
        assert_true(perf_hotspots.get("success", False), "Expected perf-hotspots success")
        assert_true(isinstance(perf_hotspots.get("hotspot_items", []), list), "Expected hotspot items list")

        status, impact_analysis = request_json(
            "POST",
            f"{base}/api/impact-analysis",
            {"asset_paths": ["/Game/Test/BP_Example"], "change_type": "modify_blueprint_graph"},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/impact-analysis success")
        assert_true(impact_analysis.get("success", False), "Expected impact-analysis success")
        assert_true(isinstance(impact_analysis.get("affected_assets", []), list), "Expected affected assets list")

        status, umg_generate = request_json(
            "POST",
            f"{base}/api/umg-generate",
            {"widget_blueprint": "/Game/UI/WBP_Menu", "template_id": "hud_basic", "style_preset": "minimal"},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/umg-generate success")
        assert_true(umg_generate.get("success", False), "Expected umg-generate success")

        status, world_generate = request_json(
            "POST",
            f"{base}/api/world-generate",
            {"layout_id": "city_grid", "bounds": [0, 0, 1000, 1000], "density": 1.0, "seed": 42},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/world-generate success")
        assert_true(world_generate.get("success", False), "Expected world-generate success")

        status, property_reflect = request_json(
            "POST",
            f"{base}/api/property-reflect",
            {"target_type": "blueprint_cdo", "blueprint_path": "/Game/Test/BP_Example", "property_name": "bHidden", "value": True, "dry_run": True},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/property-reflect success")
        assert_true(property_reflect.get("success", False), "Expected property-reflect success")

        status, function_author = request_json(
            "POST",
            f"{base}/api/blueprint-function-author",
            {"blueprint_path": "/Game/Test/BP_Example", "graph_kind": "function", "graph_name": "AgentFunc", "dry_run": True},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/blueprint-function-author success")
        assert_true(function_author.get("success", False), "Expected blueprint-function-author success")

        status, component_hierarchy = request_json(
            "POST",
            f"{base}/api/component-hierarchy",
            {"blueprint_path": "/Game/Test/BP_Example", "operation": "add_component", "component_name": "AgentMesh", "class_path": "/Script/Engine.StaticMeshComponent", "dry_run": True},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/component-hierarchy success")
        assert_true(component_hierarchy.get("success", False), "Expected component-hierarchy success")

        status, graph_ast_export = request_json(
            "POST",
            f"{base}/api/graph-ast-export",
            {"blueprint_path": "/Game/Test/BP_Example", "graph_name": "EventGraph", "include_pins": True, "max_nodes": 200},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/graph-ast-export success")
        assert_true(graph_ast_export.get("success", False), "Expected graph-ast-export success")

        status, graph_ast_apply = request_json(
            "POST",
            f"{base}/api/graph-ast-apply",
            {
                "blueprint_path": "/Game/Test/BP_Example",
                "graph_name": "EventGraph",
                "operations": [
                    {
                        "action": "wire_blueprint_pins",
                        "payload": {
                            "from_node_name": "K2Node_Event_BeginPlay",
                            "from_pin_name": "then",
                            "to_node_name": "K2Node_CallFunction_PrintString",
                            "to_pin_name": "execute",
                            "operation": "connect",
                        },
                    }
                ],
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/graph-ast-apply success")
        assert_true(graph_ast_apply.get("success", False), "Expected graph-ast-apply success")

        status, signature_edit = request_json(
            "POST",
            f"{base}/api/signature-edit",
            {
                "blueprint_path": "/Game/Test/BP_Example",
                "operation": "add_variable",
                "name": "bSmokeVar",
                "type": "bool",
                "default_value": "true",
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/signature-edit success")
        assert_true(signature_edit.get("success", False), "Expected signature-edit success")

        status, actor_transform_control = request_json(
            "POST",
            f"{base}/api/actor-transform-control",
            {"actor_label": "PlayerStart", "operation": "set_transform", "location": [0, 0, 300], "rotation": [0, 0, 0], "scale": [1, 1, 1], "dry_run": True},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/actor-transform-control success")
        assert_true(actor_transform_control.get("success", False), "Expected actor-transform-control success")

        status, system_bootstrap = request_json(
            "POST",
            f"{base}/api/system-bootstrap",
            {"system_type": "ai_controller", "asset_name": "BP_AISmoke", "package_path": "/Game/Test", "dry_run": True},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/system-bootstrap success")
        assert_true(system_bootstrap.get("success", False), "Expected system-bootstrap success")

        status, control_surface_catalog = request_json("GET", f"{base}/api/control-surface-catalog")
        assert_true(status == HTTPStatus.OK, "Expected /api/control-surface-catalog success")
        assert_true(control_surface_catalog.get("success", False), "Expected control-surface-catalog success")

        status, agent_readiness = request_json("GET", f"{base}/api/agent-readiness")
        assert_true(status == HTTPStatus.OK, "Expected /api/agent-readiness success")
        assert_true(agent_readiness.get("success", False), "Expected agent-readiness success")
        assert_true(agent_readiness.get("ready", False), "Expected ready=true for agent-readiness")
        assert_true(len(agent_readiness.get("missing_actions", [])) == 0, "Expected no missing required actions")

        status, graph_pin_wire = request_json(
            "POST",
            f"{base}/api/graph-pin-wire",
            {
                "blueprint_path": "/Game/Test/BP_Example",
                "graph_name": "EventGraph",
                "operation": "connect",
                "from_node_name": "K2Node_Event_BeginPlay",
                "from_pin_name": "then",
                "to_node_name": "K2Node_CallFunction_PrintString",
                "to_pin_name": "execute",
                "dry_run": False,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/graph-pin-wire success")
        assert_true(graph_pin_wire.get("success", False), "Expected graph-pin-wire success")
        rollback_token = str(graph_pin_wire.get("rollback_token", "")).strip()
        assert_true(bool(rollback_token), "Expected graph-pin-wire rollback_token")

        status, node_author = request_json(
            "POST",
            f"{base}/api/node-author",
            {
                "blueprint_path": "/Game/Test/BP_Example",
                "graph_name": "EventGraph",
                "operation": "spawn_function_call",
                "function_class_path": "/Script/Engine.KismetSystemLibrary",
                "function_name": "PrintString",
                "node_position": [0, 0],
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/node-author success")
        assert_true(node_author.get("success", False), "Expected node-author success")

        status, compile_diagnostics = request_json(
            "POST",
            f"{base}/api/compile-diagnostics",
            {"blueprint_path": "/Game/Test/BP_Example", "graph_name": "EventGraph", "include_pins": True, "max_nodes": 100, "dry_run": True},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/compile-diagnostics success")
        assert_true(compile_diagnostics.get("success", False), "Expected compile-diagnostics success")

        status, compile_gate = request_json(
            "POST",
            f"{base}/api/compile-gate-run",
            {"blueprint_paths": ["/Game/Test/BP_Example"], "include_pins": True, "max_nodes": 120, "dry_run": True},
        )
        assert_true(status in (HTTPStatus.OK, HTTPStatus.CONFLICT), "Expected /api/compile-gate-run status")
        assert_true("items" in compile_gate, "Expected compile-gate items")

        status, pattern_catalog = request_json("GET", f"{base}/api/node-pattern-catalog")
        assert_true(status == HTTPStatus.OK, "Expected /api/node-pattern-catalog success")
        assert_true(pattern_catalog.get("success", False), "Expected node-pattern-catalog success")

        status, workflow_catalog = request_json("GET", f"{base}/api/workflow-catalog")
        assert_true(status == HTTPStatus.OK, "Expected /api/workflow-catalog success")
        assert_true(workflow_catalog.get("success", False), "Expected workflow-catalog success")
        assert_true(int(workflow_catalog.get("count", 0)) >= 1, "Expected workflow templates in catalog")

        status, control_caps = request_json("GET", f"{base}/api/node-control-capabilities")
        assert_true(status == HTTPStatus.OK, "Expected /api/node-control-capabilities success")
        assert_true(control_caps.get("success", False), "Expected node-control-capabilities success")
        assert_true(isinstance(control_caps.get("modify_blueprint_graph_operations", []), list), "Expected graph operation list")
        assert_true(isinstance(control_caps.get("blueprint_node_authoring_operations", []), list), "Expected node authoring operation list")
        assert_true(isinstance(control_caps.get("graph_primitive_operations", []), list), "Expected graph primitive operation list")
        assert_true(isinstance(control_caps.get("workflow_templates", []), list), "Expected workflow template list")
        assert_true(isinstance(control_caps.get("animation_autonomy_templates", []), list), "Expected animation autonomy template list")
        assert_true(isinstance(control_caps.get("ai_autonomy_templates", []), list), "Expected ai autonomy template list")
        assert_true(isinstance(control_caps.get("content_pipeline_presets", []), list), "Expected content pipeline preset list")
        assert_true(isinstance(control_caps.get("multiplayer_correctness_profiles", []), list), "Expected multiplayer correctness profile list")
        assert_true(isinstance(control_caps.get("material_mesh_setup_presets", []), list), "Expected material/mesh setup preset list")
        assert_true(isinstance(control_caps.get("native_asset_authoring_types", []), list), "Expected native asset authoring type list")
        assert_true(control_caps.get("blueprint_review_scopes", []) == ["graph", "asset"], "Expected blueprint review scopes")

        status, graph_primitives_catalog = request_json("GET", f"{base}/api/graph-primitives-catalog")
        assert_true(status == HTTPStatus.OK, "Expected /api/graph-primitives-catalog success")
        assert_true(graph_primitives_catalog.get("success", False), "Expected graph-primitives-catalog success")
        assert_true(
            len(graph_primitives_catalog.get("supported_operations", [])) >= 1,
            "Expected graph primitive catalog entries",
        )

        status, animation_catalog = request_json("GET", f"{base}/api/animation-autonomy-catalog")
        assert_true(status == HTTPStatus.OK, "Expected /api/animation-autonomy-catalog success")
        assert_true(animation_catalog.get("success", False), "Expected animation-autonomy-catalog success")
        assert_true(int(animation_catalog.get("count", 0)) >= 1, "Expected animation autonomy catalog entries")

        status, ai_catalog = request_json("GET", f"{base}/api/ai-autonomy-catalog")
        assert_true(status == HTTPStatus.OK, "Expected /api/ai-autonomy-catalog success")
        assert_true(ai_catalog.get("success", False), "Expected ai-autonomy-catalog success")
        assert_true(int(ai_catalog.get("count", 0)) >= 1, "Expected ai autonomy catalog entries")

        status, content_catalog = request_json("GET", f"{base}/api/content-pipeline-catalog")
        assert_true(status == HTTPStatus.OK, "Expected /api/content-pipeline-catalog success")
        assert_true(content_catalog.get("success", False), "Expected content-pipeline-catalog success")
        assert_true(int(content_catalog.get("count", 0)) >= 1, "Expected content pipeline presets")

        status, mp_catalog = request_json("GET", f"{base}/api/multiplayer-correctness-catalog")
        assert_true(status == HTTPStatus.OK, "Expected /api/multiplayer-correctness-catalog success")
        assert_true(mp_catalog.get("success", False), "Expected multiplayer-correctness-catalog success")
        assert_true(int(mp_catalog.get("count", 0)) >= 1, "Expected multiplayer correctness profiles")

        status, material_mesh_catalog = request_json("GET", f"{base}/api/material-mesh-presets-catalog")
        assert_true(status == HTTPStatus.OK, "Expected /api/material-mesh-presets-catalog success")
        assert_true(material_mesh_catalog.get("success", False), "Expected material-mesh-presets-catalog success")
        assert_true(int(material_mesh_catalog.get("count", 0)) >= 1, "Expected material/mesh setup presets")

        status, pattern_preview = request_json(
            "POST",
            f"{base}/api/node-pattern-preview",
            {
                "pattern_id": "begin_play_print",
                "blueprint_path": "/Game/Test/BP_Example",
                "graph_name": "EventGraph",
                "message": "Smoke",
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/node-pattern-preview success")
        assert_true(pattern_preview.get("success", False), "Expected node-pattern-preview success")

        status, pattern_apply = request_json(
            "POST",
            f"{base}/api/node-pattern-apply",
            {
                "pattern_id": "begin_play_print",
                "blueprint_path": "/Game/Test/BP_Example",
                "graph_name": "EventGraph",
                "message": "Smoke Apply",
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/node-pattern-apply success")
        assert_true(pattern_apply.get("success", False), "Expected node-pattern-apply success")

        status, workflow_generate = request_json(
            "POST",
            f"{base}/api/workflow-generate",
            {
                "workflow_id": "objective_capture_loop_full",
                "namespace_root": "/Game/Test",
                "controller_asset_name": "BP_WorkflowSmoke",
                "objective_count": 3,
                "time_limit_sec": 90,
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/workflow-generate success")
        assert_true(workflow_generate.get("success", False), "Expected workflow-generate success")
        assert_true(isinstance(workflow_generate.get("generated_plan", {}), dict), "Expected workflow generated plan")

        status, animation_generate = request_json(
            "POST",
            f"{base}/api/animation-autonomy-generate",
            {
                "template_id": "locomotion_state_scaffold",
                "namespace_root": "/Game/Test",
                "anim_bp_asset_name": "ABP_Smoke",
                "character_bp_path": "/Game/Test/BP_Example",
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/animation-autonomy-generate success")
        assert_true(animation_generate.get("success", False), "Expected animation-autonomy-generate success")
        assert_true(isinstance(animation_generate.get("generated_plan", {}), dict), "Expected animation generated plan")

        status, ai_generate = request_json(
            "POST",
            f"{base}/api/ai-autonomy-generate",
            {
                "template_id": "bt_eqs_perception_scaffold",
                "namespace_root": "/Game/Test",
                "ai_controller_asset_name": "BP_AISmoke",
                "bt_task_asset_name": "BTT_AISmoke",
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/ai-autonomy-generate success")
        assert_true(ai_generate.get("success", False), "Expected ai-autonomy-generate success")
        assert_true(isinstance(ai_generate.get("generated_plan", {}), dict), "Expected ai generated plan")

        status, blackboard_evolve = request_json(
            "POST",
            f"{base}/api/blackboard-schema-evolve",
            {
                "blueprint_path": "/Game/Test/BP_Example",
                "schema": [{"key_name": "TargetActorKey", "key_type": "string", "default_value": ""}],
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/blackboard-schema-evolve success")
        assert_true(blackboard_evolve.get("success", False), "Expected blackboard-schema-evolve success")
        assert_true(isinstance(blackboard_evolve.get("generated_plan", {}), dict), "Expected blackboard generated plan")

        status, ai_validate = request_json(
            "POST",
            f"{base}/api/ai-behavior-validate",
            {"blueprint_path": "/Game/Test/BP_Example", "graph_name": "EventGraph", "assertions": []},
        )
        assert_true(status in (HTTPStatus.OK, HTTPStatus.CONFLICT), "Expected /api/ai-behavior-validate status")
        assert_true("compile" in ai_validate, "Expected ai behavior compile section")
        assert_true("scenario" in ai_validate, "Expected ai behavior scenario section")

        status, content_apply = request_json(
            "POST",
            f"{base}/api/content-pipeline-apply",
            {
                "preset_id": "static_mesh_pack_basic",
                "namespace_root": "/Game/Test",
                "pack_label": "SmokePack",
                "asset_paths": ["/Game/Test/BP_Example"],
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/content-pipeline-apply success")
        assert_true(content_apply.get("success", False), "Expected content pipeline apply success")
        assert_true("dependency_safety" in content_apply, "Expected dependency safety payload")

        status, schema_enforce = request_json(
            "POST",
            f"{base}/api/content-schema-enforce",
            {
                "package_path": "/Game",
                "recursive": True,
                "max_assets": 50,
                "allowed_roots": ["/Game"],
            },
        )
        assert_true(status in (HTTPStatus.OK, HTTPStatus.CONFLICT), "Expected /api/content-schema-enforce status")
        assert_true("violations" in schema_enforce, "Expected schema violation list")

        status, dependency_check = request_json(
            "POST",
            f"{base}/api/dependency-safety-check",
            {"asset_paths": ["/Game/Test/BP_Example"], "depth": 2},
        )
        assert_true(status in (HTTPStatus.OK, HTTPStatus.CONFLICT), "Expected /api/dependency-safety-check status")
        assert_true("items" in dependency_check, "Expected dependency safety items")

        status, mp_lint = request_json(
            "POST",
            f"{base}/api/multiplayer-lint",
            {"blueprint_path": "/Game/Test/BP_Example", "graph_name": "EventGraph"},
        )
        assert_true(status in (HTTPStatus.OK, HTTPStatus.CONFLICT), "Expected /api/multiplayer-lint status")
        assert_true("findings" in mp_lint, "Expected multiplayer lint findings")

        status, mp_guard_apply = request_json(
            "POST",
            f"{base}/api/multiplayer-guard-apply",
            {"blueprint_path": "/Game/Test/BP_Example", "dry_run": True},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/multiplayer-guard-apply success")
        assert_true(mp_guard_apply.get("success", False), "Expected multiplayer guard apply success")

        status, mp_pie_test = request_json(
            "POST",
            f"{base}/api/multiplayer-pie-test",
            {"assertions": [], "client_count": 2, "repeats": 1},
        )
        assert_true(status in (HTTPStatus.OK, HTTPStatus.CONFLICT), "Expected /api/multiplayer-pie-test status")
        assert_true("total_runs" in mp_pie_test, "Expected multiplayer pie total runs")
        assert_true("deterministic" in mp_pie_test, "Expected multiplayer pie determinism flag")
        assert_true("client_determinism" in mp_pie_test, "Expected multiplayer pie client determinism details")
        assert_true("execution_run_id" in mp_pie_test, "Expected multiplayer pie execution artifact id")

        status, bp_review = request_json(
            "POST",
            f"{base}/api/blueprint-structure-review",
            {
                "blueprint_path": "/Game/Test/BP_Example",
                "graph_name": "EventGraph",
                "include_ast": True,
            },
        )
        assert_true(status in (HTTPStatus.OK, HTTPStatus.CONFLICT), "Expected /api/blueprint-structure-review status")
        assert_true("analysis" in bp_review, "Expected blueprint review analysis section")
        assert_true("suggested_fixes" in bp_review, "Expected blueprint review suggested fixes")
        assert_true(bp_review.get("review_scope") == "graph", "Expected graph review scope response")

        status, bp_asset_review = request_json(
            "POST",
            f"{base}/api/blueprint-structure-review",
            {
                "blueprint_path": "/Game/Test/BP_Example",
                "review_scope": "asset",
                "include_ast": True,
                "max_graph_ast_exports": 4,
            },
        )
        assert_true(status in (HTTPStatus.OK, HTTPStatus.CONFLICT), "Expected /api/blueprint-structure-review asset status")
        assert_true(bp_asset_review.get("review_scope") == "asset", "Expected asset review scope response")
        assert_true(isinstance(bp_asset_review.get("graph_reviews", []), list), "Expected per-graph review list")

        status, rpc_lint = request_json(
            "POST",
            f"{base}/api/rpc-contract-lint",
            {"blueprint_path": "/Game/Test/BP_Example", "graph_name": "EventGraph"},
        )
        assert_true(status in (HTTPStatus.OK, HTTPStatus.CONFLICT), "Expected /api/rpc-contract-lint status")
        assert_true("risk_score" in rpc_lint, "Expected rpc contract lint risk score")

        status, ai_asset_authoring = request_json(
            "POST",
            f"{base}/api/ai-asset-authoring",
            {
                "namespace_root": "/Game/Test",
                "ai_controller_asset_name": "BP_AIAuthorSmoke",
                "bt_task_asset_name": "BTT_AIAuthorSmoke",
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/ai-asset-authoring success")
        assert_true(ai_asset_authoring.get("success", False), "Expected ai-asset-authoring success")
        assert_true(isinstance(ai_asset_authoring.get("generated_plan", {}), dict), "Expected ai asset authoring generated plan")

        status, material_mesh_setup = request_json(
            "POST",
            f"{base}/api/material-mesh-setup",
            {
                "preset_id": "static_mesh_actor_basic",
                "asset_name": "BP_MaterialMeshSmoke",
                "package_path": "/Game/Test",
                "static_mesh_path": "/Engine/BasicShapes/Cube.Cube",
                "material_path": "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial",
                "dry_run": True,
            },
        )
        assert_true(status in (HTTPStatus.OK, HTTPStatus.CONFLICT), "Expected /api/material-mesh-setup status")
        assert_true("step_results" in material_mesh_setup, "Expected material mesh setup step results")

        status, native_asset_catalog = request_json("GET", f"{base}/api/native-asset-authoring-catalog")
        assert_true(status == HTTPStatus.OK, "Expected /api/native-asset-authoring-catalog success")
        assert_true(native_asset_catalog.get("success", False), "Expected native asset catalog success")
        assert_true(int(native_asset_catalog.get("count", 0)) >= 1, "Expected native asset authoring entries")

        status, native_asset_create = request_json(
            "POST",
            f"{base}/api/native-asset-create",
            {
                "asset_type": "behavior_tree",
                "asset_name": "BT_Smoke",
                "package_path": "/Game/Test",
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/native-asset-create success")
        assert_true(native_asset_create.get("success", False), "Expected native asset create success")

        status, native_asset_edit = request_json(
            "POST",
            f"{base}/api/native-asset-edit",
            {
                "asset_type": "behavior_tree",
                "behavior_tree_path": "/Game/Test/BT_Smoke",
                "tasks": [{"class_path": "/Script/AIModule.BTTask_Wait", "wait_time": 0.2}],
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/native-asset-edit success")
        assert_true(native_asset_edit.get("success", False), "Expected native asset edit success")

        status, native_material_edit = request_json(
            "POST",
            f"{base}/api/native-asset-edit",
            {
                "asset_type": "material",
                "material_path": "/Game/Test/M_Smoke",
                "operations": [
                    {
                        "op": "create_expression",
                        "expression_class_path": "/Script/Engine.MaterialExpressionConstant",
                        "expression_name": "ConstSmoke",
                        "scalar_value": 0.5,
                    }
                ],
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/native-asset-edit material success")
        assert_true(native_material_edit.get("success", False), "Expected native material edit success")

        status, native_sequence_edit = request_json(
            "POST",
            f"{base}/api/native-asset-edit",
            {
                "asset_type": "level_sequence",
                "level_sequence_path": "/Game/Test/LS_Smoke",
                "operations": [
                    {"op": "ensure_float_track", "track_name": "SmokeTrack", "property_name": "SmokeValue", "property_path": "SmokeValue"},
                    {"op": "add_float_key", "track_name": "SmokeTrack", "property_name": "SmokeValue", "frame": 10, "value": 1.0, "interp": "linear"},
                ],
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/native-asset-edit level sequence success")
        assert_true(native_sequence_edit.get("success", False), "Expected native sequence edit success")

        status, native_niagara_edit = request_json(
            "POST",
            f"{base}/api/native-asset-edit",
            {
                "asset_type": "niagara_system",
                "niagara_system_path": "/Game/Test/NS_Smoke",
                "determinism": True,
                "deterministic_seed": 17,
                "operations": [
                    {"op": "add_user_parameter", "parameter_name": "User.Speed", "parameter_type": "float", "value": 350.0},
                    {"op": "set_system_playback_range", "playback_start": 0.0, "playback_end": 4.0},
                    {"op": "set_emitter_local_space", "emitter_name": "Emitter", "local_space": True},
                ],
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/native-asset-edit niagara success")
        assert_true(native_niagara_edit.get("success", False), "Expected native niagara edit success")

        status, native_asset_workflow = request_json(
            "POST",
            f"{base}/api/native-asset-authoring-workflow",
            {
                "asset_type": "behavior_tree",
                "asset_name": "BT_SmokeWF",
                "package_path": "/Game/Test",
                "behavior_tree_path": "/Game/Test/BT_SmokeWF",
                "tasks": [{"class_path": "/Script/AIModule.BTTask_Wait", "wait_time": 0.2}],
                "dry_run": True,
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/native-asset-authoring-workflow success")
        assert_true(native_asset_workflow.get("success", False), "Expected native asset workflow success")

        status, graph_primitives_apply = request_json(
            "POST",
            f"{base}/api/graph-primitives-apply",
            {
                "blueprint_path": "/Game/Test/BP_Example",
                "graph_name": "EventGraph",
                "dry_run": True,
                "operations": [
                    {
                        "operation": "spawn_node_by_class",
                        "node_class_path": "/Script/BlueprintGraph.K2Node_CustomEvent",
                        "custom_event_name": "SmokeEvent",
                        "node_name": "K2Node_CustomEvent_SmokeEvent",
                        "node_position": [300, 100],
                    }
                ],
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/graph-primitives-apply success")
        assert_true(graph_primitives_apply.get("success", False), "Expected graph-primitives-apply success")
        assert_true(isinstance(graph_primitives_apply.get("results", []), list), "Expected graph-primitives apply results")

        status, runtime_validate = request_json(
            "POST",
            f"{base}/api/runtime-validate-repair",
            {
                "blueprint_path": "/Game/Test/BP_Example",
                "assertions": [],
                "auto_repair": False,
                "max_repair_attempts": 0,
                "capture_screenshot_on_fail": False,
            },
        )
        assert_true(status in (HTTPStatus.OK, HTTPStatus.CONFLICT), "Expected /api/runtime-validate-repair status")
        assert_true("validation" in runtime_validate, "Expected runtime validation payload")
        assert_true("auto_repair" in runtime_validate, "Expected runtime auto_repair payload")

        status, autonomous_loop = request_json(
            "POST",
            f"{base}/api/autonomous-loop-run",
            {
                "blueprint_path": "/Game/Test/BP_Example",
                "assertions": [],
                "scenario_repeats": 1,
                "auto_repair": False,
                "max_repair_attempts": 0,
                "capture_screenshot_on_fail": False,
                "enable_multiplayer": True,
                "multiplayer": {"enabled": True, "assertions": [], "client_count": 2, "repeats": 1},
                "include_lint_gate": True,
                "include_perf_gate": True,
                "max_rpc_risk_score": 100.0,
                "max_multiplayer_lint_risk_score": 100.0,
                "max_perf_risk_score": 100.0,
                "rollback_on_failure": False,
            },
        )
        assert_true(status in (HTTPStatus.OK, HTTPStatus.CONFLICT), "Expected /api/autonomous-loop-run status")
        assert_true("validation" in autonomous_loop, "Expected autonomous loop validation payload")
        assert_true("timeline" in autonomous_loop, "Expected autonomous loop timeline payload")

        status, pie_replay_suite = request_json(
            "POST",
            f"{base}/api/pie-replay-suite",
            {
                "assertions": [],
                "include_multiplayer": True,
                "client_count": 2,
                "repeats": 1,
            },
        )
        assert_true(status in (HTTPStatus.OK, HTTPStatus.CONFLICT), "Expected /api/pie-replay-suite status")
        assert_true("runs" in pie_replay_suite, "Expected pie replay suite runs")
        assert_true("determinism_details" in pie_replay_suite, "Expected pie replay determinism details")
        assert_true("execution_run_id" in pie_replay_suite, "Expected pie replay execution artifact id")

        status, graph_snapshots = request_json("GET", f"{base}/api/graph-snapshots")
        assert_true(status == HTTPStatus.OK, "Expected /api/graph-snapshots success")
        assert_true(graph_snapshots.get("success", False), "Expected graph-snapshots success")

        status, replay_suite = request_json(
            "POST",
            f"{base}/api/replay-suite",
            {
                "repeats": 2,
                "cases": [
                    {
                        "case_id": "recipe_case_1",
                        "command": "Create a timed objective collection loop for parkour.",
                    }
                ],
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/replay-suite success")
        assert_true(replay_suite.get("success", False), "Expected replay-suite success")
        assert_true(int(replay_suite.get("case_passed", 0)) >= 1, "Expected replay suite to pass at least one case")

        status, release_gate = request_json(
            "POST",
            f"{base}/api/release-gate-evaluate",
            {
                "blueprint_paths": ["/Game/Test/BP_Example"],
                "replay_repeats": 2,
                "replay_cases": [
                    {
                        "case_id": "release_recipe_case",
                        "command": "Create a timed objective collection loop for parkour.",
                    }
                ],
                "multiplayer": {
                    "enabled": True,
                    "assertions": [],
                    "client_count": 2,
                    "repeats": 1,
                },
            },
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/release-gate-evaluate success")
        assert_true(release_gate.get("success", False), "Expected release gate success")
        gates = release_gate.get("gates", {})
        assert_true(bool(gates.get("replay_suite_pass", False)), "Expected replay gate pass")
        assert_true(bool(gates.get("compile_gate_pass", False)), "Expected compile gate pass")
        assert_true(bool(gates.get("contradiction_gate_pass", False)), "Expected contradiction gate pass")
        assert_true(bool(gates.get("multiplayer_gate_pass", False)), "Expected multiplayer gate pass")

        status, rollback_apply = request_json(
            "POST",
            f"{base}/api/rollback-apply",
            {"rollback_token": rollback_token, "dry_run": True, "stop_on_error": True},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/rollback-apply success")
        assert_true(rollback_apply.get("success", False), "Expected rollback-apply success")

        status, entitlements = request_json(
            "POST",
            f"{base}/api/entitlements/check",
            {"paid_token": "test-paid-token", "feature": "refactor_preview"},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/entitlements/check success")
        assert_true(entitlements.get("success", False), "Expected entitlements check success")

        status, usage_event = request_json(
            "POST",
            f"{base}/api/usage/event",
            {"paid_token": "test-paid-token", "event_type": "smoke", "route": "/api/refactor-preview"},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/usage/event success")
        assert_true(usage_event.get("success", False), "Expected usage event success")

        status, claims_evidence = request_json("GET", f"{base}/api/claims-evidence")
        assert_true(status == HTTPStatus.OK, "Expected /api/claims-evidence success")
        assert_true(claims_evidence.get("success", False), "Expected claims evidence success")
        assert_true(int(claims_evidence.get("claims_total", 0)) >= 1, "Expected claims evidence rows")

        status, admin_diag = request_json(
            "GET",
            f"{base}/api/admin/session-diagnostics",
            headers={"X-Paid-Token": "test-admin-token"},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/admin/session-diagnostics success")
        assert_true(admin_diag.get("success", False), "Expected admin diagnostics success")

        status, admin_usage = request_json(
            "GET",
            f"{base}/api/admin/usage-events?limit=10",
            headers={"X-Paid-Token": "test-admin-token"},
        )
        assert_true(status == HTTPStatus.OK, "Expected /api/admin/usage-events success")
        assert_true(admin_usage.get("success", False), "Expected admin usage success")
        assert_true(isinstance(admin_usage.get("events", []), list), "Expected admin usage events list")

        status, contradictory = request_json(
            "POST",
            f"{base}/api/analyze",
            {
                "blueprint_path": "/Game/Test/BP_Bad",
                "mode": "graph",
                "prompt": "Analyze this blueprint",
            },
        )
        assert_true(status == HTTPStatus.CONFLICT, "Expected contradiction conflict for bad graph")
        assert_true(contradictory.get("error_code") == "ANALYSIS_CONTRADICTION", "Expected ANALYSIS_CONTRADICTION")

        print("Smoke tests passed.")
    finally:
        StubUnrealHandler.delay_run_goal_sec = 0.0
        stub_server.shutdown()
        stub_server.server_close()

        web_proc.terminate()
        try:
            web_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            web_proc.kill()
            web_proc.wait(timeout=5)

        for file_path, previous in backups.items():
            if previous is None:
                if file_path.exists():
                    file_path.unlink()
            else:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(previous)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        print(f"Smoke tests failed: {exc}", file=sys.stderr)
        sys.exit(1)
