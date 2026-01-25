"""
Migration 001: Add vision extraction fields to crawl_attempts table.

Adds:
- vision_confidence (REAL): Vision model confidence score (0-1)
- fusion_method (TEXT): Extraction method (fused, vision_only, dom_only)
- extraction_time_ms (REAL): Time for vision-DOM fusion

Run: python -m spider_nix.ml.migrations.001_add_vision_fields
"""

import asyncio
import aiosqlite
from pathlib import Path


async def migrate(db_path: str | Path = "feedback.db"):
    """
    Add vision fields to existing database.
    
    Args:
        db_path: Path to feedback.db
    """
    db_path = Path(db_path)
    
    if not db_path.exists():
        print(f"Database {db_path} does not exist - skipping migration")
        return
    
    print(f"Migrating {db_path}...")
    
    async with aiosqlite.connect(db_path) as db:
        # Check if columns already exist
        cursor = await db.execute("PRAGMA table_info(crawl_attempts)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # Add vision_confidence if missing
        if "vision_confidence" not in column_names:
            print("  Adding column: vision_confidence")
            await db.execute("ALTER TABLE crawl_attempts ADD COLUMN vision_confidence REAL")
        
        # Add fusion_method if missing
        if "fusion_method" not in column_names:
            print("  Adding column: fusion_method")
            await db.execute("ALTER TABLE crawl_attempts ADD COLUMN fusion_method TEXT")
        
        # Add extraction_time_ms if missing
        if "extraction_time_ms" not in column_names:
            print("  Adding column: extraction_time_ms")
            await db.execute("ALTER TABLE crawl_attempts ADD COLUMN extraction_time_ms REAL")
        
        # Create indexes
        print("  Creating indexes...")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_fusion_method ON crawl_attempts(fusion_method)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_vision_confidence ON crawl_attempts(vision_confidence)")
        
        await db.commit()
    
    print(f"✓ Migration complete: {db_path}")


if __name__ == "__main__":
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else "feedback.db"
    asyncio.run(migrate(db_path))
