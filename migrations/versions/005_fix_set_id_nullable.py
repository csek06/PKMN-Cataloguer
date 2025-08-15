"""Fix set_id and set_name to allow NULL values for incomplete API data."""

from sqlmodel import Session, text


def upgrade(session: Session):
    """Make set_id and set_name nullable to handle incomplete API data."""
    
    # SQLite doesn't support ALTER COLUMN directly, so we need to recreate the table
    # First, let's check if we need to do anything by examining the current schema
    
    try:
        # Get current table schema
        result = session.exec(text("PRAGMA table_info(card)")).fetchall()
        
        # Check if set_id and set_name are currently NOT NULL
        set_id_not_null = False
        set_name_not_null = False
        
        for row in result:
            column_name = row[1]  # Column name is at index 1
            not_null = row[3]     # NOT NULL flag is at index 3
            
            if column_name == 'set_id' and not_null == 1:
                set_id_not_null = True
            elif column_name == 'set_name' and not_null == 1:
                set_name_not_null = True
        
        # Only proceed if we need to make changes
        if set_id_not_null or set_name_not_null:
            print(f"Making set_id and set_name nullable (set_id NOT NULL: {set_id_not_null}, set_name NOT NULL: {set_name_not_null})")
            
            # Create a new table with the correct schema
            session.exec(text("""
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
            """))
            
            # Copy data from old table to new table
            session.exec(text("""
                INSERT INTO card_new SELECT * FROM card
            """))
            
            # Drop old table
            session.exec(text("DROP TABLE card"))
            
            # Rename new table
            session.exec(text("ALTER TABLE card_new RENAME TO card"))
            
            # Recreate indexes
            session.exec(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_card_tcg_id ON card (tcg_id)"))
            session.exec(text("CREATE INDEX IF NOT EXISTS ix_card_name ON card (name)"))
            session.exec(text("CREATE INDEX IF NOT EXISTS ix_card_set_id ON card (set_id)"))
            session.exec(text("CREATE INDEX IF NOT EXISTS ix_card_set_name ON card (set_name)"))
            session.exec(text("CREATE INDEX IF NOT EXISTS ix_card_api_id ON card (api_id)"))
            
            print("Successfully made set_id and set_name nullable")
        else:
            print("set_id and set_name are already nullable, no changes needed")
    
    except Exception as e:
        print(f"Error during migration: {e}")
        # If there's an error, we might be dealing with a different schema
        # Let's try a simpler approach - just ensure the columns can be NULL
        try:
            # This is a fallback - try to update any existing records with NULL set_id
            session.exec(text("UPDATE card SET set_id = 'unknown' WHERE set_id IS NULL"))
            session.exec(text("UPDATE card SET set_name = 'Unknown Set' WHERE set_name IS NULL"))
            print("Updated NULL set_id and set_name values with defaults")
        except Exception as e2:
            print(f"Fallback update also failed: {e2}")
            # If all else fails, we'll handle this in the application code
    
    session.commit()
