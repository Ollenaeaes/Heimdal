#!/usr/bin/env bash
# SDD Kit — Set permission profile
#
# Usage:
#   .claude/scripts/set-permissions.sh autonomous   # Recommended for SDD
#   .claude/scripts/set-permissions.sh yolo          # Only in containers/VMs
#   .claude/scripts/set-permissions.sh reset         # Back to default (ask for everything)

set -e

PROFILE="${1:-help}"
CONFIGS_DIR="$(dirname "$0")/../configs"
SETTINGS_FILE="$(dirname "$0")/../settings.json"

case "$PROFILE" in
  autonomous)
    cp "$CONFIGS_DIR/settings-autonomous.json" "$SETTINGS_FILE"
    echo "✅ Autonomous mode activated."
    echo ""
    echo "What's auto-approved:"
    echo "  ✓ All file edits and reads"
    echo "  ✓ Test commands (jest, vitest, pytest, go test, cargo test)"
    echo "  ✓ Build and lint commands"
    echo "  ✓ Git operations (add, commit, checkout, branch, diff, status, log)"
    echo "  ✓ File navigation (ls, cat, find, mkdir, cp, mv)"
    echo "  ✓ Package install (npm install, pip install)"
    echo ""
    echo "What's still blocked:"
    echo "  ✗ rm -rf (destructive delete)"
    echo "  ✗ sudo (privilege escalation)"
    echo "  ✗ git push (you push when ready)"
    echo "  ✗ Piping to bash (curl | bash)"
    echo ""
    echo "This is the recommended profile for SDD implementation."
    echo "The agent can implement, test, and commit autonomously."
    echo "You push when you're ready."
    ;;

  yolo)
    echo "⚠️  WARNING: YOLO mode bypasses ALL permission checks."
    echo "   Only use this inside a Docker container or VM."
    echo ""
    read -p "Are you in a container/VM? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
      cp "$CONFIGS_DIR/settings-yolo.json" "$SETTINGS_FILE"
      echo ""
      echo "🔥 YOLO mode activated. All permissions bypassed."
      echo "   Alternatively, launch with: claude --dangerously-skip-permissions"
    else
      echo "Aborted. Use 'autonomous' profile instead — it's fast AND safe."
    fi
    ;;

  reset)
    rm -f "$SETTINGS_FILE"
    echo "✅ Permissions reset to default. Claude will ask before every action."
    ;;

  *)
    echo "SDD Kit — Permission Profiles"
    echo ""
    echo "Usage: .claude/scripts/set-permissions.sh <profile>"
    echo ""
    echo "Profiles:"
    echo "  autonomous  — Auto-approve edits, tests, git, common commands."
    echo "               Blocks: rm -rf, sudo, git push, pipe-to-bash."
    echo "               Recommended for SDD. (You push when ready.)"
    echo ""
    echo "  yolo        — Bypass ALL permissions. Container/VM only."
    echo "               Same as: claude --dangerously-skip-permissions"
    echo ""
    echo "  reset       — Back to default. Ask before everything."
    echo ""
    echo "Tip: You can also press Shift+Tab in Claude Code to cycle:"
    echo "     normal → accept-edits → plan-mode"
    ;;
esac
