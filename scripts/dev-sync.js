#!/usr/bin/env node
/**
 * dev-sync.js — sync dev changes to the live installed server.
 *
 * Reads PYTHONPATH from ~/.claude/settings.json (written there by install.py),
 * so it always targets the correct installed location regardless of npm version
 * or _npx cache hash. No hardcoding.
 *
 * Usage:
 *   npm run dev:sync
 */

const fs   = require('fs');
const path = require('path');
const os   = require('os');

// ── Find the installed server path from settings.json ────────────────────────

function findInstalledPath() {
  const candidates = [
    path.join(os.homedir(), '.claude', 'settings.json'),
    path.join(os.homedir(), 'AppData', 'Roaming', 'Claude', 'settings.json'),
  ];

  for (const candidate of candidates) {
    if (!fs.existsSync(candidate)) continue;
    try {
      const settings = JSON.parse(fs.readFileSync(candidate, 'utf8'));
      const pythonpath =
        settings?.mcpServers?.agent101?.env?.PYTHONPATH;
      if (pythonpath && fs.existsSync(pythonpath)) {
        return pythonpath;
      }
    } catch (_) { /* malformed — skip */ }
  }
  return null;
}

// ── Files and directories to sync ────────────────────────────────────────────

const DEV_ROOT = path.join(__dirname, '..');

const SYNC_FILES = [
  'server/tools/harness.py',
  'server/tools/security.py',
  'server/tools/executor.py',
  'server/tools/registry.py',
];

const SYNC_DIRS = [
  'skills',
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function copyFile(src, dst) {
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.copyFileSync(src, dst);
}

function syncDir(srcDir, dstDir) {
  if (!fs.existsSync(srcDir)) return 0;
  let count = 0;
  for (const entry of fs.readdirSync(srcDir, { withFileTypes: true })) {
    const srcPath = path.join(srcDir, entry.name);
    const dstPath = path.join(dstDir, entry.name);
    if (entry.isDirectory()) {
      count += syncDir(srcPath, dstPath);
    } else {
      copyFile(srcPath, dstPath);
      count++;
    }
  }
  return count;
}

// ── Main ──────────────────────────────────────────────────────────────────────

const installed = findInstalledPath();

if (!installed) {
  console.error('❌  Could not find installed server path in ~/.claude/settings.json');
  console.error('    Run: npx tylor-mcp  to install first.');
  process.exit(1);
}

console.log(`🎯  Target: ${installed}\n`);

let total = 0;

for (const rel of SYNC_FILES) {
  const src = path.join(DEV_ROOT, rel);
  const dst = path.join(installed, rel);
  if (!fs.existsSync(src)) {
    console.warn(`⚠️   skip (not found): ${rel}`);
    continue;
  }
  copyFile(src, dst);
  console.log(`  ✓  ${rel}`);
  total++;
}

for (const rel of SYNC_DIRS) {
  const src = path.join(DEV_ROOT, rel);
  const dst = path.join(installed, rel);
  const n = syncDir(src, dst);
  if (n > 0) {
    console.log(`  ✓  ${rel}/ (${n} files)`);
    total += n;
  }
}

console.log(`\n✅  ${total} file(s) synced. Restart Claude Code to pick up changes.`);
