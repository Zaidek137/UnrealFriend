#!/usr/bin/env python3
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

import os


AUTO_BOOTSTRAP = os.environ.get("UNREAL_AGENT_AUTO_BOOTSTRAP", "true").strip().lower() in {"1", "true", "yes", "on"}
REQUEST_EXTRA_HEADERS: Dict[str, str] = {}


def request_json(method: str, url: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json"}
    if REQUEST_EXTRA_HEADERS:
        headers.update(REQUEST_EXTRA_HEADERS)
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


def bootstrap_agent_session(base_url: str, cmd_name: str) -> Dict[str, Any]:
    payload = {
        "client_name": "ide_unreal_agent_cli",
        "client_version": "0.1.0",
        "session_label": cmd_name,
    }
    result = request_json("POST", f"{base_url}/api/agent-bootstrap", payload)
    if not bool(result.get("success", False)):
        return result
    token = str(result.get("bootstrap_token", "")).strip()
    if not token:
        return {"success": False, "error_code": "BOOTSTRAP_TOKEN_MISSING", "message": "Agent bootstrap succeeded without token.", "response": result}
    REQUEST_EXTRA_HEADERS["X-Agent-Bootstrap-Token"] = token
    return result


def parse_json_arg(raw: str, label: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError(f"{label} must be a JSON object")
        return parsed
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid {label}: {exc}") from exc


def parse_json_value(raw: str, label: str) -> Any:
    try:
        return json.loads(raw)
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
    sub.add_parser("claims-evidence")
    sub.add_parser("execution-runs")
    sub.add_parser("workflow-catalog")
    sub.add_parser("node-control-capabilities")
    execution_run_detail = sub.add_parser("execution-run-detail")
    execution_run_detail.add_argument("--run-id", required=True)
    execution_artifact = sub.add_parser("execution-artifact")
    execution_artifact.add_argument("--run-id", required=True)
    execution_artifact.add_argument("--include-snapshot", action="store_true", default=True)
    execution_artifact.add_argument("--no-include-snapshot", action="store_true")
    execution_artifact.add_argument("--include-full", action="store_true")
    sub.add_parser("paid-session-logs")
    sub.add_parser("info")
    sub.add_parser("state")
    sub.add_parser("approvals")
    admin_diag = sub.add_parser("admin-session-diagnostics")
    admin_diag.add_argument("--paid-token", default="")
    admin_usage = sub.add_parser("admin-usage-events")
    admin_usage.add_argument("--limit", type=int, default=200)
    admin_usage.add_argument("--paid-token", default="")

    approve = sub.add_parser("approve")
    approve.add_argument("--approval-token", required=True)

    paid_start = sub.add_parser("start-paid-session")
    paid_start.add_argument("--paid-token", required=True)
    paid_start.add_argument("--user-id", default="")
    paid_start.add_argument("--project-label", default="")

    paid_end = sub.add_parser("end-paid-session")
    paid_end.add_argument("--paid-token", required=True)
    paid_end.add_argument("--session-id", required=True)

    run_cmd = sub.add_parser("run-command")
    run_cmd.add_argument("--command", required=True)
    run_cmd.add_argument("--dry-run", action="store_true")
    run_cmd.add_argument("--stop-on-error", action="store_true", default=True)
    run_cmd.add_argument("--no-stop-on-error", action="store_true")
    run_cmd.add_argument("--profile", default="balanced")
    run_cmd.add_argument("--goal-context-json", default="{}")
    run_cmd.add_argument("--approval-token", default="")
    run_cmd.add_argument("--session-id", default="")

    run_goal = sub.add_parser("run-goal")
    run_goal.add_argument("--goal", required=True)
    run_goal.add_argument("--dry-run", action="store_true")
    run_goal.add_argument("--stop-on-error", action="store_true", default=True)
    run_goal.add_argument("--no-stop-on-error", action="store_true")
    run_goal.add_argument("--goal-context-json", default="{}")
    run_goal.add_argument("--approval-token", default="")
    run_goal.add_argument("--session-id", default="")

    run_plan = sub.add_parser("run-plan")
    run_plan.add_argument("--plan-json", required=True)
    run_plan.add_argument("--approval-token", default="")
    run_plan.add_argument("--session-id", default="")

    run_recipe = sub.add_parser("run-recipe")
    run_recipe.add_argument("--recipe-id", required=True)
    run_recipe.add_argument("--inputs-json", default="{}")
    run_recipe.add_argument("--dry-run", action="store_true")
    run_recipe.add_argument("--stop-on-error", action="store_true", default=True)
    run_recipe.add_argument("--no-stop-on-error", action="store_true")
    run_recipe.add_argument("--profile", default="balanced")
    run_recipe.add_argument("--approval-token", default="")
    run_recipe.add_argument("--session-id", default="")

    validate_recipe = sub.add_parser("validate-recipe")
    validate_recipe.add_argument("--recipe-id", required=True)
    validate_recipe.add_argument("--inputs-json", default="{}")
    validate_recipe.add_argument("--profile", default="balanced")

    run_scenario = sub.add_parser("run-scenario")
    run_scenario.add_argument("--assertions-json", required=True)
    run_scenario.add_argument("--dry-run", action="store_true")
    run_scenario.add_argument("--profile", default="balanced")
    run_scenario.add_argument("--release-validation", action="store_true")
    run_scenario.add_argument("--paid-token", default="")

    validate_execution = sub.add_parser("validate-execution")
    validate_execution.add_argument("--compile-blueprints-json", default="[]")
    validate_execution.add_argument("--assertions-json", default="[]")
    validate_execution.add_argument("--profile", default="balanced")
    validate_execution.add_argument("--release-validation", action="store_true")
    validate_execution.add_argument("--paid-token", default="")

    project_audit = sub.add_parser("project-audit")
    project_audit.add_argument("--package-path", default="/Game")
    project_audit.add_argument("--recursive", action="store_true", default=True)
    project_audit.add_argument("--class-paths-json", default='["/Script/Engine.Blueprint","/Script/UMG.WidgetBlueprint"]')
    project_audit.add_argument("--name-contains", default="")
    project_audit.add_argument("--max-assets", type=int, default=200)
    project_audit.add_argument("--analyze-blueprints", action="store_true", default=True)
    project_audit.add_argument("--compile-blueprints", action="store_true")
    project_audit.add_argument("--profile", default="balanced")
    project_audit.add_argument("--release-validation", action="store_true")
    project_audit.add_argument("--paid-token", default="")

    refactor_suggest = sub.add_parser("refactor-suggest")
    refactor_suggest.add_argument("--blueprint-path", required=True)
    refactor_suggest.add_argument("--mode", default="asset")
    refactor_suggest.add_argument("--profile", default="balanced")
    refactor_suggest.add_argument("--include-pins", action="store_true")
    refactor_suggest.add_argument("--max-nodes", type=int, default=1000)
    refactor_suggest.add_argument("--max-trace-depth", type=int, default=128)
    refactor_suggest.add_argument("--graph-name", default="")

    refactor_catalog = sub.add_parser("refactor-catalog")
    refactor_catalog.add_argument("--blueprint-path", default="")
    refactor_catalog.add_argument("--mode", default="asset")
    refactor_catalog.add_argument("--profile", default="balanced")
    refactor_catalog.add_argument("--include-pins", action="store_true")
    refactor_catalog.add_argument("--max-nodes", type=int, default=1000)
    refactor_catalog.add_argument("--max-trace-depth", type=int, default=128)
    refactor_catalog.add_argument("--graph-name", default="")

    refactor_preview = sub.add_parser("refactor-preview")
    refactor_preview.add_argument("--blueprint-path", required=True)
    refactor_preview.add_argument("--mode", default="asset")
    refactor_preview.add_argument("--profile", default="balanced")
    refactor_preview.add_argument("--include-pins", action="store_true")
    refactor_preview.add_argument("--max-nodes", type=int, default=1000)
    refactor_preview.add_argument("--max-trace-depth", type=int, default=128)
    refactor_preview.add_argument("--graph-name", default="")
    refactor_preview.add_argument("--transform-ids-json", default="[]")
    refactor_preview.add_argument("--transform-inputs-json", default="{}")
    refactor_preview.add_argument("--stop-on-error", action="store_true", default=True)
    refactor_preview.add_argument("--no-stop-on-error", action="store_true")

    refactor_apply = sub.add_parser("refactor-apply")
    refactor_apply.add_argument("--blueprint-path", required=True)
    refactor_apply.add_argument("--mode", default="asset")
    refactor_apply.add_argument("--include-pins", action="store_true")
    refactor_apply.add_argument("--max-nodes", type=int, default=1000)
    refactor_apply.add_argument("--max-trace-depth", type=int, default=128)
    refactor_apply.add_argument("--graph-name", default="")
    refactor_apply.add_argument("--suggestion-ids-json", default="[]")
    refactor_apply.add_argument("--transform-ids-json", default="[]")
    refactor_apply.add_argument("--transform-inputs-json", default="{}")
    refactor_apply.add_argument("--dry-run", action="store_true")
    refactor_apply.add_argument("--stop-on-error", action="store_true", default=True)
    refactor_apply.add_argument("--no-stop-on-error", action="store_true")
    refactor_apply.add_argument("--approval-token", default="")
    refactor_apply.add_argument("--profile", default="balanced")
    refactor_apply.add_argument("--release-validation", action="store_true")

    explain_selection = sub.add_parser("explain-selection")
    explain_selection.add_argument("--blueprint-path", required=True)
    explain_selection.add_argument("--graph-name", default="")
    explain_selection.add_argument("--node-names-json", default="[]")
    explain_selection.add_argument("--mode", default="graph")
    explain_selection.add_argument("--include-pins", action="store_true")
    explain_selection.add_argument("--max-nodes", type=int, default=1500)
    explain_selection.add_argument("--max-trace-depth", type=int, default=128)

    explain_screenshot = sub.add_parser("explain-screenshot")
    explain_screenshot.add_argument("--image-path", required=True)
    explain_screenshot.add_argument("--blueprint-path", default="")
    explain_screenshot.add_argument("--graph-name", default="")

    project_deps = sub.add_parser("project-dependencies")
    project_deps.add_argument("--package-path", default="/Game")
    project_deps.add_argument("--recursive", action="store_true", default=True)
    project_deps.add_argument("--depth", type=int, default=2)
    project_deps.add_argument("--max-assets", type=int, default=300)

    perf_hotspots = sub.add_parser("perf-hotspots")
    perf_hotspots.add_argument("--package-path", default="/Game")
    perf_hotspots.add_argument("--recursive", action="store_true", default=True)
    perf_hotspots.add_argument("--analyze-blueprints", action="store_true", default=True)
    perf_hotspots.add_argument("--max-assets", type=int, default=200)

    impact_analysis = sub.add_parser("impact-analysis")
    impact_analysis.add_argument("--asset-paths-json", required=True)
    impact_analysis.add_argument("--change-type", default="modify_blueprint_graph")

    umg_generate = sub.add_parser("umg-generate")
    umg_generate.add_argument("--widget-blueprint", default="")
    umg_generate.add_argument("--asset-name", default="WBP_AgentGenerated")
    umg_generate.add_argument("--package-path", default="/Game/AgentGenerated/UI")
    umg_generate.add_argument("--template-id", default="hud_basic")
    umg_generate.add_argument("--style-preset", default="minimal")
    umg_generate.add_argument("--bindings-json", default="[]")

    world_generate = sub.add_parser("world-generate")
    world_generate.add_argument("--layout-id", default="city_grid")
    world_generate.add_argument("--bounds-json", default="[0,0,5000,5000]")
    world_generate.add_argument("--density", type=float, default=1.0)
    world_generate.add_argument("--seed", type=int, default=1337)
    world_generate.add_argument("--constraints-json", default="{}")

    entitlements = sub.add_parser("entitlements-check")
    entitlements.add_argument("--paid-token", required=True)
    entitlements.add_argument("--feature", default="paid_live_logs")

    usage_event = sub.add_parser("usage-event")
    usage_event.add_argument("--paid-token", required=True)
    usage_event.add_argument("--event-type", required=True)
    usage_event.add_argument("--amount", type=float, default=1.0)
    usage_event.add_argument("--metadata-json", default="{}")

    property_reflect = sub.add_parser("property-reflect")
    property_reflect.add_argument("--target-type", default="blueprint_cdo")
    property_reflect.add_argument("--blueprint-path", default="")
    property_reflect.add_argument("--component-name", default="")
    property_reflect.add_argument("--actor", default="")
    property_reflect.add_argument("--property-name", required=True)
    property_reflect.add_argument("--value-json", required=True)
    property_reflect.add_argument("--compile-after", action="store_true")
    property_reflect.add_argument("--dry-run", action="store_true")

    function_author = sub.add_parser("blueprint-function-author")
    function_author.add_argument("--blueprint-path", required=True)
    function_author.add_argument("--graph-kind", default="function")
    function_author.add_argument("--graph-name", required=True)
    function_author.add_argument("--category", default="")
    function_author.add_argument("--compile-after", action="store_true")
    function_author.add_argument("--dry-run", action="store_true")

    component_hierarchy = sub.add_parser("component-hierarchy")
    component_hierarchy.add_argument("--blueprint-path", required=True)
    component_hierarchy.add_argument("--operation", default="add_component")
    component_hierarchy.add_argument("--component-name", default="")
    component_hierarchy.add_argument("--class-path", default="")
    component_hierarchy.add_argument("--parent-component", default="")
    component_hierarchy.add_argument("--property-name", default="")
    component_hierarchy.add_argument("--value-json", default="null")
    component_hierarchy.add_argument("--compile-after", action="store_true")
    component_hierarchy.add_argument("--dry-run", action="store_true")

    graph_ast_export = sub.add_parser("graph-ast-export")
    graph_ast_export.add_argument("--blueprint-path", required=True)
    graph_ast_export.add_argument("--graph-name", default="")
    graph_ast_export.add_argument("--include-pins", action="store_true")
    graph_ast_export.add_argument("--max-nodes", type=int, default=2000)

    graph_ast_apply = sub.add_parser("graph-ast-apply")
    graph_ast_apply.add_argument("--blueprint-path", required=True)
    graph_ast_apply.add_argument("--graph-name", default="EventGraph")
    graph_ast_apply.add_argument("--operations-json", required=True)
    graph_ast_apply.add_argument("--dry-run", action="store_true")
    graph_ast_apply.add_argument("--stop-on-error", action="store_true", default=True)
    graph_ast_apply.add_argument("--no-stop-on-error", action="store_true")

    signature_edit = sub.add_parser("signature-edit")
    signature_edit.add_argument("--blueprint-path", required=True)
    signature_edit.add_argument("--graph-name", default="EventGraph")
    signature_edit.add_argument("--operation", required=True)
    signature_edit.add_argument("--name", default="")
    signature_edit.add_argument("--type", default="bool")
    signature_edit.add_argument("--default-value", default="")
    signature_edit.add_argument("--category", default="AgentGenerated")
    signature_edit.add_argument("--function-name", default="")
    signature_edit.add_argument("--macro-name", default="")
    signature_edit.add_argument("--dry-run", action="store_true")
    signature_edit.add_argument("--stop-on-error", action="store_true", default=True)
    signature_edit.add_argument("--no-stop-on-error", action="store_true")

    actor_transform_control = sub.add_parser("actor-transform-control")
    actor_transform_control.add_argument("--actor", default="")
    actor_transform_control.add_argument("--actor-label", default="")
    actor_transform_control.add_argument("--operation", default="set_transform")
    actor_transform_control.add_argument("--location-json", default="[0,0,0]")
    actor_transform_control.add_argument("--rotation-json", default="[0,0,0]")
    actor_transform_control.add_argument("--scale-json", default="[1,1,1]")
    actor_transform_control.add_argument("--dry-run", action="store_true")

    system_bootstrap = sub.add_parser("system-bootstrap")
    system_bootstrap.add_argument("--system-type", required=True)
    system_bootstrap.add_argument("--asset-name", required=True)
    system_bootstrap.add_argument("--package-path", required=True)
    system_bootstrap.add_argument("--dry-run", action="store_true")

    agent_bootstrap = sub.add_parser("agent-bootstrap")
    agent_bootstrap.add_argument("--client-name", default="ide_unreal_agent_cli")
    agent_bootstrap.add_argument("--client-version", default="0.1.0")
    agent_bootstrap.add_argument("--session-label", default="")

    sub.add_parser("control-surface-catalog")
    sub.add_parser("agent-readiness")

    graph_pin_wire = sub.add_parser("graph-pin-wire")
    graph_pin_wire.add_argument("--blueprint-path", required=True)
    graph_pin_wire.add_argument("--graph-name", default="")
    graph_pin_wire.add_argument("--operation", default="connect")
    graph_pin_wire.add_argument("--from-node-name", default="")
    graph_pin_wire.add_argument("--from-node-title-contains", default="")
    graph_pin_wire.add_argument("--from-pin-name", required=True)
    graph_pin_wire.add_argument("--to-node-name", default="")
    graph_pin_wire.add_argument("--to-node-title-contains", default="")
    graph_pin_wire.add_argument("--to-pin-name", required=True)
    graph_pin_wire.add_argument("--compile-after", action="store_true")
    graph_pin_wire.add_argument("--dry-run", action="store_true")

    node_author = sub.add_parser("node-author")
    node_author.add_argument("--blueprint-path", required=True)
    node_author.add_argument("--graph-name", default="")
    node_author.add_argument("--operation", default="spawn_function_call")
    node_author.add_argument("--node-name", default="")
    node_author.add_argument("--target-node-name", default="")
    node_author.add_argument("--target-node-title-contains", default="")
    node_author.add_argument("--function-class-path", required=True)
    node_author.add_argument("--function-name", required=True)
    node_author.add_argument("--node-position-json", default="[0,0]")
    node_author.add_argument("--compile-after", action="store_true")
    node_author.add_argument("--dry-run", action="store_true")

    compile_diagnostics = sub.add_parser("compile-diagnostics")
    compile_diagnostics.add_argument("--blueprint-path", required=True)
    compile_diagnostics.add_argument("--graph-name", default="")
    compile_diagnostics.add_argument("--include-pins", action="store_true")
    compile_diagnostics.add_argument("--max-nodes", type=int, default=500)
    compile_diagnostics.add_argument("--dry-run", action="store_true")

    compile_gate_run = sub.add_parser("compile-gate-run")
    compile_gate_run.add_argument("--blueprint-paths-json", required=True)
    compile_gate_run.add_argument("--include-pins", action="store_true")
    compile_gate_run.add_argument("--max-nodes", type=int, default=800)
    compile_gate_run.add_argument("--dry-run", action="store_true")

    sub.add_parser("node-pattern-catalog")

    node_pattern_preview = sub.add_parser("node-pattern-preview")
    node_pattern_preview.add_argument("--pattern-id", required=True)
    node_pattern_preview.add_argument("--blueprint-path", required=True)
    node_pattern_preview.add_argument("--graph-name", default="EventGraph")
    node_pattern_preview.add_argument("--message", default="Pattern Preview")
    node_pattern_preview.add_argument("--duration", type=float, default=0.25)
    node_pattern_preview.add_argument("--base-node-name", default="AgentPattern")

    node_pattern_apply = sub.add_parser("node-pattern-apply")
    node_pattern_apply.add_argument("--pattern-id", required=True)
    node_pattern_apply.add_argument("--blueprint-path", required=True)
    node_pattern_apply.add_argument("--graph-name", default="EventGraph")
    node_pattern_apply.add_argument("--message", default="Pattern Apply")
    node_pattern_apply.add_argument("--duration", type=float, default=0.25)
    node_pattern_apply.add_argument("--base-node-name", default="AgentPattern")
    node_pattern_apply.add_argument("--dry-run", action="store_true")

    graph_snapshots = sub.add_parser("graph-snapshots")

    replay_suite = sub.add_parser("replay-suite")
    replay_suite.add_argument("--cases-json", required=True)
    replay_suite.add_argument("--repeats", type=int, default=2)

    release_gate = sub.add_parser("release-gate-evaluate")
    release_gate.add_argument("--blueprint-paths-json", required=True)
    release_gate.add_argument("--replay-cases-json", default="[]")
    release_gate.add_argument("--replay-repeats", type=int, default=2)
    release_gate.add_argument("--multiplayer-json", default="{}")

    workflow_generate = sub.add_parser("workflow-generate")
    workflow_generate.add_argument("--workflow-id", required=True)
    workflow_generate.add_argument("--inputs-json", default="{}")
    workflow_generate.add_argument("--dry-run", action="store_true")
    workflow_generate.add_argument("--stop-on-error", action="store_true", default=True)
    workflow_generate.add_argument("--no-stop-on-error", action="store_true")

    sub.add_parser("graph-primitives-catalog")

    graph_primitives_apply = sub.add_parser("graph-primitives-apply")
    graph_primitives_apply.add_argument("--blueprint-path", required=True)
    graph_primitives_apply.add_argument("--graph-name", default="EventGraph")
    graph_primitives_apply.add_argument("--operations-json", required=True)
    graph_primitives_apply.add_argument("--dry-run", action="store_true")
    graph_primitives_apply.add_argument("--stop-on-error", action="store_true", default=True)
    graph_primitives_apply.add_argument("--no-stop-on-error", action="store_true")

    runtime_validate_repair = sub.add_parser("runtime-validate-repair")
    runtime_validate_repair.add_argument("--blueprint-path", required=True)
    runtime_validate_repair.add_argument("--assertions-json", default="[]")
    runtime_validate_repair.add_argument("--auto-repair", action="store_true", default=True)
    runtime_validate_repair.add_argument("--no-auto-repair", action="store_true")
    runtime_validate_repair.add_argument("--max-repair-attempts", type=int, default=1)
    runtime_validate_repair.add_argument("--capture-screenshot-on-fail", action="store_true", default=True)
    runtime_validate_repair.add_argument("--no-capture-screenshot-on-fail", action="store_true")

    autonomous_loop_run = sub.add_parser("autonomous-loop-run")
    autonomous_loop_run.add_argument("--blueprint-path", required=True)
    autonomous_loop_run.add_argument("--graph-name", default="EventGraph")
    autonomous_loop_run.add_argument("--assertions-json", default="[]")
    autonomous_loop_run.add_argument("--scenario-repeats", type=int, default=2)
    autonomous_loop_run.add_argument("--auto-repair", action="store_true", default=True)
    autonomous_loop_run.add_argument("--no-auto-repair", action="store_true")
    autonomous_loop_run.add_argument("--max-repair-attempts", type=int, default=1)
    autonomous_loop_run.add_argument("--capture-screenshot-on-fail", action="store_true", default=True)
    autonomous_loop_run.add_argument("--no-capture-screenshot-on-fail", action="store_true")
    autonomous_loop_run.add_argument("--enable-multiplayer", action="store_true")
    autonomous_loop_run.add_argument("--multiplayer-assertions-json", default="[]")
    autonomous_loop_run.add_argument("--multiplayer-client-count", type=int, default=2)
    autonomous_loop_run.add_argument("--multiplayer-repeats", type=int, default=2)
    autonomous_loop_run.add_argument("--include-lint-gate", action="store_true", default=True)
    autonomous_loop_run.add_argument("--no-include-lint-gate", action="store_true")
    autonomous_loop_run.add_argument("--include-perf-gate", action="store_true", default=True)
    autonomous_loop_run.add_argument("--no-include-perf-gate", action="store_true")
    autonomous_loop_run.add_argument("--max-rpc-risk-score", type=float, default=40.0)
    autonomous_loop_run.add_argument("--max-multiplayer-lint-risk-score", type=float, default=40.0)
    autonomous_loop_run.add_argument("--max-perf-risk-score", type=float, default=35.0)
    autonomous_loop_run.add_argument("--rollback-on-failure", action="store_true", default=True)
    autonomous_loop_run.add_argument("--no-rollback-on-failure", action="store_true")
    autonomous_loop_run.add_argument("--rollback-accept-as-success", action="store_true", default=True)
    autonomous_loop_run.add_argument("--no-rollback-accept-as-success", action="store_true")
    autonomous_loop_run.add_argument("--rollback-token", default="")

    sub.add_parser("animation-autonomy-catalog")

    animation_autonomy_generate = sub.add_parser("animation-autonomy-generate")
    animation_autonomy_generate.add_argument("--template-id", required=True)
    animation_autonomy_generate.add_argument("--inputs-json", default="{}")
    animation_autonomy_generate.add_argument("--dry-run", action="store_true")
    animation_autonomy_generate.add_argument("--stop-on-error", action="store_true", default=True)
    animation_autonomy_generate.add_argument("--no-stop-on-error", action="store_true")

    sub.add_parser("ai-autonomy-catalog")

    ai_autonomy_generate = sub.add_parser("ai-autonomy-generate")
    ai_autonomy_generate.add_argument("--template-id", required=True)
    ai_autonomy_generate.add_argument("--inputs-json", default="{}")
    ai_autonomy_generate.add_argument("--dry-run", action="store_true")
    ai_autonomy_generate.add_argument("--stop-on-error", action="store_true", default=True)
    ai_autonomy_generate.add_argument("--no-stop-on-error", action="store_true")

    blackboard_schema_evolve = sub.add_parser("blackboard-schema-evolve")
    blackboard_schema_evolve.add_argument("--blueprint-path", required=True)
    blackboard_schema_evolve.add_argument("--graph-name", default="EventGraph")
    blackboard_schema_evolve.add_argument("--schema-json", default="[]")
    blackboard_schema_evolve.add_argument("--remove-keys-json", default="[]")
    blackboard_schema_evolve.add_argument("--rename-keys-json", default="[]")
    blackboard_schema_evolve.add_argument("--dry-run", action="store_true")
    blackboard_schema_evolve.add_argument("--stop-on-error", action="store_true", default=True)
    blackboard_schema_evolve.add_argument("--no-stop-on-error", action="store_true")

    ai_behavior_validate = sub.add_parser("ai-behavior-validate")
    ai_behavior_validate.add_argument("--blueprint-path", required=True)
    ai_behavior_validate.add_argument("--graph-name", default="EventGraph")
    ai_behavior_validate.add_argument("--assertions-json", default="[]")

    sub.add_parser("content-pipeline-catalog")

    content_pipeline_apply = sub.add_parser("content-pipeline-apply")
    content_pipeline_apply.add_argument("--preset-id", required=True)
    content_pipeline_apply.add_argument("--inputs-json", default="{}")
    content_pipeline_apply.add_argument("--asset-paths-json", default="[]")
    content_pipeline_apply.add_argument("--dependency-depth", type=int, default=2)
    content_pipeline_apply.add_argument("--dry-run", action="store_true")

    content_schema_enforce = sub.add_parser("content-schema-enforce")
    content_schema_enforce.add_argument("--package-path", default="/Game")
    content_schema_enforce.add_argument("--recursive", action="store_true", default=True)
    content_schema_enforce.add_argument("--max-assets", type=int, default=500)
    content_schema_enforce.add_argument("--naming-pattern", default=r"^(BP_|WBP_|ABP_|BTT_|BTD_|DA_|SM_|M_|MI_).+")
    content_schema_enforce.add_argument("--allowed-roots-json", default='["/Game"]')
    content_schema_enforce.add_argument("--expected-prefix", default="")

    dependency_safety_check = sub.add_parser("dependency-safety-check")
    dependency_safety_check.add_argument("--asset-paths-json", required=True)
    dependency_safety_check.add_argument("--depth", type=int, default=2)

    sub.add_parser("multiplayer-correctness-catalog")

    multiplayer_lint = sub.add_parser("multiplayer-lint")
    multiplayer_lint.add_argument("--blueprint-path", required=True)
    multiplayer_lint.add_argument("--graph-name", default="")

    multiplayer_guard_apply = sub.add_parser("multiplayer-guard-apply")
    multiplayer_guard_apply.add_argument("--blueprint-path", required=True)
    multiplayer_guard_apply.add_argument("--dry-run", action="store_true")
    multiplayer_guard_apply.add_argument("--stop-on-error", action="store_true", default=True)
    multiplayer_guard_apply.add_argument("--no-stop-on-error", action="store_true")

    multiplayer_pie_test = sub.add_parser("multiplayer-pie-test")
    multiplayer_pie_test.add_argument("--assertions-json", default="[]")
    multiplayer_pie_test.add_argument("--client-count", type=int, default=2)
    multiplayer_pie_test.add_argument("--repeats", type=int, default=2)

    blueprint_structure_review = sub.add_parser("blueprint-structure-review")
    blueprint_structure_review.add_argument("--blueprint-path", required=True)
    blueprint_structure_review.add_argument("--graph-name", default="EventGraph")
    blueprint_structure_review.add_argument("--review-scope", choices=["graph", "asset"], default="graph")
    blueprint_structure_review.add_argument("--include-all-graphs", action="store_true")
    blueprint_structure_review.add_argument("--include-ast", action="store_true", default=True)
    blueprint_structure_review.add_argument("--no-include-ast", action="store_true")
    blueprint_structure_review.add_argument("--include-refactor-catalog", action="store_true", default=True)
    blueprint_structure_review.add_argument("--no-include-refactor-catalog", action="store_true")
    blueprint_structure_review.add_argument("--max-graph-ast-exports", type=int, default=12)

    rpc_contract_lint = sub.add_parser("rpc-contract-lint")
    rpc_contract_lint.add_argument("--blueprint-path", required=True)
    rpc_contract_lint.add_argument("--graph-name", default="EventGraph")

    ai_asset_authoring = sub.add_parser("ai-asset-authoring")
    ai_asset_authoring.add_argument("--inputs-json", default="{}")
    ai_asset_authoring.add_argument("--dry-run", action="store_true")
    ai_asset_authoring.add_argument("--stop-on-error", action="store_true", default=True)
    ai_asset_authoring.add_argument("--no-stop-on-error", action="store_true")

    sub.add_parser("material-mesh-presets-catalog")

    material_mesh_setup = sub.add_parser("material-mesh-setup")
    material_mesh_setup.add_argument("--preset-id", default="static_mesh_actor_basic")
    material_mesh_setup.add_argument("--asset-name", default="BP_AgentMeshActor")
    material_mesh_setup.add_argument("--package-path", default="/Game/AgentGenerated/Props")
    material_mesh_setup.add_argument("--blueprint-path", default="")
    material_mesh_setup.add_argument("--static-mesh-path", required=True)
    material_mesh_setup.add_argument("--material-path", default="")
    material_mesh_setup.add_argument("--dry-run", action="store_true")

    sub.add_parser("native-asset-authoring-catalog")

    native_asset_create = sub.add_parser("native-asset-create")
    native_asset_create.add_argument("--asset-type", required=True)
    native_asset_create.add_argument("--inputs-json", default="{}")
    native_asset_create.add_argument("--dry-run", action="store_true")

    native_asset_edit = sub.add_parser("native-asset-edit")
    native_asset_edit.add_argument("--asset-type", required=True)
    native_asset_edit.add_argument("--inputs-json", default="{}")
    native_asset_edit.add_argument("--dry-run", action="store_true")

    native_asset_workflow = sub.add_parser("native-asset-authoring-workflow")
    native_asset_workflow.add_argument("--asset-type", required=True)
    native_asset_workflow.add_argument("--inputs-json", default="{}")
    native_asset_workflow.add_argument("--dry-run", action="store_true")
    native_asset_workflow.add_argument("--stop-on-error", action="store_true", default=True)
    native_asset_workflow.add_argument("--no-stop-on-error", action="store_true")

    pie_replay_suite = sub.add_parser("pie-replay-suite")
    pie_replay_suite.add_argument("--assertions-json", default="[]")
    pie_replay_suite.add_argument("--include-multiplayer", action="store_true", default=True)
    pie_replay_suite.add_argument("--no-include-multiplayer", action="store_true")
    pie_replay_suite.add_argument("--client-count", type=int, default=2)
    pie_replay_suite.add_argument("--repeats", type=int, default=2)

    rollback_apply = sub.add_parser("rollback-apply")
    rollback_apply.add_argument("--rollback-token", required=True)
    rollback_apply.add_argument("--dry-run", action="store_true")
    rollback_apply.add_argument("--stop-on-error", action="store_true", default=True)
    rollback_apply.add_argument("--no-stop-on-error", action="store_true")

    paid_logs = sub.add_parser("get-paid-session-logs")
    paid_logs.add_argument("--paid-token", required=True)
    paid_logs.add_argument("--session-id", required=True)
    paid_logs.add_argument("--since", type=float, default=0.0)
    paid_logs.add_argument("--limit", type=int, default=200)

    direct = sub.add_parser("direct-execute")
    direct.add_argument("--action", required=True)
    direct.add_argument("--payload-json", default="{}")
    direct.add_argument("--dry-run", action="store_true")
    direct.add_argument("--approval-token", default="")

    args = parser.parse_args()
    base = f"http://{args.host}:{args.port}"

    bootstrap_exempt_commands = {
        "health",
        "info",
        "state",
        "actions",
        "recipes",
        "release-metrics",
        "claims-evidence",
        "execution-runs",
        "execution-run-detail",
        "execution-artifact",
        "approvals",
        "approve",
        "paid-session-logs",
        "get-paid-session-logs",
        "start-paid-session",
        "end-paid-session",
        "admin-session-diagnostics",
        "admin-usage-events",
        "control-surface-catalog",
        "agent-readiness",
        "agent-bootstrap",
    }
    if AUTO_BOOTSTRAP and args.cmd not in bootstrap_exempt_commands:
        bootstrap_result = bootstrap_agent_session(base, args.cmd)
        if not bool(bootstrap_result.get("success", False)):
            if args.pretty:
                print(json.dumps(bootstrap_result, indent=2))
            else:
                print(json.dumps(bootstrap_result))
            return 1

    if args.cmd == "health":
        result = request_json("GET", f"{base}/api/health")
    elif args.cmd == "actions":
        result = request_json("GET", f"{base}/api/actions")
    elif args.cmd == "recipes":
        result = request_json("GET", f"{base}/api/recipes")
    elif args.cmd == "release-metrics":
        result = request_json("GET", f"{base}/api/release-metrics")
    elif args.cmd == "claims-evidence":
        result = request_json("GET", f"{base}/api/claims-evidence")
    elif args.cmd == "workflow-catalog":
        result = request_json("GET", f"{base}/api/workflow-catalog")
    elif args.cmd == "node-control-capabilities":
        result = request_json("GET", f"{base}/api/node-control-capabilities")
    elif args.cmd == "execution-runs":
        result = request_json("GET", f"{base}/api/execution-runs")
    elif args.cmd == "execution-run-detail":
        rid = urllib.parse.quote(str(args.run_id))
        result = request_json("GET", f"{base}/api/execution-run-detail?run_id={rid}")
    elif args.cmd == "execution-artifact":
        rid = urllib.parse.quote(str(args.run_id))
        include_snapshot = False if args.no_include_snapshot else bool(args.include_snapshot)
        include_full = bool(args.include_full)
        result = request_json(
            "GET",
            f"{base}/api/execution-artifact?run_id={rid}&include_snapshot={'1' if include_snapshot else '0'}&include_full={'1' if include_full else '0'}",
        )
    elif args.cmd == "paid-session-logs":
        result = request_json("GET", f"{base}/api/paid/session/logs")
    elif args.cmd == "info":
        result = request_json("GET", f"{base}/api/info")
    elif args.cmd == "state":
        result = request_json("GET", f"{base}/api/state")
    elif args.cmd == "approvals":
        result = request_json("GET", f"{base}/api/approvals")
    elif args.cmd == "admin-session-diagnostics":
        token = getattr(args, "paid_token", "") or ""
        url = f"{base}/api/admin/session-diagnostics"
        if token:
            url += f"?paid_token={urllib.parse.quote(token)}"
        result = request_json("GET", url)
    elif args.cmd == "admin-usage-events":
        token = str(args.paid_token or "").strip()
        url = f"{base}/api/admin/usage-events?limit={int(args.limit)}"
        if token:
            url += f"&paid_token={urllib.parse.quote(token)}"
        result = request_json("GET", url)
    elif args.cmd == "approve":
        result = request_json("POST", f"{base}/api/approve", {"approval_token": args.approval_token})
    elif args.cmd == "start-paid-session":
        result = request_json(
            "POST",
            f"{base}/api/paid/session/start",
            {
                "paid_token": args.paid_token,
                "user_id": args.user_id,
                "project_label": args.project_label,
            },
        )
    elif args.cmd == "end-paid-session":
        result = request_json(
            "POST",
            f"{base}/api/paid/session/end",
            {
                "paid_token": args.paid_token,
                "session_id": args.session_id,
            },
        )
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
                "profile": args.profile,
                "goal_context": goal_context,
                "approval_token": args.approval_token,
                "session_id": args.session_id,
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
                "session_id": args.session_id,
            },
        )
    elif args.cmd == "run-plan":
        plan = parse_json_arg(args.plan_json, "plan-json")
        result = request_json(
            "POST",
            f"{base}/api/run-plan",
            {"plan": plan, "approval_token": args.approval_token, "session_id": args.session_id},
        )
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
                "session_id": args.session_id,
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
                "paid_token": args.paid_token,
            },
        )
    elif args.cmd == "validate-execution":
        try:
            compile_blueprints = json.loads(args.compile_blueprints_json)
            if not isinstance(compile_blueprints, list):
                raise ValueError("compile-blueprints-json must be a JSON array")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid compile-blueprints-json: {exc}") from exc
        try:
            assertions = json.loads(args.assertions_json)
            if not isinstance(assertions, list):
                raise ValueError("assertions-json must be a JSON array")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid assertions-json: {exc}") from exc
        result = request_json(
            "POST",
            f"{base}/api/validate-execution",
            {
                "compile_blueprints": compile_blueprints,
                "assertions": assertions,
                "profile": args.profile,
                "release_validation": bool(args.release_validation),
                "paid_token": args.paid_token,
            },
        )
    elif args.cmd == "project-audit":
        try:
            class_paths = json.loads(args.class_paths_json)
            if not isinstance(class_paths, list):
                raise ValueError("class-paths-json must be a JSON array")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid class-paths-json: {exc}") from exc
        result = request_json(
            "POST",
            f"{base}/api/project-audit",
            {
                "package_path": args.package_path,
                "recursive": bool(args.recursive),
                "class_paths": class_paths,
                "name_contains": args.name_contains,
                "max_assets": int(args.max_assets),
                "analyze_blueprints": bool(args.analyze_blueprints),
                "compile_blueprints": bool(args.compile_blueprints),
                "profile": args.profile,
                "release_validation": bool(args.release_validation),
            },
        )
    elif args.cmd == "refactor-suggest":
        payload: Dict[str, Any] = {
            "blueprint_path": args.blueprint_path,
            "mode": args.mode,
            "profile": args.profile,
            "include_pins": bool(args.include_pins),
            "max_nodes": int(args.max_nodes),
            "max_trace_depth": int(args.max_trace_depth),
        }
        if str(args.graph_name).strip():
            payload["graph_name"] = str(args.graph_name).strip()
        result = request_json("POST", f"{base}/api/refactor-suggest", payload)
    elif args.cmd == "refactor-catalog":
        payload = {
            "blueprint_path": args.blueprint_path,
            "mode": args.mode,
            "profile": args.profile,
            "include_pins": bool(args.include_pins),
            "max_nodes": int(args.max_nodes),
            "max_trace_depth": int(args.max_trace_depth),
        }
        if str(args.graph_name).strip():
            payload["graph_name"] = str(args.graph_name).strip()
        result = request_json("POST", f"{base}/api/refactor-catalog", payload)
    elif args.cmd == "refactor-preview":
        try:
            transform_ids = json.loads(args.transform_ids_json)
            if not isinstance(transform_ids, list):
                raise ValueError("transform-ids-json must be a JSON array")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid transform-ids-json: {exc}") from exc
        transform_inputs = parse_json_arg(args.transform_inputs_json, "transform-inputs-json")
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        payload = {
            "blueprint_path": args.blueprint_path,
            "mode": args.mode,
            "profile": args.profile,
            "include_pins": bool(args.include_pins),
            "max_nodes": int(args.max_nodes),
            "max_trace_depth": int(args.max_trace_depth),
            "transform_ids": transform_ids,
            "transform_inputs": transform_inputs,
            "stop_on_error": stop_on_error,
        }
        if str(args.graph_name).strip():
            payload["graph_name"] = str(args.graph_name).strip()
        result = request_json("POST", f"{base}/api/refactor-preview", payload)
    elif args.cmd == "refactor-apply":
        try:
            suggestion_ids = json.loads(args.suggestion_ids_json)
            if not isinstance(suggestion_ids, list):
                raise ValueError("suggestion-ids-json must be a JSON array")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid suggestion-ids-json: {exc}") from exc
        try:
            transform_ids = json.loads(args.transform_ids_json)
            if not isinstance(transform_ids, list):
                raise ValueError("transform-ids-json must be a JSON array")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid transform-ids-json: {exc}") from exc
        transform_inputs = parse_json_arg(args.transform_inputs_json, "transform-inputs-json")
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        payload = {
            "blueprint_path": args.blueprint_path,
            "mode": args.mode,
            "include_pins": bool(args.include_pins),
            "max_nodes": int(args.max_nodes),
            "max_trace_depth": int(args.max_trace_depth),
            "suggestion_ids": suggestion_ids,
            "transform_ids": transform_ids,
            "transform_inputs": transform_inputs,
            "dry_run": bool(args.dry_run),
            "stop_on_error": stop_on_error,
            "approval_token": args.approval_token,
            "profile": args.profile,
            "release_validation": bool(args.release_validation),
        }
        if str(args.graph_name).strip():
            payload["graph_name"] = str(args.graph_name).strip()
        result = request_json("POST", f"{base}/api/refactor-apply", payload)
    elif args.cmd == "explain-selection":
        try:
            node_names = json.loads(args.node_names_json)
            if not isinstance(node_names, list):
                raise ValueError("node-names-json must be a JSON array")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid node-names-json: {exc}") from exc
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
            "node_names": node_names,
            "mode": args.mode,
            "include_pins": bool(args.include_pins),
            "max_nodes": int(args.max_nodes),
            "max_trace_depth": int(args.max_trace_depth),
        }
        result = request_json("POST", f"{base}/api/explain-selection", payload)
    elif args.cmd == "explain-screenshot":
        payload = {
            "image_path": args.image_path,
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
        }
        result = request_json("POST", f"{base}/api/explain-screenshot", payload)
    elif args.cmd == "project-dependencies":
        payload = {
            "package_path": args.package_path,
            "recursive": bool(args.recursive),
            "depth": int(args.depth),
            "max_assets": int(args.max_assets),
        }
        result = request_json("POST", f"{base}/api/project-dependencies", payload)
    elif args.cmd == "perf-hotspots":
        payload = {
            "package_path": args.package_path,
            "recursive": bool(args.recursive),
            "analyze_blueprints": bool(args.analyze_blueprints),
            "max_assets": int(args.max_assets),
        }
        result = request_json("POST", f"{base}/api/perf-hotspots", payload)
    elif args.cmd == "impact-analysis":
        try:
            asset_paths = json.loads(args.asset_paths_json)
            if not isinstance(asset_paths, list):
                raise ValueError("asset-paths-json must be a JSON array")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid asset-paths-json: {exc}") from exc
        payload = {
            "asset_paths": asset_paths,
            "change_type": args.change_type,
        }
        result = request_json("POST", f"{base}/api/impact-analysis", payload)
    elif args.cmd == "umg-generate":
        try:
            bindings = json.loads(args.bindings_json)
            if not isinstance(bindings, list):
                raise ValueError("bindings-json must be a JSON array")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid bindings-json: {exc}") from exc
        payload = {
            "widget_blueprint": args.widget_blueprint,
            "asset_name": args.asset_name,
            "package_path": args.package_path,
            "template_id": args.template_id,
            "style_preset": args.style_preset,
            "bindings": bindings,
        }
        result = request_json("POST", f"{base}/api/umg-generate", payload)
    elif args.cmd == "world-generate":
        try:
            bounds = json.loads(args.bounds_json)
            if not isinstance(bounds, list):
                raise ValueError("bounds-json must be a JSON array")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid bounds-json: {exc}") from exc
        constraints = parse_json_arg(args.constraints_json, "constraints-json")
        payload = {
            "layout_id": args.layout_id,
            "bounds": bounds,
            "density": float(args.density),
            "seed": int(args.seed),
            "constraints": constraints,
        }
        result = request_json("POST", f"{base}/api/world-generate", payload)
    elif args.cmd == "entitlements-check":
        payload = {"paid_token": args.paid_token, "feature": args.feature}
        result = request_json("POST", f"{base}/api/entitlements/check", payload)
    elif args.cmd == "usage-event":
        metadata = parse_json_arg(args.metadata_json, "metadata-json")
        payload = {
            "paid_token": args.paid_token,
            "event_type": args.event_type,
            "amount": float(args.amount),
            "metadata": metadata,
        }
        result = request_json("POST", f"{base}/api/usage/event", payload)
    elif args.cmd == "property-reflect":
        value = parse_json_value(args.value_json, "value-json")
        payload = {
            "target_type": args.target_type,
            "blueprint_path": args.blueprint_path,
            "component_name": args.component_name,
            "actor": args.actor,
            "property_name": args.property_name,
            "value": value,
            "compile_after": bool(args.compile_after),
            "dry_run": bool(args.dry_run),
        }
        result = request_json("POST", f"{base}/api/property-reflect", payload)
    elif args.cmd == "blueprint-function-author":
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_kind": args.graph_kind,
            "graph_name": args.graph_name,
            "category": args.category,
            "compile_after": bool(args.compile_after),
            "dry_run": bool(args.dry_run),
        }
        result = request_json("POST", f"{base}/api/blueprint-function-author", payload)
    elif args.cmd == "component-hierarchy":
        value = parse_json_value(args.value_json, "value-json")
        payload = {
            "blueprint_path": args.blueprint_path,
            "operation": args.operation,
            "component_name": args.component_name,
            "class_path": args.class_path,
            "parent_component": args.parent_component,
            "property_name": args.property_name,
            "value": value,
            "compile_after": bool(args.compile_after),
            "dry_run": bool(args.dry_run),
        }
        result = request_json("POST", f"{base}/api/component-hierarchy", payload)
    elif args.cmd == "graph-ast-export":
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
            "include_pins": bool(args.include_pins),
            "max_nodes": int(args.max_nodes),
        }
        result = request_json("POST", f"{base}/api/graph-ast-export", payload)
    elif args.cmd == "graph-ast-apply":
        operations = parse_json_value(args.operations_json, "operations-json")
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
            "operations": operations,
            "dry_run": bool(args.dry_run),
            "stop_on_error": stop_on_error,
        }
        result = request_json("POST", f"{base}/api/graph-ast-apply", payload)
    elif args.cmd == "signature-edit":
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
            "operation": args.operation,
            "name": args.name,
            "type": args.type,
            "default_value": args.default_value,
            "category": args.category,
            "function_name": args.function_name,
            "macro_name": args.macro_name,
            "dry_run": bool(args.dry_run),
            "stop_on_error": stop_on_error,
        }
        result = request_json("POST", f"{base}/api/signature-edit", payload)
    elif args.cmd == "actor-transform-control":
        location = parse_json_value(args.location_json, "location-json")
        rotation = parse_json_value(args.rotation_json, "rotation-json")
        scale = parse_json_value(args.scale_json, "scale-json")
        payload = {
            "actor": args.actor,
            "actor_label": args.actor_label,
            "operation": args.operation,
            "location": location,
            "rotation": rotation,
            "scale": scale,
            "dry_run": bool(args.dry_run),
        }
        result = request_json("POST", f"{base}/api/actor-transform-control", payload)
    elif args.cmd == "system-bootstrap":
        payload = {
            "system_type": args.system_type,
            "asset_name": args.asset_name,
            "package_path": args.package_path,
            "dry_run": bool(args.dry_run),
        }
        result = request_json("POST", f"{base}/api/system-bootstrap", payload)
    elif args.cmd == "agent-bootstrap":
        payload = {
            "client_name": args.client_name,
            "client_version": args.client_version,
            "session_label": args.session_label or "manual_bootstrap",
        }
        result = request_json("POST", f"{base}/api/agent-bootstrap", payload)
        if bool(result.get("success", False)):
            token = str(result.get("bootstrap_token", "")).strip()
            if token:
                REQUEST_EXTRA_HEADERS["X-Agent-Bootstrap-Token"] = token
    elif args.cmd == "control-surface-catalog":
        result = request_json("GET", f"{base}/api/control-surface-catalog")
    elif args.cmd == "agent-readiness":
        result = request_json("GET", f"{base}/api/agent-readiness")
    elif args.cmd == "graph-pin-wire":
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
            "operation": args.operation,
            "from_node_name": args.from_node_name,
            "from_node_title_contains": args.from_node_title_contains,
            "from_pin_name": args.from_pin_name,
            "to_node_name": args.to_node_name,
            "to_node_title_contains": args.to_node_title_contains,
            "to_pin_name": args.to_pin_name,
            "compile_after": bool(args.compile_after),
            "dry_run": bool(args.dry_run),
        }
        result = request_json("POST", f"{base}/api/graph-pin-wire", payload)
    elif args.cmd == "node-author":
        node_position = parse_json_value(args.node_position_json, "node-position-json")
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
            "operation": args.operation,
            "node_name": args.node_name,
            "target_node_name": args.target_node_name,
            "target_node_title_contains": args.target_node_title_contains,
            "function_class_path": args.function_class_path,
            "function_name": args.function_name,
            "node_position": node_position,
            "compile_after": bool(args.compile_after),
            "dry_run": bool(args.dry_run),
        }
        result = request_json("POST", f"{base}/api/node-author", payload)
    elif args.cmd == "compile-diagnostics":
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
            "include_pins": bool(args.include_pins),
            "max_nodes": int(args.max_nodes),
            "dry_run": bool(args.dry_run),
        }
        result = request_json("POST", f"{base}/api/compile-diagnostics", payload)
    elif args.cmd == "compile-gate-run":
        blueprint_paths = parse_json_value(args.blueprint_paths_json, "blueprint-paths-json")
        payload = {
            "blueprint_paths": blueprint_paths,
            "include_pins": bool(args.include_pins),
            "max_nodes": int(args.max_nodes),
            "dry_run": bool(args.dry_run),
        }
        result = request_json("POST", f"{base}/api/compile-gate-run", payload)
    elif args.cmd == "node-pattern-catalog":
        result = request_json("GET", f"{base}/api/node-pattern-catalog")
    elif args.cmd == "node-pattern-preview":
        payload = {
            "pattern_id": args.pattern_id,
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
            "message": args.message,
            "duration": float(args.duration),
            "base_node_name": args.base_node_name,
        }
        result = request_json("POST", f"{base}/api/node-pattern-preview", payload)
    elif args.cmd == "node-pattern-apply":
        payload = {
            "pattern_id": args.pattern_id,
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
            "message": args.message,
            "duration": float(args.duration),
            "base_node_name": args.base_node_name,
            "dry_run": bool(args.dry_run),
        }
        result = request_json("POST", f"{base}/api/node-pattern-apply", payload)
    elif args.cmd == "graph-snapshots":
        result = request_json("GET", f"{base}/api/graph-snapshots")
    elif args.cmd == "replay-suite":
        cases = parse_json_value(args.cases_json, "cases-json")
        payload = {
            "cases": cases,
            "repeats": int(args.repeats),
        }
        result = request_json("POST", f"{base}/api/replay-suite", payload)
    elif args.cmd == "release-gate-evaluate":
        blueprint_paths = parse_json_value(args.blueprint_paths_json, "blueprint-paths-json")
        replay_cases = parse_json_value(args.replay_cases_json, "replay-cases-json")
        multiplayer = parse_json_arg(args.multiplayer_json, "multiplayer-json")
        payload = {
            "blueprint_paths": blueprint_paths,
            "replay_cases": replay_cases,
            "replay_repeats": int(args.replay_repeats),
            "multiplayer": multiplayer,
        }
        result = request_json("POST", f"{base}/api/release-gate-evaluate", payload)
    elif args.cmd == "workflow-generate":
        inputs = parse_json_arg(args.inputs_json, "inputs-json")
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        payload = {
            "workflow_id": args.workflow_id,
            **inputs,
            "dry_run": bool(args.dry_run),
            "stop_on_error": stop_on_error,
        }
        result = request_json("POST", f"{base}/api/workflow-generate", payload)
    elif args.cmd == "graph-primitives-catalog":
        result = request_json("GET", f"{base}/api/graph-primitives-catalog")
    elif args.cmd == "graph-primitives-apply":
        operations = parse_json_value(args.operations_json, "operations-json")
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
            "operations": operations,
            "dry_run": bool(args.dry_run),
            "stop_on_error": stop_on_error,
        }
        result = request_json("POST", f"{base}/api/graph-primitives-apply", payload)
    elif args.cmd == "runtime-validate-repair":
        assertions = parse_json_value(args.assertions_json, "assertions-json")
        auto_repair = False if args.no_auto_repair else bool(args.auto_repair)
        capture_screenshot_on_fail = False if args.no_capture_screenshot_on_fail else bool(args.capture_screenshot_on_fail)
        payload = {
            "blueprint_path": args.blueprint_path,
            "assertions": assertions,
            "auto_repair": auto_repair,
            "max_repair_attempts": int(args.max_repair_attempts),
            "capture_screenshot_on_fail": capture_screenshot_on_fail,
        }
        result = request_json("POST", f"{base}/api/runtime-validate-repair", payload)
    elif args.cmd == "autonomous-loop-run":
        assertions = parse_json_value(args.assertions_json, "assertions-json")
        mp_assertions = parse_json_value(args.multiplayer_assertions_json, "multiplayer-assertions-json")
        auto_repair = False if args.no_auto_repair else bool(args.auto_repair)
        capture_screenshot_on_fail = False if args.no_capture_screenshot_on_fail else bool(args.capture_screenshot_on_fail)
        include_lint_gate = False if args.no_include_lint_gate else bool(args.include_lint_gate)
        include_perf_gate = False if args.no_include_perf_gate else bool(args.include_perf_gate)
        rollback_on_failure = False if args.no_rollback_on_failure else bool(args.rollback_on_failure)
        rollback_accept_as_success = False if args.no_rollback_accept_as_success else bool(args.rollback_accept_as_success)
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
            "assertions": assertions,
            "scenario_repeats": int(args.scenario_repeats),
            "auto_repair": auto_repair,
            "max_repair_attempts": int(args.max_repair_attempts),
            "capture_screenshot_on_fail": capture_screenshot_on_fail,
            "enable_multiplayer": bool(args.enable_multiplayer),
            "multiplayer": {
                "enabled": bool(args.enable_multiplayer),
                "assertions": mp_assertions,
                "client_count": int(args.multiplayer_client_count),
                "repeats": int(args.multiplayer_repeats),
            },
            "include_lint_gate": include_lint_gate,
            "include_perf_gate": include_perf_gate,
            "max_rpc_risk_score": float(args.max_rpc_risk_score),
            "max_multiplayer_lint_risk_score": float(args.max_multiplayer_lint_risk_score),
            "max_perf_risk_score": float(args.max_perf_risk_score),
            "rollback_on_failure": rollback_on_failure,
            "rollback_accept_as_success": rollback_accept_as_success,
            "rollback_token": args.rollback_token,
        }
        result = request_json("POST", f"{base}/api/autonomous-loop-run", payload)
    elif args.cmd == "animation-autonomy-catalog":
        result = request_json("GET", f"{base}/api/animation-autonomy-catalog")
    elif args.cmd == "animation-autonomy-generate":
        inputs = parse_json_arg(args.inputs_json, "inputs-json")
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        payload = {
            "template_id": args.template_id,
            **inputs,
            "dry_run": bool(args.dry_run),
            "stop_on_error": stop_on_error,
        }
        result = request_json("POST", f"{base}/api/animation-autonomy-generate", payload)
    elif args.cmd == "ai-autonomy-catalog":
        result = request_json("GET", f"{base}/api/ai-autonomy-catalog")
    elif args.cmd == "ai-autonomy-generate":
        inputs = parse_json_arg(args.inputs_json, "inputs-json")
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        payload = {
            "template_id": args.template_id,
            **inputs,
            "dry_run": bool(args.dry_run),
            "stop_on_error": stop_on_error,
        }
        result = request_json("POST", f"{base}/api/ai-autonomy-generate", payload)
    elif args.cmd == "blackboard-schema-evolve":
        schema = parse_json_value(args.schema_json, "schema-json")
        remove_keys = parse_json_value(args.remove_keys_json, "remove-keys-json")
        rename_keys = parse_json_value(args.rename_keys_json, "rename-keys-json")
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
            "schema": schema,
            "remove_keys": remove_keys,
            "rename_keys": rename_keys,
            "dry_run": bool(args.dry_run),
            "stop_on_error": stop_on_error,
        }
        result = request_json("POST", f"{base}/api/blackboard-schema-evolve", payload)
    elif args.cmd == "ai-behavior-validate":
        assertions = parse_json_value(args.assertions_json, "assertions-json")
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
            "assertions": assertions,
        }
        result = request_json("POST", f"{base}/api/ai-behavior-validate", payload)
    elif args.cmd == "content-pipeline-catalog":
        result = request_json("GET", f"{base}/api/content-pipeline-catalog")
    elif args.cmd == "content-pipeline-apply":
        inputs = parse_json_arg(args.inputs_json, "inputs-json")
        asset_paths = parse_json_value(args.asset_paths_json, "asset-paths-json")
        payload = {
            "preset_id": args.preset_id,
            **inputs,
            "asset_paths": asset_paths,
            "dependency_depth": int(args.dependency_depth),
            "dry_run": bool(args.dry_run),
        }
        result = request_json("POST", f"{base}/api/content-pipeline-apply", payload)
    elif args.cmd == "content-schema-enforce":
        allowed_roots = parse_json_value(args.allowed_roots_json, "allowed-roots-json")
        payload = {
            "package_path": args.package_path,
            "recursive": bool(args.recursive),
            "max_assets": int(args.max_assets),
            "naming_pattern": args.naming_pattern,
            "allowed_roots": allowed_roots,
            "expected_prefix": args.expected_prefix,
        }
        result = request_json("POST", f"{base}/api/content-schema-enforce", payload)
    elif args.cmd == "dependency-safety-check":
        asset_paths = parse_json_value(args.asset_paths_json, "asset-paths-json")
        payload = {
            "asset_paths": asset_paths,
            "depth": int(args.depth),
        }
        result = request_json("POST", f"{base}/api/dependency-safety-check", payload)
    elif args.cmd == "multiplayer-correctness-catalog":
        result = request_json("GET", f"{base}/api/multiplayer-correctness-catalog")
    elif args.cmd == "multiplayer-lint":
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
        }
        result = request_json("POST", f"{base}/api/multiplayer-lint", payload)
    elif args.cmd == "multiplayer-guard-apply":
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        payload = {
            "blueprint_path": args.blueprint_path,
            "dry_run": bool(args.dry_run),
            "stop_on_error": stop_on_error,
        }
        result = request_json("POST", f"{base}/api/multiplayer-guard-apply", payload)
    elif args.cmd == "multiplayer-pie-test":
        assertions = parse_json_value(args.assertions_json, "assertions-json")
        payload = {
            "assertions": assertions,
            "client_count": int(args.client_count),
            "repeats": int(args.repeats),
        }
        result = request_json("POST", f"{base}/api/multiplayer-pie-test", payload)
    elif args.cmd == "blueprint-structure-review":
        include_ast = False if args.no_include_ast else bool(args.include_ast)
        include_refactor_catalog = False if args.no_include_refactor_catalog else bool(args.include_refactor_catalog)
        review_scope = "asset" if args.include_all_graphs else args.review_scope
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
            "review_scope": review_scope,
            "include_all_graphs": bool(args.include_all_graphs),
            "include_ast": include_ast,
            "include_refactor_catalog": include_refactor_catalog,
            "max_graph_ast_exports": int(args.max_graph_ast_exports),
        }
        result = request_json("POST", f"{base}/api/blueprint-structure-review", payload)
    elif args.cmd == "rpc-contract-lint":
        payload = {
            "blueprint_path": args.blueprint_path,
            "graph_name": args.graph_name,
        }
        result = request_json("POST", f"{base}/api/rpc-contract-lint", payload)
    elif args.cmd == "ai-asset-authoring":
        inputs = parse_json_arg(args.inputs_json, "inputs-json")
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        payload = {
            **inputs,
            "dry_run": bool(args.dry_run),
            "stop_on_error": stop_on_error,
        }
        result = request_json("POST", f"{base}/api/ai-asset-authoring", payload)
    elif args.cmd == "material-mesh-presets-catalog":
        result = request_json("GET", f"{base}/api/material-mesh-presets-catalog")
    elif args.cmd == "material-mesh-setup":
        payload = {
            "preset_id": args.preset_id,
            "asset_name": args.asset_name,
            "package_path": args.package_path,
            "blueprint_path": args.blueprint_path,
            "static_mesh_path": args.static_mesh_path,
            "material_path": args.material_path,
            "dry_run": bool(args.dry_run),
        }
        result = request_json("POST", f"{base}/api/material-mesh-setup", payload)
    elif args.cmd == "native-asset-authoring-catalog":
        result = request_json("GET", f"{base}/api/native-asset-authoring-catalog")
    elif args.cmd == "native-asset-create":
        inputs = parse_json_arg(args.inputs_json, "inputs-json")
        payload = {
            "asset_type": args.asset_type,
            **inputs,
            "dry_run": bool(args.dry_run),
        }
        result = request_json("POST", f"{base}/api/native-asset-create", payload)
    elif args.cmd == "native-asset-edit":
        inputs = parse_json_arg(args.inputs_json, "inputs-json")
        payload = {
            "asset_type": args.asset_type,
            **inputs,
            "dry_run": bool(args.dry_run),
        }
        result = request_json("POST", f"{base}/api/native-asset-edit", payload)
    elif args.cmd == "native-asset-authoring-workflow":
        inputs = parse_json_arg(args.inputs_json, "inputs-json")
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        payload = {
            "asset_type": args.asset_type,
            **inputs,
            "dry_run": bool(args.dry_run),
            "stop_on_error": stop_on_error,
        }
        result = request_json("POST", f"{base}/api/native-asset-authoring-workflow", payload)
    elif args.cmd == "pie-replay-suite":
        assertions = parse_json_value(args.assertions_json, "assertions-json")
        include_multiplayer = False if args.no_include_multiplayer else bool(args.include_multiplayer)
        payload = {
            "assertions": assertions,
            "include_multiplayer": include_multiplayer,
            "client_count": int(args.client_count),
            "repeats": int(args.repeats),
        }
        result = request_json("POST", f"{base}/api/pie-replay-suite", payload)
    elif args.cmd == "rollback-apply":
        stop_on_error = False if args.no_stop_on_error else bool(args.stop_on_error)
        payload = {
            "rollback_token": args.rollback_token,
            "dry_run": bool(args.dry_run),
            "stop_on_error": stop_on_error,
        }
        result = request_json("POST", f"{base}/api/rollback-apply", payload)
    elif args.cmd == "get-paid-session-logs":
        url = (
            f"{base}/api/paid/session/logs"
            f"?session_id={urllib.parse.quote(args.session_id)}"
            f"&since={args.since}"
            f"&limit={int(args.limit)}"
        )
        req_headers = {"X-Paid-Token": args.paid_token}
        if REQUEST_EXTRA_HEADERS:
            req_headers.update(REQUEST_EXTRA_HEADERS)
        req = urllib.request.Request(url=url, headers=req_headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                result = json.loads(body)
            except json.JSONDecodeError:
                result = {"success": False, "message": f"HTTP {exc.code}", "raw": body}
        except Exception as exc:  # noqa: BLE001
            result = {"success": False, "message": str(exc)}
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
