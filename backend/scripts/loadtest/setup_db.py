"""Creates a throwaway `veekay_load` database next to the dev one, migrates and seeds it, then loads realistic volume."""
import os
import re
import subprocess
import sys

import psycopg
from dotenv import dotenv_values

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRATCH = os.path.dirname(os.path.abspath(__file__))
base = dotenv_values(os.path.join(BACKEND, ".env"))["DATABASE_URL"]
load_url = re.sub(r"/[^/?]+(\?.*)?$", "/veekay_load", base)
admin_dsn = re.sub(r"/[^/?]+(\?.*)?$", "/postgres", base).replace("postgresql+psycopg://", "postgresql://")

with psycopg.connect(admin_dsn, autocommit=True) as c:
    c.execute('DROP DATABASE IF EXISTS "veekay_load" WITH (FORCE)')
    c.execute('CREATE DATABASE "veekay_load"')
print("database veekay_load created")

env = {**os.environ, "DATABASE_URL": load_url, "ENVIRONMENT": "development", "STORE_SYNC_ENABLED": "false",
       "ORDER_SYNC_ENABLED": "false", "LOG_LEVEL": "WARNING"}
for cmd in (["-m", "alembic", "upgrade", "head"], ["scripts/seed.py"]):
    r = subprocess.run([sys.executable, *cmd], cwd=BACKEND, env=env, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stdout + r.stderr)
print("migrated + seeded")
r = subprocess.run([sys.executable, os.path.join(SCRATCH, "seed_volume.py")], cwd=BACKEND, env=env, text=True)
raise SystemExit(r.returncode)
