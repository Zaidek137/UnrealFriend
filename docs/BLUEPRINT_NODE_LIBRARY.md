# Blueprint Node Paste Library: What It Is And How To Use It

## What this file is

`NodeDump.txt` is a reverse-engineered reference of Unreal Blueprint node text/paste structure and wiring patterns.

It captures:

- node classes (`K2Node_*`, `UK2Node_*` variants)
- key properties (`FunctionReference`, `MemberGuid`, `GraphGuid`, etc.)
- pin signatures/types/defaults
- common connection patterns (RPC guards, loop wiring, enum checks)

This is useful for agent tooling because it describes how nodes are represented and connected, including common failure points (self-context, GUID sensitivity, macro graph GUIDs, wildcard pin resolution).

## Why it is valuable for your tooling

1. Improves planning quality:
- Agent can reason in terms of valid node/pin patterns before graph mutation.

2. Reduces invalid graph edits:
- Avoids wrong self-context, enum pin typing, and unsupported paste assumptions.

3. Enables deterministic templates:
- Reusable graph recipes can be built from known-good connection patterns.

4. Helps debugging:
- When graph edits fail, compare generated node/pin payloads against reference entries.

## What we implemented in this repo

Canonical storage:
- Raw source: `data/blueprint-node-library/NodeDump.txt`
- Normalized index: `data/blueprint-node-library/node_library_index.json`

Tooling:
- Index/search tool: `tools/blueprint_node_library.py`

Commands:

```bash
python3 tools/blueprint_node_library.py build
python3 tools/blueprint_node_library.py search --q "K2Node_CallFunction"
python3 tools/blueprint_node_library.py search --q "ForEachLoop"
```

## Best way to preserve long-term

1. Keep 3 layers versioned in git:
- raw (`NodeDump.txt`)
- normalized (`node_library_index.json`)
- docs (this file)

2. Track source metadata:
- add where it came from and Unreal version range in commit notes or a sidecar file.

3. Treat as reference, not authority:
- Unreal version updates can invalidate details (pins, class/module paths, GUID behavior).

4. Add periodic revalidation:
- when upgrading UE, run sample graph edits and update this library if any signatures differ.

## Recommended integration pattern

1. Retrieval step before graph mutation:
- search index for target node and expected pins/properties.

2. Plan-time validation:
- ensure operation requirements match available node patterns.

3. Post-edit verification:
- inspect graph inventory and compare expected node classes/pin counts.

## Planner integration (implemented)

The web planner now uses this library in two places:

1. Plan context injection:
- Relevant node/pattern snippets are injected into LLM planning prompts.

2. Pre-execution validation:
- Plans are checked before execution.
- Invalid graph steps are rejected with:
  - `error_code=PLAN_NODELIB_VALIDATION_FAILED`

Endpoints:
- `GET /api/node-library` (index info)
- `GET /api/node-library?q=<term>` (search)

## Practical caveats

- Some entries are context-sensitive (`MemberGuid`, macro graph GUIDs, self-context).
- Some nodes/events are not safely pasteable (`K2Node_Event` note in source).
- Wildcard pins require connected type resolution.

## Next logical upgrade (optional)

- Add a small "graph recipe" catalog (JSON) that maps intents to node sequences:
  - e.g., "BeginPlay -> Branch -> PrintString" recipe with required pin mapping.
- Then let the agent choose a recipe and apply parameterized values.
