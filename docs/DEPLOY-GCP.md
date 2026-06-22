# Deploy to Google Cloud (Compute Engine)

Run **Conductor OSS + the D&D game frontend** on a single small VM. Best for demos; not production-hardened.

## Architecture

```
Internet → VM (e2-micro)
            ├── conductor server start   → :8080  (Conductor UI + API)
            └── npm start (game-frontend) → :3456  (quest game UI)
```

## 1. Create a GCP project

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. **New project** → e.g. `conductor-quest-demo`
3. Enable billing (e2-micro is [free tier](https://cloud.google.com/free) in eligible regions)

Enable Compute Engine:

```bash
gcloud services enable compute.googleapis.com
```

## 2. Create a VM

**Console:** Compute Engine → VM instances → Create

| Setting | Value |
|---------|--------|
| Name | `conductor-quest` |
| Region | `us-west1`, `us-central1`, or `us-east1` (free-tier eligible) |
| Machine type | `e2-micro` |
| Boot disk | Ubuntu 22.04 LTS, 30 GB |
| Firewall | Allow HTTP + HTTPS (optional) |

**Or with gcloud** (replace `PROJECT_ID`):

```bash
gcloud config set project PROJECT_ID

gcloud compute instances create conductor-quest \
  --zone=us-west1-b \
  --machine-type=e2-micro \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB \
  --tags=conductor-server
```

## 3. Open firewall ports

```bash
gcloud compute firewall-rules create allow-conductor \
  --allow=tcp:8080,tcp:3456 \
  --target-tags=conductor-server \
  --description="Conductor UI and game frontend"
```

> For a public demo, restrict source ranges later (`--source-ranges=YOUR_IP/32`) or put nginx + auth in front.

## 4. SSH into the VM

```bash
gcloud compute ssh conductor-quest --zone=us-west1-b
```

## 5. Install dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y openjdk-21-jdk nodejs npm git curl

# Conductor CLI
curl -fsSL https://raw.githubusercontent.com/conductor-oss/conductor-cli/main/install.sh | sh
echo 'export PATH="$HOME/.conductor-cli/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

java -version    # 21+
conductor --version
```

## 6. Clone the repo

```bash
git clone https://github.com/jcpopdigitalpartners/conductor_oss.git
cd conductor_oss
```

(Use your fork URL if different.)

## 7. Register workflows

```bash
# Conductor server must not be on /mnt/c-style mounts — use Linux home
cd ~/conductor_oss
conductor workflow create dnd_quest_pipeline.json
conductor workflow create job_application_pipeline.json
conductor workflow create workflow.json
```

## 8. Run Conductor as a systemd service

```bash
sudo tee /etc/systemd/system/conductor.service << 'EOF'
[Unit]
Description=Conductor OSS Server
After=network.target

[Service]
Type=simple
User=YOUR_LINUX_USER
WorkingDirectory=/home/YOUR_LINUX_USER
Environment=PATH=/home/YOUR_LINUX_USER/.conductor-cli/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/home/YOUR_LINUX_USER/.conductor-cli/bin/conductor server start
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

Replace `YOUR_LINUX_USER` with `whoami` output, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable conductor
sudo systemctl start conductor
sudo systemctl status conductor
```

First start downloads the server JAR (~430 MB) — wait a few minutes.

Conductor listens on **8080** inside the VM.

## 9. Run the game frontend

```bash
cd ~/conductor_oss/game-frontend
npm install
```

```bash
sudo tee /etc/systemd/system/quest-game.service << 'EOF'
[Unit]
Description=D&D Quest Game Frontend
After=conductor.service
Requires=conductor.service

[Service]
Type=simple
User=YOUR_LINUX_USER
WorkingDirectory=/home/YOUR_LINUX_USER/conductor_oss/game-frontend
Environment=PORT=3456
Environment=PATH=/home/YOUR_LINUX_USER/.conductor-cli/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/bin/npm start
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable quest-game
sudo systemctl start quest-game
```

## 10. Get the external IP

```bash
gcloud compute instances describe conductor-quest \
  --zone=us-west1-b \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

Open in a browser:

| URL | What |
|-----|------|
| `http://EXTERNAL_IP:8080` | Conductor UI — workflows & executions |
| `http://EXTERNAL_IP:3456` | D&D quest game |

## Updates after code changes

```bash
cd ~/conductor_oss && git pull
conductor workflow create dnd_quest_pipeline.json
sudo systemctl restart quest-game
# restart conductor only if server config changed:
# sudo systemctl restart conductor
```

## Optional: Orkes instead of OSS on the VM

Skip Conductor server on the VM; point CLI at Orkes:

```bash
# /etc/systemd/system/quest-game.service — add Environment lines:
Environment=CONDUCTOR_SERVER_URL=https://developer.orkescloud.com/api
Environment=CONDUCTOR_AUTH_KEY=your-key-id
Environment=CONDUCTOR_AUTH_SECRET=your-key-secret
Environment=CONDUCTOR_SERVER_TYPE=Enterprise
```

Do **not** commit secrets to git. Use GCP Secret Manager or instance metadata for production.

## Costs & limits

- **e2-micro**: free tier in US regions (1 per account); always-on demo is usually within free limits
- **Egress**: small for demos; heavy traffic costs money
- **SQLite**: data lives on the VM disk — snapshot the disk or accept loss if the VM is deleted

## Troubleshooting

```bash
# Logs
sudo journalctl -u conductor -f
sudo journalctl -u quest-game -f

# Health
curl -s localhost:8080/api/health
curl -s localhost:3456/api/health

# Re-register workflow
cd ~/conductor_oss && conductor workflow create dnd_quest_pipeline.json
```

## Alternative: Cloud Run (game only)

Cloud Run is **not** a good fit for `conductor server start` (JVM + SQLite). Use Cloud Run only for the **Node game API** if the workflow runs on **Orkes Cloud** instead of OSS on a VM.
