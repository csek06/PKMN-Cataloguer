#!/usr/bin/env python3
"""
Migration script to add pc_game_url column to PriceChartingLink table.
This script should be run once to update the database schema.
"""

import sqlite3
import sys
from pathlib import Path

def migrate_database():
    """Add pc_game_url column to PriceChartingLink table if it doesn't exist."""
    
    # Database path
    db_path = Path("data/app.db")
    
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(pricechartinglink)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'pc_game_url' in columns:
            print("Column 'pc_game_url' already exists in PriceChartingLink table")
            conn.close()
            return True
        
        # Add the new column
        print("Adding 'pc_game_url' column to PriceChartingLink table...")
        cursor.execute("ALTER TABLE pricechartinglink ADD COLUMN pc_game_url TEXT")
        
        # Commit changes
        conn.commit()
        
        # Verify the column was added
        cursor.execute("PRAGMA table_info(pricechartinglink)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'pc_game_url' in columns:
            print("✅ Successfully added 'pc_game_url' column")
            
            # Show current record count
            cursor.execute("SELECT COUNT(*) FROM pricechartinglink")
            count = cursor.fetchone()[0]
            print(f"📊 Found {count} existing PriceChartingLink records")
            
            if count > 0:
                print("💡 Note: Existing records will have NULL pc_game_url values.")
                print("   These will be populated when cards are next accessed or during price refresh.")
            
            conn.close()
            return True
        else:
            print("❌ Failed to add column")
            conn.close()
            return False
            
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Starting database migration...")
    success = migrate_database()
    
    if success:
        print("✅ Migration completed successfully!")
        sys.exit(0)
    else:
        print("❌ Migration failed!")
        sys.exit(1)
