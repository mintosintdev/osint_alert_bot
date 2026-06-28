#!/usr/bin/env bash
# ── Border Sentinel: Build Python sidecar with PyInstaller ──────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."
BACKEND_DIR="$ROOT/backend"
DIST_DIR="$BACKEND_DIR/dist"

echo "🔧 Building Python backend with PyInstaller..."
echo "   Backend dir: $BACKEND_DIR"

cd "$BACKEND_DIR"

# Create venv if not exists
if [ ! -d ".venv" ]; then
  echo "📦 Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# Install dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet

# Read Tauri target triple
TARGET=$(rustc -Vv | grep host | cut -d' ' -f2)
echo "🎯 Target triple: $TARGET"

# Build with PyInstaller
echo "🚀 Running PyInstaller..."
pyinstaller \
  --onefile \
  --name "backend" \
  --distpath "$DIST_DIR" \
  --workpath "$BACKEND_DIR/build" \
  --specpath "$BACKEND_DIR" \
  --hidden-import=uvicorn.logging \
  --hidden-import=uvicorn.loops \
  --hidden-import=uvicorn.loops.auto \
  --hidden-import=uvicorn.protocols \
  --hidden-import=uvicorn.protocols.http \
  --hidden-import=uvicorn.protocols.http.auto \
  --hidden-import=uvicorn.protocols.websockets \
  --hidden-import=uvicorn.protocols.websockets.auto \
  --hidden-import=uvicorn.lifespan \
  --hidden-import=uvicorn.lifespan.on \
  --hidden-import=aiohttp \
  --hidden-import=groq \
  --hidden-import=sqlite3 \
  --collect-all groq \
  --collect-all aiohttp \
  backend.py

# Rename to include target triple (Tauri sidecar requirement)
BINARY="$DIST_DIR/backend"
RENAMED="$DIST_DIR/backend-$TARGET"

if [ -f "$BINARY" ]; then
  cp "$BINARY" "$RENAMED"
  echo "✅ Binary built: $RENAMED"
else
  echo "❌ Build failed — binary not found"
  exit 1
fi

# Also copy .env if exists
if [ -f "$ROOT/.env" ]; then
  cp "$ROOT/.env" "$DIST_DIR/.env"
  echo "📋 .env copied to dist"
fi

deactivate
echo ""
echo "✅ Backend build complete!"
echo "   Binary: $RENAMED"
echo ""
echo "Now run: npm run build (or tauri build)"
