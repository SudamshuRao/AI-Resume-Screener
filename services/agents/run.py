"""
Render entry-point for the agent service (native Python runtime).

Adds the services/ directory to sys.path so the 'agents' package is
importable, then starts uvicorn.
"""
import os
import sys

# services/ dir → makes 'agents' importable as a top-level package
_services_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _services_dir)

import uvicorn  # noqa: E402 — must come after sys.path fix

uvicorn.run("agents.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8001")))