#!/usr/bin/env python3
"""
Migration script to add Pokémon TCG API fields to the Card model.
This adds fields for storing comprehensive card metadata from the Pokémon TCG API.
"""

import os
import sys
from datetime import datetime
from sqlalchemy import text

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.db import get_db_session
from app.logging import get_logger

logger = get_logger("migration")

def migrate_tcg_api_fields():
    """Add Pokémon TCG API fields to the Card table."""
    
    logger.info("Starting TCG API fields migration...")
    
    try:
        with get_db_session() as session:
            # Add new columns to Card table
            migration_queries = [
                # API identification and caching
                "ALTER TABLE card ADD COLUMN api_id TEXT",  # e.g., "sm4-57", "xy1-1"
                "ALTER TABLE card ADD COLUMN api_last_synced_at TIMESTAMP",
                
                # Card stats and metadata
                "ALTER TABLE card ADD COLUMN hp INTEGER",  # Hit Points
                "ALTER TABLE card ADD COLUMN types TEXT",  # JSON array of types
                "ALTER TABLE card ADD COLUMN retreat_cost INTEGER",  # Retreat cost
                
                # Card abilities and attacks
                "ALTER TABLE card ADD COLUMN abilities TEXT",  # JSON array of abilities
                "ALTER TABLE card ADD COLUMN attacks TEXT",  # JSON array of attacks
                "ALTER TABLE card ADD COLUMN weaknesses TEXT",  # JSON array of weaknesses
                "ALTER TABLE card ADD COLUMN resistances TEXT",  # JSON array of resistances
                
                # High-quality images from API
                "ALTER TABLE card ADD COLUMN api_image_small TEXT",  # High-quality small image
                "ALTER TABLE card ADD COLUMN api_image_large TEXT",  # High-quality large image
                
                # Additional metadata
                "ALTER TABLE card ADD COLUMN artist TEXT",  # Card artist
                "ALTER TABLE card ADD COLUMN flavor_text TEXT",  # Flavor text
                "ALTER TABLE card ADD COLUMN national_pokedex_numbers TEXT",  # JSON array of Pokédex numbers
                "ALTER TABLE card ADD COLUMN evolves_from TEXT",  # What this card evolves from
                "ALTER TABLE card ADD COLUMN evolves_to TEXT",  # JSON array of what this evolves to
                
                # Market and legality info
                "ALTER TABLE card ADD COLUMN legalities TEXT",  # JSON object of format legalities
                "ALTER TABLE card ADD COLUMN tcg_player_id INTEGER",  # TCGPlayer product ID from API
                "ALTER TABLE card ADD COLUMN cardmarket_id INTEGER",  # Cardmarket product ID from API
            ]
            
            for query in migration_queries:
                try:
                    session.execute(text(query))
                    logger.info(f"Executed: {query}")
                except Exception as e:
                    if "duplicate column name" in str(e).lower():
                        logger.info(f"Column already exists, skipping: {query}")
                    else:
                        logger.error(f"Error executing query: {query} - {e}")
                        raise
            
            # Create index on api_id for fast lookups
            try:
                session.execute(text("CREATE INDEX IF NOT EXISTS idx_card_api_id ON card(api_id)"))
                logger.info("Created index on api_id")
            except Exception as e:
                logger.warning(f"Index creation failed (may already exist): {e}")
            
            # Create index on api_last_synced_at for batch processing
            try:
                session.execute(text("CREATE INDEX IF NOT EXISTS idx_card_api_synced ON card(api_last_synced_at)"))
                logger.info("Created index on api_last_synced_at")
            except Exception as e:
                logger.warning(f"Index creation failed (may already exist): {e}")
            
            session.commit()
            logger.info("TCG API fields migration completed successfully!")
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

if __name__ == "__main__":
    migrate_tcg_api_fields()
