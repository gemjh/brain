#!/usr/bin/env bash
# Quick helper to start a Cloudflare quick tunnel, parse the issued URL from the
# logs, and update the project's .env API_BASE_URL accordingly.
# Usage: ./scripts/update_api_base.sh [local_url]
# Example: ./scripts/update_api_base.sh http://localhost:8000

set -euo pipefail

LOCAL_URL="${1:-http://localhost:8000}"
APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${APP_ROOT}/.env"
LOG_FILE="${APP_ROOT}/cloudflared.log"

echo "[INFO] Starting Cloudflare quick tunnel for ${LOCAL_URL}"
echo "[INFO] Logs: ${LOG_FILE}"

# Start cloudflared in the background and capture logs
cloudflared tunnel --url "${LOCAL_URL}" > "${LOG_FILE}" 2>&1 &
CF_PID=$!

# Wait for the issued quick tunnel URL to appear in the logs
TUNNEL_URL=""
for _ in $(seq 1 30); do
    if TUNNEL_URL=$(grep -m1 -oE 'https://[A-Za-z0-9.-]+\.trycloudflare\.com' "${LOG_FILE}"); then
        break
    fi
    sleep 1
done

if [[ -z "${TUNNEL_URL}" ]]; then
    echo "[ERROR] Failed to detect tunnel URL in logs. Check ${LOG_FILE}."
    exit 1
fi

API_BASE_URL="${TUNNEL_URL}/api/v1"
echo "[INFO] Detected tunnel URL: ${TUNNEL_URL}"
echo "[INFO] Setting API_BASE_URL=${API_BASE_URL} in ${ENV_FILE}"

if grep -q '^API_BASE_URL=' "${ENV_FILE}"; then
    # macOS/BSD sed requires an empty string after -i
    sed -i '' "s|^API_BASE_URL=.*|API_BASE_URL=${API_BASE_URL}|" "${ENV_FILE}"
else
    echo "API_BASE_URL=${API_BASE_URL}" >> "${ENV_FILE}"
fi

echo "[INFO] Tunnel PID: ${CF_PID}"
echo "[INFO] Leave this tunnel running while you test. Stop it with: kill ${CF_PID}"
echo "[INFO] If your app reads .env at startup, restart the API/Streamlit process to pick up the new URL."
