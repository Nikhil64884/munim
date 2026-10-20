"""
Munim Ji AI — Entry point.

Usage:
    python run.py
    # or in production:
    uvicorn app.main:app --host 0.0.0.0 --port 8000

Notes:
    - Adds the project root to sys.path so `app.main` imports reliably
      even when the script is invoked from a different working directory.
    - reload=False is correct for production. Set ENV=dev + reload=True
      for local development if you want auto-reload.
"""

import os
import sys

import uvicorn
from dotenv import load_dotenv

load_dotenv()

# ---- Windows console UTF-8 fix ----
if sys.platform == "win32":
    import io
    if True:          # Only apply fix when connected to a console
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if True:          # Only apply fix when connected to a console
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---- Ensure project root is on sys.path ----
# This makes `import app.main` work even if you run this script from
# another folder, or from an IDE with a different working directory.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main() -> None:
    """Start the FastAPI server."""
    # Auto-reload only in dev. Production uses reload=False.
    env = os.environ.get("ENV", "dev").lower()
    reload = env == "dev" and os.environ.get("RELOAD", "1") == "1"

    # Allow override via env vars for flexibility (Docker, PaaS, etc.)
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    log_level = os.environ.get("LOG_LEVEL", "info").lower()

    print(f"🚀 Starting Munim Ji AI on http://{host}:{port} (reload={reload})")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
