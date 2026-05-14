---
name: new-thread
description: Create a new agent101 thread by prompting for a thread name and calling the new_thread MCP tool.
---

# /new-thread

Use when the user invokes `/new-thread` or asks to create a new Tylor thread.

## Workflow

1. If the user did not provide a name, prompt for the thread name.
2. Call `new_thread(name: str)` with that exact thread name.
3. Show a formatted confirmation:

```text
Created thread: <name>
Thread ID: <thread_id>
Created at: <created_at>
```

## Error Handling

Use this recovery format exactly.

If the tool fails, respond with:

```text
Failed operation: new_thread
Reason: <tool error>
Recovery steps:
- Choose a unique thread name.
- Use 3-64 characters.
- Use only letters, numbers, spaces, hyphens, and underscores.
```
