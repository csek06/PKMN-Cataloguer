"""Add TCG API metadata fields to Card table."""

from sqlmodel import Session, text


def upgrade(session: Session):
    """Add TCG API metadata fields to Card table."""
    
    # Add TCG API fields to Card table
    tcg_fields = [
        "ALTER TABLE card ADD COLUMN api_id VARCHAR",
        "ALTER TABLE card ADD COLUMN api_last_synced_at DATETIME",
        "ALTER TABLE card ADD COLUMN hp INTEGER",
        "ALTER TABLE card ADD COLUMN types JSON",
        "ALTER TABLE card ADD COLUMN retreat_cost INTEGER",
        "ALTER TABLE card ADD COLUMN abilities JSON",
        "ALTER TABLE card ADD COLUMN attacks JSON",
        "ALTER TABLE card ADD COLUMN weaknesses JSON",
        "ALTER TABLE card ADD COLUMN resistances JSON",
        "ALTER TABLE card ADD COLUMN api_image_small VARCHAR",
        "ALTER TABLE card ADD COLUMN api_image_large VARCHAR",
        "ALTER TABLE card ADD COLUMN artist VARCHAR",
        "ALTER TABLE card ADD COLUMN flavor_text VARCHAR",
        "ALTER TABLE card ADD COLUMN national_pokedex_numbers JSON",
        "ALTER TABLE card ADD COLUMN evolves_from VARCHAR",
        "ALTER TABLE card ADD COLUMN evolves_to JSON",
        "ALTER TABLE card ADD COLUMN legalities JSON",
        "ALTER TABLE card ADD COLUMN tcg_player_id INTEGER",
        "ALTER TABLE card ADD COLUMN cardmarket_id INTEGER"
    ]
    
    for field_sql in tcg_fields:
        try:
            session.exec(text(field_sql))
        except Exception as e:
            # Column might already exist, continue
            pass
    
    # Create index on api_id
    try:
        session.exec(text("CREATE INDEX IF NOT EXISTS ix_card_api_id ON card (api_id)"))
    except Exception:
        pass
    
    session.commit()
