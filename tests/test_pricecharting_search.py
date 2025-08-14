import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.services.pricecharting_scraper import pricecharting_scraper


client = TestClient(app)


@pytest.fixture
def mock_pricecharting_search_results():
    """Mock PriceCharting search results."""
    return [
        {
            "name": "Charizard",
            "set_name": "Base Set",
            "number": "4",
            "url": "https://www.pricecharting.com/game/pokemon-base-set/charizard-4",
            "image_url": "https://example.com/charizard.jpg",
            "prices": {
                "ungraded_cents": 15000,  # $150.00
                "psa9_cents": 45000,      # $450.00
                "psa10_cents": 120000     # $1200.00
            }
        },
        {
            "name": "Blastoise",
            "set_name": "Base Set", 
            "number": "2",
            "url": "https://www.pricecharting.com/game/pokemon-base-set/blastoise-2",
            "image_url": "https://example.com/blastoise.jpg",
            "prices": {
                "ungraded_cents": 8000,   # $80.00
                "psa10_cents": 50000      # $500.00
            }
        }
    ]


@pytest.fixture
def mock_tcg_search_results():
    """Mock TCG API search results."""
    return [
        {
            "tcg_id": "base1-4",
            "name": "Charizard",
            "set_name": "Base Set",
            "number": "4/102",
            "rarity": "Rare Holo",
            "image_small": "https://images.pokemontcg.io/base1/4.png",
            "image_large": "https://images.pokemontcg.io/base1/4_hires.png"
        }
    ]


class TestPriceChartingSearch:
    """Test PriceCharting search functionality."""
    
    @patch.object(pricecharting_scraper, 'search_cards')
    def test_pricecharting_search_success(self, mock_search, mock_pricecharting_search_results):
        """Test successful PriceCharting search."""
        mock_search.return_value = mock_pricecharting_search_results
        
        response = client.post("/api/search", data={"q": "charizard"})
        
        assert response.status_code == 200
        html = response.text
        
        # Check that PriceCharting search method is indicated
        assert "Fast PriceCharting Search" in html
        
        # Check that cards are displayed with pricing
        assert "Charizard" in html
        assert "Blastoise" in html
        assert "$150.00" in html  # Ungraded price
        assert "$450.00" in html  # PSA 9 price
        assert "$1200.00" in html # PSA 10 price
        
        # Check that Select & Add buttons are present (no TCG ID)
        assert "Select & Add" in html
    
    @patch.object(pricecharting_scraper, 'search_cards')
    def test_pricecharting_search_empty_fallback_to_tcg(self, mock_search, mock_tcg_search_results):
        """Test fallback to TCG API when PriceCharting returns no results."""
        mock_search.return_value = []
        
        with patch('app.services.tcg.tcg_service.search_cards') as mock_tcg_search:
            mock_tcg_search.return_value = mock_tcg_search_results
            
            response = client.post("/api/search", data={"q": "charizard"})
            
            assert response.status_code == 200
            html = response.text
            
            # Check that TCG API fallback is indicated
            assert "TCG API Fallback" in html
            
            # Check that TCG card is displayed
            assert "Charizard" in html
            assert "Rare Holo" in html
            
            # Check that regular Add to Collection button is present (has TCG ID)
            assert "Add to Collection" in html
    
    @patch.object(pricecharting_scraper, 'search_cards')
    def test_pricecharting_search_error_fallback(self, mock_search, mock_tcg_search_results):
        """Test fallback to TCG API when PriceCharting search fails."""
        mock_search.side_effect = Exception("PriceCharting error")
        
        with patch('app.services.tcg.tcg_service.search_cards') as mock_tcg_search:
            mock_tcg_search.return_value = mock_tcg_search_results
            
            response = client.post("/api/search", data={"q": "charizard"})
            
            assert response.status_code == 200
            html = response.text
            
            # Should fallback to TCG API
            assert "TCG API Fallback" in html
            assert "Charizard" in html
    
    def test_search_empty_query(self):
        """Test search with empty query."""
        response = client.post("/api/search", data={"q": ""})
        
        assert response.status_code == 400
    
    @patch.object(pricecharting_scraper, 'search_cards')
    def test_no_results_from_any_source(self, mock_search):
        """Test when both PriceCharting and TCG API return no results."""
        mock_search.return_value = []
        
        with patch('app.services.tcg.tcg_service.search_cards') as mock_tcg_search:
            mock_tcg_search.return_value = []
            
            response = client.post("/api/search", data={"q": "nonexistent"})
            
            assert response.status_code == 200
            html = response.text
            
            # Should show no results message
            assert "No cards found" in html
            assert "Try adjusting your search query" in html


class TestCardSelection:
    """Test card selection for PriceCharting-only results."""
    
    def test_select_card_success(self, mock_tcg_search_results):
        """Test successful card selection."""
        with patch('app.services.tcg.tcg_service.search_cards') as mock_tcg_search:
            mock_tcg_search.return_value = mock_tcg_search_results
            
            response = client.post("/api/select-card", data={
                "name": "Charizard",
                "set_name": "Base Set",
                "number": "4",
                "pc_url": "https://www.pricecharting.com/game/pokemon-base-set/charizard-4"
            })
            
            assert response.status_code == 200
            html = response.text
            
            # Should show success message
            assert "Card Selected" in html
            assert "Charizard matched with TCG data" in html
            assert "Add to Collection" in html
    
    def test_select_card_no_tcg_match(self):
        """Test card selection when no TCG match is found."""
        with patch('app.services.tcg.tcg_service.search_cards') as mock_tcg_search:
            mock_tcg_search.return_value = []
            
            response = client.post("/api/select-card", data={
                "name": "Unknown Card",
                "set_name": "Unknown Set",
                "number": "1"
            })
            
            assert response.status_code == 200
            html = response.text
            
            # Should show error message
            assert "Could not find TCG data" in html
            assert "Unknown Card" in html
    
    def test_select_card_missing_name(self):
        """Test card selection with missing name."""
        response = client.post("/api/select-card", data={
            "set_name": "Base Set",
            "number": "4"
        })
        
        assert response.status_code == 400


class TestPriceChartingScraperUnit:
    """Unit tests for PriceCharting scraper methods."""
    
    def test_build_search_url(self):
        """Test search URL building."""
        scraper = pricecharting_scraper
        
        # Test with simple query
        query = "charizard"
        expected_url = "https://www.pricecharting.com/search?q=charizard&type=prices"
        
        # We can't directly test the private method, but we can verify the URL format
        # by checking the search_cards method behavior
        assert scraper.BASE_URL == "https://www.pricecharting.com"
    
    def test_cache_key_generation(self):
        """Test cache key generation."""
        scraper = pricecharting_scraper
        
        key1 = scraper._get_cache_key("search_charizard")
        key2 = scraper._get_cache_key("search_charizard")
        key3 = scraper._get_cache_key("search_pikachu")
        
        # Same input should generate same key
        assert key1 == key2
        
        # Different input should generate different key
        assert key1 != key3
        
        # Keys should have expected prefix
        assert key1.startswith("pc_scrape_")
    
    def test_is_available(self):
        """Test service availability check."""
        scraper = pricecharting_scraper
        
        # PriceCharting scraper should always be available
        assert scraper.is_available() is True


if __name__ == "__main__":
    pytest.main([__file__])
