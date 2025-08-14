# Product Context - Pokémon Card Cataloguer

## Project Purpose and Goals
A single-user Pokémon card cataloguer web application that allows users to:
- Search for Pokémon cards using natural language queries (e.g., "charizard gx", "pikachu 25/102")
- Add cards to their personal collection directly from search results
- View collection in both table and poster formats
- Track card prices through PriceCharting integration
- Manage collection with sorting, filtering, and pagination

## Core User Problems/Solutions
**Problem**: Pokémon card collectors need an easy way to catalog and track their collection with accurate pricing data.

**Solution**: Web-based cataloguer with:
- Natural language search powered by PriceCharting scraping
- Real-time price tracking via PriceCharting integration
- Radarr-style UI with table and poster views
- Local SQLite database for fast access
- Production-grade logging and monitoring

## Key Workflows
1. **Card Search & Add**:
   - User types natural query (e.g., "charizard base set", "buzzwole gx 57")
   - System searches PriceCharting directly for matching cards
   - Results shown in modal with images and current pricing
   - User clicks "Add to Collection" to add card with pricing data

2. **Collection Management**:
   - View cards in sortable table or poster grid
   - Filter by name, set, condition
   - Edit quantities, conditions, notes
   - Track purchase prices and variants

3. **Price Tracking**:
   - Real-time pricing from PriceCharting during search
   - Historical price snapshots stored in database
   - Price history charts per card
   - Graceful degradation when no pricing token available

## Product Priorities
1. **Core Functionality**: Search, add, view collection with PriceCharting integration
2. **Data Integrity**: Reliable SQLite storage with PriceCharting product linking
3. **Performance**: Fast PriceCharting searches (sub-5 seconds), efficient scraping
4. **User Experience**: Clean HTMX-powered UI, responsive design
5. **Monitoring**: Structured logging for debugging and analytics

## Architecture Philosophy
**Single Source of Truth**: PriceCharting serves as the primary data source for both card discovery and pricing information. This eliminates the complexity of multiple API integrations while providing users with the most relevant marketplace data for their collection tracking needs.
