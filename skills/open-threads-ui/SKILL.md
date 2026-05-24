---
name: open-threads-ui
description: Open the local agent101 thread visualizer dashboard in the system browser.
---

# /open-threads-ui

Use when the user invokes `/open-threads-ui`, asks to open the thread dashboard, or wants to view live thread and agent activity.

## Workflow

1. Call `open_threads_ui`.
2. Return the tool response exactly enough for the user to know whether the dashboard opened or why it is unavailable.
3. If the UI reports that all ports are unavailable, tell the user to free a port in the reported range and restart the plugin.

## Expected Result

When successful, the command opens the local Thread Visualizer and returns the local URL.

## Error Handling

Use this recovery format exactly.

If opening the UI fails, respond with:

```text
Failed operation: open_threads_ui
Reason: <tool error or unavailable UI message>
Recovery steps:
- Restart Claude Code so the plugin can start the UI server.
- Check whether another process is using the reported localhost port.
- Use `/list-threads` to inspect thread state while the visual dashboard is unavailable.
```
