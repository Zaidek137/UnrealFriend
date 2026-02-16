# Web Tool And IDE Integration

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
- `GET /api/info`
- `GET /api/state`
- `GET /api/actions`
- `GET /api/recipes`
- `GET /api/release-metrics`
- `GET /api/approvals`
- `POST /api/settings`
- `POST /api/approve`
- `POST /api/direct-execute`
- `POST /api/run-plan`
- `POST /api/run-goal`
- `POST /api/run-recipe`
- `POST /api/validate-recipe`
- `POST /api/run-scenario`
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
- `approve --approval-token ...`
- `run-command`
- `run-goal`
- `run-plan`
- `run-recipe`
- `validate-recipe`
- `run-scenario`
- `direct-execute`

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
