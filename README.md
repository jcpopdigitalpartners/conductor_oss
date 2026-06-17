# conductor_oss

Conductor OSS workflow demos — JSON definitions plus sample inputs.

## Workflows

| File | Description |
|------|-------------|
| `workflow.json` | Hello-world: HTTP fetch + INLINE parse |
| `job_application_pipeline.json` | Hiring flow: screen → parallel reviews → manager approval |
| `dnd_quest_pipeline.json` | D&D quest: travel, fork/join scouting, DM crossroads, boss fight |

## Quick start

```bash
# Install CLI + Java 21, then:
conductor server start          # from ~ on WSL, not /mnt/c/...

conductor workflow create dnd_quest_pipeline.json
conductor workflow start -w dnd_quest_pipeline -f sample_quest_input.json
```

**WSL note:** Start the server from a Linux path (`cd ~`). SQLite fails on `/mnt/c/`.

## D&D quest — complete the DM step

The quest pauses at a HUMAN task. Resume with:

```bash
conductor task update-execution \
  --workflow-id <workflow-id> \
  --task-ref-name dm_crossroads_ref \
  --status COMPLETED \
  --output '{"approach":"stealth","dmNotes":"Shadows favored."}'
```

Use `"assault"` or `"parley"` for other paths.

## UI

http://localhost:8080
