from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel

from app.models import ConditionEnum


class SearchRequest(BaseModel):
    q: str


class AddToCollectionRequest(BaseModel):
    pc_product_id: str


class UpdateCollectionEntryRequest(BaseModel):
    qty: Optional[int] = None
    condition: Optional[ConditionEnum] = None
    purchase_price_cents: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    variant: Optional[str] = None


class CardResponse(BaseModel):
    id: int
    tcg_id: str
    name: str
    set_id: str
    set_name: str
    number: str
    rarity: Optional[str]
    supertype: Optional[str]
    subtypes: Optional[List[str]]
    image_small: str
    image_large: str
    release_date: Optional[date]
    created_at: datetime
    updated_at: datetime


class PriceSnapshotResponse(BaseModel):
    id: int
    as_of_date: date
    ungraded_cents: Optional[int]
    psa9_cents: Optional[int]
    psa10_cents: Optional[int]
    bgs10_cents: Optional[int]
    source: str


class CollectionEntryResponse(BaseModel):
    id: int
    card_id: int
    qty: int
    condition: ConditionEnum
    purchase_price_cents: Optional[int]
    notes: Optional[str]
    tags: Optional[List[str]]
    variant: Optional[str]
    created_at: datetime
    updated_at: datetime
    card: CardResponse


class SearchCandidate(BaseModel):
    """Candidate card from search results."""
    tcg_id: Optional[str] = None  # May be None for PriceCharting-only results
    name: str
    set_name: str
    number: str
    rarity: Optional[str] = None
    image_small: str
    image_large: str
    pc_product_id: Optional[str] = None
    pc_product_name: Optional[str] = None
    pc_url: Optional[str] = None  # PriceCharting URL for reference
    ungraded_price_cents: Optional[int] = None
    psa9_price_cents: Optional[int] = None
    psa10_price_cents: Optional[int] = None
    bgs10_price_cents: Optional[int] = None


class PriceHistoryPoint(BaseModel):
    date: str  # ISO date string
    ungraded_cents: Optional[int]
    psa9_cents: Optional[int]
    psa10_cents: Optional[int]
    bgs10_cents: Optional[int]


class CollectionFilters(BaseModel):
    name: Optional[str] = None
    set_name: Optional[str] = None
    condition: Optional[ConditionEnum] = None
    tags: Optional[List[str]] = None
    page: int = 1
    page_size: int = 50
    sort: str = "name"
    direction: str = "asc"


class HealthResponse(BaseModel):
    status: str
    database: bool
    timestamp: datetime


class AppSettingsResponse(BaseModel):
    """Response model for application settings."""
    id: int
    log_level: str
    local_tz: str
    price_refresh_batch_size: int
    price_refresh_requests_per_sec: int
    sql_echo: bool
    created_at: datetime
    updated_at: datetime


class UpdateAppSettingsRequest(BaseModel):
    """Request model for updating application settings."""
    log_level: Optional[str] = None
    local_tz: Optional[str] = None
    price_refresh_batch_size: Optional[int] = None
    price_refresh_requests_per_sec: Optional[int] = None
    sql_echo: Optional[bool] = None
