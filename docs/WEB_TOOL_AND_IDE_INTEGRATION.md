# Web Tool And IDE Integration

Target engine for this competitive-parity track: **UE 5.7**.

## Architecture

1. Unreal Editor plugin exposes local bridge (`/unreal-agent/v1/*`).
2. Web tool (`apps/unreal-agent-web/server.py`) adds:
- browser UI
- optional LLM planning
- approval token workflow
- version compatibility checks
- run lock (single active mutation run)
- audit logging
3. IDE agent calls web tool API or CLI bridge (`tools/ide_unreal_agent.py`).

## Start Sequence

1. Start Unreal Editor with plugin enabled.
2. Verify Unreal bridge:
- `curl http://127.0.0.1:47777/unreal-agent/v1/health`
3. Start web tool:
- Terminal option: `python3 apps/unreal-agent-web/server.py`
- No-terminal option (macOS): double-click `apps/unreal-agent-web/Launch Unreal Agent Chat.command`
4. Open UI:
- `http://127.0.0.1:8787`

## Natural Language-Only Flow

Use the chat UI only:

1. Open `http://127.0.0.1:8787`
2. Keep `LLM Planner` disabled for no API key mode.
3. Type natural-language task in chat and click `Send`.
4. If approval is enabled and required, click `Approve & Retry` in the UI.

No CLI commands are required for day-to-day use in this mode.

## Web Tool API Contract

- `GET /api/health`
- `GET /api/agent-readiness`
- `GET /api/info`
- `GET /api/state`
- `GET /api/actions`
- `GET /api/recipes`
- `GET /api/release-metrics`
- `GET /api/approvals`
- `GET /api/execution-run-detail`
- `GET /api/execution-artifact`
- `GET /api/workflow-catalog`
- `GET /api/node-control-capabilities`
- `GET /api/graph-primitives-catalog`
- `GET /api/animation-autonomy-catalog`
- `GET /api/ai-autonomy-catalog`
- `GET /api/content-pipeline-catalog`
- `GET /api/multiplayer-correctness-catalog`
- `GET /api/material-mesh-presets-catalog`
- `GET /api/native-asset-authoring-catalog`
- `GET /api/claims-evidence`
- `GET /api/admin/session-diagnostics`
- `GET /api/admin/usage-events`
- `POST /api/settings`
- `POST /api/approve`
- `POST /api/direct-execute`
- `POST /api/run-plan`
- `POST /api/run-goal`
- `POST /api/run-recipe`
- `POST /api/validate-recipe`
- `POST /api/run-scenario`
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
- `POST /api/replay-suite`
- `POST /api/release-gate-evaluate`
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
- `POST /api/command` (LLM-backed command mode)
- `POST /api/chat` (chat-first alias for natural-language clients)

## Approval Flow

1. Call a mutating endpoint without `approval_token`.
2. Receive `202` with `error_code=APPROVAL_REQUIRED` and `approval_token`.
3. Approve token:
- `POST /api/approve` with `{"approval_token":"..."}`.
4. Retry original call with the approved token.

Set `require_approval_for_mutations=false` in `/api/settings` to bypass approvals.

## IDE Bridge CLI

Script:

- `tools/ide_unreal_agent.py`

Commands:

- `health`, `actions`, `recipes`, `release-metrics`, `info`, `state`, `approvals`
- `claims-evidence`
- `execution-run-detail`
- `execution-artifact`
- `workflow-catalog`
- `node-control-capabilities`
- `graph-primitives-catalog`
- `animation-autonomy-catalog`
- `ai-autonomy-catalog`
- `content-pipeline-catalog`
- `multiplayer-correctness-catalog`
- `material-mesh-presets-catalog`
- `admin-session-diagnostics`
- `admin-usage-events`
- `approve --approval-token ...`
- `run-command`
- `run-goal`
- `run-plan`
- `run-recipe`
- `validate-recipe`
- `run-scenario`
- `direct-execute`
- `refactor-catalog`, `refactor-preview`, `refactor-apply`, `refactor-suggest`
- `explain-selection`, `explain-screenshot`
- `project-dependencies`, `perf-hotspots`, `impact-analysis`
- `umg-generate`, `world-generate`
- `entitlements-check`, `usage-event`
- `agent-readiness`
- `replay-suite`
- `release-gate-evaluate`
- `workflow-generate`
- `graph-primitives-apply`
- `runtime-validate-repair`
- `autonomous-loop-run`
- `animation-autonomy-generate`
- `ai-autonomy-generate`
- `blackboard-schema-evolve`
- `ai-behavior-validate`
- `content-pipeline-apply`
- `content-schema-enforce`
- `dependency-safety-check`
- `multiplayer-lint`
- `multiplayer-guard-apply`
- `multiplayer-pie-test`
- `blueprint-structure-review`
- `rpc-contract-lint`
- `ai-asset-authoring`
- `material-mesh-setup`
- `native-asset-authoring-catalog`
- `native-asset-create`
- `native-asset-edit`
- `native-asset-authoring-workflow`
- `pie-replay-suite`

Blueprint full-asset review (all graphs):

- `python3 tools/ide_unreal_agent.py --pretty blueprint-structure-review --blueprint-path /Game/MyBP --review-scope asset --include-ast --max-graph-ast-exports 12`

## MCP Parity

`tools/cursor_unreal_mcp.py` includes tool parity for:

- `unreal_refactor_catalog`
- `unreal_refactor_preview`
- `unreal_explain_selection`
- `unreal_explain_screenshot`
- `unreal_project_dependencies`
- `unreal_perf_hotspots`
- `unreal_impact_analysis`
- `unreal_umg_generate`
- `unreal_world_generate`
- `unreal_claims_evidence`
- `unreal_execution_run_detail`
- `unreal_execution_artifact`
- `unreal_workflow_catalog`
- `unreal_node_control_capabilities`
- `unreal_workflow_generate`
- `unreal_graph_primitives_catalog`
- `unreal_graph_primitives_apply`
- `unreal_runtime_validate_repair`
- `unreal_autonomous_loop_run`
- `unreal_animation_autonomy_catalog`
- `unreal_animation_autonomy_generate`
- `unreal_ai_autonomy_catalog`
- `unreal_ai_autonomy_generate`
- `unreal_blackboard_schema_evolve`
- `unreal_ai_behavior_validate`
- `unreal_content_pipeline_catalog`
- `unreal_content_pipeline_apply`
- `unreal_content_schema_enforce`
- `unreal_dependency_safety_check`
- `unreal_multiplayer_correctness_catalog`
- `unreal_multiplayer_lint`
- `unreal_multiplayer_guard_apply`
- `unreal_multiplayer_pie_test`
- `unreal_blueprint_structure_review`
- `unreal_rpc_contract_lint`
- `unreal_ai_asset_authoring`
- `unreal_native_asset_authoring_catalog`
- `unreal_native_asset_create`
- `unreal_native_asset_edit`
- `unreal_native_asset_authoring_workflow`
- `unreal_pie_replay_suite`
- `unreal_material_mesh_presets_catalog`
- `unreal_material_mesh_setup`
- `unreal_agent_readiness`
- `unreal_replay_suite`
- `unreal_release_gate_evaluate`

Examples:

```bash
python3 tools/ide_unreal_agent.py health --pretty
python3 tools/ide_unreal_agent.py info --pretty
python3 tools/ide_unreal_agent.py state --pretty
python3 tools/ide_unreal_agent.py run-command --command "Create BP_Player and add print on begin play" --goal-context-json '{"asset_name":"BP_Player","package_path":"/Game/Player","message":"Player init"}' --pretty
python3 tools/ide_unreal_agent.py direct-execute --action compile_blueprint --payload-json '{"blueprint_path":"/Game/Player/BP_Player"}' --pretty
```

## Cursor/IDE Agent Integration

For Cursor (or any IDE agent with shell tool support):

1. Register `python3 /Users/ericdiaz/Desktop/Unreal\ Friend/tools/ide_unreal_agent.py` as an allowed command.
2. Let the IDE agent call `run-command` for natural language goals.
3. If response is `APPROVAL_REQUIRED`, have the agent:
- call `approvals`
- call `approve --approval-token <token>`
- retry previous command with `--approval-token <token>`.
4. Use `info` and `state` before mutations to ground planning.

## Smoke Test Harness

Run:

```bash
python3 tests/smoke_web_tool.py
```

It validates approval flow, compatibility checks, lock behavior, pass-through endpoints, and audit logging against a stub Unreal bridge.
