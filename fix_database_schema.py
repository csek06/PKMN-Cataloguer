#!/usr/bin/env python3
"""
Database schema fix script for set_id constraint issue.
This script checks and fixes the database schema to allow NULL values for set_id and set_name.
"""

import sqlite3
import sys
from pathlib import Path

def check_and_fix_database_schema(db_path: str):
    """Check and fix the database schema for set_id constraint."""
    
    print(f"Checking database schema at: {db_path}")
    
    # Check if database file exists
    if not Path(db_path).exists():
        print(f"ERROR: Database file not found at {db_path}")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check current table schema
        print("\n=== Current card table schema ===")
        cursor.execute("PRAGMA table_info(card)")
        columns = cursor.fetchall()
        
        set_id_not_null = False
        set_name_not_null = False
        
        for col in columns:
            col_id, name, type_name, not_null, default_val, pk = col
            print(f"Column: {name:20} Type: {type_name:10} NOT NULL: {bool(not_null):5} Default: {default_val}")
            
            if name == 'set_id' and not_null == 1:
                set_id_not_null = True
            elif name == 'set_name' and not_null == 1:
                set_name_not_null = True
        
        print(f"\nset_id has NOT NULL constraint: {set_id_not_null}")
        print(f"set_name has NOT NULL constraint: {set_name_not_null}")
        
        # Check if we need to fix the schema
        if set_id_not_null or set_name_not_null:
            print("\n=== FIXING DATABASE SCHEMA ===")
            print("Creating new table with nullable set_id and set_name...")
            
            # Begin transaction
            cursor.execute("BEGIN TRANSACTION")
            
            # Create new table with correct schema
            cursor.execute("""
                CREATE TABLE card_new (
                    id INTEGER PRIMARY KEY,
                    tcg_id VARCHAR NOT NULL UNIQUE,
                    name VARCHAR NOT NULL,
                    set_id VARCHAR,  -- Made nullable
                    set_name VARCHAR,  -- Made nullable
                    number VARCHAR NOT NULL,
                    rarity VARCHAR,
                    supertype VARCHAR,
                    subtypes JSON,
                    image_small VARCHAR NOT NULL,
                    image_large VARCHAR NOT NULL,
                    release_date DATE,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    api_id VARCHAR,
                    api_last_synced_at DATETIME,
                    hp INTEGER,
                    types JSON,
                    retreat_cost INTEGER,
                    abilities JSON,
                    attacks JSON,
                    weaknesses JSON,
                    resistances JSON,
                    api_image_small VARCHAR,
                    api_image_large VARCHAR,
                    artist VARCHAR,
                    flavor_text VARCHAR,
                    national_pokedex_numbers JSON,
                    evolves_from VARCHAR,
                    evolves_to JSON,
                    legalities JSON,
                    tcg_player_id INTEGER,
                    cardmarket_id INTEGER
                )
            """)
            
            # Copy data from old table to new table
            print("Copying data from old table to new table...")
            cursor.execute("INSERT INTO card_new SELECT * FROM card")
            
            # Get count of copied records
            cursor.execute("SELECT COUNT(*) FROM card_new")
            count = cursor.fetchone()[0]
            print(f"Copied {count} records to new table")
            
            # Drop old table
            print("Dropping old table...")
            cursor.execute("DROP TABLE card")
            
            # Rename new table
            print("Renaming new table...")
            cursor.execute("ALTER TABLE card_new RENAME TO card")
            
            # Recreate indexes
            print("Recreating indexes...")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_card_tcg_id ON card (tcg_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_card_name ON card (name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_card_set_id ON card (set_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_card_set_name ON card (set_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_card_api_id ON card (api_id)")
            
            # Commit transaction
            cursor.execute("COMMIT")
            
            print("\n=== SCHEMA FIX COMPLETED ===")
            
            # Verify the fix
            print("\n=== Verifying fixed schema ===")
            cursor.execute("PRAGMA table_info(card)")
            columns = cursor.fetchall()
            
            for col in columns:
                col_id, name, type_name, not_null, default_val, pk = col
                if name in ['set_id', 'set_name']:
                    print(f"Column: {name:20} Type: {type_name:10} NOT NULL: {bool(not_null):5} Default: {default_val}")
            
            # Test inserting a record with NULL set_id
            print("\n=== Testing NULL insertion ===")
            try:
                cursor.execute("""
                    INSERT INTO card (tcg_id, name, set_id, set_name, number, image_small, image_large, created_at, updated_at)
                    VALUES ('test_null_set', 'Test Card', NULL, NULL, '999', 'test.jpg', 'test.jpg', datetime('now'), datetime('now'))
                """)
                cursor.execute("DELETE FROM card WHERE tcg_id = 'test_null_set'")
                print("✅ NULL set_id insertion test PASSED")
            except Exception as e:
                print(f"❌ NULL set_id insertion test FAILED: {e}")
                return False
            
        else:
            print("\n✅ Schema is already correct - set_id and set_name are nullable")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        try:
            conn.rollback()
            conn.close()
        except:
            pass
        return False

def main():
    """Main function."""
    # Try common database paths
    possible_paths = [
        "/data/app.db",  # Docker path
        "data/app.db",   # Local development path
        "app.db"         # Current directory
    ]
    
    db_path = None
    for path in possible_paths:
        if Path(path).exists():
            db_path = path
            break
    
    if not db_path:
        print("ERROR: Could not find database file. Tried:")
        for path in possible_paths:
            print(f"  - {path}")
        print("\nPlease specify the database path as an argument:")
        print("  python fix_database_schema.py /path/to/app.db")
        return False
    
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    success = check_and_fix_database_schema(db_path)
    
    if success:
        print("\n🎉 Database schema check/fix completed successfully!")
        return True
    else:
        print("\n❌ Database schema fix failed!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
