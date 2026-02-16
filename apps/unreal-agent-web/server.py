#!/usr/bin/env python3
import json
import os
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
SETTINGS_PATH = DATA_DIR / "settings.json"
APPROVALS_PATH = DATA_DIR / "approvals.json"
AUDIT_LOG_PATH = DATA_DIR / "audit.log.jsonl"
NODE_LIBRARY_INDEX_PATH = ROOT_DIR / "data" / "blueprint-node-library" / "node_library_index.json"

RUN_LOCK = threading.Lock()
APPROVALS_LOCK = threading.Lock()
AUDIT_LOCK = threading.Lock()

MUTATING_ACTIONS = {
    "create_blueprint",
    "spawn_actor",
    "modify_blueprint_graph",
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
    "risky_actions": sorted(list(MUTATING_ACTIONS)),
    "min_api_version": "v1",
    "min_plugin_version": "0.1.0",
}


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


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


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


def validate_plan_with_node_library(plan: Dict[str, Any]) -> Dict[str, Any]:
    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        return {"ok": False, "errors": ["Plan steps must be an array."], "warnings": []}

    errors: List[str] = []
    warnings: List[str] = []
    allowed_graph_ops = {
        "add_print_string_on_begin_play",
        "add_variable",
        "set_default",
        "add_branch",
        "call_function",
    }

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
            elif op == "add_variable":
                if not str(payload.get("variable_name", "")).strip():
                    errors.append(f"Step {i}: add_variable requires payload.variable_name.")
            elif op == "set_default":
                if not str(payload.get("variable_name", "")).strip():
                    errors.append(f"Step {i}: set_default requires payload.variable_name.")
                if "default_value" not in payload:
                    errors.append(f"Step {i}: set_default requires payload.default_value.")

        elif action == "create_blueprint":
            package_path = str(payload.get("package_path", "")).strip()
            if package_path and not package_path.startswith("/Game"):
                warnings.append(f"Step {i}: create_blueprint package_path should usually be under /Game.")

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

    def _with_run_lock(self, fn):
        if not RUN_LOCK.acquire(blocking=False):
            return HTTPStatus.CONFLICT, make_error("RUN_BUSY", "Another Unreal run is already in progress.")
        try:
            return fn()
        finally:
            RUN_LOCK.release()

    def do_GET(self) -> None:
        try:
            parsed_url = urllib.parse.urlparse(self.path)
            path = parsed_url.path
            query = urllib.parse.parse_qs(parsed_url.query)
            settings = load_settings()

            if path == "/":
                self._serve_index()
                return
            if path == "/api/settings":
                safe = dict(settings)
                if safe.get("llm_api_key"):
                    safe["llm_api_key"] = "********"
                self._json_response(HTTPStatus.OK, {"success": True, "settings": safe})
                return
            if path == "/api/approvals":
                approvals = load_approvals()
                items = list(approvals.get("items", {}).values())
                items.sort(key=lambda x: float(x.get("created_at", 0.0)), reverse=True)
                self._json_response(HTTPStatus.OK, {"success": True, "approvals": items})
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

            if path == "/api/settings":
                merged = dict(settings)
                for key in DEFAULT_SETTINGS.keys():
                    if key in body:
                        merged[key] = body[key]
                merged = save_settings(merged)
                safe = dict(merged)
                if safe.get("llm_api_key"):
                    safe["llm_api_key"] = "********"
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

            compatibility = check_compatibility(settings)
            if not compatibility.get("ok", False):
                self._json_response(
                    HTTPStatus.PRECONDITION_FAILED,
                    make_error("VERSION_INCOMPATIBLE", "Unreal plugin/API compatibility check failed.", compatibility=compatibility),
                )
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

                def run_plan():
                    result = call_unreal(settings, "POST", "/run-plan", plan)
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_plan)
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
                dry_run = bool(goal_request.get("dry_run", False))
                approval_token = str(body.get("approval_token", goal_request.get("approval_token", ""))).strip()
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

                def run_goal():
                    result = call_unreal(settings, "POST", "/run-goal", goal_request)
                    return result.status_code, result.payload

                status, response = self._with_run_lock(run_goal)
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
                    "approval_token": str(body.get("approval_token", "")).strip(),
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

                approval_token = str(body.get("approval_token", "")).strip()
                llm_enabled = bool(settings.get("llm_enabled", True))
                llm_model = str(settings.get("llm_model", "")).strip()
                llm_base_url = str(settings.get("llm_base_url", "")).strip()
                use_llm = llm_enabled and bool(llm_model) and bool(llm_base_url)

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
                        return HTTPStatus.OK if result.status_code < 500 else HTTPStatus.BAD_GATEWAY, response

                    status, response = self._with_run_lock(run_command_plan)
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
