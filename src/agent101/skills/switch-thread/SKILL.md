---
name: switch-thread
description: Switch the active agent101 thread after listing available threads and asking the user to select one.
---

# /switch-thread

Use when the user invokes `/switch-thread` or asks to switch Tylor threads.

## Workflow

1. Call `list_threads()` first.
2. Show the list with thread name, status, message count, and thread ID.
3. If the user provided a partial or approximate thread name instead of a thread ID, call `switch_thread_by_name(query: str)`.
4. If `switch_thread_by_name` returns `status: ambiguous`, show the `Did you mean` choices and wait for the user's selection.
5. If the user selects from the list by exact thread ID, call `switch_thread(thread_id: str)` with the selected thread ID.
6. Show a formatted confirmation:

```text
Switched thread: <thread_id>
Status: switched
Switched at: <switched_at>
```

## Error Handling

Use this recovery format exactly.

If the tool fails, respond with:

```text
Failed operation: switch_thread
Reason: <tool error>
Recovery steps:
- Run /list-threads to verify available threads.
- Select an exact thread ID from the displayed list or retry with a more specific fuzzy query.
- Create a new thread with /new-thread if no suitable thread exists.
```
