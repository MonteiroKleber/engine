#!/bin/bash
export ENGINE_CONSOLE_SESSION_SECRET="8428c38ce4f72c43d54c4cf9a4b004f08438919b7bb1bd7bee5ba5ff4c8d53a4"
export ENGINE_ISE_ADMIN_TOKEN="8ys2YaUvzdZc0sFm7tPsvVisxee362xe5UgSyTj_ZEo"
export ENGINE_ENV=development
export ENGINE_INSTALL_MODE=dev
export ENGINE_AUTH_MODE=dev
export ENGINE_DATA_ROOT="/home/bazari/engine/tmp/acme_data"
export ENGINE_LEDGER_PATH="/home/bazari/engine/tmp/acme_data/ledger/audit_ledger.jsonl"
export PYTHONPATH=src
cd /home/bazari/engine
exec python -m uvicorn engine.api.server:app --host 127.0.0.1 --port 8001
