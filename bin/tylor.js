#!/usr/bin/env node
const { spawnSync, execSync } = require('child_process');
const path = require('path');
const https = require('https');
const fs = require('fs');

// ── Update check ──────────────────────────────────────────────────────────────
function checkForUpdate() {
    try {
        const pkgPath = path.join(__dirname, '..', 'package.json');
        const localPkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
        const localVersion = localPkg.version;
        const pkgName = localPkg.name;

        const url = `https://registry.npmjs.org/${pkgName}/latest`;
        const req = https.get(url, { timeout: 3000 }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    const latest = JSON.parse(data).version;
                    if (latest && latest !== localVersion) {
                        console.log('');
                        console.log(`  ⚠️  Update available: ${localVersion} → ${latest}`);
                        console.log(`  Run: npm update -g ${pkgName}  (or npx ${pkgName}@latest)`);
                        console.log('');
                    }
                } catch (_) { /* silent */ }
            });
        });
        req.on('error', () => { /* silent — offline or registry down */ });
        req.on('timeout', () => { req.destroy(); });
    } catch (_) { /* silent */ }
}

checkForUpdate();

// ── Installer ─────────────────────────────────────────────────────────────────
const installPy = path.join(__dirname, '..', 'install.py');
const args = process.argv.slice(2);

console.log("👔 Running Tylor Installer...");

// Try `python` first (standard on Windows and some Unix systems)
let result = spawnSync('python', [installPy, ...args], { stdio: 'inherit' });

// Fallback to `python3` if `python` fails (standard on macOS/Linux)
if (result.error || result.status !== 0) {
    result = spawnSync('python3', [installPy, ...args], { stdio: 'inherit' });

    if (result.error) {
        console.error("❌ Failed to launch the Tylor installer. Please ensure Python 3.8+ is installed on your system.");
        process.exit(1);
    }
}

process.exit(result.status);
