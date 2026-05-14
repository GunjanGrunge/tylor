---
name: set-sandbox
description: Declare or clear sandbox roots used by agent101 AFK execution tools.
---

# /set-sandbox

Use when the user invokes `/set-sandbox`, asks to allow a project path for AFK execution, or asks to clear executor sandbox paths.

## Workflow

1. Ask for the sandbox path if the user did not provide it.
2. If the user provided `clear`, call `set_sandbox(path="clear")`.
3. Otherwise call `set_sandbox(path="<path>")`.
4. Confirm the returned message and list the current sandbox roots.
5. If the user tries to run execution before any sandbox is set, call `execute_in_sandbox` only when appropriate and surface its no-sandbox error.

## Required Behavior

- Paths must be absolute after `~` expansion and must exist on disk.
- Additional paths append to existing sandbox roots.
- `clear` empties sandbox roots.
- `execute_in_sandbox` must refuse execution until roots are configured.

## Error Handling

Use this recovery format exactly.

If sandbox declaration fails, respond with:

```text
Failed operation: set_sandbox
Reason: <tool error>
Recovery steps:
- Provide an absolute existing path, or use ~/... for a home-relative path.
- Run /switch-thread first if no active thread is set.
- Use /set-sandbox clear to remove all sandbox roots.
```
