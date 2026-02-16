# Unreal Agent Web

Local web control plane for Unreal Agent plugin.

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
- Sends natural language commands:
  - LLM plan generation -> `/run-plan` in Unreal, or
  - fallback directly to Unreal `/run-goal`
- Supports direct action execution and raw plan execution
- Adds compatibility checks against Unreal `/info`
- Adds run lock so only one Unreal execution request runs at a time
- Provides chat-first endpoint: `POST /api/chat` (alias of `/api/command`)

## API Endpoints

- `GET /api/health`
- `GET /api/info`
- `GET /api/state`
- `GET /api/actions`
- `GET /api/node-library`
- `GET /api/approvals`
- `POST /api/settings`
- `POST /api/approve`
- `POST /api/direct-execute`
- `POST /api/run-plan`
- `POST /api/run-goal`
- `POST /api/command`
