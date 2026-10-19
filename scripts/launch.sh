#!/usr/bin/env bash
set -euo pipefail
cd /home/fahmy_root/projects/video_clipping
source "$HOME/.nvm/nvm.sh"
nvm use 22 >/dev/null
exec npm run dev
