import asyncio
import re
import time
from typing import Dict, Any, Optional, List
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup
from fastapi import Request

from app.config import settings
from app.logging import ExternalCallLogger, get_logger


logger = get_logger("pricecharting_scraper")


class PriceChartingScraper:
    """Service for scraping PriceCharting website directly."""
    
    BASE_URL = "https://www.pricecharting.com"
    
    # Mapping of TCG API set names to PriceCharting URL slugs
    SET_SLUG_MAPPING = {
        # Base Sets
        "base": "base-set",
        "base set": "base-set",
        "jungle": "jungle",
        "fossil": "fossil",
        "team rocket": "team-rocket",
        "gym heroes": "gym-heroes",
        "gym challenge": "gym-challenge",
        
        # Neo Series
        "neo genesis": "neo-genesis",
        "neo discovery": "neo-discovery",
        "neo destiny": "neo-destiny",
        "neo revelation": "neo-revelation",
        
        # E-Card Series
        "expedition base set": "expedition",
        "aquapolis": "aquapolis",
        "skyridge": "skyridge",
        
        # EX Series
        "ruby & sapphire": "ruby-sapphire",
        "sandstorm": "sandstorm",
        "dragon": "dragon",
        "team magma vs team aqua": "team-magma-vs-team-aqua",
        "hidden legends": "hidden-legends",
        "firered & leafgreen": "firered-leafgreen",
        "team rocket returns": "team-rocket-returns",
        "deoxys": "deoxys",
        "emerald": "emerald",
        "unseen forces": "unseen-forces",
        "delta species": "delta-species",
        "legend maker": "legend-maker",
        "holon phantoms": "holon-phantoms",
        "crystal guardians": "crystal-guardians",
        "dragon frontiers": "dragon-frontiers",
        "power keepers": "power-keepers",
        
        # Diamond & Pearl Series
        "diamond & pearl": "diamond-pearl",
        "mysterious treasures": "mysterious-treasures",
        "secret wonders": "secret-wonders",
        "great encounters": "great-encounters",
        "majestic dawn": "majestic-dawn",
        "legends awakened": "legends-awakened",
        "stormfront": "stormfront",
        
        # Platinum Series
        "platinum": "platinum",
        "rising rivals": "rising-rivals",
        "supreme victors": "supreme-victors",
        "arceus": "arceus",
        
        # HeartGold & SoulSilver Series
        "heartgold & soulsilver": "heartgold-soulsilver",
        "unleashed": "unleashed",
        "undaunted": "undaunted",
        "triumphant": "triumphant",
        "call of legends": "call-of-legends",
        
        # Black & White Series
        "black & white": "black-white",
        "emerging powers": "emerging-powers",
        "noble victories": "noble-victories",
        "next destinies": "next-destinies",
        "dark explorers": "dark-explorers",
        "dragons exalted": "dragons-exalted",
        "boundaries crossed": "boundaries-crossed",
        "plasma storm": "plasma-storm",
        "plasma freeze": "plasma-freeze",
        "plasma blast": "plasma-blast",
        "legendary treasures": "legendary-treasures",
        
        # XY Series
        "xy": "xy",
        "flashfire": "flashfire",
        "furious fists": "furious-fists",
        "phantom forces": "phantom-forces",
        "primal clash": "primal-clash",
        "roaring skies": "roaring-skies",
        "ancient origins": "ancient-origins",
        "breakthrough": "breakthrough",
        "breakpoint": "breakpoint",
        "fates collide": "fates-collide",
        "steam siege": "steam-siege",
        "evolutions": "evolutions",
        
        # Sun & Moon Series
        "sun & moon": "sun-moon",
        "guardians rising": "guardians-rising",
        "burning shadows": "burning-shadows",
        "crimson invasion": "crimson-invasion",
        "ultra prism": "ultra-prism",
        "forbidden light": "forbidden-light",
        "celestial storm": "celestial-storm",
        "lost thunder": "lost-thunder",
        "team up": "team-up",
        "detective pikachu": "detective-pikachu",
        "unbroken bonds": "unbroken-bonds",
        "unified minds": "unified-minds",
        "hidden fates": "hidden-fates",
        "cosmic eclipse": "cosmic-eclipse",
        
        # Sword & Shield Series
        "sword & shield": "sword-shield",
        "rebel clash": "rebel-clash",
        "darkness ablaze": "darkness-ablaze",
        "champions path": "champions-path",
        "vivid voltage": "vivid-voltage",
        "shining fates": "shining-fates",
        "battle styles": "battle-styles",
        "chilling reign": "chilling-reign",
        "evolving skies": "evolving-skies",
        "celebrations": "celebrations",
        "fusion strike": "fusion-strike",
        "brilliant stars": "brilliant-stars",
        "astral radiance": "astral-radiance",
        "pokemon go": "pokemon-go",
        "lost origin": "lost-origin",
        "silver tempest": "silver-tempest",
        "crown zenith": "crown-zenith",
        
        # Scarlet & Violet Series
        "scarlet & violet": "scarlet-violet",
        "paldea evolved": "paldea-evolved",
        "obsidian flames": "obsidian-flames",
        "paradox rift": "paradox-rift",
        "paldean fates": "paldean-fates",
        "temporal forces": "temporal-forces",
        "twilight masquerade": "twilight-masquerade",
        "shrouded fable": "shrouded-fable",
        "stellar crown": "stellar-crown",
        
        # Special Sets
        "pokemon 151": "151",
        "151": "151",
        "25th anniversary collection": "celebrations",
        "classic collection": "classic-collection",
        "generations": "generations",
        "double crisis": "double-crisis",
        "dragon vault": "dragon-vault",
        "mcdonald's collection": "mcdonalds-collection",
    }
    
    def __init__(self):
        self.last_request_time = 0
        self.requests_per_sec = 0.5  # Be conservative with scraping rate
        self._cache = {}  # Simple in-memory cache
        self._cache_ttl = 3600  # 1 hour cache
    
    async def _throttle(self):
        """Throttle requests to be respectful to PriceCharting."""
        min_interval = 1.0 / self.requests_per_sec
        elapsed = time.time() - self.last_request_time
        
        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _build_card_url(self, card_data: Dict[str, Any]) -> Optional[str]:
        """Build PriceCharting URL from card data."""
        try:
            # Get set slug
            set_name = card_data.get("set_name", "").lower()
            set_slug = self.SET_SLUG_MAPPING.get(set_name)
            
            if not set_slug:
                # Try to create a slug from the set name
                set_slug = re.sub(r'[^a-z0-9]+', '-', set_name).strip('-')
                if not set_slug:
                    logger.warning("pricecharting_no_set_slug", set_name=set_name)
                    return None
            
            # Build card slug
            card_name = card_data.get("name", "").lower()
            card_number = card_data.get("number", "")
            
            # Clean card name for URL
            card_slug = re.sub(r'[^a-z0-9]+', '-', card_name).strip('-')
            
            # Add card number if present
            if card_number:
                # Extract just the number part (before any slash)
                number_match = re.match(r'(\d+)', card_number)
                if number_match:
                    card_slug += f"-{number_match.group(1)}"
            
            url = f"{self.BASE_URL}/game/pokemon-{set_slug}/{card_slug}"
            
            logger.debug(
                "pricecharting_url_built",
                card_name=card_name,
                set_name=set_name,
                card_number=card_number,
                url=url
            )
            
            return url
            
        except Exception as e:
            logger.error(
                "pricecharting_url_build_error",
                card_data=card_data,
                error=str(e),
                exc_info=True
            )
            return None
    
    def _get_cache_key(self, url: str) -> str:
        """Generate cache key for URL."""
        return f"pc_scrape_{hash(url)}"
    
    def _is_cache_valid(self, cache_entry: Dict[str, Any]) -> bool:
        """Check if cache entry is still valid."""
        return time.time() - cache_entry.get("timestamp", 0) < self._cache_ttl
    
    async def search_cards(
        self,
        query: str,
        request: Optional[Request] = None
    ) -> List[Dict[str, Any]]:
        """Search PriceCharting for cards matching the query."""
        if not query.strip():
            return []
        
        # Build search URL
        search_url = f"{self.BASE_URL}/search-products?q={quote(query)}"
        
        # Check cache first
        cache_key = self._get_cache_key(f"search_{query}")
        if cache_key in self._cache and self._is_cache_valid(self._cache[cache_key]):
            logger.debug("pricecharting_search_cache_hit", query=query)
            return self._cache[cache_key]["data"]
        
        request_id = getattr(request.state, "request_id", None) if request else None
        
        try:
            await self._throttle()
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                with ExternalCallLogger("pricecharting_search", search_url, request_id):
                    response = await client.get(search_url, headers=headers)
                    response.raise_for_status()
                    
                    search_results = self._parse_search_results(response.text, query)
                    
                    # Cache the results
                    self._cache[cache_key] = {
                        "data": search_results,
                        "timestamp": time.time()
                    }
                    
                    logger.info(
                        "pricecharting_search_complete",
                        query=query,
                        results_count=len(search_results),
                        request_id=request_id
                    )
                    
                    return search_results
        
        except httpx.HTTPError as e:
            logger.error(
                "pricecharting_search_error",
                query=query,
                error=str(e),
                status_code=getattr(e.response, 'status_code', None),
                request_id=request_id,
                exc_info=True
            )
            return []
        except Exception as e:
            logger.error(
                "pricecharting_search_unexpected_error",
                query=query,
                error=str(e),
                request_id=request_id,
                exc_info=True
            )
            return []

    async def get_card_prices(
        self,
        card_data: Dict[str, Any],
        request: Optional[Request] = None
    ) -> Optional[Dict[str, Any]]:
        """Scrape prices for a card from PriceCharting."""
        url = self._build_card_url(card_data)
        if not url:
            return None
        
        # Check cache first
        cache_key = self._get_cache_key(url)
        if cache_key in self._cache and self._is_cache_valid(self._cache[cache_key]):
            logger.debug("pricecharting_cache_hit", url=url)
            return self._cache[cache_key]["data"]
        
        request_id = getattr(request.state, "request_id", None) if request else None
        
        try:
            await self._throttle()
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                with ExternalCallLogger("pricecharting_scraper", url, request_id):
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    
                    prices = self._parse_prices_from_html(response.text, url)
                    
                    # Cache the result
                    self._cache[cache_key] = {
                        "data": prices,
                        "timestamp": time.time()
                    }
                    
                    logger.info(
                        "pricecharting_scrape_complete",
                        url=url,
                        prices_found=bool(prices),
                        request_id=request_id
                    )
                    
                    return prices
        
        except httpx.HTTPError as e:
            logger.error(
                "pricecharting_scrape_error",
                url=url,
                error=str(e),
                status_code=getattr(e.response, 'status_code', None),
                request_id=request_id,
                exc_info=True
            )
            return None
        except Exception as e:
            logger.error(
                "pricecharting_scrape_unexpected_error",
                url=url,
                error=str(e),
                request_id=request_id,
                exc_info=True
            )
            return None
    
    def _parse_prices_from_html(self, html: str, url: str) -> Optional[Dict[str, Any]]:
        """Parse prices and metadata from PriceCharting HTML."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Check if page exists (not a 404 or "not found" page)
            if "not found" in soup.get_text().lower() or soup.find("h1", string=re.compile("404|not found", re.I)):
                logger.debug("pricecharting_page_not_found", url=url)
                return None
            
            result = {}
            prices = {}
            
            # Look for the main grade price boxes in table rows
            # These are <td class="price js-price"> elements within <tr> elements that contain grade names
            
            price_elements = soup.find_all('td', class_=['price', 'js-price'])
            
            for element in price_elements:
                price_text = element.get_text().strip()
                price_value = self._parse_price_text(price_text)
                
                if not price_value:
                    continue
                
                # Get the parent row to find the grade type
                parent_row = element.find_parent('tr')
                if not parent_row:
                    continue
                
                # Get all text from the row to determine grade type
                row_text = parent_row.get_text().strip().lower()
                
                # Map to grade types based on row content
                grade_type = None
                
                if 'ungraded' in row_text:
                    # Make sure this is the main ungraded row, not a sub-category
                    if not any(sub in row_text for sub in ['grade 1', 'grade 2', 'grade 3', 'grade 4', 'grade 5', 'grade 6', 'grade 7']):
                        grade_type = 'ungraded_cents'
                elif 'psa 10' in row_text:
                    # Make sure this is the main PSA 10, not a variant
                    if 'black' not in row_text and 'pristine' not in row_text:
                        grade_type = 'psa10_cents'
                elif 'psa 9' in row_text:
                    grade_type = 'psa9_cents'
                elif 'bgs 10' in row_text:
                    # Make sure this is the main BGS 10, not Black Label
                    if 'black' not in row_text:
                        grade_type = 'bgs10_cents'
                
                if grade_type and grade_type not in prices:
                    prices[grade_type] = price_value
                    
                    logger.debug(
                        "price_mapped",
                        grade_type=grade_type,
                        price=f"${price_value/100:.2f}",
                        row_text=row_text[:50]
                    )
            
            # Extract metadata from the product details section
            metadata = self._extract_product_metadata(soup, url)
            
            result['prices'] = prices if prices else None
            result['metadata'] = metadata
            
            logger.debug(
                "pricecharting_data_parsed",
                url=url,
                prices_found=list(prices.keys()) if prices else [],
                metadata_found=list(metadata.keys()) if metadata else [],
                price_count=len(prices) if prices else 0
            )
            
            return result if prices or metadata else None
            
        except Exception as e:
            logger.error(
                "pricecharting_parse_error",
                url=url,
                error=str(e),
                exc_info=True
            )
            return None
    
    def _extract_prices_from_table(self, table) -> Dict[str, int]:
        """Extract prices from a price table."""
        prices = {}
        
        try:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    label_cell = cells[0]
                    price_cell = cells[-1]  # Last cell is usually the price
                    
                    label = label_cell.get_text().strip().lower()
                    price_text = price_cell.get_text().strip()
                    price_value = self._parse_price_text(price_text)
                    
                    if price_value:
                        # Map label to our price type
                        if "ungraded" in label or "loose" in label or "raw" in label:
                            prices["ungraded_cents"] = price_value
                        elif "psa 9" in label or "psa9" in label:
                            prices["psa9_cents"] = price_value
                        elif "psa 10" in label or "psa10" in label or "gem mint" in label:
                            prices["psa10_cents"] = price_value
                        elif "bgs 10" in label or "bgs10" in label:
                            prices["bgs10_cents"] = price_value
        
        except Exception as e:
            logger.debug("table_parse_error", error=str(e))
        
        return prices
    
    def _get_price_context(self, element) -> Optional[str]:
        """Get context for a price element to determine its type."""
        try:
            # Look at parent elements and siblings for context
            context_text = ""
            
            # Check parent elements
            parent = element.parent
            for _ in range(3):  # Check up to 3 levels up
                if parent:
                    context_text += " " + parent.get_text()
                    parent = parent.parent
                else:
                    break
            
            # Check siblings
            if element.parent:
                for sibling in element.parent.find_all():
                    if sibling != element:
                        context_text += " " + sibling.get_text()
            
            context_text = context_text.lower()
            
            # Determine price type from context
            if "ungraded" in context_text or "loose" in context_text or "raw" in context_text:
                return "ungraded_cents"
            elif "psa 9" in context_text or "psa9" in context_text:
                return "psa9_cents"
            elif "psa 10" in context_text or "psa10" in context_text or "gem mint" in context_text:
                return "psa10_cents"
            elif "bgs 10" in context_text or "bgs10" in context_text:
                return "bgs10_cents"
            
            return None
            
        except Exception:
            return None

    def _get_detailed_price_context(self, element) -> str:
        """Get detailed context for a price element to determine its grade type."""
        try:
            context_text = ""
            
            # Get text from the element itself
            context_text += element.get_text().strip()
            
            # Check parent elements for more context
            parent = element.parent
            for level in range(5):  # Check up to 5 levels up
                if parent:
                    parent_text = parent.get_text().strip()
                    context_text += f" {parent_text}"
                    parent = parent.parent
                else:
                    break
            
            return context_text
            
        except Exception:
            return ""
    
    def _find_nearby_price(self, element) -> Optional[Any]:
        """Find a price element near the given element."""
        try:
            # Look in the same row/container
            if element.parent:
                price_element = element.parent.find(string=re.compile(r'\$\d+\.\d{2}'))
                if price_element:
                    return price_element.parent if hasattr(price_element, 'parent') else price_element
            
            # Look in next sibling
            if hasattr(element, 'next_sibling') and element.next_sibling:
                price_element = element.next_sibling.find(string=re.compile(r'\$\d+\.\d{2}'))
                if price_element:
                    return price_element.parent if hasattr(price_element, 'parent') else price_element
            
            return None
            
        except Exception:
            return None
    
    def _parse_search_results(self, html: str, query: str) -> List[Dict[str, Any]]:
        """Parse search results from PriceCharting HTML."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            results = []
            
            # Look for search result items - PriceCharting uses <tr class="offer">
            result_rows = soup.find_all("tr", {"class": "offer"})
            
            if not result_rows:
                # Fallback: look for other possible selectors
                result_rows = soup.find_all("tr", {"class": re.compile("search|result", re.I)})
            
            if not result_rows:
                # Look for any table rows that might contain results
                table = soup.find("table")
                if table:
                    result_rows = table.find_all("tr")[1:]  # Skip header row
            
            for row in result_rows[:10]:  # Limit to first 10 results
                try:
                    result_data = self._extract_search_result_data(row, query)
                    if result_data:
                        results.append(result_data)
                except Exception as e:
                    logger.debug("search_result_parse_error", error=str(e))
                    continue
            
            logger.debug(
                "pricecharting_search_results_parsed",
                query=query,
                results_count=len(results)
            )
            
            return results
            
        except Exception as e:
            logger.error(
                "pricecharting_search_parse_error",
                query=query,
                error=str(e),
                exc_info=True
            )
            return []
    
    def _extract_search_result_data(self, row, query: str = "") -> Optional[Dict[str, Any]]:
        """Extract data from a single search result row."""
        try:
            result = {}
            
            # Look for product name in the meta cell
            meta_cell = row.find("td", {"class": "meta"})
            if meta_cell:
                # Find the h2 element with product name
                h2_element = meta_cell.find("h2", {"class": "product_name"})
                if h2_element:
                    # Get the link inside h2 for card name
                    name_link = h2_element.find("a")
                    if name_link:
                        # Extract card name (clean up whitespace)
                        card_name = name_link.get_text().strip()
                        result["name"] = card_name
                        
                        # Get the offers URL
                        href = name_link.get("href", "")
                        if href:
                            result["url"] = self.BASE_URL + href
                    
                    # Extract set name (text after <br> tag)
                    full_text = h2_element.get_text()
                    # Split by newlines and clean up
                    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
                    if len(lines) >= 2:
                        # Second line is usually the set name
                        set_name = lines[1].replace("Pokemon ", "").strip()
                        result["set_name"] = set_name
                    else:
                        result["set_name"] = "Unknown Set"
            
            # Look for image in photo cell
            photo_cell = row.find("td", {"class": "photo"})
            if photo_cell:
                img = photo_cell.find("img")
                if img and img.get("src"):
                    img_src = img.get("src")
                    if not img_src.startswith("http"):
                        img_src = self.BASE_URL + img_src
                    result["image_url"] = img_src
            
            # Look for prices in the pricebox cell
            pricebox_cell = row.find("td", {"class": "pricebox"})
            if pricebox_cell:
                # Look for the main price element
                price_element = pricebox_cell.find("p", {"class": "price"})
                if price_element:
                    price_text = price_element.get_text().strip()
                    price_value = self._parse_price_text(price_text)
                    if price_value:
                        result["prices"] = {"ungraded_cents": price_value}
            
            # Try to extract card number - prioritize most reliable sources
            card_number = None
            
            # Note: For search results, we don't have access to the page title yet
            # The most reliable extraction will happen when we scrape the full product page
            
            # 1. Try to extract from the original search query first (most reliable for search)
            if query:
                number_patterns = [
                    r'(\d+)/\d+',  # 57/111 from "buzzwole gx 57/111"
                    r'#([A-Z0-9]+)',  # #GG44 or #57
                    r'\s([A-Z0-9]+)\s',  # space-number-space
                ]
                for pattern in number_patterns:
                    number_match = re.search(pattern, query, re.IGNORECASE)
                    if number_match:
                        card_number = number_match.group(1).upper()
                        logger.debug(
                            "card_number_from_query",
                            query=query,
                            extracted_number=card_number,
                            card_name=result.get("name")
                        )
                        break
            
            # 2. Try to extract from card name
            if not card_number and result.get("name"):
                name = result["name"]
                # Look for patterns like "Buzzwole GX 57/111" or "Buzzwole GX #57"
                number_patterns = [
                    r'(\d+)/\d+',  # 57/111
                    r'#([A-Z0-9]+)',     # #GG44 or #57
                    r'\s([A-Z0-9]+)$',   # ending with space and number/code
                ]
                for pattern in number_patterns:
                    number_match = re.search(pattern, name, re.IGNORECASE)
                    if number_match:
                        card_number = number_match.group(1).upper()
                        break
            
            # 3. Try to extract from URL (less reliable for search results)
            if not card_number and result.get("url"):
                url = result["url"]
                # URLs often have numbers like /pokemon-set/card-name-57 or /card-name-gg44
                number_match = re.search(r'-([a-z0-9]+)(?:/|$)', url, re.IGNORECASE)
                if number_match:
                    potential_number = number_match.group(1).upper()
                    # Only use if it looks like a card number
                    if re.match(r'^[A-Z]*\d+[A-Z]*$', potential_number):
                        card_number = potential_number
            
            if card_number:
                result["number"] = card_number
            
            # Only return if we have at least a name
            if result.get("name"):
                logger.debug(
                    "extracted_search_result",
                    name=result.get("name"),
                    set_name=result.get("set_name"),
                    has_price=bool(result.get("prices")),
                    has_image=bool(result.get("image_url")),
                    url=result.get("url", "")
                )
                return result
            
            return None
            
        except Exception as e:
            logger.debug("extract_result_error", error=str(e), exc_info=True)
            return None

    def _parse_price_text(self, text: str) -> Optional[int]:
        """Parse price text like '$12.34' to cents (1234)."""
        try:
            # Extract price using regex
            price_match = re.search(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', text)
            if price_match:
                price_str = price_match.group(1).replace(',', '')
                return int(float(price_str) * 100)
            return None
        except (ValueError, TypeError):
            return None
    
    async def scrape_product_page(
        self,
        url: str,
        request: Optional[Request] = None
    ) -> Optional[Dict[str, Any]]:
        """Scrape a specific PriceCharting product page for detailed pricing."""
        result = await self.scrape_product_page_with_url(url, request)
        return result.get("pricing_data") if result else None

    async def scrape_product_page_with_url(
        self,
        url: str,
        request: Optional[Request] = None
    ) -> Optional[Dict[str, Any]]:
        """Scrape a specific PriceCharting product page and return both pricing data and final URL."""
        if not url.strip():
            return None
        
        # Check cache first
        cache_key = self._get_cache_key(url)
        if cache_key in self._cache and self._is_cache_valid(self._cache[cache_key]):
            logger.debug("pricecharting_product_cache_hit", url=url)
            return self._cache[cache_key]["data"]
        
        request_id = getattr(request.state, "request_id", None) if request else None
        final_url = url
        
        try:
            await self._throttle()
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                with ExternalCallLogger("pricecharting_product_scraper", url, request_id):
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    
                    # Check if this is an offers page that needs to be redirected to pricing page
                    if "/offers?product=" in url:
                        pricing_page_url = self._extract_pricing_page_url(response.text, url)
                        if pricing_page_url:
                            logger.info(
                                "pricecharting_redirecting_to_pricing_page",
                                offers_url=url,
                                pricing_url=pricing_page_url,
                                request_id=request_id
                            )
                            # Recursively call with the pricing page URL
                            return await self.scrape_product_page_with_url(pricing_page_url, request)
                    
                    # Update final_url to the actual URL we ended up scraping
                    final_url = str(response.url)
                    
                    parsed_data = self._parse_prices_from_html(response.text, final_url)
                    
                    result = {
                        "pricing_data": parsed_data.get("prices") if parsed_data else None,
                        "metadata": parsed_data.get("metadata") if parsed_data else {},
                        "final_url": final_url
                    }
                    
                    # Cache the result
                    self._cache[cache_key] = {
                        "data": result,
                        "timestamp": time.time()
                    }
                    
                    logger.info(
                        "pricecharting_product_scrape_complete",
                        original_url=url,
                        final_url=final_url,
                        prices_found=bool(result.get("pricing_data")),
                        metadata_found=bool(result.get("metadata")),
                        request_id=request_id
                    )
                    
                    return result
        
        except httpx.HTTPError as e:
            logger.error(
                "pricecharting_product_scrape_error",
                url=url,
                error=str(e),
                status_code=getattr(e.response, 'status_code', None),
                request_id=request_id,
                exc_info=True
            )
            return None
        except Exception as e:
            logger.error(
                "pricecharting_product_scrape_unexpected_error",
                url=url,
                error=str(e),
                request_id=request_id,
                exc_info=True
            )
            return None

    def _extract_product_metadata(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract product metadata from PriceCharting product details section."""
        metadata = {}
        
        try:
            # Look for the product details section - usually in a table or div with specific structure
            # PriceCharting typically has details in a format like:
            # Genre: Pokemon Card
            # Release Date: September 22, 2023
            # Card Number: #199
            # Notes: Special Illustration Rare
            # TCGPlayer ID: 517045 (as a link)
            
            # Method 1: Look for definition list (dl/dt/dd structure)
            details_list = soup.find('dl')
            if details_list:
                dt_elements = details_list.find_all('dt')
                dd_elements = details_list.find_all('dd')
                
                for dt, dd in zip(dt_elements, dd_elements):
                    label = dt.get_text().strip().lower().replace(':', '')
                    value = dd.get_text().strip()
                    
                    if 'tcgplayer id' in label or 'tcg player id' in label:
                        # Extract TCGPlayer ID and construct URL
                        tcgplayer_id = value.strip()
                        if tcgplayer_id.isdigit():
                            metadata['tcgplayer_id'] = tcgplayer_id
                            metadata['tcgplayer_url'] = f"https://tcgplayer.pxf.io/c/3029031/1780961/21018?u=https%3A%2F%2Fwww.tcgplayer.com%2Fproduct%2F{tcgplayer_id}%2F-"
                    elif 'notes' in label:
                        metadata['notes'] = value
                    elif 'card number' in label:
                        metadata['card_number'] = value.replace('#', '').strip()
                    elif 'release date' in label:
                        metadata['release_date'] = value
                    elif 'genre' in label:
                        metadata['genre'] = value
            
            # Method 2: Look for table-based details (fallback)
            if not metadata:
                # Look for tables that might contain product details
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 2:
                            label = cells[0].get_text().strip().lower().replace(':', '')
                            value_cell = cells[1]
                            
                            # Check if this cell contains a link (for TCGPlayer ID)
                            link = value_cell.find('a')
                            if link and ('tcgplayer' in label or 'tcg player' in label):
                                # Extract TCGPlayer ID from the link
                                href = link.get('href', '')
                                tcgplayer_match = re.search(r'tcgplayer\.com.*?(\d+)', href)
                                if tcgplayer_match:
                                    tcgplayer_id = tcgplayer_match.group(1)
                                    metadata['tcgplayer_id'] = tcgplayer_id
                                    metadata['tcgplayer_url'] = href
                                else:
                                    # Fallback: get text content as ID
                                    tcgplayer_id = value_cell.get_text().strip()
                                    if tcgplayer_id.isdigit():
                                        metadata['tcgplayer_id'] = tcgplayer_id
                                        metadata['tcgplayer_url'] = f"https://tcgplayer.pxf.io/c/3029031/1780961/21018?u=https%3A%2F%2Fwww.tcgplayer.com%2Fproduct%2F{tcgplayer_id}%2F-"
                            else:
                                value = value_cell.get_text().strip()
                                if 'notes' in label:
                                    metadata['notes'] = value
                                elif 'card number' in label:
                                    metadata['card_number'] = value.replace('#', '').strip()
                                elif 'release date' in label:
                                    metadata['release_date'] = value
                                elif 'genre' in label:
                                    metadata['genre'] = value
            
            # Method 3: Look for specific patterns in the page text (last resort)
            if not metadata.get('tcgplayer_id'):
                # Look for "TCGPlayer ID:" followed by a number or link
                page_text = soup.get_text()
                tcgplayer_match = re.search(r'TCGPlayer ID[:\s]+(\d+)', page_text, re.IGNORECASE)
                if tcgplayer_match:
                    tcgplayer_id = tcgplayer_match.group(1)
                    metadata['tcgplayer_id'] = tcgplayer_id
                    metadata['tcgplayer_url'] = f"https://tcgplayer.pxf.io/c/3029031/1780961/21018?u=https%3A%2F%2Fwww.tcgplayer.com%2Fproduct%2F{tcgplayer_id}%2F-"
                
                # Look for "Notes:" followed by rarity/variant info
                if not metadata.get('notes'):
                    notes_match = re.search(r'Notes[:\s]+([^\n\r]+)', page_text, re.IGNORECASE)
                    if notes_match:
                        metadata['notes'] = notes_match.group(1).strip()
            
            # Method 4: Extract card number from page title or URL if not found in details
            if not metadata.get('card_number'):
                # Try to extract from page title (e.g., "Mewtwo VSTAR #GG44")
                title_element = soup.find('title')
                if title_element:
                    title_text = title_element.get_text()
                    number_match = re.search(r'#([A-Z0-9]+)', title_text)
                    if number_match:
                        metadata['card_number'] = number_match.group(1)
                
                # Fallback: extract from URL (e.g., /mewtwo-vstar-gg44)
                if not metadata.get('card_number'):
                    # Extract the last part of the URL path which often contains the card number
                    url_parts = url.rstrip('/').split('/')
                    if url_parts:
                        last_part = url_parts[-1]
                        # Look for patterns like "card-name-gg44" or "card-name-57"
                        number_match = re.search(r'-([a-z0-9]+)$', last_part, re.IGNORECASE)
                        if number_match:
                            potential_number = number_match.group(1).upper()
                            # Only use if it looks like a card number (contains letters or is numeric)
                            if re.match(r'^[A-Z]*\d+[A-Z]*$', potential_number):
                                metadata['card_number'] = potential_number
            
            logger.debug(
                "product_metadata_extracted",
                url=url,
                metadata_keys=list(metadata.keys()),
                tcgplayer_id=metadata.get('tcgplayer_id'),
                notes=metadata.get('notes')
            )
            
            return metadata
            
        except Exception as e:
            logger.error(
                "extract_product_metadata_error",
                url=url,
                error=str(e),
                exc_info=True
            )
            return {}

    def _extract_pricing_page_url(self, html: str, offers_url: str) -> Optional[str]:
        """Extract the pricing page URL from an offers page."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for "See Historic Prices" link
            pricing_link = soup.find("a", string=re.compile("See Historic Prices", re.I))
            if pricing_link and pricing_link.get("href"):
                href = pricing_link.get("href")
                if href.startswith("/"):
                    return self.BASE_URL + href
                return href
            
            # Fallback: look for any link to /game/pokemon-
            game_links = soup.find_all("a", href=re.compile(r"/game/pokemon-"))
            if game_links:
                href = game_links[0].get("href")
                if href.startswith("/"):
                    return self.BASE_URL + href
                return href
            
            logger.warning(
                "pricecharting_pricing_page_not_found",
                offers_url=offers_url
            )
            return None
            
        except Exception as e:
            logger.error(
                "pricecharting_extract_pricing_url_error",
                offers_url=offers_url,
                error=str(e),
                exc_info=True
            )
            return None

    def is_available(self) -> bool:
        """Check if scraping service is available."""
        return True  # Always available since we don't need API tokens


# Global service instance
pricecharting_scraper = PriceChartingScraper()
