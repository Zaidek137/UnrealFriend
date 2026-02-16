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
ANALYSIS_RUNS_DIR = DATA_DIR / "analysis-runs"
RECIPES_DIR = ROOT_DIR / "data" / "recipes"
SETTINGS_PATH = DATA_DIR / "settings.json"
APPROVALS_PATH = DATA_DIR / "approvals.json"
AUDIT_LOG_PATH = DATA_DIR / "audit.log.jsonl"
RELEASE_METRICS_PATH = DATA_DIR / "release_metrics.json"
NODE_LIBRARY_INDEX_PATH = ROOT_DIR / "data" / "blueprint-node-library" / "node_library_index.json"

RUN_LOCK = threading.Lock()
APPROVALS_LOCK = threading.Lock()
AUDIT_LOCK = threading.Lock()
RELEASE_METRICS_LOCK = threading.Lock()

MUTATING_ACTIONS = {
    "create_blueprint",
    "spawn_actor",
    "modify_blueprint_graph",
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
    "risky_actions": sorted(list(MUTATING_ACTIONS)),
    "min_api_version": "v1",
    "min_plugin_version": "0.1.0",
    "analysis_llm_summary": True,
    "analysis_require_citations": True,
    "analysis_disallow_speculative": True,
    "analysis_store_artifacts": True,
    "analysis_max_saved_runs": 200,
    "execution_profile": "balanced",
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
    ANALYSIS_RUNS_DIR.mkdir(parents=True, exist_ok=True)


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

    wants_mp = any(k in text for k in ["multiplayer", "mp", "replication", "authority", "network"])
    if any(k in text for k in ["timed", "timer"]) and any(k in text for k in ["objective", "collect", "capture"]):
        return "objective_loop_timed_collection_mp_safe" if wants_mp else "objective_loop_timed_collection_sp"
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

            if path == "/api/debug/clear":
                result = call_unreal(settings, "POST", "/debug/clear", payload={})
                self._json_response(result.status_code, result.payload)
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
                profile = str(body.get("profile", settings.get("execution_profile", "balanced"))).strip().lower() or "balanced"
                approval_token = str(body.get("approval_token", "")).strip()
                release_validation = bool(body.get("release_validation", False))

                recipe_def = get_recipe_definition(recipe_id)
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

                request_payload = {
                    "recipe_id": recipe_id,
                    "inputs": resolved_inputs,
                    "dry_run": dry_run,
                    "stop_on_error": stop_on_error,
                    "profile": profile,
                }

                def run_recipe():
                    result = call_unreal(settings, "POST", "/run-recipe", request_payload)
                    return result.status_code, result.payload

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

                update_release_metrics(
                    run_kind="recipe_runs",
                    run_success=run_success,
                    http_status=int(status),
                    response_payload=response,
                    profile=profile,
                    release_validation=release_validation,
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

                profile = str(body.get("profile", settings.get("execution_profile", "balanced"))).strip().lower() or "balanced"
                release_validation = bool(body.get("release_validation", True))
                recipe_def = get_recipe_definition(recipe_id)
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
                profile = str(body.get("profile", settings.get("execution_profile", "balanced"))).strip().lower() or "balanced"
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

                artifact = {
                    "timestamp": time.time(),
                    "blueprint_path": blueprint_path,
                    "mode": mode,
                    "action": action_name,
                    "action_payload": action_payload,
                    "report_source": report_source,
                    "report_generation_errors": report_errors,
                    "analysis": analysis_payload,
                    "lint_findings": lint_findings,
                    "report": report,
                    "report_validation": report_validation,
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
                        "lint_findings": lint_findings,
                        "report": report,
                        "report_validation": report_validation,
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
                issues = collect_analysis_contradictions(response)
                if issues:
                    status = HTTPStatus.CONFLICT
                    response = make_error(
                        "ANALYSIS_CONTRADICTION",
                        "Plan execution reported analysis contradictions.",
                        issues=issues,
                        upstream=response,
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
                    "recipe_id": str(body.get("recipe_id", "")).strip(),
                    "inputs": body.get("inputs", {}),
                    "profile": str(body.get("profile", settings.get("execution_profile", "balanced"))).strip(),
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
                profile = str(body.get("profile", settings.get("execution_profile", "balanced"))).strip().lower() or "balanced"

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

                    recipe_request = {
                        "recipe_id": routed_recipe_id,
                        "inputs": recipe_inputs,
                        "dry_run": dry_run,
                        "stop_on_error": stop_on_error,
                        "profile": profile,
                    }

                    def run_command_recipe():
                        result = call_unreal(settings, "POST", "/run-recipe", recipe_request)
                        payload = result.payload if isinstance(result.payload, dict) else {"success": False, "raw": result.payload}
                        response = {
                            "success": bool(payload.get("success", False)),
                            "mode": "recipe",
                            "recipe_id": routed_recipe_id,
                            "profile": profile,
                            "resolved_inputs": recipe_inputs,
                            "input_validation": recipe_validation,
                            "execution": payload,
                            "unreal_status_code": result.status_code,
                        }
                        issues = collect_analysis_contradictions(response)
                        if issues:
                            return HTTPStatus.CONFLICT, make_error(
                                "ANALYSIS_CONTRADICTION",
                                "Recipe execution reported analysis contradictions.",
                                issues=issues,
                                result=response,
                            )
                        return HTTPStatus.OK if result.status_code < 500 else HTTPStatus.BAD_GATEWAY, response

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
