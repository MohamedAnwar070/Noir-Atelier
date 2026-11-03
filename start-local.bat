@echo off
setlocal EnableDelayedExpansion
title Noir Atelier - Local Platform Starter

echo ==============================================================================
echo                      NOIR ATELIER - LOCAL PLATFORM
echo               (FastAPI Backend :8000 ^| Frontend :3000 ^| Local PG)
echo ==============================================================================

cd /d "%~dp0"

:: 1. Environment File Check
if not exist ".env" (
    if exist ".env.example" (
        echo [*] .env not found. Creating from .env.example...
        copy ".env.example" ".env" >nul
        echo [OK] Created .env
    ) else (
        echo [!] ERROR: Neither .env nor .env.example found.
        pause
        exit /b 1
    )
)

:: 2. Check Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [!] ERROR: Python is not installed or not in PATH.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version') do echo [OK] %%v detected.

:: 3. Check Local PostgreSQL Connection on Port 5432
echo [*] Checking local PostgreSQL on port 5432...
powershell -NoProfile -Command "try { (New-Object System.Net.Sockets.TcpClient).Connect('127.0.0.1', 5432); exit 0 } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK] Local PostgreSQL service is running and accepting connections on 5432.
) else (
    echo [WARNING] Port 5432 is not responding.
    echo           Please ensure PostgreSQL service is running.
)

:: 4. Start Backend Service in a Dedicated Terminal
echo [*] Launching FastAPI Backend on http://127.0.0.1:8000 ...
start "Noir Atelier - Backend API" cmd /k python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload

:: 5. Start Frontend Service (if initialized) in a Dedicated Terminal
if exist "frontend\apps\storefront\package.json" (
    where npm >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        echo [*] Launching Next.js Storefront on http://localhost:3000 ...
        start "Noir Atelier - Storefront UI" cmd /k "cd frontend\apps\storefront && npm run dev"
    ) else (
        echo [INFO] npm not found; skipping storefront auto-start.
    )
) else (
    echo [INFO] Frontend storefront package.json not yet scaffolded.
    echo        Backend API is live and ready for development.
)

echo.
echo ==============================================================================
echo [SUCCESS] Services launched:
echo   - Backend API Docs  : http://127.0.0.1:8000/docs
echo   - Backend Health    : http://127.0.0.1:8000/health
echo   - Storefront Web    : http://localhost:3000 (when scaffolded)
echo ==============================================================================
echo.
pause
