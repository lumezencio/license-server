import os
from dotenv import load_dotenv

print("=== System Environment ===")
db_url = os.environ.get("DATABASE_URL")
print(f"DATABASE_URL from os.environ: {db_url}")

print("\n=== After loading .env ===")
load_dotenv(override=True)
db_url = os.environ.get("DATABASE_URL")
print(f"DATABASE_URL after dotenv: {db_url}")

print("\n=== Pydantic Settings ===")
from app.core.config import Settings
s = Settings()
print(f"Settings.DATABASE_URL: {s.DATABASE_URL}")
print(f"Settings.LICENSE_DATABASE_URL: {s.LICENSE_DATABASE_URL}")
print(f"Settings.db_url: {s.db_url}")
