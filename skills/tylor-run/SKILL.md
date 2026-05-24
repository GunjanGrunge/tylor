---
name: tylor-run
description: Activate Tylor to handle a task. Routes the request through the full Tylor harness — intent classification, skill auto-loading, multi-agent orchestration, and Bumblebee security scanning. All responses are labelled Tylor: so you always know the plugin is running, not native Claude/Codex/Antigravity.
---

# /Tylor_run

Use when the user invokes `/Tylor_run <task>` or explicitly wants Tylor to handle a request.

## How it works

1. Resolve the active thread ID — call `list_threads()` and pick the most recently active thread, or use one the user has already switched to.
2. Call `run_in_thread(thread_id=<active_thread_id>, message=<user_task>, cwd=<project_dir>)`.
3. Stream the result back exactly as returned — do not paraphrase or summarise it. The response already starts with `Tylor:` so the user can see the plugin is running.

## What Tylor does automatically (no commands needed)

- Classifies intent and selects the right role(s): researcher, implementer, reviewer, planner, drafter
- Auto-loads ECC skill groups (ecc/web, ecc/data, ecc/presentation, ecc/diagrams, ecc/pipeline) based on the task
- Runs a Bumblebee session-start security scan on first use in a thread
- Watches for dependency file changes and scans them inline
- Prompts before git push
- Spawns multiple agents in parallel when the task warrants it
- Streams a live orchestration log so the user can follow what is happening

## Example interactions

```
/Tylor_run research the top 3 CI/CD tools and draft a comparison doc
→ Tylor:
  [agent101] intent classified: researcher, drafter
  [agent101] auto-loaded skill: ecc/web (web_scrape, web_fetch)
  [agent101] auto-loaded skill: ecc/presentation (build_doc)
  [bumblebee] starting session-start package scan...
  [agent: researcher #1] starting — gather CI/CD tool comparisons
  $ web_fetch
  $ web_fetch
  [agent: researcher #1] done
  [agent: drafter #2] starting — build comparison doc from research
  $ build_doc
  [agent: drafter #2] done
  [bumblebee] ✅ session-start scan — no vulnerabilities found
  [supervisor] complete — 2 agents ran

/Tylor_run fix the failing auth tests
→ Tylor:
  [agent101] intent classified: implementer
  [agent: implementer #1] starting — fix failing auth tests
  $ Read
  $ Edit
  $ Bash
  [agent: implementer #1] done
  [supervisor] complete — 1 agent ran
```

## Notes

- The `Tylor:` label at the top of every response confirms the plugin is active — not native Claude Code, Codex, or Antigravity
- Works identically across all supported platforms: Claude Code CLI, Claude Desktop, GitHub Copilot CLI, Antigravity
- If no thread is active, suggest the user run `/new-thread <name>` first
- Pass `cwd` as the current project directory so agents have filesystem context
