# Pokémon Card Cataloguer

A single-user Pokémon card collection manager with real-time pricing integration. Built with FastAPI, HTMX, and SQLite, powered by PriceCharting for accurate market data.

## Features

- **🔍 Natural Language Search**: Type queries like "buzzwole gx 57/111" or "charizard base set" to find cards
- **📊 Dual View Modes**: Table view for detailed management, poster view for visual browsing  
- **💰 Real-time Pricing**: Live market prices from PriceCharting during search and collection viewing
- **📈 Price History**: Track price changes over time with interactive charts
- **⚡ Smart Collection Management**: Add cards with one click, manage quantities with +/- buttons
- **🎯 Zero-Quantity Deletion**: Reduce quantity to 0 to automatically remove cards from collection
- **🔄 Automated Price Updates**: Daily scheduled price refreshes with comprehensive job tracking
- **⚙️ Database-Driven Settings**: Manage configuration through web interface
- **📝 Production Logging**: File-based structured logs with rotation and compression
- **🐳 Docker Support**: Single container deployment with persistent data

## Quick Start

1. **Clone and Setup**
   ```bash
   git clone https://github.com/csek06/PKMN-Cataloguer.git
   cd PKMN-Cataloguer
   cp .env.example .env
   ```

2. **Run with Docker**
   ```bash
   docker compose up --build
   ```

3. **Access the Application**
   Open http://localhost:8000

4. **Start Collecting**
   - Search for cards using natural language
   - Click "Add to Collection" from search results
   - Manage quantities with +/- buttons
   - View detailed card information by clicking card names
   - Switch between table and poster views

## Architecture

### Single Data Source Design
The application uses **PriceCharting as the single source of truth** for both card discovery and pricing data. This simplified architecture provides:

- **Consistent Data**: All information comes from the same marketplace source
- **Real-time Pricing**: Current market prices during search and collection viewing
- **Simplified Maintenance**: No complex API coordination or fallback logic
- **Reliable Performance**: Predictable response times and data format

### Tech Stack
- **Backend**: Python 3.12, FastAPI, SQLModel (SQLite with WAL mode)
- **Frontend**: HTMX, Alpine.js, Tailwind CSS, Chart.js
- **Data Source**: PriceCharting (scraping-based integration)
- **Scheduling**: APScheduler for automated price updates
- **Logging**: Structured file-based logging with rotation
- **Deployment**: Docker with single container

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DATA_DIR` | Data directory path | `/data` | No |
| `SECRET_KEY` | Application secret key | `change-me` | Yes |

### Database-Driven Settings

Most configuration is now managed through the web interface at `/settings`:

- **Log Level**: DEBUG, INFO, WARNING, ERROR
- **Timezone**: 35+ timezone options grouped by region
- **Price Refresh Batch Size**: 10-1000 cards per batch
- **Rate Limiting**: 0.1-10 requests per second to PriceCharting
- **SQL Echo**: Enable verbose database logging for debugging

### PriceCharting Integration

The application uses direct web scraping of PriceCharting in a bot-friendly manner:

- **No API Token Required**: Direct scraping eliminates the need for API keys
- **Respectful Scraping**: Built-in rate limiting and delays to respect PriceCharting's servers
- **Reliable Data**: Extracts card information, pricing, and metadata directly from product pages
- **Automatic Fallbacks**: Multiple parsing methods ensure robust data extraction
## Usage

### Search Capabilities

The search system understands natural language queries:

- **Basic**: `charizard` - Find cards with "charizard" in the name
- **With Number**: `charizard 4/102` - Find card #4 from a set of 102  
- **With Set**: `charizard base` - Find Charizard from Base Set
- **With Variants**: `charizard gx` - Find Charizard-GX cards
- **Complex**: `buzzwole gx 57/111 crimson invasion` - Specific card from specific set

**Supported Patterns**: `gx`, `ex`, `vmax`, `vstar`, `v`, `full art`, `reverse`, `holo`, `shadowless`, `first edition`

### Collection Management

#### Adding Cards
1. Type search query in the search box
2. Click search icon or press Enter
3. Modal opens with "Searching for cards..." loading state
4. Results appear with card images and current pricing
5. Click "Add to Collection" to add with real-time pricing data

#### Managing Quantities
- **Increase**: Click `+` button to add more copies
- **Decrease**: Click `-` button to reduce quantity
- **Remove**: Reduce quantity to 0 to automatically remove from collection
- **All changes happen instantly** without page refresh

#### Collection Views
- **Table View**: Sortable columns with detailed information
  - Click card names to open details modal
  - All 10 columns are sortable (Name, Set, #, Rarity, Variant, Condition, Qty, Ungraded Price, PSA 10 Price, Updated)
  - Hover effects and sort indicators
- **Poster View**: Visual grid layout with card images

#### Card Details
- **Comprehensive Information**: Images, stats, set details, pricing history
- **Editable Conditions**: 7-option dropdown (Near Mint, Lightly Played, etc.)
- **Price History Charts**: Interactive visualization of price trends
- **External Links**: Direct links to PriceCharting and TCGPlayer product pages

### Pricing Features

- **Real-time Search Pricing**: Current market prices shown during search
- **Collection Pricing**: Ungraded and PSA 10 prices with update dates
- **Automated Updates**: Daily refresh at 3:00 AM (configurable timezone)
- **Manual Refresh**: Trigger updates from Settings page with real-time progress
- **Price History**: Historical data with interactive charts
- **Job Tracking**: Complete history of all price refresh jobs

## Project Structure

```
app/
├── main.py                    # FastAPI application entry point
├── config.py                  # Configuration management with database settings
├── logging.py                 # File-based structured logging setup
├── db.py                      # Database connection and SQLite setup
├── models.py                  # SQLModel database models
├── schemas.py                 # Pydantic request/response schemas
├── services/                  # Business logic services
│   ├── parser.py              # Natural language query parsing
│   ├── pricecharting_scraper.py # PriceCharting integration
│   └── pricing_refresh.py     # Automated price update service
├── api/                       # API route handlers
│   ├── routes_search.py       # Card search endpoints
│   ├── routes_collection.py   # Collection management
│   ├── routes_cards.py        # Card details and history
│   ├── routes_settings.py     # Settings management
│   └── routes_admin.py        # Administrative functions
└── ui/                        # UI route handlers
    └── pages.py               # Main page rendering

templates/                     # Jinja2 HTML templates
├── base.html                  # Base template with navigation
├── index.html                 # Main collection page
├── settings.html              # Settings management page
├── _search_modal.html         # Search results modal
├── _collection_table.html     # Sortable collection table
├── _collection_table_row.html # Individual table rows
├── _collection_info_section.html # Reusable collection info component
├── _card_details.html         # Card details modal
└── _*.html                    # Other template fragments

data/                          # Persistent data directory
├── app.db                     # SQLite database
└── logs/                      # Log files with rotation
    ├── app.log                # All application logs
    ├── access.log             # HTTP request logs
    ├── external.log           # PriceCharting API calls
    ├── error.log              # Error-level messages only
    └── *.log.N.gz             # Compressed rotated logs

tests/                         # Unit and integration tests
```

## Database Schema

### Core Models

#### Card
- Basic card information extracted from PriceCharting
- Images, set information, rarity, card numbers
- Unique identifier using PriceCharting product ID

#### CollectionEntry  
- User's collection with quantities and conditions
- Links to Card model with foreign key relationship
- Tracks purchase prices, notes, and variants

#### PriceChartingLink
- Links cards to PriceCharting products
- Stores product IDs, URLs, and metadata
- Tracks TCGPlayer integration data

#### PriceSnapshot
- Historical price data points over time
- Supports multiple price types (ungraded, PSA 10, etc.)
- Linked to both Card and PriceChartingLink models

#### AppSettings
- Database-stored configuration settings
- Replaces environment variables for user-configurable options
- Cached for performance with automatic invalidation

#### JobHistory
- Tracks all price refresh jobs
- Stores job status, progress, and error information
- Provides audit trail for automated processes

## API Endpoints

### Public Endpoints
- `GET /` - Main collection page
- `GET /settings` - Settings management page
- `GET /api/healthz` - Application health check

### Search & Discovery
- `POST /api/search` - Search PriceCharting for cards (returns HTML modal)
- `POST /api/select-card` - Add selected card to collection with pricing

### Collection Management
- `GET /api/collection` - Get collection table view (HTML)
- `GET /api/collection/poster` - Get collection poster view (HTML)
- `POST /api/collection` - Add card to collection
- `PATCH /api/collection/{entry_id}` - Update collection entry (quantity, condition)

### Card Details
- `GET /api/cards/{card_id}` - Get card details modal (HTML)
- `GET /api/cards/{card_id}/price-history.json` - Price history data for charts

### Settings Management
- `GET /api/settings/app` - Get current application settings (JSON)
- `PUT /api/settings/app` - Update application settings
- `GET /api/settings/app/form` - Get settings form (HTML)

### Price Refresh System
- `POST /api/settings/pricing/run` - Trigger manual price refresh
- `GET /api/settings/pricing/status` - Get current job status (HTML)
- `GET /api/settings/pricing/history` - Get job history (HTML)
- `GET /api/settings/pricing/stats` - Get pricing statistics (HTML)

## Logging System

### File-Based Logging
The application uses comprehensive file-based logging stored in `/data/logs/`:

- **app.log**: All application logs (INFO, WARNING, ERROR levels)
- **access.log**: HTTP request logs with timing and client information
- **external.log**: External API calls to PriceCharting (URLs sanitized)
- **error.log**: Error-level messages only for quick debugging

### Log Rotation
- **File Size**: 10MB maximum per log file
- **Backup Files**: Keep 5 rotated files per log type
- **Compression**: Automatic gzip compression (.gz files)
- **Dual Output**: Both file and console logging (Docker-compatible)

### Log Format
Structured JSON logging with consistent fields:

```json
{
  "timestamp": "2025-08-14T19:18:00.123Z",
  "level": "info", 
  "event": "http_request",
  "request_id": "b9c8d7e6-f5a4-3b2c-1d0e-9f8e7d6c5b4a",
  "method": "POST",
  "path": "/api/search",
  "status": 200,
  "duration_ms": 1247,
  "client_ip": "172.18.0.1",
  "route": "POST /api/search"
}
```

## Development

### Local Development Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Edit configuration if needed (SECRET_KEY for production)
nano .env

# Run development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Running Tests

```bash
# Install test dependencies (included in requirements.txt)
pip install pytest pytest-asyncio

# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_pricecharting_scraper.py -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

### Development Features

- **Hot Reload**: Uvicorn automatically reloads on code changes
- **Debug Logging**: Set `LOG_LEVEL=DEBUG` in settings for verbose output
- **SQL Echo**: Enable in settings to see all database queries
- **Test Database**: Tests use separate SQLite database

## Deployment

### Docker Compose (Recommended)

```bash
# Build and run in background
docker compose up --build -d

# View real-time logs
docker compose logs -f

# Stop services
docker compose down

# Update and restart
git pull
docker compose up --build -d
```

### Manual Docker Deployment

```bash
# Build image
docker build -t pokemon-cataloguer .

# Run container with data persistence
docker run -d \
  --name pokemon-cataloguer \
  -p 8000:8000 \
  -v $(pwd)/data:/data \
  --env-file .env \
  pokemon-cataloguer

# View logs
docker logs -f pokemon-cataloguer
```

### Production Considerations

- **Data Persistence**: Mount `/data` volume for database and logs
- **Environment Variables**: Use `.env` file or Docker secrets
- **Reverse Proxy**: Consider nginx for SSL termination
- **Monitoring**: Log files provide comprehensive application metrics
- **Backups**: Regular backups of `/data/app.db` recommended

## Troubleshooting

### Common Issues

**Search returns no results**
- Verify internet connectivity to PriceCharting
- Check if PriceCharting website is accessible
- Review `external.log` for scraping errors
- Try different search terms

**No pricing data showing**
- Verify internet connectivity to PriceCharting
- Check if PriceCharting website is accessible
- Review `external.log` for scraping errors
- Try different search terms or wait and retry

**Price updates not running**
- Check Settings page for scheduler status
- Verify timezone configuration in settings
- Review `app.log` for scheduler errors
- Ensure sufficient disk space for database updates

**Collection changes not saving**
- Check browser console for JavaScript errors
- Verify HTMX requests are completing successfully
- Review `access.log` for HTTP request errors
- Ensure database file is writable

**Application won't start**
- Check `error.log` for startup errors
- Verify `/data` directory permissions
- Ensure port 8000 is available
- Check Docker container logs

### Health Check

Visit `/api/healthz` to verify application status:

```json
{
  "status": "healthy",
  "database": true,
  "timestamp": "2025-08-14T19:18:00.000Z"
}
```

### Debug Mode

Enable debug logging for detailed troubleshooting:
1. Go to Settings page
2. Set Log Level to "DEBUG"
3. Save settings
4. Check `app.log` for detailed information

## Performance

### System Requirements
- **Memory**: 512MB RAM minimum, 1GB recommended
- **Storage**: 100MB for application, additional space for collection data
- **CPU**: Single core sufficient for personal use
- **Network**: Internet connection required for PriceCharting integration

### Performance Characteristics
- **Search Speed**: 2-5 seconds for PriceCharting queries
- **Collection Loading**: Sub-second for collections under 1000 cards
- **Database Performance**: SQLite with WAL mode for concurrent access
- **Memory Usage**: ~50MB base, scales with collection size

### Optimization Tips
- **Batch Size**: Adjust price refresh batch size in settings (default: 200)
- **Rate Limiting**: Configure PriceCharting request rate (default: 1/sec)
- **Log Levels**: Use INFO or WARNING in production to reduce log volume
- **Database Maintenance**: SQLite auto-vacuums, no manual maintenance needed

## Contributing

1. Fork the repository on GitHub
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with appropriate tests
4. Ensure all tests pass (`pytest tests/`)
5. Update documentation if needed
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

### Development Guidelines
- Follow existing code style and patterns
- Add tests for new functionality
- Update documentation for user-facing changes
- Use structured logging for new features
- Maintain backward compatibility when possible

## License

This project is provided as-is for educational and personal use. See the repository for specific license terms.

## Support

For issues and questions:

1. **Check Documentation**: Review this README and troubleshooting section
2. **Review Logs**: Check `/data/logs/` files for error details
3. **GitHub Issues**: Open an issue with logs and reproduction steps
4. **Health Check**: Verify `/api/healthz` shows healthy status

## Acknowledgments

- **PriceCharting**: Market data and pricing information
- **Pokémon Company**: Card images and metadata
- **FastAPI**: High-performance web framework
- **HTMX**: Modern HTML-over-the-wire approach
- **SQLModel**: Type-safe database operations
