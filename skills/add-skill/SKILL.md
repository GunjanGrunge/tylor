---
name: add-skill
description: Install an agent101 skill package by copying it into skills/ and generating a registry.json entry.
---

# /add-skill

Use when the user invokes `/add-skill` or asks to install a skill package into agent101.

## Workflow

1. Ask for the source path if the user did not provide it.
2. Ask for the skill name if it cannot be inferred from the package `SKILL.md`.
3. If the skill already exists, prompt the user to confirm overwrite before proceeding.
4. Run the installer module:

```text
python3 -m server.tools.skill_installer <source_path> [--name <name>] [--overwrite]
```

5. Confirm the generated `registry.json` entry and install location.

## Error Handling

Use this recovery format exactly.

If the installer fails, respond with:

```text
Failed operation: add_skill
Reason: <installer error>
Recovery steps:
- Verify the source path is a directory.
- Verify the source directory contains SKILL.md.
- If the skill already exists, rerun only after confirming overwrite.
- Check registry.json remains valid JSON.
```
