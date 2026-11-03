#!/usr/bin/env bash
# ==============================================================================
#                      NOIR ATELIER - LOCAL PLATFORM STARTER
#                     (macOS & Linux: Local Postgres, Backend, UI)
# ==============================================================================

set -e

# Resolve project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=============================================================================="
echo "                     NOIR ATELIER - LOCAL PLATFORM"
echo "             (FastAPI Backend :8000 | Frontend :3000 | Local PG)"
echo "=============================================================================="

# 1. Check or initialize .env
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "[*] .env not found. Creating from .env.example..."
        cp .env.example .env
        echo "[OK] Created .env"
    else
        echo "[!] ERROR: Neither .env nor .env.example found."
        exit 1
    fi
fi

# 2. Check Python
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "[!] ERROR: Python 3 is not installed or not in PATH."
    exit 1
fi
echo "[OK] $($PYTHON_CMD --version) detected."

# 3. Check Local PostgreSQL (Port 5432)
echo "[*] Checking local PostgreSQL on port 5432..."
if command -v nc >/dev/null 2>&1; then
    if nc -z 127.0.0.1 5432 2>/dev/null; then
        echo "[OK] PostgreSQL port 5432 is accepting connections."
    else
        echo "[WARNING] Port 5432 not responding. Ensure PostgreSQL service is running."
    fi
else
    echo "[INFO] 'nc' utility not installed; skipping port check."
fi

# 4. Cleanup on Exit
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    echo "[*] Shutting down Noir Atelier local services..."
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    echo "[OK] All local processes terminated."
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# 5. Launch Backend Service
echo "[*] Launching FastAPI Backend on http://127.0.0.1:8000 ..."
$PYTHON_CMD -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# 6. Launch Frontend (if initialized)
if [ -f "frontend/apps/storefront/package.json" ]; then
    if command -v npm >/dev/null 2>&1; then
        echo "[*] Launching Next.js Storefront on http://localhost:3000 ..."
        (cd frontend/apps/storefront && [ -d node_modules ] || npm install && npm run dev) &
        FRONTEND_PID=$!
    else
        echo "[INFO] npm not found; skipping storefront auto-start."
    fi
else
    echo "[INFO] Frontend storefront package.json not yet scaffolded."
    echo "       Backend API is live and ready for development."
fi

echo ""
echo "=============================================================================="
echo "[SUCCESS] Services live:"
echo "  - Backend API Docs  : http://127.0.0.1:8000/docs"
echo "  - Backend Health    : http://127.0.0.1:8000/health"
echo "  - Storefront Web    : http://localhost:3000 (when scaffolded)"
echo "Press Ctrl+C to stop all running services."
echo "=============================================================================="
echo ""

# Keep script running to maintain process lifecycle
wait
