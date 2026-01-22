#!/bin/bash
export ENGINE_CONSOLE_SESSION_SECRET="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
export ENGINE_ISE_ADMIN_TOKEN="HR_Admin_Token_2026_Secure_Key_Value"
export ENGINE_ENV=development
export ENGINE_INSTALL_MODE=dev
export ENGINE_AUTH_MODE=dev
export ENGINE_DATA_ROOT="/home/bazari/engine/tmp/hr_data"
export PYTHONPATH=src
cd /home/bazari/engine
exec python -m uvicorn engine.api.server:app --host 127.0.0.1 --port 8001
