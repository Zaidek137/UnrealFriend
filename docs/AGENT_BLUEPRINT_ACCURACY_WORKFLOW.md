# Agent Blueprint Accuracy Workflow

Engine target for this workflow: **UE 5.7** (current project baseline as of February 17, 2026).

## Goal

Provide a deterministic workflow for generating Blueprint gameplay loops with minimal rework:

- no ambiguous graph edits
- no silent compile regressions
- no speculative node wiring

This document is for agent execution quality, not team process.

## Core Rules

1. Prefer recipe or plan execution paths over direct heuristic goal execution.
2. Always run `dry_run` first for new loop intents.
3. Every `modify_blueprint_graph` step must have compile coverage:
   - `compile_after: true`, or
   - blueprint path included in plan `compile_blueprints`.
4. Treat deterministic graph analysis contradictions as hard failures.
5. Do not accept a run as complete until compile + analysis checks pass.

## Recommended Run Path

1. `POST /api/command` with:
   - explicit `recipe_id` when the intent matches an existing recipe, or
   - strong `goal_context` for LLM plan mode.
   - `profile: strict` for production loop generation.
2. Execute once in `dry_run=true`.
3. Execute with `dry_run=false` only after dry-run success.
4. Verify result:
   - `inspect_compile_errors` on every mutated blueprint.
   - `analyze_blueprint_graph` and fail on contradictions.
   - optional `run_pie_scenario` / `assert_world_state` for gameplay-loop assertions.
5. For autonomous mutate loops, run:
   - `POST /api/autonomous-loop-run` for compile + contradiction + scenario + multiplayer + perf/rpc gates.
   - `POST /api/pie-replay-suite` for deterministic replay evidence over repeated runs.

## Refactor / Explain / Intelligence Path

Use deterministic parity endpoints in this order:

1. `POST /api/refactor-catalog`
2. `POST /api/refactor-preview` (`dry_run=true`)
3. `POST /api/refactor-apply` (after preview acceptance)
4. `POST /api/explain-selection` or `POST /api/explain-screenshot`
5. `POST /api/project-dependencies`
6. `POST /api/perf-hotspots`
7. `POST /api/impact-analysis`
8. `POST /api/native-asset-authoring-workflow` when authoring BT/Blackboard/EQS/AnimBP/Material/Niagara/LevelSequence assets.

Guardrails:

- Keep contradiction blocking enabled.
- Keep compile coverage checks enabled.
- Keep `profile=strict` when applying transforms in production assets.
- Keep `auto_verify_after_mutation=true` and `auto_verify_enforce_pass=true` in settings for fail-fast mutation gates.

## Required Context Quality

Low-context prompts produce low-confidence graph structures. Supply explicit context keys.

Use this minimum context contract for Blueprint graph work:

```json
{
  "blueprint_path": "/Game/Gameplay/BP_LoopController",
  "asset_name": "BP_LoopController",
  "package_path": "/Game/Gameplay",
  "parent_class": "/Script/Engine.Actor",
  "variable_name": "LoopState",
  "variable_type": "string",
  "default_value": "Idle",
  "variable_category": "Loop",
  "function_class_path": "/Script/Engine.KismetSystemLibrary",
  "function_name": "PrintString",
  "exec_source": "begin_play",
  "function_inputs": {
    "InString": "Loop initialized"
  }
}
```

If you need branch wiring, include that intent explicitly in the command text (`branch`, `if`, `condition`).

## Strict Blueprint Loop Pattern

For a gameplay loop controller blueprint:

1. Create blueprint.
2. Add loop state and progression variables.
3. Add branch gate(s) on execution source.
4. Add deterministic function calls with explicit inputs.
5. Compile.
6. Analyze graph for contradictions.
7. Run scenario assertions.

## Cursor / IDE Example

Dry run:

```bash
python3 tools/ide_unreal_agent.py run-command \
  --command "Create a blueprint loop controller with state variable, branch gate, and init print" \
  --goal-context-json '{"asset_name":"BP_LoopController","package_path":"/Game/Gameplay","parent_class":"/Script/Engine.Actor","variable_name":"LoopState","variable_type":"string","default_value":"Idle","function_class_path":"/Script/Engine.KismetSystemLibrary","function_name":"PrintString","exec_source":"begin_play","function_inputs":{"InString":"Loop initialized"}}' \
  --profile strict \
  --dry-run --pretty
```

Execute:

```bash
python3 tools/ide_unreal_agent.py run-command \
  --command "Create a blueprint loop controller with state variable, branch gate, and init print" \
  --goal-context-json '{"asset_name":"BP_LoopController","package_path":"/Game/Gameplay","parent_class":"/Script/Engine.Actor","variable_name":"LoopState","variable_type":"string","default_value":"Idle","function_class_path":"/Script/Engine.KismetSystemLibrary","function_name":"PrintString","exec_source":"begin_play","function_inputs":{"InString":"Loop initialized"}}' \
  --profile strict \
  --pretty
```

Verify compile:

```bash
python3 tools/ide_unreal_agent.py direct-execute \
  --action inspect_compile_errors \
  --payload-json '{"blueprint_path":"/Game/Gameplay/BP_LoopController"}' \
  --pretty
```

Verify deterministic graph analysis:

```bash
python3 tools/ide_unreal_agent.py direct-execute \
  --action analyze_blueprint_graph \
  --payload-json '{"blueprint_path":"/Game/Gameplay/BP_LoopController","graph_name":"EventGraph"}' \
  --pretty
```

Run the sky platform objective loop recipe directly:

```bash
python3 tools/ide_unreal_agent.py run-command \
  --command "Create a sky platform environment with jump platforms and 5 objectives to capture." \
  --profile strict \
  --dry-run \
  --pretty
```

## Current Guardrails In This Repo

- Web plan validation now enforces compile coverage when `compile_after=false` is used in graph mutations.
- `set_default` validation supports both:
  - variable defaults (`variable_name`), and
  - function pin defaults (`class_path` + `function_name`).
- Unsupported graph operation payloads are rejected before execution.

## UE Documentation Anchors

- Blueprint best practices: event-driven flow, avoiding heavy tick usage.  
  <https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprint-best-practices-in-unreal-engine>
- Blueprint communication patterns (direct, interfaces, dispatchers).  
  <https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprint-communication-usage-in-unreal-engine>
- Blueprint technical guidance.  
  <https://dev.epicgames.com/documentation/en-us/unreal-engine/technical-guide-for-blueprints-visual-scripting-in-unreal-engine>
- C++ vs Blueprint role boundaries.  
  <https://dev.epicgames.com/documentation/en-us/unreal-engine/coding-in-unreal-engine-blueprint-vs-cplusplus>
- Gameplay framework role constraints (GameMode/GameState/GameInstance).  
  <https://dev.epicgames.com/documentation/en-us/unreal-engine/gameplay-framework-in-unreal-engine>
- Replication fundamentals for gameplay correctness.  
  <https://dev.epicgames.com/documentation/en-us/unreal-engine/replication-system>
