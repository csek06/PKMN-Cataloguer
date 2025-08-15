import asyncio
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from app.logging import get_logger

logger = get_logger("tcgdx_api")

# API constants
TCGDX_BASE_URL = "https://api.tcgdex.net/v2/en"
REQUEST_TIMEOUT = 30  # 30 seconds timeout
RATE_LIMIT_DELAY = 0.5  # 0.5 second between requests (TCGdx is faster)


class TCGdxAPIService:
    """Service for interacting with the TCGdx API."""
    
    def __init__(self):
        self.client = None
        self._last_request_time = 0
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                headers={
                    "User-Agent": "PKMN-Cataloguer/1.0 (Pokemon Card Collection Manager)",
                    "Accept": "application/json"
                }
            )
        return self.client
    
    async def _rate_limit(self):
        """Implement rate limiting to be respectful to the API."""
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < RATE_LIMIT_DELAY:
            await asyncio.sleep(RATE_LIMIT_DELAY - time_since_last)
        
        self._last_request_time = asyncio.get_event_loop().time()
    
    async def get_card_by_id(self, api_id: str) -> Optional[Dict]:
        """
        Get card data by API ID (direct lookup - fastest method).
        
        Args:
            api_id: The API ID (e.g., "swsh3-136", "xy1-1", "base1-4")
            
        Returns:
            Card data dictionary or None if not found
        """
        try:
            await self._rate_limit()
            client = await self._get_client()
            
            url = f"{TCGDX_BASE_URL}/cards/{api_id}"
            
            logger.info(
                "tcgdx_direct_lookup_start",
                api_id=api_id,
                url=url
            )
            
            start_time = asyncio.get_event_loop().time()
            response = await client.get(url)
            duration = (asyncio.get_event_loop().time() - start_time) * 1000
            
            if response.status_code == 200:
                card_data = response.json()
                
                if card_data:
                    logger.info(
                        "tcgdx_direct_lookup_success",
                        api_id=api_id,
                        card_name=card_data.get("name"),
                        set_name=card_data.get("set", {}).get("name"),
                        duration_ms=round(duration, 1)
                    )
                    return card_data
                else:
                    logger.warning(
                        "tcgdx_direct_lookup_no_data",
                        api_id=api_id,
                        duration_ms=round(duration, 1)
                    )
                    return None
            
            elif response.status_code == 404:
                logger.info(
                    "tcgdx_direct_lookup_not_found",
                    api_id=api_id,
                    duration_ms=round(duration, 1)
                )
                return None
            
            else:
                logger.error(
                    "tcgdx_direct_lookup_error",
                    api_id=api_id,
                    status_code=response.status_code,
                    response_text=response.text[:500],
                    duration_ms=round(duration, 1)
                )
                return None
                
        except Exception as e:
            logger.error(
                "tcgdx_direct_lookup_exception",
                api_id=api_id,
                error=str(e),
                exc_info=True
            )
            return None
    
    async def search_cards(self, name: str, set_name: str = None, number: str = None, limit: int = 10) -> List[Dict]:
        """
        Search for cards by name, set, and number using TCGdx filtering.
        
        Args:
            name: Card name to search for
            set_name: Set name to filter by (optional)
            number: Card number to filter by (optional)
            limit: Maximum number of results to return
            
        Returns:
            List of card data dictionaries
        """
        try:
            await self._rate_limit()
            client = await self._get_client()
            
            url = f"{TCGDX_BASE_URL}/cards"
            params = {}
            
            # Add name search (laxist matching by default)
            if name:
                clean_name = name.strip()
                params["name"] = clean_name
            
            # Add set name filter
            if set_name:
                clean_set = set_name.strip()
                params["set.name"] = clean_set
            
            # Add number filter (exact match)
            if number:
                clean_number = number.strip()
                params["localId"] = f"eq:{clean_number}"
            
            # Add pagination
            if limit:
                params["pagination:itemsPerPage"] = min(limit, 100)
            
            logger.info(
                "tcgdx_search_start",
                name=name,
                set_name=set_name,
                number=number,
                params=params,
                url=url
            )
            
            start_time = asyncio.get_event_loop().time()
            response = await client.get(url, params=params)
            duration = (asyncio.get_event_loop().time() - start_time) * 1000
            
            if response.status_code == 200:
                cards = response.json()
                
                # TCGdx returns array directly for search
                if isinstance(cards, list):
                    logger.info(
                        "tcgdx_search_success",
                        name=name,
                        set_name=set_name,
                        number=number,
                        results_count=len(cards),
                        duration_ms=round(duration, 1)
                    )
                    return cards
                else:
                    logger.warning(
                        "tcgdx_search_unexpected_format",
                        name=name,
                        response_type=type(cards).__name__
                    )
                    return []
            
            else:
                logger.error(
                    "tcgdx_search_error",
                    name=name,
                    set_name=set_name,
                    number=number,
                    status_code=response.status_code,
                    response_text=response.text[:500],
                    duration_ms=round(duration, 1)
                )
                return []
                
        except Exception as e:
            logger.error(
                "tcgdx_search_exception",
                name=name,
                set_name=set_name,
                number=number,
                error=str(e),
                exc_info=True
            )
            return []
    
    async def search_and_find_best_match(self, name: str, set_name: str, number: str) -> Optional[Dict]:
        """
        Search for a card and find the best match based on name, set, and number.
        
        Args:
            name: Card name
            set_name: Set name
            number: Card number
            
        Returns:
            Best matching card data or None
        """
        try:
            # First try exact search with all parameters
            cards = await self.search_cards(name, set_name, number, limit=20)
            
            if not cards:
                # Try without set name if no exact matches
                logger.info(
                    "tcgdx_search_fallback_no_set",
                    name=name,
                    set_name=set_name,
                    number=number
                )
                cards = await self.search_cards(name, number=number, limit=20)
            
            if not cards:
                # Try with just name
                logger.info(
                    "tcgdx_search_fallback_name_only",
                    name=name,
                    set_name=set_name,
                    number=number
                )
                cards = await self.search_cards(name, limit=20)
            
            if not cards:
                logger.info(
                    "tcgdx_search_no_results",
                    name=name,
                    set_name=set_name,
                    number=number
                )
                return None
            
            # Find best match
            best_match = self._find_best_match(cards, name, set_name, number)
            
            if best_match:
                logger.info(
                    "tcgdx_search_best_match",
                    name=name,
                    set_name=set_name,
                    number=number,
                    match_id=best_match.get("id"),
                    match_name=best_match.get("name"),
                    match_set=best_match.get("set", {}).get("name"),
                    match_number=best_match.get("localId")
                )
            else:
                logger.warning(
                    "tcgdx_search_no_good_match",
                    name=name,
                    set_name=set_name,
                    number=number,
                    candidates_count=len(cards)
                )
            
            return best_match
            
        except Exception as e:
            logger.error(
                "tcgdx_search_best_match_exception",
                name=name,
                set_name=set_name,
                number=number,
                error=str(e),
                exc_info=True
            )
            return None
    
    def _find_best_match(self, cards: List[Dict], target_name: str, target_set: str, target_number: str) -> Optional[Dict]:
        """
        Find the best matching card from search results.
        
        Args:
            cards: List of card candidates
            target_name: Target card name
            target_set: Target set name
            target_number: Target card number
            
        Returns:
            Best matching card or None
        """
        if not cards:
            return None
        
        # Normalize strings for comparison
        def normalize(s: str) -> str:
            if not s:
                return ""
            return re.sub(r'[^a-zA-Z0-9]', '', s.lower())
        
        target_name_norm = normalize(target_name)
        target_set_norm = normalize(target_set)
        target_number_norm = normalize(target_number)
        
        best_score = -1
        best_match = None
        
        for card in cards:
            score = 0
            
            # Name matching (most important)
            card_name = card.get("name", "")
            if normalize(card_name) == target_name_norm:
                score += 100  # Exact name match
            elif target_name_norm in normalize(card_name):
                score += 50   # Partial name match
            
            # Set matching
            card_set = card.get("set", {}).get("name", "")
            if normalize(card_set) == target_set_norm:
                score += 30   # Exact set match
            elif target_set_norm in normalize(card_set):
                score += 15   # Partial set match
            
            # Number matching (TCGdx uses localId)
            card_number = card.get("localId", "")
            if normalize(card_number) == target_number_norm:
                score += 20   # Exact number match
            
            # Prefer cards with more complete data
            if card.get("hp"):
                score += 5
            if card.get("types"):
                score += 5
            if card.get("attacks"):
                score += 5
            
            if score > best_score:
                best_score = score
                best_match = card
        
        # Only return if we have a reasonable match (at least name similarity)
        if best_score >= 50:
            return best_match
        
        return None
    
    def extract_card_data(self, api_card: Dict) -> Dict:
        """
        Extract and normalize card data from TCGdx API response.
        
        Args:
            api_card: Raw card data from TCGdx API
            
        Returns:
            Normalized card data dictionary
        """
        try:
            # Basic card info
            card_data = {
                "api_id": api_card.get("id"),
                "name": api_card.get("name"),
                "supertype": api_card.get("category"),  # TCGdx uses "category"
                "subtypes": [api_card.get("stage")] if api_card.get("stage") else [],
                "hp": self._safe_int(api_card.get("hp")),
                "types": api_card.get("types", []),
                "retreat_cost": self._safe_int(api_card.get("retreat", 0)),
                "rarity": api_card.get("rarity"),
                "artist": api_card.get("illustrator"),  # TCGdx uses "illustrator"
                "flavor_text": api_card.get("description"),  # TCGdx uses "description"
                "national_pokedex_numbers": [],  # Not available in TCGdx
                "evolves_from": api_card.get("evolveFrom"),
                "evolves_to": [],  # Not directly available in TCGdx
            }
            
            # Set information
            set_info = api_card.get("set", {})
            card_data.update({
                "set_id": set_info.get("id"),
                "set_name": set_info.get("name"),
                "number": api_card.get("localId"),
                "release_date": None,  # Not available in TCGdx
            })
            
            # Images - TCGdx has simpler image structure
            image_url = api_card.get("image")
            card_data.update({
                "api_image_small": image_url,
                "api_image_large": image_url,  # TCGdx uses single image URL
            })
            
            # Complex data structures
            card_data.update({
                "abilities": [],  # TCGdx doesn't separate abilities from attacks
                "attacks": api_card.get("attacks", []),
                "weaknesses": api_card.get("weaknesses", []),
                "resistances": api_card.get("resistances", []),
                "legalities": api_card.get("legal", {}),
            })
            
            # Market data - not available in TCGdx
            card_data.update({
                "tcg_player_id": None,
                "cardmarket_id": None,
            })
            
            # Add sync timestamp
            card_data["api_last_synced_at"] = datetime.utcnow()
            
            return card_data
            
        except Exception as e:
            logger.error(
                "tcgdx_extract_data_error",
                api_id=api_card.get("id"),
                error=str(e),
                exc_info=True
            )
            return {}
    
    def _safe_int(self, value) -> Optional[int]:
        """Safely convert value to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None
    
    async def is_available(self) -> bool:
        """Check if the API service is available."""
        try:
            await self._rate_limit()
            client = await self._get_client()
            
            logger.info("tcgdx_api_availability_check_start", url=f"{TCGDX_BASE_URL}/cards")
            
            # Test with a simple request with shorter timeout for availability check
            response = await client.get(f"{TCGDX_BASE_URL}/cards", params={"pagination:itemsPerPage": 1}, timeout=10)
            
            if response.status_code == 200:
                logger.info("tcgdx_api_availability_check_success", status_code=response.status_code)
                return True
            else:
                logger.warning(
                    "tcgdx_api_availability_check_failed_status", 
                    status_code=response.status_code,
                    response_text=response.text[:200]
                )
                return False
                
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            
            logger.warning(
                "tcgdx_api_availability_check_failed", 
                error_type=error_type,
                error=error_msg,
                url=f"{TCGDX_BASE_URL}/cards"
            )
            
            # Log specific timeout issues more clearly
            if "timeout" in error_type.lower() or "timeout" in error_msg.lower():
                logger.warning(
                    "tcgdx_api_timeout_detected",
                    message="TCGdx API is not responding within timeout period. The API service may be down or experiencing issues."
                )
            
            return False


# Global service instance
tcgdx_api = TCGdxAPIService()
