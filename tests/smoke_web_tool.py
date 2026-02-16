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
AUDIT_LOG = ROOT / "apps" / "unreal-agent-web" / ".data" / "audit.log.jsonl"


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


def request_json(method: str, url: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, Any]]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url=url, method=method, data=data, headers=headers)
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
    managed_files = [SETTINGS_FILE, APPROVALS_FILE, AUDIT_LOG]
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

        status, _ = request_json("GET", f"{base}/api/info")
        assert_true(status == HTTPStatus.OK, "Expected /api/info to proxy correctly")

        status, _ = request_json("GET", f"{base}/api/state")
        assert_true(status == HTTPStatus.OK, "Expected /api/state to proxy correctly")

        status, recipes = request_json("GET", f"{base}/api/recipes")
        assert_true(status == HTTPStatus.OK, "Expected /api/recipes to succeed")
        assert_true(recipes.get("success", False), "Expected /api/recipes success")
        assert_true(int(recipes.get("local_recipe_count", 0)) >= 1, "Expected local recipe catalog")

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
