#!/usr/bin/env bash
# Tear down the whole topology. Keeps .env (the key) so `up` is idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose down
echo "[down] stopped. (.env kept; delete it to rotate the API key)"
