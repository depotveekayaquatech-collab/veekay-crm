"""Starts the API on :8010 against veekay_load with 2 workers (as in fly.toml). Rate limiting is off: all simulated users share one IP."""
import os
import re
import sys

from dotenv import dotenv_values

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)
os.environ["PYTHONPATH"] = BACKEND   # the spawned workers need it too
base = dotenv_values(os.path.join(BACKEND, ".env"))["DATABASE_URL"]
os.environ.update({
    "DATABASE_URL": re.sub(r"/[^/?]+(\?.*)?$", "/veekay_load", base),
    "ENVIRONMENT": "development", "RATE_LIMIT_ENABLED": "false", "LOG_LEVEL": "WARNING",
    "STORE_SYNC_ENABLED": "false", "ORDER_SYNC_ENABLED": "false", "STORAGE_BACKEND": "local",
    "UPLOAD_DIR": os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads"),
    "DB_POOL_SIZE": "10", "DB_MAX_OVERFLOW": "20", "DASHBOARD_CACHE_SECONDS": "30",
})
import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8010, workers=2, log_level="warning")
