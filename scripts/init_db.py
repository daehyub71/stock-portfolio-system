#!/usr/bin/env python3
"""Database initialization script.

This script creates all database tables based on SQLAlchemy models.
Run this script once to set up the database schema.

Usage:
    python scripts/init_db.py
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.connection import engine, Base, test_connection
from models import (
    Sector,
    Stock,
    DailyPrice,
    FinancialStatement,
    FinancialRatio,
    CorpCodeMap,
)


def init_database():
    """Initialize database by creating all tables."""
    print("=" * 60)
    print("Database Initialization Script")
    print("=" * 60)
    print()

    # Test connection first
    print("Step 1: Testing database connection...")
    if not test_connection():
        print("\n❌ Database connection failed. Please check your .env configuration.")
        print("   Make sure PostgreSQL is running and credentials are correct.")
        sys.exit(1)
    print()

    # Create all tables
    print("Step 2: Creating database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ All tables created successfully!")
        print()

        # List created tables
        print("Created tables:")
        for table_name in Base.metadata.tables.keys():
            print(f"  - {table_name}")
        print()

    except Exception as e:
        print(f"\n❌ Failed to create tables: {e}")
        sys.exit(1)

    print("=" * 60)
    print("✅ Database initialization completed successfully!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Verify tables in TablePlus or psql")
    print("  2. Run data collection scripts to populate the database")
    print("  3. Start building your stock portfolio system!")


if __name__ == "__main__":
    init_database()
