#!/usr/bin/env bash
# iOS 17+ REAL cihazlar ucun RemoteXPC tunnel.
# SUDO PAROL TELEB EDIR. Bu pencereni aciq saxla.
set -e

export PATH="$HOME/.local/node-current/bin:$PATH"
export DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer"

echo "RemoteXPC tunnel yaradilir (sudo parol soruşacaq)..."
echo "(dayandirmaq ucun Ctrl+C)"

exec sudo -E appium driver run xcuitest tunnel-creation
