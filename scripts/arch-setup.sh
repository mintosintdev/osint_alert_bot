#!/usr/bin/env bash
# ── Border Sentinel: Arch Linux setup ──────────────────────────────────────
set -e

echo "=== 1. System dependencies ==="
sudo pacman -S --needed --noconfirm \
  webkit2gtk-4.1 \
  base-devel \
  curl \
  wget \
  file \
  openssl \
  appmenu-gtk-module \
  gtk3 \
  libayatana-appindicator \
  javascriptcoregtk-4.1 \
  xdotool \
  libnotify \
  pkg-config

# Rust (если нет)
if ! command -v rustc &>/dev/null; then
  echo "=== Installing Rust ==="
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  source "$HOME/.cargo/env"
fi

# Node.js (если нет)
if ! command -v node &>/dev/null; then
  echo "=== Installing Node.js ==="
  sudo pacman -S --needed --noconfirm nodejs npm
fi

echo "=== 2. Tauri CLI ==="
npm install

echo "=== 3. Check versions ==="
rustc --version
cargo --version
node --version
npm --version

echo ""
echo "✅ Setup complete! Now run:"
echo "   npm run build:backend   # Build Python sidecar"
echo "   npm run dev             # Dev mode"
echo "   npm run build           # Release build"
