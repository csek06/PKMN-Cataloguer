#!/usr/bin/env python3
"""
Migration script to add TCGPlayer fields to PriceChartingLink table.

This script adds the following fields:
- tcgplayer_id: TCGPlayer product ID
- tcgplayer_url: Full TCGPlayer product URL
- notes: Rarity/variant info from PriceCharting Notes field

Run this script from the project root directory.
"""

import sqlite3
import sys
from pathlib import Path

def migrate_database():
    """Add TCGPlayer fields to PriceChartingLink table."""
    
    # Database path
    db_path = Path("data/app.db")
    
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        print("Make sure you're running this script from the project root directory.")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔍 Checking current PriceChartingLink table structure...")
        
        # Get current table structure
        cursor.execute("PRAGMA table_info(pricechartinglink)")
        columns = cursor.fetchall()
        existing_columns = [col[1] for col in columns]
        
        print(f"📋 Current columns: {existing_columns}")
        
        # Check which fields need to be added
        fields_to_add = []
        
        if 'tcgplayer_id' not in existing_columns:
            fields_to_add.append(('tcgplayer_id', 'TEXT'))
        
        if 'tcgplayer_url' not in existing_columns:
            fields_to_add.append(('tcgplayer_url', 'TEXT'))
        
        if 'notes' not in existing_columns:
            fields_to_add.append(('notes', 'TEXT'))
        
        if not fields_to_add:
            print("✅ All TCGPlayer fields already exist in the database.")
            return True
        
        print(f"➕ Adding {len(fields_to_add)} new fields...")
        
        # Add each missing field
        for field_name, field_type in fields_to_add:
            print(f"   Adding {field_name} ({field_type})...")
            cursor.execute(f"ALTER TABLE pricechartinglink ADD COLUMN {field_name} {field_type}")
        
        # Commit changes
        conn.commit()
        
        print("✅ Migration completed successfully!")
        print("\n📊 Updated table structure:")
        
        # Show updated structure
        cursor.execute("PRAGMA table_info(pricechartinglink)")
        columns = cursor.fetchall()
        for col in columns:
            print(f"   {col[1]} ({col[2]})")
        
        # Show record count
        cursor.execute("SELECT COUNT(*) FROM pricechartinglink")
        count = cursor.fetchone()[0]
        print(f"\n📈 Total PriceChartingLink records: {count}")
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def main():
    """Main migration function."""
    print("🚀 Starting TCGPlayer fields migration...")
    print("=" * 50)
    
    success = migrate_database()
    
    print("=" * 50)
    if success:
        print("✅ Migration completed successfully!")
        print("\n📝 Next steps:")
        print("1. Restart your application")
        print("2. Add new cards to populate TCGPlayer data")
        print("3. Run price refresh to populate existing cards")
    else:
        print("❌ Migration failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
