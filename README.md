# Unreal Agent Plugin Starter

Current competitive-parity target engine: **UE 5.7**.

This workspace now contains a starter Unreal Engine plugin at:

- `Plugins/UnrealAgent`

It gives you:

- A central action registry (`IAgentAction` + `FAgentActionRegistry`)
- An editor subsystem entrypoint (`UAgentEditorSubsystem`)
- A local HTTP bridge for external agents (`UAgentHttpBridgeSubsystem`)
- Agent actions with safety checks and dry-run mode:
  - `create_blueprint`
  - `spawn_actor`
  - `compile_blueprint`
  - `inspect_asset`
  - `inspect_blueprint_graph`
  - `analyze_blueprint_graph`
  - `analyze_blueprint_asset`
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
  - `modify_blueprint_graph`:
    - `add_print_string_on_begin_play`
    - `add_variable`
    - `remove_variable`
    - `set_default`
    - `add_branch`
    - `call_function`
    - `remove_function_call`
    - `remove_nodes`
    - `disconnect_pin`

Blueprint reliability playbooks:

- `docs/AGENT_BLUEPRINT_ACCURACY_WORKFLOW.md`
- `docs/BLUEPRINT_NODE_LIBRARY.md`

Autonomy expansion routes in the web bridge (`apps/unreal-agent-web/server.py`):

- `GET /api/graph-primitives-catalog`
- `POST /api/graph-primitives-apply`
- `POST /api/runtime-validate-repair`
- `POST /api/autonomous-loop-run`
- `POST /api/pie-replay-suite`
- `GET /api/animation-autonomy-catalog`
- `POST /api/animation-autonomy-generate`
- `GET /api/ai-autonomy-catalog`
- `POST /api/ai-autonomy-generate`
- `POST /api/blackboard-schema-evolve`
- `POST /api/ai-behavior-validate`
- `GET /api/content-pipeline-catalog`
- `POST /api/content-pipeline-apply`
- `POST /api/content-schema-enforce`
- `POST /api/dependency-safety-check`
- `GET /api/multiplayer-correctness-catalog`
- `POST /api/multiplayer-lint`
- `POST /api/multiplayer-guard-apply`
- `POST /api/multiplayer-pie-test`
- `GET /api/material-mesh-presets-catalog`
- `POST /api/material-mesh-setup`
- `POST /api/ai-asset-authoring`
- `GET /api/native-asset-authoring-catalog`
- `POST /api/native-asset-create`
- `POST /api/native-asset-edit`
- `POST /api/native-asset-authoring-workflow`
- `POST /api/blueprint-structure-review`
- `POST /api/rpc-contract-lint`

## Install Into Unreal Project

1. Copy `Plugins/UnrealAgent` into your Unreal project root.
2. Regenerate project files.
3. Build the Editor target.
4. Enable `Unreal Agent` in `Edit -> Plugins`.

## Call From Blueprint/Python

Use `AgentEditorSubsystem.ExecuteAction(ActionName, PayloadJson, bDryRun)`.

Example payload for `create_blueprint`:

```json
{
  "asset_name": "BP_EnemyGrunt",
  "package_path": "/Game/AI/Blueprints",
  "parent_class": "/Script/Engine.Character"
}
```

Example action call:

- `ActionName`: `create_blueprint`
- `PayloadJson`: JSON above (as a string)
- `bDryRun`: `true` first, then `false`

The subsystem returns a JSON string:

```json
{
  "success": true,
  "message": "Blueprint created successfully.",
  "payload": {
    "asset_name": "BP_EnemyGrunt",
    "package_path": "/Game/AI/Blueprints",
    "asset_path": "/Game/AI/Blueprints/BP_EnemyGrunt.BP_EnemyGrunt",
    "parent_class": "/Script/Engine.Character"
  }
}
```

## Call From External AI Agent (HTTP)

The plugin now starts a local-only HTTP bridge in the editor:

- Base URL: `http://127.0.0.1:47777/unreal-agent/v1`
- Endpoints:
  - `GET /health`
  - `GET /actions`
  - `GET /state`
  - `GET /info`
  - `POST /execute`
  - `POST /run-plan`
  - `POST /run-goal`
  - `GET /recipes`
  - `POST /run-recipe`
  - `POST /validate-recipe`
  - `POST /run-scenario`
  - `GET /debug/traces`
  - `POST /debug/clear`

Port override:

- Launch UE with `-UnrealAgentPort=48777` to use a different port.

Deterministic recipe catalog:

- `data/recipes/*.json`
- Default namespace root: `/Game/AgentGenerated`
- Profiles: `balanced` (default), `strict`, `aggressive` (dev)

Example: list actions

```bash
curl http://127.0.0.1:47777/unreal-agent/v1/actions
```

Response includes action metadata:

```json
{
  "success": true,
  "actions": [
    {
      "name": "create_blueprint",
      "description": "Creates a Blueprint Actor asset under /Game."
    }
  ]
}
```

Example: dry-run Blueprint creation

```bash
curl -X POST http://127.0.0.1:47777/unreal-agent/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "action": "create_blueprint",
    "dry_run": true,
    "payload": {
      "asset_name": "BP_EnemyGrunt",
      "package_path": "/Game/AI/Blueprints",
      "parent_class": "/Script/Engine.Character"
    }
  }'
```

Example: spawn actor in current editor level

```bash
curl -X POST http://127.0.0.1:47777/unreal-agent/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "action": "spawn_actor",
    "dry_run": false,
    "payload": {
      "class_path": "/Script/Engine.StaticMeshActor",
      "actor_label": "AgentPlacedMesh",
      "location": [300, 100, 80],
      "rotation": [0, 90, 0],
      "scale": [1, 1, 1],
      "folder_path": "AgentGenerated",
      "select_actor": true
    }
  }'
```

Example: compile blueprint after generation

```bash
curl -X POST http://127.0.0.1:47777/unreal-agent/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "action": "compile_blueprint",
    "dry_run": false,
    "payload": {
      "blueprint_path": "/Game/AI/Blueprints/BP_EnemyGrunt"
    }
  }'
```

Example: fetch recent plugin debug traces

```bash
curl "http://127.0.0.1:47777/unreal-agent/v1/debug/traces?limit=50&filter=run-plan"
```

Example: clear plugin debug traces

```bash
curl -X POST http://127.0.0.1:47777/unreal-agent/v1/debug/clear \
  -H "Content-Type: application/json" \
  -d '{}'
```

Example: inspect if an asset exists

```bash
curl -X POST http://127.0.0.1:47777/unreal-agent/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "action": "inspect_asset",
    "payload": {
      "asset_path": "/Game/AI/Blueprints/BP_EnemyGrunt"
    }
  }'
```

Example: inspect blueprint event graph node inventory

```bash
curl -X POST http://127.0.0.1:47777/unreal-agent/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "action": "inspect_blueprint_graph",
    "payload": {
      "blueprint_path": "/Game/AI/Blueprints/BP_EnemyGrunt",
      "max_nodes": 100,
      "include_pins": false
    }
  }'
```

Example: deterministic blueprint graph analysis (flow + guards + contradictions)

```bash
curl -X POST http://127.0.0.1:47777/unreal-agent/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "action": "analyze_blueprint_graph",
    "payload": {
      "blueprint_path": "/Game/AI/Blueprints/BP_EnemyGrunt",
      "graph_name": "EventGraph",
      "include_pins": true,
      "max_nodes": 500,
      "max_trace_depth": 128
    }
  }'
```

Example: modify Event Graph (BeginPlay -> PrintString)

```bash
curl -X POST http://127.0.0.1:47777/unreal-agent/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "action": "modify_blueprint_graph",
    "dry_run": false,
    "payload": {
      "blueprint_path": "/Game/AI/Blueprints/BP_EnemyGrunt",
      "operation": "add_print_string_on_begin_play",
      "message": "Enemy spawned",
      "compile_after": true
    }
  }'
```

Example: add variable + set default metadata

```bash
curl -X POST http://127.0.0.1:47777/unreal-agent/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "action": "modify_blueprint_graph",
    "payload": {
      "blueprint_path": "/Game/AI/Blueprints/BP_EnemyGrunt",
      "operation": "add_variable",
      "variable_name": "bAggroEnabled",
      "variable_type": "bool",
      "default_value": "true",
      "category": "AI",
      "compile_after": false
    }
  }'
```

```bash
curl -X POST http://127.0.0.1:47777/unreal-agent/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "action": "modify_blueprint_graph",
    "payload": {
      "blueprint_path": "/Game/AI/Blueprints/BP_EnemyGrunt",
      "operation": "set_default",
      "variable_name": "bAggroEnabled",
      "default_value": "false",
      "compile_after": true
    }
  }'
```

Example: add branch and call function

```bash
curl -X POST http://127.0.0.1:47777/unreal-agent/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "action": "modify_blueprint_graph",
    "payload": {
      "blueprint_path": "/Game/AI/Blueprints/BP_EnemyGrunt",
      "operation": "add_branch",
      "condition_default": true,
      "compile_after": false
    }
  }'
```

```bash
curl -X POST http://127.0.0.1:47777/unreal-agent/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "action": "modify_blueprint_graph",
    "payload": {
      "blueprint_path": "/Game/AI/Blueprints/BP_EnemyGrunt",
      "operation": "call_function",
      "class_path": "/Script/Engine.KismetSystemLibrary",
      "function_name": "PrintString",
      "exec_source": "branch_true",
      "inputs": {
        "InString": "Branch TRUE path"
      },
      "compile_after": true
    }
  }'
```

Example: run multi-step autonomous plan (create -> modify -> compile)

```bash
curl -X POST http://127.0.0.1:47777/unreal-agent/v1/run-plan \
  -H "Content-Type: application/json" \
  -d '{
    "plan_id": "enemy-grunt-seed",
    "dry_run": false,
    "stop_on_error": true,
    "steps": [
      {
        "id": "create_bp",
        "action": "create_blueprint",
        "payload": {
          "asset_name": "BP_EnemyGrunt",
          "package_path": "/Game/AI/Blueprints",
          "parent_class": "/Script/Engine.Character"
        }
      },
      {
        "id": "wire_begin_play",
        "action": "modify_blueprint_graph",
        "payload": {
          "blueprint_path": "/Game/AI/Blueprints/BP_EnemyGrunt",
          "operation": "add_print_string_on_begin_play",
          "message": "Enemy ready",
          "compile_after": false
        }
      }
    ],
    "compile_blueprints": [
      "/Game/AI/Blueprints/BP_EnemyGrunt"
    ]
  }'
```

Example: run autonomous goal planner (goal text -> generated plan -> execute)

```bash
curl -X POST http://127.0.0.1:47777/unreal-agent/v1/run-goal \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Create an enemy blueprint, add an aggro variable, branch on begin play, and print a debug message",
    "dry_run": false,
    "goal_context": {
      "asset_name": "BP_EnemyScout",
      "package_path": "/Game/AI/Blueprints",
      "parent_class": "/Script/Engine.Character",
      "variable_name": "bAggroEnabled",
      "variable_type": "bool",
      "default_value": "true",
      "message": "Enemy scout initialized"
    }
  }'
```

## Optional Local Client

A small helper client is included at:

- `tools/unreal_agent_http_client.py`

Examples:

```bash
python3 tools/unreal_agent_http_client.py actions
python3 tools/unreal_agent_http_client.py execute --action create_blueprint --dry-run --payload-json '{"asset_name":"BP_Test","package_path":"/Game/Test"}'
python3 tools/unreal_agent_http_client.py run-plan --plan-json '{"steps":[{"action":"create_blueprint","payload":{"asset_name":"BP_TestPlan","package_path":"/Game/Test"}}],"compile_blueprints":["/Game/Test/BP_TestPlan"]}'
python3 tools/unreal_agent_http_client.py run-goal --goal "Create enemy blueprint and print on begin play" --context-json '{"asset_name":"BP_GoalTest","package_path":"/Game/Test","message":"Goal pipeline works"}'
```

## Web Tool (UI + LLM + IDE Bridge)

You can run a browser-based control tool instead of using raw HTTP commands:

1. Start:

```bash
python3 apps/unreal-agent-web/server.py
```

2. Open:

- `http://127.0.0.1:8787`

This UI lets you:

- configure Unreal bridge URL
- configure LLM API (OpenAI-compatible)
- run natural-language commands
- run direct actions and plans
- use approval tokens for mutating runs
- inspect Unreal state/info without writing commands

IDE bridge CLI:

- `tools/ide_unreal_agent.py`
- readiness check: `python3 tools/ide_unreal_agent.py --pretty agent-readiness`
- bootstrap session (optional manual check): `python3 tools/ide_unreal_agent.py --pretty agent-bootstrap`
- node control capability map: `python3 tools/ide_unreal_agent.py --pretty node-control-capabilities`
- workflow catalog: `python3 tools/ide_unreal_agent.py --pretty workflow-catalog`
- replay suite: `python3 tools/ide_unreal_agent.py --pretty replay-suite --cases-json '[{"case_id":"c1","command":"Create a timed objective collection loop for parkour."}]' --repeats 2`
- release gate: `python3 tools/ide_unreal_agent.py --pretty release-gate-evaluate --blueprint-paths-json '["/Game/Test/BP_Example"]' --replay-cases-json '[{"case_id":"c1","command":"Create a timed objective collection loop for parkour."}]' --replay-repeats 2`
- autonomous bulletproof loop: `python3 tools/ide_unreal_agent.py --pretty autonomous-loop-run --blueprint-path /Game/Test/BP_Example --scenario-repeats 2 --enable-multiplayer --multiplayer-client-count 2 --multiplayer-repeats 2`
- execution artifact view: `python3 tools/ide_unreal_agent.py --pretty execution-artifact --run-id <exec_run_id> --include-full`
- workflow generate (dry-run): `python3 tools/ide_unreal_agent.py --pretty workflow-generate --workflow-id objective_capture_loop_full --inputs-json '{"namespace_root":"/Game/AgentGenerated","controller_asset_name":"BP_AutoController","objective_count":5,"time_limit_sec":180}' --dry-run`
- blueprint full-asset review: `python3 tools/ide_unreal_agent.py --pretty blueprint-structure-review --blueprint-path /Game/Test/BP_Example --review-scope asset --include-ast --max-graph-ast-exports 12`

Integration guide:

- `docs/WEB_TOOL_AND_IDE_INTEGRATION.md`
- `docs/CURSOR_AGENT_SETUP.md`
- `docs/BLUEPRINT_NODE_LIBRARY.md`
- `POST /api/analyze` in web tool:
  - deterministic blueprint analysis first
  - optional LLM summarization on top (strictly evidence-linked)
  - hard-fails uncited/speculative claims
  - stores artifacts at `apps/unreal-agent-web/.data/analysis-runs/<run_id>/analysis.json`

Example: run strict analysis via web tool

```bash
curl -X POST http://127.0.0.1:8787/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "blueprint_path": "/Game/AI/Blueprints/BP_EnemyGrunt",
    "mode": "asset",
    "max_nodes": 1000,
    "max_trace_depth": 128,
    "prompt": "Analyze all gameplay-critical paths and guard conditions."
  }'
```

Example: list recent analysis artifacts

```bash
curl http://127.0.0.1:8787/api/analysis-runs
```

## Next Actions To Add

- `create_material`
- `create_animation_blueprint`
- `edit_project_settings`
- `run_playtest` / `capture_test_results`
