#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if command -v nvm >/dev/null; then nvm use 22; elif [ -f "$HOME/.nvm/nvm.sh" ]; then source "$HOME/.nvm/nvm.sh"; nvm use 22; fi
command -v ffmpeg >/dev/null || { echo 'Pasang ffmpeg: sudo apt install ffmpeg'; exit 1; }
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock.txt
npm --prefix apps/web ci
test -f .env || cp .env.example .env
echo 'Isi .env, kemudian jalankan npm run dev.'
