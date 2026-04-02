import asyncio
import asyncpg
import os
from backend.config import settings

async def migrate():
    print("Connecting to database...")
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST
    )
    
    try:
        print("Adding columns to pipelines table...")
        await conn.execute("""
            ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS version INT DEFAULT 1;
            ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS description TEXT;
            ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active';
        """)
        
        # Check for existing unique constraint on 'name'
        # In PostgreSQL, it's usually 'pipelines_name_key' if created as UNIQUE
        try:
            await conn.execute("ALTER TABLE pipelines DROP CONSTRAINT IF EXISTS pipelines_name_key CASCADE;")
        except Exception as e:
            print(f"Warning: Could not drop pipelines_name_key: {e}")

        # Add new composite unique constraint
        await conn.execute("ALTER TABLE pipelines ADD CONSTRAINT pipelines_name_version_key UNIQUE(name, version);")
        
        print("Adding pipeline_version to pipeline_runs table...")
        await conn.execute("""
            ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS pipeline_version INT;
        """)
        
        print("Migration complete!")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate())
