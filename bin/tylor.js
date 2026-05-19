#!/usr/bin/env node
const { spawnSync } = require('child_process');
const path = require('path');

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
