---
name: afk-status
description: Report current AFK execution progress for the active thread.
---

# /afk-status

Use when the developer invokes `/afk-status` or asks whether an AFK session is running.

Call the `afk_status` Tier 1 tool with the active thread unless the user supplies a specific thread id.

If no session is active, show the tool message exactly:

`No AFK session running`

If a session is active, report:
- current step
- steps completed / total
- elapsed time
- last command output
