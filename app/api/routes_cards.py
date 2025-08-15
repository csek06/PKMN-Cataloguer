from typing import List

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func

from app.db import get_session
from app.logging import get_logger
from app.models import Card, CollectionEntry, PriceSnapshot, PriceChartingLink
from app.schemas import PriceHistoryPoint
from app.services.pricecharting_scraper import pricecharting_scraper


router = APIRouter(prefix="/api", tags=["cards"])
templates = Jinja2Templates(directory="templates")
logger = get_logger("cards_api")


@router.get("/cards/{card_id}", response_class=HTMLResponse)
async def get_card_details(
    request: Request,
    card_id: int,
    session: Session = Depends(get_session)
):
    """Get card details for the details drawer/modal."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        # Get the card
        card = session.get(Card, card_id)
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")
        
        # Get collection entry if it exists
        collection_entry = session.exec(
            select(CollectionEntry).where(CollectionEntry.card_id == card_id)
        ).first()
        
        # Get latest price snapshot
        latest_price = session.exec(
            select(PriceSnapshot)
            .where(PriceSnapshot.card_id == card_id)
            .order_by(PriceSnapshot.as_of_date.desc())
        ).first()
        
        # Get PriceCharting link for external links
        pc_link = session.exec(
            select(PriceChartingLink)
            .where(PriceChartingLink.card_id == card_id)
        ).first()
        
        # Build external links
        external_links = {}
        
        # TCGPlayer link - use stored URL if available, otherwise construct search URL
        if pc_link and pc_link.tcgplayer_url:
            # Use the actual TCGPlayer product URL from PriceCharting
            external_links["tcg_api"] = pc_link.tcgplayer_url
        elif card.tcg_id and card.tcg_id != "sm4-57":  # Don't use the old malformed ID
            # Fallback: use a generic TCG Player search
            tcg_search_query = f"{card.name} {card.set_name}".replace(" ", "+")
            external_links["tcg_api"] = f"https://tcgplayer.pxf.io/c/3029031/1780961/21018?u=https%3A%2F%2Fwww.tcgplayer.com%2Fsearch%2Fpokemon%2Fproduct%3Fq%3D{tcg_search_query}"
        else:
            # Last resort fallback: construct search URL
            tcg_search_query = f"{card.name} {card.set_name}".replace(" ", "+")
            external_links["tcg_api"] = f"https://tcgplayer.pxf.io/c/3029031/1780961/21018?u=https%3A%2F%2Fwww.tcgplayer.com%2Fsearch%2Fpokemon%2Fproduct%3Fq%3D{tcg_search_query}"
        
        # PriceCharting link if available - use the stored game URL
        if pc_link:
            if pc_link.pc_game_url:
                # Use the stored game URL (preferred)
                external_links["pricecharting"] = pc_link.pc_game_url
            else:
                # Fallback to offers URL if game URL not available
                external_links["pricecharting"] = f"https://www.pricecharting.com/offers?product={pc_link.pc_product_id}"
        
        logger.info(
            "card_details_request",
            card_id=card_id,
            card_name=card.name,
            has_collection_entry=bool(collection_entry),
            has_latest_price=bool(latest_price),
            has_pc_link=bool(pc_link),
            request_id=request_id
        )
        
        return templates.TemplateResponse(
            "_card_details.html",
            {
                "request": request,
                "card": card,
                "collection_entry": collection_entry,
                "latest_price": latest_price,
                "pc_link": pc_link,
                "external_links": external_links,
                "has_pricing": pricecharting_scraper.is_available()
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_card_details_error",
            card_id=card_id,
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve card details"
        )


@router.get("/cards/{card_id}/price-history.json")
async def get_card_price_history(
    request: Request,
    card_id: int,
    session: Session = Depends(get_session)
):
    """Get price history for a card as JSON for Chart.js."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        # Get the card to verify it exists
        card = session.get(Card, card_id)
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")
        
        # Get price history (last 365 days, ordered by date)
        price_snapshots = session.exec(
            select(PriceSnapshot)
            .where(PriceSnapshot.card_id == card_id)
            .order_by(PriceSnapshot.as_of_date.asc())
        ).all()
        
        # Convert to chart data format
        history_points = []
        for snapshot in price_snapshots:
            point = PriceHistoryPoint(
                date=snapshot.as_of_date.isoformat(),
                ungraded_cents=snapshot.ungraded_cents,
                psa9_cents=snapshot.psa9_cents,
                psa10_cents=snapshot.psa10_cents,
                bgs10_cents=snapshot.bgs10_cents
            )
            history_points.append(point.dict())
        
        logger.info(
            "price_history_request",
            card_id=card_id,
            card_name=card.name,
            history_points_count=len(history_points),
            request_id=request_id
        )
        
        return JSONResponse(content={
            "card_id": card_id,
            "card_name": card.name,
            "history": history_points
        })
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_price_history_error",
            card_id=card_id,
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve price history"
        )


@router.get("/collection/poster", response_class=HTMLResponse)
async def get_collection_poster_view(
    request: Request,
    name: str = None,
    set_name: str = None,
    condition: str = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(48, ge=1, le=100),
    sort: str = Query("name"),
    direction: str = Query("asc"),
    session: Session = Depends(get_session)
):
    """Get collection in poster/grid view with pagination."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        # Build base query
        query = (
            select(CollectionEntry, Card)
            .select_from(CollectionEntry)
            .join(Card, CollectionEntry.card_id == Card.id)
        )
        
        # Apply filters
        if name:
            query = query.where(Card.name.ilike(f"%{name}%"))
        
        if set_name:
            query = query.where(Card.set_name.ilike(f"%{set_name}%"))
        
        if condition:
            query = query.where(CollectionEntry.condition == condition)
        
        # Apply sorting
        sort_column = None
        if sort == "name":
            sort_column = Card.name
        elif sort == "set_name":
            sort_column = Card.set_name
        elif sort == "number":
            sort_column = Card.number
        elif sort == "rarity":
            sort_column = Card.rarity
        elif sort == "condition":
            sort_column = CollectionEntry.condition
        elif sort == "qty":
            sort_column = CollectionEntry.qty
        elif sort == "updated_at":
            sort_column = CollectionEntry.updated_at
        else:
            sort_column = Card.name
        
        if direction.lower() == "desc":
            sort_column = sort_column.desc()
        
        query = query.order_by(sort_column)
        
        # Count total results for pagination
        count_query = (
            select(func.count(CollectionEntry.id))
            .select_from(CollectionEntry)
            .join(Card, CollectionEntry.card_id == Card.id)
        )
        
        # Apply same filters to count query
        if name:
            count_query = count_query.where(Card.name.ilike(f"%{name}%"))
        if set_name:
            count_query = count_query.where(Card.set_name.ilike(f"%{set_name}%"))
        if condition:
            count_query = count_query.where(CollectionEntry.condition == condition)
        
        total_count = session.exec(count_query).first()
        
        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        
        results = session.exec(query).all()
        
        # Calculate pagination info
        total_pages = (total_count + page_size - 1) // page_size
        has_prev = page > 1
        has_next = page < total_pages
        
        logger.info(
            "collection_poster_request",
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            results_count=len(results),
            filters={"name": name, "set_name": set_name, "condition": condition},
            sort=sort,
            direction=direction,
            request_id=request_id
        )
        
        return templates.TemplateResponse(
            "_collection_poster.html",
            {
                "request": request,
                "results": results,
                "total_count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "has_prev": has_prev,
                "has_next": has_next,
                "sort": sort,
                "direction": direction,
                "filters": {
                    "name": name or "",
                    "set_name": set_name or "",
                    "condition": condition or ""
                },
                "has_pricing": pricecharting_scraper.is_available()
            }
        )
    
    except Exception as e:
        logger.error(
            "get_collection_poster_error",
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve poster view"
        )
