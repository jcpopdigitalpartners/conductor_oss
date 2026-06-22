# conductor_oss

Conductor OSS workflow demos — JSON definitions plus sample inputs.

## Install Conductor CLI

**Prerequisites:** Java 21+ (required for `conductor server start`) and Node.js 16+ (for npm install only).

### WSL / Linux

```bash
# One-line install (recommended)
curl -fsSL https://raw.githubusercontent.com/conductor-oss/conductor-cli/main/install.sh | sh

# Or via npm
npm install -g @conductor-oss/conductor-cli
```

Install Java 21 if needed (Ubuntu/Debian):

```bash
sudo apt update && sudo apt install -y openjdk-21-jdk
java -version   # should show 21+
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/conductor-oss/conductor-cli/main/install.ps1 | iex
# Or: npm install -g @conductor-oss/conductor-cli
```

Install Java 21 from [Adoptium](https://adoptium.net/) if `java` is not in PATH.

### Verify

```bash
conductor --version
conductor server start    # first run downloads the server JAR (~430 MB)
```

Docs: [Conductor quickstart](https://conductor-oss.github.io/conductor/quickstart/) · [conductor-cli](https://github.com/conductor-oss/conductor-cli)

## Workflows

| File | Description |
|------|-------------|
| `workflow.json` | Hello-world: HTTP fetch + INLINE parse |
| `job_application_pipeline.json` | Hiring flow: screen → parallel reviews → manager approval |
| `dnd_quest_pipeline.json` | D&D quest: travel, fork/join scouting, DM crossroads, boss fight |

## Quick start

```bash
# Start server from ~ on WSL (not /mnt/c/ — SQLite fails on Windows mounts)
cd ~
conductor server start

cd /path/to/conductor_oss
conductor workflow create dnd_quest_pipeline.json
conductor workflow start -w dnd_quest_pipeline -f sample_quest_input.json
```

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

## Game frontend (CLI-driven)

A small web UI in `game-frontend/` runs the quest by shelling out to the **Conductor CLI** — start workflow, poll execution, complete the DM HUMAN task.

**Prerequisites:** Conductor server running, workflow registered, Node.js 18+.

### WSL (recommended)

```bash
# Terminal 1 — Conductor server (from ~, not /mnt/c/)
cd ~ && conductor server start

# Terminal 2 — game UI
cd /mnt/c/Users/jobec/projects/conductor_oss/game-frontend
npm install
npm start
```

Open http://localhost:3456

1. Click **Begin quest** → CLI runs `conductor workflow start`
2. Story log fills as tasks complete
3. At **The Crossroads**, pick Stealth / Assault / Parley → CLI runs `conductor task update-execution`
4. Boss fight and epilogue resolve automatically

### Windows Node + WSL conductor

If `conductor` is only installed in WSL:

```powershell
$env:CONDUCTOR_CMD = "wsl conductor"
cd c:\Users\jobec\projects\conductor_oss\game-frontend
npm install
npm start
```

### Orkes Cloud

Load credentials before starting the game server:

```bash
set -a && source /path/to/.env && set +a
export CONDUCTOR_SERVER_TYPE=Enterprise
npm start
```

## UI

http://localhost:8080

## Deploy to Google Cloud

See [docs/DEPLOY-GCP.md](docs/DEPLOY-GCP.md) — run Conductor OSS + the game frontend on a free-tier **Compute Engine e2-micro** VM.
