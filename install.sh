#!/bin/bash
# One-time setup for the Chromebook (Crostini/Linux) desktop launcher.
# Run this once after cloning the repo:
#
#     ./install.sh
#
# It installs the one Python dependency, creates/seeds the database if
# needed, and registers a "Classroom Jeopardy" entry in your Chromebook's
# app launcher. Safe to re-run any time (e.g. after a `git pull`).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$APPS_DIR/jeopardy.desktop"

echo "Installing Python dependencies..."
if ! command -v pip3 >/dev/null 2>&1; then
    echo "pip3 was not found. Install it first, e.g.: sudo apt install python3-pip"
    exit 1
fi
pip3 install --user -r "$SCRIPT_DIR/requirements.txt"

echo "Setting up the database..."
python3 "$SCRIPT_DIR/init_db.py"

echo "Making the launcher script executable..."
chmod +x "$SCRIPT_DIR/launch_app.sh"

echo "Registering the app in your Chromebook's app launcher..."
mkdir -p "$APPS_DIR"
sed "s|__SCRIPT_DIR__|$SCRIPT_DIR|g" "$SCRIPT_DIR/jeopardy.desktop.template" >"$DESKTOP_FILE"

echo
echo "Setup complete!"
echo "Look for 'Classroom Jeopardy' in your Chromebook app launcher within"
echo "about 15 seconds. If it doesn't show up, restart Linux from"
echo "Chrome OS Settings > Linux > Shut down Linux, then reopen a Linux"
echo "terminal once and try again."
