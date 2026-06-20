#!/bin/bash
# enable-https.sh — activate TLS via Let's Encrypt certbot
# Run AFTER DNS A record points to this VPS IP (146.190.83.230)
# Usage: ./enable-https.sh yourdomain.com admin@yourdomain.com
set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"
DEPLOY_DIR="/opt/metocare"

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
  echo "Usage: $0 <domain> <email>"
  echo "Example: $0 metocare.example.com admin@example.com"
  exit 1
fi

echo "=== Enabling HTTPS for $DOMAIN ==="

# Install certbot if needed
if ! command -v certbot &>/dev/null; then
  apt-get install -y certbot python3-certbot-nginx
fi

# Verify DNS resolves to this IP
MY_IP=$(curl -sf https://api.ipify.org 2>/dev/null || echo "unknown")
DNS_IP=$(dig +short "$DOMAIN" 2>/dev/null | tail -1 || echo "unknown")
echo "VPS IP: $MY_IP | DNS resolves to: $DNS_IP"
if [ "$MY_IP" != "$DNS_IP" ]; then
  echo "⚠️  WARNING: DNS does not yet point to this VPS ($MY_IP). Certbot may fail."
  read -p "Continue anyway? [y/N] " CONFIRM
  [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]] && exit 1
fi

# Get cert (webroot mode via /var/www/certbot)
mkdir -p /var/www/certbot
certbot certonly \
  --webroot -w /var/www/certbot \
  -d "$DOMAIN" \
  --email "$EMAIL" \
  --agree-tos \
  --non-interactive

# Write HTTPS nginx config
cat > "$DEPLOY_DIR/nginx.conf" << NGINXCONF
# MetoCare Nginx — HTTPS enabled for ${DOMAIN}
server {
    listen 80;
    server_name ${DOMAIN};
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name ${DOMAIN};

    ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_session_cache   shared:SSL:10m;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    location / {
        proxy_pass         http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
        client_max_body_size 20m;
    }
}
NGINXCONF

# Reload nginx
cd "$DEPLOY_DIR"
docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload
echo "✅ Nginx reloaded with HTTPS config"

# Update CORS in .env
sed -i "s|^MCP_CORS_ALLOWED_ORIGINS=.*|MCP_CORS_ALLOWED_ORIGINS=https://${DOMAIN}|" .env
docker compose restart backend
echo "✅ Backend restarted with CORS=https://$DOMAIN"

# Certbot auto-renew cron
(crontab -l 2>/dev/null | grep -v certbot; \
 echo "0 3 * * * certbot renew --quiet --deploy-hook 'cd /opt/metocare && docker compose exec nginx nginx -s reload'") | crontab -
echo "✅ Certbot auto-renew cron set (03:00 UTC daily)"

echo ""
echo "=== HTTPS active for https://$DOMAIN ==="
curl -sf "https://$DOMAIN/health" && echo "" || echo "Check DNS propagation if curl fails"
