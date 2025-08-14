from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func, or_

from app.db import get_session
from app.logging import get_logger
from app.models import Card, CollectionEntry, PriceChartingLink, PriceSnapshot
from app.schemas import AddToCollectionRequest, UpdateCollectionEntryRequest, CollectionFilters
from app.services.pricecharting_scraper import pricecharting_scraper


router = APIRouter(prefix="/api", tags=["collection"])
templates = Jinja2Templates(directory="templates")
logger = get_logger("collection_api")


@router.post("/collection", response_class=HTMLResponse)
async def add_to_collection(
    request: Request,
    add_request: AddToCollectionRequest,
    session: Session = Depends(get_session)
):
    """Add a card to the collection using PriceCharting data only."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        logger.info(
            "add_to_collection_start",
            pc_product_id=add_request.pc_product_id,
            request_id=request_id
        )
        
        # Since we're PriceCharting-only, we need the PC product ID
        if not add_request.pc_product_id:
            raise HTTPException(
                status_code=400,
                detail="PriceCharting product ID is required"
            )
        
        # Check if card already exists by PC product ID
        existing_link = session.exec(
            select(PriceChartingLink)
            .where(PriceChartingLink.pc_product_id == add_request.pc_product_id)
        ).first()
        
        if existing_link:
            card = session.get(Card, existing_link.card_id)
            logger.debug("using_existing_card", card_id=card.id, request_id=request_id)
        else:
            # We need to get card data from the form submission
            # This should come from the search results
            form_data = await request.form()
            name = form_data.get("name", "").strip()
            set_name = form_data.get("set_name", "").strip()
            number = form_data.get("number", "").strip()
            image_url = form_data.get("image_url", "").strip()
            
            if not name:
                raise HTTPException(
                    status_code=400,
                    detail="Card name is required"
                )
            
            # Create new card with PriceCharting data
            card = Card(
                tcg_id=f"pc_{add_request.pc_product_id}",  # Use PC ID as unique identifier
                name=name,
                set_id="",  # Not available from PriceCharting
                set_name=set_name,
                number=number,
                rarity="",  # Not available from PriceCharting
                supertype="Pokémon",  # Default assumption
                subtypes=[],  # Not available from PriceCharting
                image_small=image_url,
                image_large=image_url,
                release_date=None  # Not available from PriceCharting
            )
            
            session.add(card)
            session.flush()  # Get the card ID
            
            # Create PriceCharting link
            pc_link = PriceChartingLink(
                card_id=card.id,
                pc_product_id=add_request.pc_product_id,
                pc_product_name=name
            )
            session.add(pc_link)
            
            logger.info(
                "card_created",
                card_id=card.id,
                card_name=card.name,
                request_id=request_id
            )
        
        # Try to fetch current prices if scraper is available
        if pricecharting_scraper.is_available():
            try:
                # Get pricing data from the form (already scraped during search)
                form_data = await request.form()
                ungraded_cents = form_data.get("ungraded_cents")
                psa9_cents = form_data.get("psa9_cents")
                psa10_cents = form_data.get("psa10_cents")
                
                if any([ungraded_cents, psa9_cents, psa10_cents]):
                    snapshot = PriceSnapshot(
                        card_id=card.id,
                        as_of_date=datetime.utcnow().date(),
                        ungraded_cents=int(ungraded_cents) if ungraded_cents else None,
                        psa9_cents=int(psa9_cents) if psa9_cents else None,
                        psa10_cents=int(psa10_cents) if psa10_cents else None,
                        source="pricecharting"
                    )
                    session.add(snapshot)
                    
                    logger.info(
                        "initial_price_snapshot_created",
                        card_id=card.id,
                        pc_product_id=add_request.pc_product_id,
                        request_id=request_id
                    )
            
            except Exception as e:
                logger.warning(
                    "initial_price_fetch_failed",
                    card_id=card.id,
                    pc_product_id=add_request.pc_product_id,
                    error=str(e),
                    request_id=request_id
                )
        
        # Check if already in collection
        existing_entry = session.exec(
            select(CollectionEntry).where(CollectionEntry.card_id == card.id)
        ).first()
        
        if existing_entry:
            # Increment quantity
            existing_entry.qty += 1
            existing_entry.updated_at = datetime.utcnow()
            collection_entry = existing_entry
            
            logger.info(
                "collection_entry_updated",
                entry_id=collection_entry.id,
                new_qty=collection_entry.qty,
                request_id=request_id
            )
        else:
            # Create new collection entry
            collection_entry = CollectionEntry(
                card_id=card.id,
                qty=1
            )
            session.add(collection_entry)
            session.flush()  # Get the entry ID
            
            logger.info(
                "collection_entry_created",
                entry_id=collection_entry.id,
                card_id=card.id,
                request_id=request_id
            )
        
        session.commit()
        
        # Get the latest price for display
        latest_price = session.exec(
            select(PriceSnapshot)
            .where(PriceSnapshot.card_id == card.id)
            .order_by(PriceSnapshot.as_of_date.desc())
        ).first()
        
        # Return updated table row
        return templates.TemplateResponse(
            "_collection_table_row.html",
            {
                "request": request,
                "entry": collection_entry,
                "card": card,
                "latest_price": latest_price,
                "has_pricing": pricecharting_scraper.is_available()
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "add_to_collection_error",
            pc_product_id=add_request.pc_product_id if 'add_request' in locals() else "unknown",
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=500,
            detail="Failed to add card to collection"
        )


@router.get("/collection", response_class=HTMLResponse)
async def get_collection(
    request: Request,
    name: Optional[str] = Query(None),
    set_name: Optional[str] = Query(None),
    condition: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    sort: str = Query("name"),
    direction: str = Query("asc"),
    session: Session = Depends(get_session)
):
    """Get collection with filtering, sorting, and pagination."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        # Build base query - back to simple approach
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
        elif sort == "ungraded_price":
            # For price sorting, we'll need to join with PriceSnapshot and sort by latest price
            # This is more complex, so we'll handle it separately
            sort_column = Card.name  # Fallback to name for now
        elif sort == "psa10_price":
            # For price sorting, we'll need to join with PriceSnapshot and sort by latest price
            # This is more complex, so we'll handle it separately
            sort_column = Card.name  # Fallback to name for now
        elif sort == "updated_at":
            sort_column = CollectionEntry.updated_at
        else:
            sort_column = Card.name
        
        if direction.lower() == "desc":
            sort_column = sort_column.desc()
        
        query = query.order_by(sort_column)
        
        # Count total results
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
        
        # Fetch latest price for each card
        results_with_prices = []
        for entry, card in results:
            latest_price = session.exec(
                select(PriceSnapshot)
                .where(PriceSnapshot.card_id == card.id)
                .order_by(PriceSnapshot.as_of_date.desc())
            ).first()
            results_with_prices.append((entry, card, latest_price))
        
        # Calculate pagination info
        total_pages = (total_count + page_size - 1) // page_size
        has_prev = page > 1
        has_next = page < total_pages
        
        logger.info(
            "collection_query_complete",
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            filters={"name": name, "set_name": set_name, "condition": condition},
            sort=sort,
            direction=direction,
            request_id=request_id
        )
        
        return templates.TemplateResponse(
            "_collection_table.html",
            {
                "request": request,
                "results": results_with_prices,
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
            "get_collection_error",
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve collection"
        )


@router.patch("/collection/{entry_id}", response_class=HTMLResponse)
async def update_collection_entry(
    request: Request,
    entry_id: int,
    session: Session = Depends(get_session)
):
    """Update a collection entry."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        # Get the collection entry
        entry = session.get(CollectionEntry, entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Collection entry not found")
        
        # Get form data from HTMX request
        form_data = await request.form()
        
        # Parse the form data
        qty = form_data.get("qty")
        condition = form_data.get("condition")
        purchase_price_cents = form_data.get("purchase_price_cents")
        notes = form_data.get("notes")
        
        # Convert qty to int if provided
        if qty is not None:
            try:
                qty = int(qty)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid quantity value")
        
        # Handle quantity changes - if qty is 0 or less, delete the entry and all related data
        if qty is not None and qty <= 0:
            card_id = entry.card_id
            
            # Delete the collection entry first
            session.delete(entry)
            
            # Check if this was the last collection entry for this card
            remaining_entries = session.exec(
                select(CollectionEntry).where(CollectionEntry.card_id == card_id)
            ).all()
            
            # If no other collection entries exist for this card, delete all related data
            if not remaining_entries:
                # Get the card
                card = session.get(Card, card_id)
                
                if card:
                    # Delete all price snapshots for this card
                    price_snapshots = session.exec(
                        select(PriceSnapshot).where(PriceSnapshot.card_id == card_id)
                    ).all()
                    for snapshot in price_snapshots:
                        session.delete(snapshot)
                    
                    # Delete PriceCharting link
                    pc_link = session.exec(
                        select(PriceChartingLink).where(PriceChartingLink.card_id == card_id)
                    ).first()
                    if pc_link:
                        session.delete(pc_link)
                    
                    # Finally, delete the card itself
                    session.delete(card)
                    
                    logger.info(
                        "card_completely_removed",
                        card_id=card_id,
                        card_name=card.name,
                        entry_id=entry_id,
                        request_id=request_id
                    )
            
            session.commit()
            
            logger.info(
                "collection_entry_deleted",
                entry_id=entry_id,
                card_id=card_id,
                request_id=request_id
            )
            
            # Return empty response for deletion (HTMX will handle the DOM removal)
            return HTMLResponse(content="", status_code=200)
        
        # Update fields from form data
        updates = {}
        if qty is not None:
            entry.qty = qty
            updates["qty"] = qty
        if condition is not None:
            entry.condition = condition
            updates["condition"] = condition
        if purchase_price_cents is not None:
            entry.purchase_price_cents = int(purchase_price_cents)
            updates["purchase_price_cents"] = purchase_price_cents
        if notes is not None:
            entry.notes = notes
            updates["notes"] = notes
        
        entry.updated_at = datetime.utcnow()
        session.commit()
        
        # Get related data for response
        card = session.get(Card, entry.card_id)
        latest_price = session.exec(
            select(PriceSnapshot)
            .where(PriceSnapshot.card_id == card.id)
            .order_by(PriceSnapshot.as_of_date.desc())
        ).first()
        
        logger.info(
            "collection_entry_updated",
            entry_id=entry_id,
            updates=updates,
            request_id=request_id
        )
        
        # Check if this request is coming from the card details modal
        # by looking at the HX-Target header or referer
        hx_target = request.headers.get("HX-Target", "")
        
        if "bg-blue-50" in hx_target or "collection-info" in hx_target:
            # Return the collection info section for card details modal
            return templates.TemplateResponse(
                "_collection_info_section.html",
                {
                    "request": request,
                    "collection_entry": entry,
                    "has_pricing": pricecharting_scraper.is_available()
                }
            )
        else:
            # Return the table row for collection table
            return templates.TemplateResponse(
                "_collection_table_row.html",
                {
                    "request": request,
                    "entry": entry,
                    "card": card,
                    "latest_price": latest_price,
                    "has_pricing": pricecharting_scraper.is_available()
                }
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "update_collection_entry_error",
            entry_id=entry_id,
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=500,
            detail="Failed to update collection entry"
        )
