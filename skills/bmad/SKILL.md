---
name: bmad
description: Use when the user wants to create a PRD, review stories, or run BMAD workflows.
module: server.tools.ecc.web
tools: ["web_fetch", "web_scrape"]
---

# /bmad

Use when the user wants to create a PRD, review stories, or run BMAD workflows.

This skill package registers the BMAD workflow metadata for automatic detection and lazy-loaded ECC tool usage.

Call `load_skill_tools("bmad")` when this trigger matches.
