from typing import List
from datetime import datetime
import re

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.db import get_session
from app.logging import get_logger
from app.schemas import SearchRequest, SearchCandidate
from app.services.pricecharting_scraper import pricecharting_scraper
from app.services.tcgdx_api import tcgdx_api
from app.models import Card, CollectionEntry, PriceChartingLink, PriceSnapshot


router = APIRouter(prefix="/api", tags=["search"])
templates = Jinja2Templates(directory="templates")
logger = get_logger("search_api")


def _parse_rarity_and_variant(notes: str) -> tuple[str, str]:
    """Parse rarity and variant information from PriceCharting notes field."""
    if not notes:
        return "", ""
    
    notes_lower = notes.lower().strip()
    rarity = ""
    variant = ""
    
    # Common rarity patterns
    rarity_patterns = {
        "secret rare": "Secret Rare",
        "ultra rare": "Ultra Rare", 
        "rare holo": "Rare Holo",
        "rare": "Rare",
        "uncommon": "Uncommon",
        "common": "Common",
        "promo": "Promo"
    }
    
    # Special card type patterns (these often indicate rarity)
    card_type_patterns = {
        "special illustration rare": "Special Illustration Rare",
        "illustration rare": "Illustration Rare",
        "alternate art": "Alternate Art Rare",
        "full art": "Full Art Rare",
        "rainbow rare": "Rainbow Rare",
        "gold rare": "Gold Rare",
        "hyper rare": "Hyper Rare"
    }
    
    # Variant patterns
    variant_patterns = {
        "reverse holo": "Reverse Holo",
        "reverse": "Reverse Holo",
        "holo": "Holo",
        "world championships": "World Championships",
        "staff": "Staff Promo",
        "prerelease": "Prerelease Promo",
        "first edition": "First Edition",
        "shadowless": "Shadowless",
        "unlimited": "Unlimited"
    }
    
    # Check for card type patterns first (they're more specific)
    for pattern, rarity_name in card_type_patterns.items():
        if pattern in notes_lower:
            rarity = rarity_name
            break
    
    # If no card type found, check general rarity patterns
    if not rarity:
        for pattern, rarity_name in rarity_patterns.items():
            if pattern in notes_lower:
                rarity = rarity_name
                break
    
    # Check for variant patterns
    for pattern, variant_name in variant_patterns.items():
        if pattern in notes_lower:
            variant = variant_name
            break
    
    return rarity, variant


@router.post("/search", response_class=HTMLResponse)
async def search_cards(
    request: Request,
    session: Session = Depends(get_session)
):
    """Search for Pokémon cards and return HTML fragment for modal."""
    try:
        # Get form data
        form_data = await request.form()
        query = form_data.get("q", "").strip()
        
        if not query:
            raise HTTPException(status_code=400, detail="Search query is required")
        
        logger.info(
            "search_request",
            query=query,
            request_id=getattr(request.state, "request_id", None)
        )
        
        candidates = []
        search_method = "pricecharting"
        
        # PriceCharting search only
        if pricecharting_scraper.is_available():
            try:
                pc_results = await pricecharting_scraper.search_cards(query, request)
                
                if pc_results:
                    # Convert PriceCharting results to SearchCandidates
                    for pc_result in pc_results:
                        candidate = SearchCandidate(
                            # Use PriceCharting data as primary source
                            tcg_id=None,  # No TCG integration
                            name=pc_result.get("name", ""),
                            set_name=pc_result.get("set_name", ""),
                            number=pc_result.get("number", ""),
                            rarity="",  # Not available from PriceCharting search
                            image_small=pc_result.get("image_url", ""),
                            image_large=pc_result.get("image_url", "")
                        )
                        
                        # Add pricing data
                        prices = pc_result.get("prices", {})
                        if "ungraded_cents" in prices:
                            candidate.ungraded_price_cents = prices["ungraded_cents"]
                        if "psa9_cents" in prices:
                            candidate.psa9_price_cents = prices["psa9_cents"]
                        if "psa10_cents" in prices:
                            candidate.psa10_price_cents = prices["psa10_cents"]
                        
                        # Store PriceCharting metadata
                        candidate.pc_product_name = pc_result.get("name", "")
                        candidate.pc_url = pc_result.get("url", "")
                        
                        candidates.append(candidate)
                    
                    logger.info(
                        "pricecharting_search_success",
                        query=query,
                        results_count=len(candidates),
                        request_id=getattr(request.state, "request_id", None)
                    )
                
            except Exception as e:
                logger.error(
                    "pricecharting_search_failed",
                    query=query,
                    error=str(e),
                    request_id=getattr(request.state, "request_id", None)
                )
        else:
            logger.error(
                "pricecharting_not_available",
                query=query,
                request_id=getattr(request.state, "request_id", None)
            )
        
        # Return results
        if not candidates:
            return templates.TemplateResponse(
                "_search_modal.html",
                {
                    "request": request,
                    "candidates": [],
                    "query": query,
                    "has_pricing": pricecharting_scraper.is_available(),
                    "error": None,
                    "search_method": search_method
                }
            )
        
        logger.info(
            "search_complete",
            query=query,
            candidates_count=len(candidates),
            search_method=search_method,
            has_pricing=pricecharting_scraper.is_available(),
            request_id=getattr(request.state, "request_id", None)
        )
        
        return templates.TemplateResponse(
            "_search_modal.html",
            {
                "request": request,
                "candidates": candidates,
                "query": query,
                "has_pricing": pricecharting_scraper.is_available(),
                "error": None,
                "search_method": search_method
            }
        )
    
    except HTTPException:
        # Re-raise HTTPExceptions as-is (like 400 for missing query)
        raise
    except Exception as e:
        logger.error(
            "search_error",
            query=query if 'query' in locals() else "unknown",
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        # Determine error message based on exception type
        error_message = "Search failed. Please try again."
        if "timeout" in str(e).lower() or "readtimeout" in str(e).lower():
            error_message = "Search timed out. The Pokémon TCG API may be experiencing issues. Please try again later."
        
        return templates.TemplateResponse(
            "_search_modal.html",
            {
                "request": request,
                "candidates": [],
                "query": query if 'query' in locals() else "unknown",
                "has_pricing": pricecharting_scraper.is_available(),
                "error": error_message
            }
        )


@router.post("/preview-card", response_class=HTMLResponse)
async def preview_card(
    request: Request,
    session: Session = Depends(get_session)
):
    """Preview a card from search results with full details before adding to collection."""
    try:
        # Get form data
        form_data = await request.form()
        pc_url = form_data.get("pc_url", "").strip()
        name = form_data.get("name", "").strip()
        set_name = form_data.get("set_name", "").strip()
        number = form_data.get("number", "").strip()
        image_url = form_data.get("image_url", "").strip()
        
        request_id = getattr(request.state, "request_id", None)
        
        logger.info(
            "preview_card_start",
            pc_url=pc_url,
            name=name,
            set_name=set_name,
            number=number,
            request_id=request_id
        )
        
        if not pc_url or not name:
            raise HTTPException(
                status_code=400,
                detail="PriceCharting URL and card name are required"
            )
        
        # Extract product ID from URL for reference
        pc_product_id = None
        if pc_url:
            if "product=" in pc_url:
                product_match = re.search(r'product=(\d+)', pc_url)
                if product_match:
                    pc_product_id = product_match.group(1)
            else:
                pc_product_id = pc_url.split("/")[-1]
        
        # Scrape the PriceCharting product page for full details
        pricing_data = None
        metadata = {}
        game_url = pc_url
        
        if pricecharting_scraper.is_available():
            try:
                scrape_result = await pricecharting_scraper.scrape_product_page_with_url(pc_url, request)
                
                if scrape_result:
                    pricing_data = scrape_result.get("pricing_data")
                    metadata = scrape_result.get("metadata", {})
                    game_url = scrape_result.get("final_url", pc_url)
                    
                    logger.info(
                        "preview_scrape_complete",
                        name=name,
                        pc_product_id=pc_product_id,
                        prices_found=bool(pricing_data),
                        metadata_found=bool(metadata),
                        request_id=request_id
                    )
                else:
                    logger.warning(
                        "preview_scrape_empty",
                        pc_url=pc_url,
                        request_id=request_id
                    )
            
            except Exception as e:
                logger.warning(
                    "preview_scrape_failed",
                    pc_url=pc_url,
                    error=str(e),
                    request_id=request_id
                )
        
        # Parse rarity and variant from metadata
        rarity = ""
        variant = ""
        if metadata.get("notes"):
            rarity, variant = _parse_rarity_and_variant(metadata["notes"])
        
        # Fetch TCGdx metadata for complete card details
        tcgdx_metadata = {}
        if tcgdx_api and await tcgdx_api.is_available():
            try:
                logger.info(
                    "preview_fetching_tcgdx_metadata",
                    name=name,
                    set_name=set_name,
                    number=number,
                    request_id=request_id
                )
                
                # Search for the card in TCGdx API
                api_card_data = await tcgdx_api.search_and_find_best_match(
                    name, set_name, number or metadata.get("card_number", "")
                )
                
                if api_card_data:
                    # Extract normalized card data
                    extracted_data = tcgdx_api.extract_card_data(api_card_data)
                    if extracted_data:
                        tcgdx_metadata = extracted_data
                        logger.info(
                            "preview_tcgdx_metadata_fetched",
                            name=name,
                            api_id=extracted_data.get("api_id"),
                            hp=extracted_data.get("hp"),
                            types=extracted_data.get("types"),
                            rarity_from_api=extracted_data.get("rarity"),
                            request_id=request_id
                        )
                    else:
                        logger.warning(
                            "preview_tcgdx_extraction_failed",
                            name=name,
                            request_id=request_id
                        )
                else:
                    logger.info(
                        "preview_tcgdx_no_match",
                        name=name,
                        set_name=set_name,
                        number=number,
                        request_id=request_id
                    )
            
            except Exception as e:
                logger.warning(
                    "preview_tcgdx_fetch_failed",
                    name=name,
                    error=str(e),
                    request_id=request_id
                )
        
        # Create a temporary card object for preview (not saved to database)
        # Combine PriceCharting and TCGdx data, with TCGdx taking priority for metadata
        preview_card = {
            "name": name,
            "set_name": set_name,
            "number": number or metadata.get("card_number", ""),
            "rarity": tcgdx_metadata.get("rarity") or rarity,  # TCGdx rarity takes priority
            "supertype": tcgdx_metadata.get("supertype", "Pokémon"),
            "hp": tcgdx_metadata.get("hp"),
            "types": tcgdx_metadata.get("types", []),
            "abilities": tcgdx_metadata.get("abilities", []),
            "attacks": tcgdx_metadata.get("attacks", []),
            "weaknesses": tcgdx_metadata.get("weaknesses", []),
            "resistances": tcgdx_metadata.get("resistances", []),
            "retreat_cost": tcgdx_metadata.get("retreat_cost", 0),
            "evolves_to": tcgdx_metadata.get("evolves_to", []),
            "national_pokedex_numbers": tcgdx_metadata.get("national_pokedex_numbers", []),
            "image_small": tcgdx_metadata.get("api_image_small") or image_url,
            "image_large": tcgdx_metadata.get("api_image_large") or image_url,
            "pc_url": game_url,
            "tcgplayer_url": metadata.get("tcgplayer_url"),
            "notes": metadata.get("notes", ""),
            "variant": variant,
            "api_id": tcgdx_metadata.get("api_id"),
            "has_tcgdx_metadata": bool(tcgdx_metadata)
        }
        
        # Create pricing info for display
        latest_price = None
        if pricing_data:
            latest_price = {
                "ungraded_cents": pricing_data.get("ungraded_cents"),
                "psa9_cents": pricing_data.get("psa9_cents"),
                "psa10_cents": pricing_data.get("psa10_cents"),
                "bgs10_cents": pricing_data.get("bgs10_cents"),
                "as_of_date": datetime.utcnow().date()
            }
        
        # Return preview modal with card details and add/cancel options
        return templates.TemplateResponse(
            "_card_preview.html",
            {
                "request": request,
                "card": preview_card,
                "latest_price": latest_price,
                "pc_url": pc_url,  # Original URL for adding to collection
                "image_url": image_url,
                "has_pricing": bool(pricing_data)
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "preview_card_error",
            pc_url=pc_url if 'pc_url' in locals() else "unknown",
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=500,
            detail="Failed to preview card details"
        )


@router.post("/select-card", response_class=HTMLResponse)
async def select_card(
    request: Request,
    session: Session = Depends(get_session)
):
    """Select a card from search results and scrape full details from PriceCharting."""
    try:
        # Get form data
        form_data = await request.form()
        pc_url = form_data.get("pc_url", "").strip()
        name = form_data.get("name", "").strip()
        set_name = form_data.get("set_name", "").strip()
        number = form_data.get("number", "").strip()
        
        request_id = getattr(request.state, "request_id", None)
        
        logger.info(
            "select_card_start",
            pc_url=pc_url,
            name=name,
            set_name=set_name,
            number=number,
            request_id=request_id
        )
        
        if not pc_url or not name:
            raise HTTPException(
                status_code=400,
                detail="PriceCharting URL and card name are required"
            )
        
        # Extract product ID from URL for database storage
        # URL format: https://www.pricecharting.com/offers?product=961204
        pc_product_id = None
        if pc_url:
            # Handle offers URL format: /offers?product=961204
            if "product=" in pc_url:
                product_match = re.search(r'product=(\d+)', pc_url)
                if product_match:
                    pc_product_id = product_match.group(1)
            else:
                # Fallback: try to extract from end of URL
                pc_product_id = pc_url.split("/")[-1]
        
        if not pc_product_id:
            raise HTTPException(
                status_code=400,
                detail="Invalid PriceCharting URL format - could not extract product ID"
            )
        
        # Check if card already exists by PC product ID
        existing_link = session.exec(
            select(PriceChartingLink)
            .where(PriceChartingLink.pc_product_id == pc_product_id)
        ).first()
        
        if existing_link:
            card = session.get(Card, existing_link.card_id)
            pc_link = existing_link
            logger.debug("using_existing_card", card_id=card.id, request_id=request_id)
        else:
            # Create new card with basic data from search
            card = Card(
                tcg_id=f"pc_{pc_product_id}",  # Use PC ID as unique identifier
                name=name,
                set_id="",  # Not available from PriceCharting
                set_name=set_name,
                number=number,
                rarity="",  # Not available from PriceCharting
                supertype="Pokémon",  # Default assumption
                subtypes=[],  # Not available from PriceCharting
                image_small=form_data.get("image_url", ""),
                image_large=form_data.get("image_url", ""),
                release_date=None  # Not available from PriceCharting
            )
            
            session.add(card)
            session.flush()  # Get the card ID
            
            # Create PriceCharting link (game_url will be updated after scraping)
            pc_link = PriceChartingLink(
                card_id=card.id,
                pc_product_id=pc_product_id,
                pc_product_name=name,
                pc_game_url=None  # Will be updated after scraping
            )
            session.add(pc_link)
            
            logger.info(
                "card_created",
                card_id=card.id,
                card_name=card.name,
                pc_product_id=pc_product_id,
                request_id=request_id
            )
        
        # Scrape the actual PriceCharting product page for full pricing data, metadata, and get the game URL
        game_url = None
        metadata = {}
        if pricecharting_scraper.is_available():
            try:
                # Use the scraper to get detailed pricing and metadata from the product page
                scrape_result = await pricecharting_scraper.scrape_product_page_with_url(pc_url, request)
                
                if scrape_result:
                    pricing_data = scrape_result.get("pricing_data")
                    metadata = scrape_result.get("metadata", {})
                    game_url = scrape_result.get("final_url")  # This will be the game URL after redirect
                    
                    # Update the PriceChartingLink with the actual game URL and metadata
                    if game_url and game_url != pc_url:
                        pc_link.pc_game_url = game_url
                    
                    # Update with TCGPlayer data if available
                    if metadata.get("tcgplayer_id"):
                        pc_link.tcgplayer_id = metadata["tcgplayer_id"]
                        pc_link.tcgplayer_url = metadata.get("tcgplayer_url")
                    
                    # Update with Notes (rarity/variant info)
                    if metadata.get("notes"):
                        pc_link.notes = metadata["notes"]
                        
                        # Parse rarity and variant from notes and update card
                        rarity, variant = _parse_rarity_and_variant(metadata["notes"])
                        if rarity:
                            card.rarity = rarity
                        # Note: variant is stored in CollectionEntry, not Card
                    
                    logger.info(
                        "pc_link_metadata_updated",
                        card_id=card.id,
                        pc_product_id=pc_product_id,
                        original_url=pc_url,
                        game_url=game_url,
                        tcgplayer_id=metadata.get("tcgplayer_id"),
                        notes=metadata.get("notes"),
                        request_id=request_id
                    )
                    
                    if pricing_data:
                        # Create price snapshot with scraped data
                        snapshot = PriceSnapshot(
                            card_id=card.id,
                            as_of_date=datetime.utcnow().date(),
                            ungraded_cents=pricing_data.get("ungraded_cents"),
                            psa9_cents=pricing_data.get("psa9_cents"),
                            psa10_cents=pricing_data.get("psa10_cents"),
                            bgs10_cents=pricing_data.get("bgs10_cents"),
                            source="pricecharting"
                        )
                        session.add(snapshot)
                        
                        logger.info(
                            "price_snapshot_created_from_scraping",
                            card_id=card.id,
                            pc_product_id=pc_product_id,
                            prices_found=list(pricing_data.keys()),
                            game_url=game_url,
                            request_id=request_id
                        )
                    else:
                        logger.warning(
                            "no_pricing_data_scraped",
                            card_id=card.id,
                            pc_url=pc_url,
                            game_url=game_url,
                            request_id=request_id
                        )
                else:
                    logger.warning(
                        "scrape_result_empty",
                        card_id=card.id,
                        pc_url=pc_url,
                        request_id=request_id
                    )
            
            except Exception as e:
                logger.warning(
                    "price_scraping_failed",
                    card_id=card.id,
                    pc_url=pc_url,
                    error=str(e),
                    request_id=request_id
                )
        
        # Fetch TCGdx metadata and update card with complete information
        if tcgdx_api and await tcgdx_api.is_available():
            try:
                logger.info(
                    "select_card_fetching_tcgdx_metadata",
                    card_id=card.id,
                    name=name,
                    set_name=set_name,
                    number=number,
                    request_id=request_id
                )
                
                # Search for the card in TCGdx API
                api_card_data = await tcgdx_api.search_and_find_best_match(
                    name, set_name, number or metadata.get("card_number", "")
                )
                
                if api_card_data:
                    # Extract normalized card data
                    extracted_data = tcgdx_api.extract_card_data(api_card_data)
                    if extracted_data:
                        # Update card with TCGdx metadata
                        for field, value in extracted_data.items():
                            if hasattr(card, field) and field not in ['name']:  # Don't override name
                                setattr(card, field, value)
                        
                        # Always update the sync timestamp
                        card.api_last_synced_at = datetime.utcnow()
                        card.updated_at = datetime.utcnow()
                        
                        logger.info(
                            "select_card_tcgdx_metadata_updated",
                            card_id=card.id,
                            api_id=extracted_data.get("api_id"),
                            hp=extracted_data.get("hp"),
                            types=extracted_data.get("types"),
                            rarity_from_api=extracted_data.get("rarity"),
                            set_id=extracted_data.get("set_id"),
                            set_name_from_api=extracted_data.get("set_name"),
                            request_id=request_id
                        )
                    else:
                        logger.warning(
                            "select_card_tcgdx_extraction_failed",
                            card_id=card.id,
                            name=name,
                            request_id=request_id
                        )
                else:
                    logger.info(
                        "select_card_tcgdx_no_match",
                        card_id=card.id,
                        name=name,
                        set_name=set_name,
                        number=number,
                        request_id=request_id
                    )
            
            except Exception as e:
                logger.warning(
                    "select_card_tcgdx_fetch_failed",
                    card_id=card.id,
                    name=name,
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
        
        # Return success message
        return HTMLResponse(
            content=f"""
            <div class="text-center py-8">
                <svg class="mx-auto h-12 w-12 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                <h3 class="mt-2 text-sm font-medium text-gray-900">Card Added Successfully!</h3>
                <p class="mt-1 text-sm text-gray-500">
                    "{card.name}" has been added to your collection.
                </p>
                <div class="mt-4">
                    <button 
                        onclick="closeSearchModal(); window.location.reload();" 
                        class="bg-green-600 text-white px-4 py-2 rounded-md text-sm hover:bg-green-700 transition-colors"
                    >
                        View Collection
                    </button>
                </div>
            </div>
            """,
            status_code=200
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "select_card_error",
            pc_url=pc_url if 'pc_url' in locals() else "unknown",
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=500,
            detail="Failed to select and add card to collection"
        )
