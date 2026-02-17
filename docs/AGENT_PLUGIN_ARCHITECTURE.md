# Ideal Unreal Agent Plugin Architecture

Engine target for current rollout: **UE 5.7**.

## Goal

Let an AI agent perform high-leverage Unreal creation tasks while staying safe, auditable, and reversible.

## Design Principles

- Agent should call explicit, typed actions instead of raw editor internals.
- Every action should support `dry_run`, validation, and structured result payloads.
- High-impact actions should require policy checks before execution.
- All changes should be undoable using editor transactions.

## Layered Architecture

1. `Transport Layer`
- Receives requests from external AI orchestrator.
- Suggested options:
  - Local loopback HTTP/WebSocket bridge
  - In-editor Python bridge
  - File queue bridge for offline workflows

2. `Agent Execution Layer`
- Parses command envelope:
  - `goal_id`, `step_id`, `action`, `payload`, `dry_run`, `trace_id`
- Handles:
  - timeouts
  - retries
  - cancellation
  - idempotency keys

3. `Action Registry Layer` (implemented starter)
- `IAgentAction` interface per capability.
- Action metadata:
  - name
  - description
  - risk level
  - required permissions

4. `Policy & Safety Layer`
- Allowlist actions and package roots (`/Game`, `/Game/AI`).
- Require confirmation for destructive operations.
- Enforce per-action quotas and cooldowns.
- Block operations during PIE unless explicitly allowed.

5. `State & Memory Layer`
- Persist action logs to JSONL:
  - input payload
  - normalized plan
  - output payload
  - latency
  - success/failure
- Store artifacts:
  - generated assets
  - screenshots
  - compile diagnostics

6. `Feedback Layer`
- Return structured results for each action:
  - machine-readable `payload`
  - human-readable `message`
  - error code taxonomy

## Action Taxonomy

Start with these categories:

- Content creation:
  - create blueprint/material/widget/animation blueprint
- Graph editing:
  - add node, connect pins, set default values
- World editing:
  - place actor, set transform, assign components
- Data authoring:
  - create data assets, data tables, gameplay tags
- Validation:
  - compile blueprints, run map checks, run automated tests
- Build/packaging:
  - cook/build/package with configuration presets

## Execution Contract (Recommended)

Request:

```json
{
  "trace_id": "uuid",
  "action": "create_blueprint",
  "payload": {
    "asset_name": "BP_EnemyGrunt",
    "package_path": "/Game/AI/Blueprints",
    "parent_class": "/Script/Engine.Character"
  },
  "dry_run": true
}
```

Response:

```json
{
  "success": true,
  "message": "Dry run successful. No asset created.",
  "payload": {
    "asset_name": "BP_EnemyGrunt",
    "package_path": "/Game/AI/Blueprints",
    "parent_class": "/Script/Engine.Character"
  },
  "metrics": {
    "duration_ms": 18
  }
}
```

## Security Model

- Local-only transport by default (`127.0.0.1`).
- Optional shared-secret auth for remote orchestration.
- No arbitrary code execution action in production mode.
- Separate:
  - `SafeMode` profile for normal use
  - `DevMode` profile for trusted rapid iteration

## Roadmap

1. Build transport bridge and command envelope handling. (done in starter with loopback HTTP)
2. Add 10-15 high-value actions (content + validation).
3. Add policy engine + action permissions.
4. Add full audit trail and replay.
5. Add planner integration (LLM decides action sequence).
6. Add autonomous loop:
  - plan
  - execute
  - validate
  - repair

## What Was Implemented Here

- Plugin scaffold with runtime and editor modules.
- Central action registry.
- Editor subsystem entrypoint for agent commands.
- Loopback HTTP bridge:
  - `GET /unreal-agent/v1/health`
  - `GET /unreal-agent/v1/actions`
  - `GET /unreal-agent/v1/state`
  - `GET /unreal-agent/v1/info`
  - `POST /unreal-agent/v1/execute`
  - `POST /unreal-agent/v1/run-plan`
  - `POST /unreal-agent/v1/run-goal`
  - `GET /unreal-agent/v1/recipes`
  - `POST /unreal-agent/v1/run-recipe`
  - `POST /unreal-agent/v1/validate-recipe`
  - `POST /unreal-agent/v1/run-scenario`
  - `GET /unreal-agent/v1/debug/traces`
  - `POST /unreal-agent/v1/debug/clear`
- Initial actions:
  - `create_blueprint`
  - `spawn_actor`
  - `compile_blueprint`
  - `inspect_asset`
  - `inspect_blueprint_graph`
  - recipe/world/data/validation families:
    - `create_widget_blueprint`
    - `modify_widget_tree`
    - `bind_widget_events`
    - `generate_widget_template`
    - `analyze_widget_tree`
    - `create_objective_actor`
    - `wire_objective_progress`
    - `create_timer_system`
    - `create_score_system`
    - `create_restart_flow`
    - `batch_spawn_actors`
    - `layout_along_spline`
    - `create_level_chunk`
    - `generate_layout_from_template`
    - `scatter_assets_with_constraints`
    - `clear_generated_layout_by_token`
    - `tag_and_group_actors`
    - `list_asset_dependencies`
    - `list_asset_referencers`
    - `analyze_asset_impact`
    - `analyze_project_hotspots`
    - `create_data_asset`
    - `create_behavior_tree_asset`
    - `edit_behavior_tree_asset`
    - `create_blackboard_data_asset`
    - `edit_blackboard_data_asset`
    - `create_eqs_query_asset`
    - `edit_eqs_query_asset`
    - `create_anim_blueprint_asset`
    - `edit_anim_blueprint_state_machine`
    - `create_material_asset`
    - `edit_material_asset`
    - `create_niagara_system_asset`
    - `edit_niagara_system_graph`
    - `create_level_sequence_asset`
    - `edit_level_sequence_asset`
    - `validate_data_schema`
    - `inspect_compile_errors`
    - `run_pie_scenario`
    - `assert_world_state`
    - `capture_screenshot`
  - `modify_blueprint_graph` operations:
    - `add_print_string_on_begin_play`
    - `add_variable`
    - `remove_variable`
    - `set_default`
    - `add_branch`
    - `call_function`
    - `remove_function_call`
    - `remove_nodes`
    - `disconnect_pin`
  - `blueprint_node_authoring` operations:
    - `spawn_function_call`
    - `replace_function_call`
    - `spawn_custom_event`
    - `spawn_branch_node`

## Deterministic UMG Extensions

- `modify_widget_tree` now supports additional widget classes:
  - `ProgressBar`, `ScrollBox`, `UniformGridPanel`, `WrapBox`, `RichTextBlock`
- `modify_widget_tree` slot handling supports:
  - Canvas slot layout
  - Vertical/Horizontal/Overlay alignment and padding
  - Uniform grid row/column/span/alignment/padding
- `modify_widget_tree` style/property support includes:
  - `font_family`, `font_size`, `font_weight`
  - `text_color`, `brush_tint`
  - `padding`/`margins`
  - `alignment_preset`
- `bind_widget_events` supports action modes:
  - `call_function`
  - `dispatch_event` (function-call fallback path)
  - `toggle_visibility`
  - `set_text`
  - `set_progress`

## New Action Contracts (Summary)

- `generate_widget_template`
  - request: `{"widget_blueprint","template_id","style_preset","bindings[]?","compile_after?"}`
  - response payload: template operations + binding summary
- `analyze_widget_tree`
  - request: `{"widget_blueprint"}`
  - response payload: widget inventory, lint findings, binding completeness
- `list_asset_dependencies`
  - request: `{"asset_path","depth?"}`
  - response payload: `dependencies[]`, count
- `list_asset_referencers`
  - request: `{"asset_path","depth?"}`
  - response payload: `referencers[]`, count
- `analyze_asset_impact`
  - request: `{"asset_path","change_type?","depth?"}`
  - response payload: dependencies/referencers + risk flags/score
- `analyze_project_hotspots`
  - request: `{"package_path?","recursive?","max_assets?"}`
  - response payload: hotspot items with deterministic risk scores
- `generate_layout_from_template`
  - request: `{"layout_id","origin?","rows?","cols?","spacing?","class_path?","static_mesh_path?","folder_path?","tags?"}`
  - response payload: spawn summary from selected generator
- `scatter_assets_with_constraints`
  - request: `{"bounds","count?","seed?","class_path?","static_mesh_path?","folder_path?","tags?"}`
  - response payload: batch spawn results
- `clear_generated_layout_by_token`
  - request: `{"cleanup_token"}`
  - response payload: delete summary
- `create_behavior_tree_asset`
  - request: `{"asset_name?","package_path?","asset_class_path?","factory_class_path?"}`
  - response payload: created native asset descriptor
- `edit_behavior_tree_asset`
  - request: `{"behavior_tree_path|asset_path","blackboard_path?","root_class_path?","tasks[]?"}`
  - response payload: root/task topology summary
- `create_blackboard_data_asset` / `edit_blackboard_data_asset`
  - request: blackboard create + deterministic key schema mutations (`keys[]`, `replace_existing?`)
  - response payload: schema change counts
- `create_eqs_query_asset` / `edit_eqs_query_asset`
  - request: EQS create + deterministic option/generator/test scaffolding
  - response payload: options/tests created summary
- `create_anim_blueprint_asset` / `edit_anim_blueprint_state_machine`
  - request: anim blueprint scaffold + deterministic state-machine helper states
  - response payload: generated state scaffolding summary
- `create_material_asset` / `edit_material_asset`
  - request: material create + deterministic property edits (`two_sided`, `blend_mode`, `shading_model`)
  - response payload: applied property summary
- `create_niagara_system_asset` / `edit_niagara_system_graph`
  - request: Niagara system create + deterministic graph/system seed settings
  - response payload: seed + mutation summary
- `create_level_sequence_asset` / `edit_level_sequence_asset`
  - request: sequence create + deterministic playback scaffold edits
  - response payload: playback edit summary
- Plan runner:
  - executes ordered `steps[]`
  - optional `compile_blueprints[]` post-phase
  - returns per-step status, timings, and aggregate summary
- Goal runner:
  - receives natural-language `goal` + optional `goal_context`
  - synthesizes a plan heuristically
  - executes via the same plan engine and returns generated plan + execution results
