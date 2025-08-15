from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel, JSON, Column


class ConditionEnum(str, Enum):
    NM = "NM"
    LP = "LP"
    MP = "MP"
    HP = "HP"
    DMG = "DMG"
    GRADED = "GRADED"
    UNKNOWN = "UNKNOWN"


class SchemaVersion(SQLModel, table=True):
    """Track database schema version for migrations."""
    version: int = Field(primary_key=True)
    applied_at: datetime = Field(default_factory=datetime.utcnow)
    description: str


class Card(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tcg_id: str = Field(unique=True, index=True)
    name: str = Field(index=True)
    set_id: Optional[str] = Field(default=None, index=True)
    set_name: Optional[str] = Field(default=None, index=True)
    number: str
    rarity: Optional[str] = None
    supertype: Optional[str] = None
    subtypes: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    image_small: str
    image_large: str
    release_date: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Pokémon TCG API fields
    api_id: Optional[str] = Field(default=None, index=True)  # e.g., "sm4-57", "xy1-1"
    api_last_synced_at: Optional[datetime] = None
    
    # Card stats and metadata
    hp: Optional[int] = None
    types: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    retreat_cost: Optional[int] = None
    
    # Card abilities and attacks
    abilities: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    attacks: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    weaknesses: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    resistances: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    
    # High-quality images from API
    api_image_small: Optional[str] = None
    api_image_large: Optional[str] = None
    
    # Additional metadata
    artist: Optional[str] = None
    flavor_text: Optional[str] = None
    national_pokedex_numbers: Optional[List[int]] = Field(default=None, sa_column=Column(JSON))
    evolves_from: Optional[str] = None
    evolves_to: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    
    # Market and legality info
    legalities: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    tcg_player_id: Optional[int] = None
    cardmarket_id: Optional[int] = None
    
    # Relationships
    collection_entries: List["CollectionEntry"] = Relationship(back_populates="card")
    price_snapshots: List["PriceSnapshot"] = Relationship(back_populates="card")
    pricecharting_links: List["PriceChartingLink"] = Relationship(back_populates="card")


class PriceChartingLink(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="card.id", index=True)
    pc_product_id: str = Field(index=True)
    pc_product_name: str
    pc_game_url: Optional[str] = None  # Store the actual game URL (e.g., /game/pokemon-crimson-invasion/buzzwole-gx-57)
    tcgplayer_id: Optional[str] = None  # TCGPlayer product ID from PriceCharting
    tcgplayer_url: Optional[str] = None  # Full TCGPlayer URL
    notes: Optional[str] = None  # Rarity/variant info from PriceCharting Notes field
    last_synced_at: Optional[datetime] = None
    
    # Relationships
    card: Card = Relationship(back_populates="pricecharting_links")


class PriceSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="card.id", index=True)
    as_of_date: date = Field(index=True)
    ungraded_cents: Optional[int] = None
    psa9_cents: Optional[int] = None
    psa10_cents: Optional[int] = None
    bgs10_cents: Optional[int] = None
    source: str = Field(default="pricecharting")
    
    # Relationships
    card: Card = Relationship(back_populates="price_snapshots")


class CollectionEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="card.id", index=True)
    qty: int = Field(default=1)
    condition: ConditionEnum = Field(default=ConditionEnum.UNKNOWN)
    purchase_price_cents: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    card: Card = Relationship(back_populates="collection_entries")


class JobHistory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_type: str = Field(index=True)  # "scheduled", "manual"
    job_name: str = Field(index=True)  # "daily_prices", "manual_refresh"
    started_at: datetime = Field(index=True)
    completed_at: Optional[datetime] = None
    status: str = Field(index=True)  # "running", "completed", "failed"
    processed: int = Field(default=0)
    succeeded: int = Field(default=0)
    failed: int = Field(default=0)
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    job_metadata: Optional[dict] = Field(default=None, sa_column=Column(JSON))


class User(SQLModel, table=True):
    """User authentication model for single-user application."""
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    is_setup_complete: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AppSettings(SQLModel, table=True):
    """Application settings stored in database with UI management."""
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Logging Settings
    log_level: str = Field(default="INFO")  # DEBUG|INFO|WARNING|ERROR
    
    # Timezone Settings
    local_tz: str = Field(default="America/New_York")
    
    # Price Refresh Settings
    price_refresh_batch_size: int = Field(default=200)
    price_refresh_requests_per_sec: int = Field(default=1)
    
    # Database Settings
    sql_echo: bool = Field(default=False)
    
    # Backup Settings
    auto_backup_enabled: bool = Field(default=True)
    backup_schedule: str = Field(default="daily")  # daily, weekly
    backup_retention_days: int = Field(default=7)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
