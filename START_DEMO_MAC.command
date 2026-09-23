#!/bin/bash
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.10 or newer is required. Install Python, then run this file again."
else
    python3 demo_launcher.py
fi
echo
read -r -p "Demo stopped. Press Enter to close this window."
