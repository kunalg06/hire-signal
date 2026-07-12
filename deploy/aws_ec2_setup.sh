#!/usr/bin/env bash
set -euo pipefail

# One-time provisioning for hire-signal on an AWS EC2 instance running
# Ubuntu 24.04 LTS (e.g. t4g.small, Arm64/Graviton2).
#
# Prerequisites done before running this script:
#   1. EC2 instance launched with a public IP.
#   2. Security group allows inbound TCP 22 (SSH), 8000 (dashboard), and
#      7100-7900 (candidate containers) from 0.0.0.0/0.
#
# No host-level firewall step is needed here (unlike Oracle Linux) — the
# EC2 Security Group already gates all inbound traffic at the hypervisor
# level, and stock Ubuntu AMIs ship with ufw installed but inactive.
#
# Usage (run over SSH on the instance, as the default ubuntu user):
#   bash deploy/aws_ec2_setup.sh [repo-url]

REPO_DIR="$HOME/hire-signal"
REPO_URL="${1:-https://github.com/kunalg06/hire-signal.git}"

echo "==> Installing system packages"
sudo apt-get update
sudo apt-get install -y docker.io git curl

sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

echo "==> Installing uv"
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "==> Fetching hire-signal"
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull
else
  git clone "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"

echo "==> Creating virtualenv and installing pinned dependencies"
uv venv --no-managed-python
uv pip sync requirements.txt --python .venv

if [ ! -f .env ]; then
  echo "==> Writing .env (edit GEMINI_API_KEY before starting the service)"
  cat > .env <<EOF
GEMINI_API_KEY=REPLACE_ME
FLASK_ENV=production
SECRET_KEY=$(openssl rand -hex 32)
EOF
fi

echo "==> Building the candidate-container image"
(cd docker && docker build -f Dockerfile.codeserver -t coding-platform-student:latest .)

echo "==> Installing systemd service"
sudo tee /etc/systemd/system/hire-signal.service > /dev/null <<EOF
[Unit]
Description=hire-signal Flask app
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$REPO_DIR
EnvironmentFile=$REPO_DIR/.env
ExecStart=$REPO_DIR/.venv/bin/python run.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable hire-signal

cat <<'EOF'

Setup complete. Remaining steps:
  1. Edit ~/hire-signal/.env and set your real GEMINI_API_KEY.
  2. Start the app:   sudo systemctl start hire-signal
  3. Check status:    sudo systemctl status hire-signal
  4. Tail logs:       journalctl -u hire-signal -f
  5. Open http://<instance-public-ip>:8000 in a browser.
EOF
