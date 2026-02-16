# Ideal Unreal Agent Plugin Architecture

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
    - `create_objective_actor`
    - `wire_objective_progress`
    - `create_timer_system`
    - `create_score_system`
    - `create_restart_flow`
    - `batch_spawn_actors`
    - `layout_along_spline`
    - `create_level_chunk`
    - `tag_and_group_actors`
    - `create_data_asset`
    - `validate_data_schema`
    - `inspect_compile_errors`
    - `run_pie_scenario`
    - `assert_world_state`
    - `capture_screenshot`
  - `modify_blueprint_graph` operations:
    - `add_print_string_on_begin_play`
    - `add_variable`
    - `set_default`
    - `add_branch`
    - `call_function`
- Plan runner:
  - executes ordered `steps[]`
  - optional `compile_blueprints[]` post-phase
  - returns per-step status, timings, and aggregate summary
- Goal runner:
  - receives natural-language `goal` + optional `goal_context`
  - synthesizes a plan heuristically
  - executes via the same plan engine and returns generated plan + execution results
