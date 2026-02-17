# Unreal Agent Web

Local web control plane for Unreal Agent plugin.

Primary target for this rollout: **Unreal Engine 5.7**.

It connects to:

- Unreal HTTP bridge at `http://127.0.0.1:47777/unreal-agent/v1`
- Optional LLM API (OpenAI-compatible Chat Completions API)

## Run

```bash
python3 /Users/ericdiaz/Desktop/Unreal\ Friend/apps/unreal-agent-web/server.py
```

Then open:

- `http://127.0.0.1:8787`

## No-Terminal Launch (macOS)

Double-click:

- `/Users/ericdiaz/Desktop/Unreal Friend/apps/unreal-agent-web/Launch Unreal Agent Chat.command`

This starts the server in the background (if needed) and opens the chat UI.

## Env Overrides

- `UNREAL_AGENT_WEB_HOST` (default: `127.0.0.1`)
- `UNREAL_AGENT_WEB_PORT` (default: `8787`)

## What It Does

- Saves local settings (`apps/unreal-agent-web/.data/settings.json`)
- Stores approvals (`apps/unreal-agent-web/.data/approvals.json`)
- Writes audit log (`apps/unreal-agent-web/.data/audit.log.jsonl`)
- Writes release metrics (`apps/unreal-agent-web/.data/release_metrics.json`)
- Writes execution artifacts (`apps/unreal-agent-web/.data/execution-runs/<run_id>/execution.json`)
- Writes paid session logs (`apps/unreal-agent-web/.data/paid-session-logs/<session_id>.jsonl`)
- Writes paid usage events (`apps/unreal-agent-web/.data/usage_events.jsonl`)
- Writes claim evidence snapshots (`apps/unreal-agent-web/.data/claims_evidence.json`)
- Sends natural language commands:
  - recipe-first deterministic routing -> `/run-recipe` in Unreal, then
  - LLM plan generation -> `/run-plan` in Unreal, or
  - fallback directly to Unreal `/run-goal` (blocked in `strict` profile)
- Supports direct action execution and raw plan execution
- Supports deterministic recipe validation and scenario runs
- Adds compatibility checks against Unreal `/info`
- Adds run lock so only one Unreal execution request runs at a time
- Provides chat-first endpoint: `POST /api/chat` (alias of `/api/command`)

## Execution Profiles

- `balanced` (default): recipe-first, then LLM plan, then fallback goal runner.
- `strict`: recipe-first or LLM plan only; rejects heuristic goal fallback.
- `aggressive`: reserved for future expansion; currently follows balanced command routing.

Set default profile:

```bash
curl -X POST http://127.0.0.1:8787/api/settings \
  -H "Content-Type: application/json" \
  -d '{"execution_profile":"strict"}'
```

Set default Unreal project targeting context (auto-merged into `goal_context`, and recipe inputs when schema supports those fields):

```bash
curl -X POST http://127.0.0.1:8787/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "default_uproject_path": "/Users/ericdiaz/Documents/Unreal Projects/ScavTest/ScavTest.uproject",
    "default_project_root": "/Users/ericdiaz/Documents/Unreal Projects/ScavTest",
    "default_source_root": "/Users/ericdiaz/Documents/Unreal Projects/ScavTest/Source",
    "default_content_root": "/Users/ericdiaz/Documents/Unreal Projects/ScavTest/Content"
  }'
```

Execution safeguards (set in `/api/settings`):

- `execution_preflight_enabled` (default `true`): runs deterministic dry-run preflight before mutating `run-plan`, `run-goal`, and recipe executions.
- `execution_store_artifacts` (default `true`): stores request/response artifacts under `.data/execution-runs`.
- `execution_max_saved_runs` (default `300`): cap for saved execution artifact runs.
- `require_agent_bootstrap_for_routes` (default `true`): enforces bootstrap token on agent mutating routes.
- `agent_bootstrap_ttl_sec` (default `28800`): bootstrap session token TTL in seconds.

Agent bootstrap handshake:

1. Call `POST /api/agent-bootstrap` with `client_name`, `client_version`, `session_label`.
2. Read `bootstrap_token` from response.
3. Send header `X-Agent-Bootstrap-Token: <token>` on mutating route calls.

Paid live log scaffolding (set in `/api/settings`):

- `paid_live_logs_enabled` (default `false`): enables paid live session logs.
- `paid_live_logs_tokens` (default `[]`): list of valid paid access tokens.
- `paid_admin_tokens` (default `[]`): admin tokens for diagnostics and usage event review.
- `paid_live_logs_max_session_events` (default `2000`): cap per session log file.

Plan-tier gate (set in `/api/settings`):

- `plan_tier_gate_enabled` (default `false`): enforces paid token checks on paid routes.
- `paid_tier_required_routes` (default includes project audit, validate execution, and paid session routes).
- When blocked, API returns HTTP `402` with `error_code=PLAN_TIER_REQUIRED`.

## API Endpoints

- `GET /api/health`
- `GET /api/info`
- `GET /api/state`
- `GET /api/actions`
- `GET /api/recipes`
- `GET /api/release-metrics`
- `GET /api/claims-evidence`
- `GET /api/admin/session-diagnostics`
- `GET /api/admin/usage-events`
- `GET /api/node-library`
- `GET /api/execution-runs`
- `GET /api/execution-run-detail`
- `GET /api/workflow-catalog`
- `GET /api/node-control-capabilities`
- `GET /api/graph-primitives-catalog`
- `GET /api/animation-autonomy-catalog`
- `GET /api/ai-autonomy-catalog`
- `GET /api/content-pipeline-catalog`
- `GET /api/multiplayer-correctness-catalog`
- `GET /api/material-mesh-presets-catalog`
- `GET /api/native-asset-authoring-catalog`
- `GET /api/paid/session/logs`
- `GET /api/paid/session/stream` (SSE)
- `GET /api/approvals`
- `POST /api/settings`
- `POST /api/agent-bootstrap`
- `POST /api/approve`
- `POST /api/paid/session/start`
- `POST /api/paid/session/end`
- `POST /api/direct-execute`
- `POST /api/run-plan`
- `POST /api/run-goal`
- `POST /api/run-recipe`
- `POST /api/validate-recipe`
- `POST /api/validate-execution`
- `POST /api/project-audit`
- `POST /api/refactor-suggest`
- `POST /api/refactor-catalog`
- `POST /api/refactor-preview`
- `POST /api/refactor-apply`
- `POST /api/explain-selection`
- `POST /api/explain-screenshot`
- `POST /api/project-dependencies`
- `POST /api/perf-hotspots`
- `POST /api/impact-analysis`
- `POST /api/umg-generate`
- `POST /api/world-generate`
- `POST /api/entitlements/check`
- `POST /api/usage/event`
- `POST /api/run-scenario`
- `POST /api/workflow-generate`
- `POST /api/graph-primitives-apply`
- `POST /api/runtime-validate-repair`
- `POST /api/autonomous-loop-run`
- `POST /api/pie-replay-suite`
- `POST /api/animation-autonomy-generate`
- `POST /api/ai-autonomy-generate`
- `POST /api/blackboard-schema-evolve`
- `POST /api/ai-behavior-validate`
- `POST /api/content-pipeline-apply`
- `POST /api/content-schema-enforce`
- `POST /api/dependency-safety-check`
- `POST /api/multiplayer-lint`
- `POST /api/multiplayer-guard-apply`
- `POST /api/multiplayer-pie-test`
- `POST /api/blueprint-structure-review`
- `POST /api/rpc-contract-lint`
- `POST /api/ai-asset-authoring`
- `POST /api/material-mesh-setup`
- `POST /api/native-asset-create`
- `POST /api/native-asset-edit`
- `POST /api/native-asset-authoring-workflow`
- `POST /api/command`

`/api/refactor-apply` now also returns:

- `determinism_score` (compile/contradiction/lint/replay weighted score)
- `fingerprint_before` and `fingerprint_after`
- `graph_diff` (before/after node delta summary)
- `timeline` (deterministic execution stages)
- `auto_repair_report` (if auto-repair is enabled and needed)

Paid-token transport:
- Header: `X-Paid-Token: <token>`
- Body: `"paid_token": "<token>"`
- Query (for SSE convenience): `?paid_token=<token>`

`modify_blueprint_graph` supports:
- `add_variable`, `remove_variable`
- `set_default`, `add_branch`
- `call_function`, `remove_function_call`
- `remove_nodes`, `disconnect_pin`
- `add_print_string_on_begin_play`

## Competitive Parity Route Schemas

- `POST /api/refactor-catalog`
  - request: `{"blueprint_path?","profile"}`
  - response: `{"success","transforms":[...],"transform_count"}`
- `POST /api/refactor-preview`
  - request: `{"blueprint_path","transform_ids?","transform_inputs?","dry_run":true}`
  - response: `{"success","generated_plan","estimated_impact"}`
- `POST /api/explain-selection`
  - request: `{"blueprint_path","graph_name?","node_names[]"}`
  - response: `{"success","explanation","evidence","suggested_fixes[]"}`
- `POST /api/explain-screenshot`
  - request: `{"image_path","blueprint_path?","graph_name?"}`
  - response: `{"success","parsed_nodes","confidence","explanation","suggested_fixes[]"}`
- `POST /api/project-dependencies`
  - request: `{"package_path","recursive","depth","max_assets?"}`
  - response: `{"success","nodes","edges","hotspots"}`
- `POST /api/perf-hotspots`
  - request: `{"package_path","analyze_blueprints","recursive?","max_assets?"}`
  - response: `{"success","hotspot_items","risk_score"}`
- `POST /api/impact-analysis`
  - request: `{"asset_paths[]","change_type"}`
  - response: `{"success","affected_assets","compile_targets","risk_flags"}`
- `POST /api/umg-generate`
  - request: `{"widget_blueprint?","template_id","bindings[]?","style_preset"}`
  - response: `{"success","operations_applied","compile_status"}`
- `POST /api/world-generate`
  - request: `{"layout_id","bounds","density","seed","constraints?"}`
  - response: `{"success","spawned","tags","cleanup_token"}`
- `POST /api/workflow-generate`
  - request: `{"workflow_id","dry_run?","stop_on_error?","...template_inputs"}`
  - response: `{"success","generated_plan","result","outputs"}`
- `POST /api/graph-primitives-apply`
  - request: `{"blueprint_path","graph_name?","operations[]","dry_run?","stop_on_error?"}`
  - response: `{"success","summary","results[]","rollback_plan?","execution_run_id?"}`
- `POST /api/runtime-validate-repair`
  - request: `{"blueprint_path","assertions[]?","auto_repair?","max_repair_attempts?","capture_screenshot_on_fail?"}`
  - response: `{"success","validation","auto_repair","timeline","failure_screenshot?","execution_run_id?"}`
- `POST /api/autonomous-loop-run`
  - request: `{"blueprint_path","assertions[]?","scenario_repeats?","multiplayer?","include_lint_gate?","include_perf_gate?","auto_repair?","max_repair_attempts?","rollback_on_failure?","rollback_token?"}`
  - response: `{"success","validation","repairs[]","rollback","timeline","failure_screenshot?","execution_run_id?"}`
- `POST /api/pie-replay-suite`
  - request: `{"assertions[]?","include_multiplayer?","client_count?","repeats?"}`
  - response: `{"success","deterministic","hashes[]","runs[]","total_runs","passed_runs","failed_runs"}`
- `POST /api/animation-autonomy-generate`
  - request: `{"template_id","dry_run?","stop_on_error?","...template_inputs"}`
  - response: `{"success","generated_plan","result","outputs"}`
- `POST /api/ai-autonomy-generate`
  - request: `{"template_id","dry_run?","stop_on_error?","...template_inputs"}`
  - response: `{"success","generated_plan","result","outputs"}`
- `POST /api/blackboard-schema-evolve`
  - request: `{"blueprint_path","schema[]?","remove_keys[]?","rename_keys[]?","dry_run?"}`
  - response: `{"success","generated_plan","summary","result?"}`
- `POST /api/ai-behavior-validate`
  - request: `{"blueprint_path","graph_name?","assertions[]?"}`
  - response: `{"success","compile","analysis_lint","scenario"}`
- `POST /api/content-pipeline-apply`
  - request: `{"preset_id","dry_run?","asset_paths[]?","dependency_depth?"}`
  - response: `{"success","recipe_id","recipe_inputs","dependency_safety","result"}`
- `POST /api/content-schema-enforce`
  - request: `{"package_path","recursive?","max_assets?","naming_pattern?","allowed_roots[]?","expected_prefix?"}`
  - response: `{"success","violations[]","migration_plan[]","assets_scanned"}`
- `POST /api/dependency-safety-check`
  - request: `{"asset_paths[]","depth?"}`
  - response: `{"success","items[]","blockers[]","warnings[]","total_risk_score"}`
- `POST /api/multiplayer-lint`
  - request: `{"blueprint_path","graph_name?"}`
  - response: `{"success","risk_score","findings[]"}`
- `POST /api/multiplayer-guard-apply`
  - request: `{"blueprint_path","dry_run?","stop_on_error?"}`
  - response: `{"success","applied","selected_transforms","generated_plan","result?"}`
- `POST /api/multiplayer-pie-test`
  - request: `{"assertions[]?","client_count?","repeats?"}`
  - response: `{"success","client_count","repeats","total_runs","runs[]"}`
- `POST /api/blueprint-structure-review`
  - request: `{"blueprint_path","review_scope?":"graph|asset","include_all_graphs?","graph_name?","include_ast?","include_refactor_catalog?","max_graph_ast_exports?"}`
  - response: `{"success","review_scope","compile","analysis","graph_reviews?","ast?","suggested_fixes","deterministic_review"}`
- `POST /api/rpc-contract-lint`
  - request: `{"blueprint_path","graph_name?"}`
  - response: `{"success","risk_score","findings[]","rpc_event_count","rpc_call_count"}`
- `POST /api/ai-asset-authoring`
  - request: `{"dry_run?","stop_on_error?","...naming/namespace inputs"}`
  - response: `{"success","generated_plan","outputs","result"}`
- `POST /api/material-mesh-setup`
  - request: `{"preset_id?","asset_name?","package_path?","blueprint_path?","static_mesh_path","material_path?","dry_run?"}`
  - response: `{"success","blueprint_path","step_results[]"}`
- `POST /api/native-asset-create`
  - request: `{"asset_type","dry_run?","...asset_type_specific_inputs"}`
  - response: `{"success","asset_type","action","payload","result"}`
- `POST /api/native-asset-edit`
  - request: `{"asset_type","dry_run?","...asset_type_specific_inputs"}`
  - response: `{"success","asset_type","action","payload","result"}`
- `POST /api/native-asset-authoring-workflow`
  - request: `{"asset_type","dry_run?","stop_on_error?","include_edit_pass?","...asset_type_specific_inputs"}`
  - response: `{"success","generated_plan","result"}`

Minimal example:

```bash
curl -X POST http://127.0.0.1:8787/api/refactor-preview \
  -H "Content-Type: application/json" \
  -d '{"blueprint_path":"/Game/Test/BP_Player","dry_run":true}'
```
