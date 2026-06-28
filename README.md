# Border Sentinel — Desktop App (Tauri v2)

OSINT monitoring desktop application. FastAPI backend + OSINTRadar frontend wrapped in Tauri v2.

## Stack

- **Frontend**: HTML/CSS/JS (Material You dark theme)
- **Backend**: Python FastAPI + SearXNG + Groq (Llama 3.3 70B)
- **Desktop**: Tauri v2 (Rust)
- **Packaging**: PyInstaller → Tauri sidecar

---

## Prerequisites (Arch Linux)

```bash
# Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Tauri system deps
sudo pacman -S --needed \
  webkit2gtk-4.1 base-devel curl wget file \
  openssl appmenu-gtk-module \
  gtk3 libayatana-appindicator

# Node.js (for Tauri CLI)
sudo pacman -S nodejs npm

# Python
sudo pacman -S python python-pip

# Docker (for SearXNG)
sudo pacman -S docker
sudo systemctl enable --now docker
```

## Prerequisites (Windows)

```powershell
# Install Rust from https://rustup.rs
# Install Node.js from https://nodejs.org
# Install Python from https://python.org
# Install WebView2 (usually pre-installed on Win10/11)
```

---

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/mintosintdev/osint_alert_bot
cd osint_alert_bot

# Copy env
cp .env.example .env
# Edit .env with your GROQ_API_KEY
```

### 2. Start SearXNG

```bash
docker run -d \
  --name searxng \
  --restart unless-stopped \
  -p 8304:8080 \
  searxng/searxng:latest
```

### 3. Install Node dependencies

```bash
npm install
```

### 4. Build Python backend (PyInstaller)

```bash
npm run build:backend
# This creates: backend/dist/backend-x86_64-unknown-linux-gnu
```

### 5. Run in dev mode

```bash
# Option A: Dev mode (auto-starts backend sidecar)
npm run dev

# Option B: Manual (backend separately for debugging)
cd backend && python backend.py &
npm run dev
```

### 6. Build production binary

```bash
npm run build:all
# Output: src-tauri/target/release/bundle/
```

---

## API Keys (Keychain)

In production, API keys are stored in the OS keychain (KWallet on Arch, Credential Manager on Windows).

From the Settings page in the app, enter your Groq API key — it will be stored securely and never written to disk in plaintext.

In dev mode, the app falls back to reading from `.env`.

---

## Hotkeys

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+S` | Show window & focus search |
| `Ctrl+Shift+H` | Hide to system tray |
| `Ctrl+Shift+P` | Panic hide (instant) |
| `/` | Focus search bar (in-app) |
| `1-5` | Switch pages (in-app) |
| `E` | Export data (in-app) |

---

## Project Structure

```
border-sentinel/
├── src-tauri/
│   ├── src/
│   │   ├── main.rs          ← Tauri entry point
│   │   └── lib.rs           ← Sidecar, tray, hotkeys, keychain, commands
│   ├── capabilities/
│   │   └── default.json     ← Tauri v2 permissions (minimal)
│   ├── Cargo.toml
│   ├── build.rs
│   └── tauri.conf.json      ← App config + sidecar path
├── src/
│   ├── index.html           ← OSINTRadar dashboard
│   └── tauri-bridge.js     ← JS ↔ Rust bridge
├── backend/
│   ├── backend.py           ← FastAPI server
│   ├── requirements.txt
│   └── dist/               ← PyInstaller output (gitignored)
├── scripts/
│   └── build_backend.sh    ← PyInstaller build script
├── .env.example
└── package.json
```

---

## Author

**Alexander Mints** — OSINT Engineer · AI Developer · [GitHub](https://github.com/mintosintdev)
