# Cursor Agent Setup For Unreal (No Terminal Workflow)

This setup gives Cursor chat an MCP tool bridge into Unreal through your existing plugin.

## What Was Added

- MCP server script:
  - `/Users/ericdiaz/Desktop/Unreal Friend/tools/cursor_unreal_mcp.py`
- Cursor MCP config:
  - `/Users/ericdiaz/Desktop/Unreal Friend/.cursor/mcp.json`

## Architecture

1. Cursor Agent calls MCP tools.
2. MCP server calls Unreal Agent Web (`http://127.0.0.1:8787`).
3. Web calls Unreal plugin HTTP bridge (`http://127.0.0.1:47777/unreal-agent/v1`).

Unreal itself does not need native MCP support.

## Required Running Apps

- Unreal Editor project open with plugin enabled.
- Cursor opened in this workspace.

The MCP server can auto-start the web bridge (`UNREAL_AGENT_WEB_AUTOSTART=true`).

## Cursor Steps

1. Open this folder in Cursor:
   - `/Users/ericdiaz/Desktop/Unreal Friend`
2. Reload Cursor window so it re-reads `.cursor/mcp.json`.
3. In Cursor agent chat, verify MCP tool availability (you should see `unreal_chat`, `unreal_run_recipe`, `unreal_validate_recipe`, etc.).

## Primary Tool

Use `unreal_chat` as the default tool for natural-language control.

Example prompt in Cursor chat:

- "Create BP_EnemyScout in /Game/AI/Blueprints, add bool bAggroEnabled default true, then print 'Enemy ready' on BeginPlay."

The agent should call `unreal_chat` and not require manual action names.
`unreal_chat` now routes to deterministic recipes first when intent matches (objective loops, world layout, asset pack setup).

## Available MCP Tools

- `unreal_chat` (natural language; primary)
- `unreal_run_recipe`
- `unreal_validate_recipe`
- `unreal_run_scenario`
- `unreal_debug_traces`
- `unreal_info`
- `unreal_state`
- `unreal_actions`
- `unreal_execute_action` (advanced fallback)

## Notes

- `UNREAL_AGENT_AUTO_APPROVE=true` is enabled in `.cursor/mcp.json` by default.
- If you later want manual approval flow, set it to `false`.
