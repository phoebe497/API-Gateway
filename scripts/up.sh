#!/usr/bin/env bash
# Generate the API key on first run, then bring up the gateway + target.
# The key is created ONCE and stored only in .env (gitignored). The gateway
# reads GATEWAY_API_KEY; the tool reads SAFE_PROBE_API_KEY. Same value, two
# names, because they are two independent processes.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  key="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  {
    echo "GATEWAY_API_KEY=${key}"
    echo "SAFE_PROBE_API_KEY=${key}"
  } > .env
  chmod 600 .env
  echo "[up] generated a fresh API key -> .env"
else
  echo "[up] reusing existing .env key"
fi

echo "[up] building and starting gateway + demo-api ..."
docker compose up -d --build

echo
echo "[up] gateway listening on http://localhost:8080"
echo "[up] load the tool's env in your shell with:"
echo "        set -a; . ./.env; set +a"
