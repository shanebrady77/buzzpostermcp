"""
Database migration utilities
"""
from .connection import init_db


async def run_migrations():
    """Run database migrations (create tables)"""
    await init_db()
    print("Database migrations completed successfully")
