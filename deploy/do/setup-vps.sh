#!/bin/bash
# [LEGACY — DEPRECATED 2026-06-28] DigitalOcean VPS bootstrap. Retained for archive only.
# MetoCare VPS bootstrap — run once on fresh Ubuntu 24.04 as root
# Usage: curl -sL <url>/setup-vps.sh | bash
# Or: scp setup-vps.sh root@<ip>:~ && ssh root@<ip> bash setup-vps.sh
set -euo pipefail

echo "=== MetoCare VPS Bootstrap ==="
echo "Started: $(date -u)"

# ─── System update ────────────────────────────────────────────────────────────
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y --no-install-recommends \
  curl git ufw fail2ban unzip \
  ca-certificates gnupg lsb-release

# ─── Docker ───────────────────────────────────────────────────────────────────
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -qq
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

systemctl enable docker
systemctl start docker

# Docker Compose v2 alias
ln -sf /usr/libexec/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose
docker compose version

# ─── UFW firewall ─────────────────────────────────────────────────────────────
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   comment "SSH"
ufw allow 80/tcp   comment "HTTP"
ufw allow 443/tcp  comment "HTTPS"
ufw --force enable
ufw status verbose

# ─── fail2ban ─────────────────────────────────────────────────────────────────
systemctl enable fail2ban
systemctl start fail2ban

# ─── Deploy directory ─────────────────────────────────────────────────────────
mkdir -p /opt/metocare
echo "✅ Bootstrap complete. Next: upload deploy files and run deploy.sh"
