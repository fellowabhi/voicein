#!/usr/bin/env bash
# Create a named Cloudflare tunnel for voice.rasdine.com → localhost:8765
set -euo pipefail

HOSTNAME="${VOICEIN_WEB_HOST:-voice.rasdine.com}"
TUNNEL_NAME="${VOICEIN_TUNNEL_NAME:-voicein}"
CF_DIR="${HOME}/.cloudflared"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is not installed. Install: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/"
  exit 1
fi

mkdir -p "${CF_DIR}"

if [[ ! -f "${CF_DIR}/cert.pem" ]]; then
  echo "Opening Cloudflare login in a browser (one-time)."
  echo "Authorize the rasdine.com zone, then re-run this script."
  cloudflared tunnel login
fi

if ! cloudflared tunnel list 2>/dev/null | grep -q "${TUNNEL_NAME}"; then
  cloudflared tunnel create "${TUNNEL_NAME}"
fi

TUNNEL_ID="$(cloudflared tunnel list -o json 2>/dev/null | python3 -c "
import json,sys
rows=json.load(sys.stdin)
for row in rows:
    if row.get('name')=='${TUNNEL_NAME}':
        print(row['id']); break
" || true)"

if [[ -z "${TUNNEL_ID}" ]]; then
  # older cloudflared has no -o json
  TUNNEL_ID="$(cloudflared tunnel list | awk -v n="${TUNNEL_NAME}" '$0 ~ n {print $1; exit}')"
fi

if [[ -z "${TUNNEL_ID}" ]]; then
  echo "Could not find tunnel id for ${TUNNEL_NAME}"
  cloudflared tunnel list
  exit 1
fi

CRED="${CF_DIR}/${TUNNEL_ID}.json"
if [[ ! -f "${CRED}" ]]; then
  echo "Missing credentials file ${CRED}"
  exit 1
fi

cat >"${CF_DIR}/voicein.yml" <<EOF
tunnel: ${TUNNEL_ID}
credentials-file: ${CRED}

ingress:
  - hostname: ${HOSTNAME}
    service: http://127.0.0.1:8765
  - service: http_status:404
EOF

echo "Wrote ${CF_DIR}/voicein.yml"

if cloudflared tunnel route dns "${TUNNEL_NAME}" "${HOSTNAME}"; then
  echo "DNS: ${HOSTNAME} → tunnel ${TUNNEL_NAME}"
else
  echo "Could not create DNS automatically. In Cloudflare → rasdine.com → DNS add:"
  echo "  Type: CNAME"
  echo "  Name: voice"
  echo "  Target: ${TUNNEL_ID}.cfargotunnel.com"
  echo "  Proxy: ON (orange cloud)"
fi

UNIT="${HOME}/.config/systemd/user/cloudflared-voicein.service"
mkdir -p "${HOME}/.config/systemd/user"
cat >"${UNIT}" <<EOF
[Unit]
Description=Cloudflare tunnel for VoiceIn (${HOSTNAME})
After=network-online.target

[Service]
Type=simple
ExecStart=$(command -v cloudflared) tunnel --config ${CF_DIR}/voicein.yml run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now cloudflared-voicein.service
echo "Tunnel service enabled. Test: https://${HOSTNAME}"
