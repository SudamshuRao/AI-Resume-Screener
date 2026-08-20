"""
Render entry-point for the API service (native Python runtime).

Adds the services/ directory to sys.path so the 'api' package is
importable, runs alembic migrations, then starts uvicorn.
"""
import os
import subprocess
import sys

# services/ dir → makes 'api' importable as a top-level package
_services_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_api_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _services_dir)

# Run migrations (alembic.ini lives in services/api/)
_env = {**os.environ, "PYTHONPATH": _services_dir}
subprocess.run(["alembic", "upgrade", "head"], cwd=_api_dir, env=_env, check=True)

import uvicorn  # noqa: E402 — must come after sys.path fix

uvicorn.run("api.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))