---
name: kill-thread
description: Close an agent101 thread with kill_thread and confirm that async summarization has started.
---

# /kill-thread

Use when the user invokes `/kill-thread` or asks to close, kill, archive, or summarize a Tylor thread.

## Workflow

1. If the user did not provide a thread ID, call `list_threads()` and ask which active thread to kill.
2. Call `kill_thread(thread_id: str)`.
3. Show a formatted confirmation:

```text
Killing thread: <thread_id>
Status: killing
Message: Summarization in progress
```

## Error Handling

Use this recovery format exactly.

If the tool fails, respond with:

```text
Failed operation: kill_thread
Reason: <tool error>
Recovery steps:
- Run /list-threads and verify the thread ID.
- Retry /kill-thread with an active thread ID.
- If summarization fails later, the fallback summary will store raw last messages.
```
