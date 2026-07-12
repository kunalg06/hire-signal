#!/usr/bin/env bash
set -euo pipefail

# One-time provisioning for hire-signal on an Oracle Cloud "Always Free"
# Ampere A1 VM running Oracle Linux 9 (recommended over OL10 here: it's the
# combo Docker's own upstream repo actively supports for RHEL-family hosts;
# OL10 is too new for that to be reliably verified yet).
#
# Prerequisites done in the OCI console BEFORE running this script:
#   1. Compute instance created (Ampere A1, Always Free eligible shape,
#      Oracle Linux 9 image), with a public IP and an SSH key pair.
#   2. Ingress rules added to the instance's subnet Security List:
#      TCP 8000 (dashboard) and TCP 7100-7900 (candidate containers),
#      source 0.0.0.0/0. Port 22 is open by default on quick-create.
#
# Usage (run over SSH on the VM, as the default opc user):
#   bash deploy/oracle_setup.sh [repo-url]

REPO_DIR="$HOME/hire-signal"
REPO_URL="${1:-https://github.com/kunalg06/hire-signal.git}"

echo "==> Installing system packages"
sudo dnf install -y git curl python3.11

echo "==> Installing Docker CE (Docker's official RHEL-family repo)"
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

echo "==> Configuring host firewall (firewalld, not iptables, is the default on Oracle Linux)"
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --permanent --add-port=7100-7900/tcp
sudo firewall-cmd --reload

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
uv venv --no-managed-python --python python3.11
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
  2. Log out/in once (or run 'newgrp docker') so your own shell picks up
     docker-group membership if you want to run `docker` commands directly
     — the systemd service itself doesn't need this, it reads group
     membership fresh at start.
  3. Start the app:   sudo systemctl start hire-signal
  4. Check status:    sudo systemctl status hire-signal
  5. Tail logs:       journalctl -u hire-signal -f
  6. Open http://<vm-public-ip>:8000 in a browser.

Note: SELinux is enforcing by default on Oracle Linux. The guarded-mode
bind mounts in app/services/docker_service.py already carry the :Z
relabel flag needed for this, so no extra SELinux config should be
required — if a guarded-mode container's Gemini CLI still can't read its
mounted GEMINI.md, check `sudo ausearch -m avc -ts recent` for denials.
EOF
