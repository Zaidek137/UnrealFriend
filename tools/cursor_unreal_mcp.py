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
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


JSONRPC_VERSION = "2.0"

DEFAULT_WEB_BASE = os.environ.get("UNREAL_AGENT_WEB_BASE", "http://127.0.0.1:8787").rstrip("/")
AUTO_APPROVE = os.environ.get("UNREAL_AGENT_AUTO_APPROVE", "true").strip().lower() in {"1", "true", "yes", "on"}
AUTO_START_WEB = os.environ.get("UNREAL_AGENT_WEB_AUTOSTART", "true").strip().lower() in {"1", "true", "yes", "on"}
WEB_SERVER_PATH = Path(os.environ.get("UNREAL_AGENT_WEB_SERVER_PATH", "/Users/ericdiaz/Desktop/Unreal Friend/apps/unreal-agent-web/server.py"))

_web_start_attempted = False


def request_json(method: str, path: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 120) -> Tuple[int, Dict[str, Any]]:
    url = f"{DEFAULT_WEB_BASE}{path}"
    data = None
    headers = {"Content-Type": "application/json"}
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
        "goal_context": goal_context,
    }

    status, result = request_json("POST", "/api/chat", payload)

    if result.get("error_code") == "APPROVAL_REQUIRED" and AUTO_APPROVE:
        token = str(result.get("approval_token", "")).strip()
        if token:
            approve_status, approve_result = request_json("POST", "/api/approve", {"approval_token": token})
            if approve_status < 400 and approve_result.get("success", False):
                payload["approval_token"] = token
                status, result = request_json("POST", "/api/chat", payload)
            else:
                return mcp_error_content("Approval failed during auto-approve", {"approval": approve_result, "initial": result})

    if status >= 400 and not result.get("success", False):
        return mcp_error_content("unreal_chat failed", {"http_status": status, "response": result})

    return mcp_content(to_text(result))


def call_endpoint(path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ensure_web_available()
    status, result = request_json(method, path, payload)
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

    status, result = request_json("POST", "/api/direct-execute", body)
    if result.get("error_code") == "APPROVAL_REQUIRED" and AUTO_APPROVE:
        token = str(result.get("approval_token", "")).strip()
        if token:
            approve_status, approve_result = request_json("POST", "/api/approve", {"approval_token": token})
            if approve_status < 400 and approve_result.get("success", False):
                body["approval_token"] = token
                status, result = request_json("POST", "/api/direct-execute", body)
            else:
                return mcp_error_content("Approval failed during auto-approve", {"approval": approve_result, "initial": result})

    if status >= 400 and not result.get("success", False):
        return mcp_error_content("unreal_execute_action failed", {"http_status": status, "response": result})

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
