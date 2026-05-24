---
name: help-agent101
description: Show a current structured listing of agent101 commands, tools, skills, personas, and ECC categories.
---

# /help-agent101

Use when the user invokes `/help-agent101` or asks what agent101 can do.

## Workflow

1. Call `help_agent101` to get the current capability index.
2. Present the result in these sections:
   - Slash commands
   - Tier 1 MCP tools
   - Registered skill packages
   - Available personas
   - ECC tool categories
3. Keep the output concise. Include command/tool names and one-line descriptions only.
4. If the user asks for installed skills specifically, call `list_registry`.
5. If the user asks for personas specifically, call `list_personas`.

## Required Coverage

The slash-command section must include:

- `/new-thread`
- `/switch-thread`
- `/kill-thread`
- `/list-threads`
- `/recall`
- `/add-skill`
- `/open-threads-ui`
- `/run`

## Error Handling

Use this recovery format exactly.

If capability discovery fails, respond with:

```text
Failed operation: help_agent101
Reason: <tool error>
Recovery steps:
- Try `list_registry` to inspect installed skills.
- Try `list_personas` to inspect available personas.
- Check registry.json remains valid JSON.
```
