#!/usr/bin/env bash
# smolfiddle fork: guided Termux installer.
# Idempotent — safe to re-run after `pkg upgrade chromium`.
set -u
PREFIX_TERMUX="/data/data/com.termux/files/usr"
if [ ! -d "$PREFIX_TERMUX" ]; then
    echo "ERROR: this script is for Termux on Android ($PREFIX_TERMUX not found)." >&2
    exit 1
fi

echo "==> Installing Termux packages (x11-repo chromium + python)..."
pkg update -y
pkg install -y x11-repo tur-repo
pkg install -y chromium python

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> Installing Python dependencies (no xvfbwrapper)..."
pip install -r "$REPO_ROOT/termux/requirements-termux.txt"

echo "==> Sanity checks..."
CHROME=""
for c in "$PREFIX_TERMUX/lib/chromium/chrome" \
         "$PREFIX_TERMUX/bin/chromium-browser" \
         "$PREFIX_TERMUX/bin/chromium"; do
    if [ -x "$c" ]; then CHROME="$c"; break; fi
done
if [ -z "$CHROME" ]; then
    echo "ERROR: no executable Chromium found under $PREFIX_TERMUX." >&2
    exit 1
fi
echo "Chromium: $CHROME"
"$CHROME" --version || echo "WARN: 'chrome --version' failed (non-fatal)."

DRIVER=""
for d in "$PREFIX_TERMUX/bin/chromedriver" \
         "$PREFIX_TERMUX/lib/chromium/chromedriver"; do
    if [ -x "$d" ]; then DRIVER="$d"; break; fi
done
if [ -z "$DRIVER" ]; then
    echo "WARN: no chromedriver found — reinstall chromium: pkg reinstall chromium." >&2
else
    echo "Chromedriver: $DRIVER"
    "$DRIVER" --version || echo "WARN: 'chromedriver --version' failed (non-fatal)."
fi

echo
echo "OK. Start headless with:"
echo "  HEADLESS=true python \"$REPO_ROOT/src/flaresolverr.py\""
echo "Headed under LXQt/Termux:X11 with:"
echo "  DISPLAY=:0 HEADLESS=false python \"$REPO_ROOT/src/flaresolverr.py\""
