# Tech Context - Pokémon Card Cataloguer

## Core Technologies and Frameworks

### Backend Stack
- **Python 3.12**: Modern Python with latest features
- **FastAPI 0.115.x**: High-performance async web framework
- **SQLModel 0.0.22**: Type-safe ORM combining SQLAlchemy + Pydantic
- **SQLite**: Embedded database with WAL mode for performance
- **Uvicorn 0.30.x**: ASGI server with hot reload for development

### Frontend Stack
- **HTMX 1.9.10**: HTML-over-the-wire for dynamic interactions
- **Alpine.js 3.x**: Minimal reactive framework for client-side state
- **Tailwind CSS**: Utility-first CSS framework via CDN
- **Chart.js**: Client-side charting for price history visualization
- **Jinja2 3.1.x**: Server-side templating engine
- **EventSource API**: Native browser SSE support (NEEDS IMPLEMENTATION)

### External APIs
- **PriceCharting**: Primary data source for card search and pricing
- **httpx 0.27.x**: Async HTTP client for PriceCharting scraping
- **BeautifulSoup4**: HTML parsing for PriceCharting data extraction

### Development & Operations
- **APScheduler 3.10.x**: Background job scheduling for price refresh
- **structlog 24.x**: Structured logging with JSON output
- **python-multipart 0.0.9**: Form parsing for HTMX requests
- **python-dotenv 1.0.x**: Environment variable management

## Integration Patterns

### Database Integration
```python
# SQLModel pattern for type-safe database operations
class Card(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tcg_id: str = Field(unique=True, index=True)  # Uses pc_{product_id} format
    name: str = Field(index=True)
    # ... other fields

# Session management with dependency injection
def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
```

### Server-Side Events Integration (NEEDS IMPLEMENTATION)
```python
# FastAPI SSE endpoint pattern
@router.get("/pricing/events")
async def pricing_events(request: Request):
    async def event_generator():
        while True:
            # Check for job updates
            job_status = get_current_job_status()
            if job_status:
                yield f"data: {json.dumps(job_status)}\n\n"
            await asyncio.sleep(1)
    
    return StreamingResponse(event_generator(), media_type="text/plain")

# Frontend EventSource pattern
const eventSource = new EventSource('/api/settings/pricing/events');
eventSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    updateJobStatus(data);
};
```

### PriceCharting Integration
```python
# Async HTTP client with proper error handling
async def search_cards(self, query, request):
    async with httpx.AsyncClient() as client:
        response = await client.get(search_url, headers=self.headers)
        # Parse HTML with BeautifulSoup for card data extraction
```

### HTMX Integration
```html
<!-- Server-side rendered fragments -->
<div hx-get="/api/collection" hx-trigger="load once">
    <!-- Content loaded dynamically -->
</div>
```

## Technical Constraints

### Performance Constraints
- **SQLite Limitations**: Single writer, but WAL mode allows concurrent reads
- **PriceCharting Rate Limits**: Respectful scraping with delays between requests
- **Memory Usage**: All data stored locally, no external database dependencies

### Development Constraints
- **No Build Step**: All frontend dependencies via CDN for simplicity
- **Single User**: No authentication or multi-tenancy required
- **Local First**: Designed to run locally, Docker for deployment

### API Constraints
- **PriceCharting Scraping**: Requires respectful rate limiting and error handling
- **Network Timeouts**: 30-second timeout for external requests
- **HTML Parsing**: Dependent on PriceCharting's HTML structure stability

## Development Environment

### Local Development Setup
```bash
# Virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Dependencies
pip install -r requirements.txt

# Environment variables
cp .env.example .env
# Edit .env with PriceCharting token

# Run development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker Deployment
```dockerfile
# Multi-stage build not needed (no Node.js)
FROM python:3.12-slim
# Install system dependencies, Python packages
# Create non-root user, set up healthcheck
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Environment Variables
```bash
# Database and application config
DB_PATH=/data/app.db
SECRET_KEY=change-me-in-production
LOG_LEVEL=INFO
LOCAL_TZ=America/New_York

# Price refresh configuration
PRICE_REFRESH_BATCH_SIZE=200
PRICE_REFRESH_REQUESTS_PER_SEC=1
SQL_ECHO=false
```

## Key Dependencies and Versions
```txt
fastapi==0.115.*          # Web framework
uvicorn[standard]==0.30.*  # ASGI server
sqlmodel==0.0.22          # Type-safe ORM
httpx==0.27.*             # Async HTTP client
beautifulsoup4==4.12.*    # HTML parsing
apscheduler==3.10.*       # Job scheduling
jinja2==3.1.*             # Templating
python-dotenv==1.0.*      # Environment management
structlog==24.*           # Structured logging
orjson==3.10.*            # Fast JSON serialization
python-multipart==0.0.9   # Form parsing
pydantic-settings==2.0.*  # Settings management
pytest==7.4.*             # Testing framework
pytest-asyncio==0.21.*    # Async testing support
```

## Integration Testing Strategy
- **Unit Tests**: Service layer and parser logic
- **Integration Tests**: API endpoints with mocked PriceCharting responses
- **End-to-End Tests**: Full workflow testing with test database
- **Scraping Tests**: PriceCharting HTML parsing validation with sample data

## Architecture Simplifications
**Single Data Source**: By using only PriceCharting, we eliminate:
- Complex API fallback logic
- Multiple data source synchronization
- API rate limit coordination
- Data consistency issues between sources

This results in a more maintainable, predictable system with faster development cycles.
