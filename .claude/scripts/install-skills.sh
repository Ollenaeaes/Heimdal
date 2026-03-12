#!/usr/bin/env bash
# SDD Kit — Install recommended community skills
#
# These skills are installed at the USER level (~/.claude/skills/)
# so they're available across ALL your projects without bloating any repo.
#
# Run this once per machine:
#   chmod +x .claude/scripts/install-skills.sh
#   .claude/scripts/install-skills.sh
#
# Each skill is optional — comment out any you don't want.

set -e

SKILLS_DIR="$HOME/.claude/skills"
mkdir -p "$SKILLS_DIR"

echo "Installing recommended skills for SDD workflow..."
echo "Target: $SKILLS_DIR"
echo ""

# ─── Anthropic Official Skills ───────────────────────────────────────────────

echo "📦 [1/5] Frontend Design (Anthropic) — UI/UX implementation guidance"
if [ ! -d "$SKILLS_DIR/frontend-design" ]; then
  git clone --depth 1 https://github.com/anthropics/skills.git /tmp/anthropic-skills 2>/dev/null || true
  cp -r /tmp/anthropic-skills/frontend-design "$SKILLS_DIR/frontend-design" 2>/dev/null || echo "  ⚠ Skipped — clone manually from https://github.com/anthropics/skills"
  rm -rf /tmp/anthropic-skills
else
  echo "  ✓ Already installed"
fi

echo "📦 [2/5] MCP Builder (Anthropic) — Build Model Context Protocol servers"
if [ ! -d "$SKILLS_DIR/mcp-builder" ]; then
  git clone --depth 1 https://github.com/anthropics/skills.git /tmp/anthropic-skills 2>/dev/null || true
  cp -r /tmp/anthropic-skills/mcp-builder "$SKILLS_DIR/mcp-builder" 2>/dev/null || echo "  ⚠ Skipped — clone manually from https://github.com/anthropics/skills"
  rm -rf /tmp/anthropic-skills
else
  echo "  ✓ Already installed"
fi

echo "📦 [3/5] Skill Creator (Anthropic) — Create and improve skills"
if [ ! -d "$SKILLS_DIR/skill-creator" ]; then
  git clone --depth 1 https://github.com/anthropics/skills.git /tmp/anthropic-skills 2>/dev/null || true
  cp -r /tmp/anthropic-skills/skill-creator "$SKILLS_DIR/skill-creator" 2>/dev/null || echo "  ⚠ Skipped — clone manually from https://github.com/anthropics/skills"
  rm -rf /tmp/anthropic-skills
else
  echo "  ✓ Already installed"
fi

# ─── Community Skills (High Value for SDD) ───────────────────────────────────

echo "📦 [4/5] Superpowers (obra) — 20+ battle-tested skills including TDD, debugging, planning"
if [ ! -d "$SKILLS_DIR/superpowers" ]; then
  git clone --depth 1 https://github.com/obra/superpowers.git "$SKILLS_DIR/superpowers" 2>/dev/null || echo "  ⚠ Skipped — clone manually from https://github.com/obra/superpowers"
else
  echo "  ✓ Already installed"
fi

echo "📦 [5/5] VibeSec — Security-first coding, prevents common vulnerabilities"
if [ ! -d "$SKILLS_DIR/vibesec" ]; then
  git clone --depth 1 https://github.com/BehiSecc/vibesec.git "$SKILLS_DIR/vibesec" 2>/dev/null || echo "  ⚠ Skipped — clone manually from https://github.com/BehiSecc/vibesec"
else
  echo "  ✓ Already installed"
fi

echo ""
echo "✅ Done! Installed skills are available across all your projects."
echo ""
echo "To verify, run Claude Code and type: /context"
echo "You should see the new skills listed."
echo ""
echo "Optional: Install more skills from these curated lists:"
echo "  https://github.com/travisvn/awesome-claude-skills"
echo "  https://github.com/VoltAgent/awesome-agent-skills"
echo "  https://github.com/jqueryscript/awesome-claude-code"
