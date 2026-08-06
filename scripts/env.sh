#!/usr/bin/env bash
# Umumi mühit deyiskenleri. Istifade:  source scripts/env.sh
export PATH="$HOME/.local/node-current/bin:$HOME/Library/Android/sdk/platform-tools:$PATH"
export ANDROID_HOME="$HOME/Library/Android/sdk"
export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
export DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer"

# Appium client / playwright bu Python-da qurulub (sistem python3 (3.14) qebul etmir)
export PY="/usr/bin/python3"
