---
name: run
description: Run a task in the active thread using the agent harness. Automatically routes to the right specialist (code agent, CTO, analyst, CEO) and activates BMAD workflows based on thread context. Just describe what you need.
---

# /run

Use when the user wants to delegate a task to the right specialist agent for the active thread.

## How it works

1. Call `detect_thread_team(thread_id=<active_thread_id>, message=<user_message>)` to preview which agents will activate
2. Call `run_in_thread(thread_id=<active_thread_id>, message=<user_message>, cwd=<project_dir>)` to execute

## Examples

```
/run check if the frontend is polished
→ Frontend thread → code_agent activates → reads files, checks UI quality

/run design the database schema  
→ Backend thread → cto + code_agent activate → architecture guidance

/run create a PRD for this feature
→ PRD thread → ceo + analyst activate + BMAD PRD workflow silently injected
```

## Notes

- The active thread is the one set by SwThread or CT
- Agents spawn only when the task matches their specialty
- BMAD workflows activate silently based on thread name
- Results stream back directly — no separate session needed
