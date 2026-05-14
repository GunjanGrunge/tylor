---
name: list-threads
description: List agent101 threads by calling list_threads and formatting active, killed, and message_count details.
---

# /list-threads

Use when the user invokes `/list-threads` or asks to show Tylor threads.

## Workflow

1. Call `list_threads()`.
2. Show every returned thread in a compact table:

```text
Name | Thread ID | Status | message_count | Last activity
```

3. Mark `Status: active` rows as Active in the display.
4. If no threads exist, say no threads were found and suggest `/new-thread`.

## Error Handling

Use this recovery format exactly.

If the tool fails, respond with:

```text
Failed operation: list_threads
Reason: <tool error>
Recovery steps:
- Check that the agent101 MCP server is connected.
- Verify storage configuration in ~/.agent101/config.json or server/.env.
- Retry after restarting Claude Code if the MCP connection is stale.
```
