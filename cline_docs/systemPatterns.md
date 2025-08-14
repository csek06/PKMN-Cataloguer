# System Patterns - Pokémon Card Cataloguer

## High-Level Architecture
**Single-User Web Application** with simplified PriceCharting-only integration:

```
Frontend (HTMX + Alpine.js + Tailwind)
    ↓ HTTP Requests
FastAPI Application Layer
    ↓ Business Logic
PriceCharting Scraper Service
    ↓ Data Access
SQLModel ORM
    ↓ Storage
SQLite Database
```

## Technical Patterns and Data Flow

### Request Flow Pattern
1. **User Action** → HTMX request to FastAPI endpoint
2. **API Route** → Validates input, calls PriceCharting scraper
3. **Scraper Service** → Fetches and parses PriceCharting data
4. **Database Layer** → SQLModel ORM operations
5. **Response** → Jinja2 template renders HTML fragment
6. **Frontend** → HTMX swaps content, Alpine.js handles state

### Simplified Search Flow Pattern
```
SINGLE PATH (PriceCharting Only):
User Query → PriceCharting Search → Immediate Results with Pricing
    ↓
"charizard gx 57" → PriceCharting scrape → Card candidates with prices (2-5s)
    ↓
Search modal template → HTMX modal display with pricing

COLLECTION PATH (Direct Add):
User Selection → Collection Addition with PriceCharting Data
    ↓
PC card selection → Create Card + CollectionEntry + PriceSnapshot → Add to collection
    ↓
Collection table update → HTMX table row insertion
```

### Collection Management Pattern
```
Add Card → Create Card from PC Data → Create Collection Entry → Price Snapshot
    ↓
PC Product ID → Card table (PC metadata) → CollectionEntry table (user data) → PriceSnapshot table (pricing history)
```

## Key Technical Decisions

### Database Design
- **SQLite with WAL mode**: Fast local access, concurrent reads
- **SQLModel ORM**: Type-safe database operations with Pydantic integration
- **Relationship Strategy**: Foreign keys with explicit joins (no lazy loading)
- **Price Storage**: Cents as integers to avoid floating-point precision issues
- **Card Identification**: Uses `pc_{product_id}` format for unique tcg_id field

### PriceCharting Integration Strategy
- **Async HTTP Client**: httpx for non-blocking scraping requests
- **HTML Parsing**: BeautifulSoup4 for reliable data extraction
- **Rate Limiting**: Built-in delays to respect PriceCharting's servers
- **Error Handling**: Graceful degradation when scraping fails
- **Caching**: In-memory caching of search results to reduce requests

### Frontend Architecture
- **HTMX**: Server-side rendering with dynamic content swapping
- **Alpine.js**: Minimal client-side state management
- **Tailwind CSS**: Utility-first styling via CDN
- **No Build Step**: Direct CDN includes for rapid development

## Operational Patterns and Error Handling

### Logging Strategy
- **Dual Output**: Both file-based and console logging for Docker compatibility
- **File-based Logging**: Persistent logs stored in `/data/logs/` directory
- **Log Rotation**: 10MB max file size, 5 backup files with gzip compression
- **Structured Separation**: Separate log files for different log types
- **Request Tracing**: UUID request IDs across all operations
- **Scraping Call Logging**: Sanitized URLs (tokens redacted)
- **Performance Metrics**: Duration tracking for all operations

### Log File Structure
```
/data/logs/
├── app.log          # All application logs (INFO, WARNING, ERROR)
├── app.log.1.gz     # Rotated application logs (compressed)
├── access.log       # HTTP request logs with timing and client info
├── external.log     # External API calls (PriceCharting scraper)
├── error.log        # Error-level messages only
└── *.log.N.gz       # Compressed rotated logs (up to 5 files each)
```

### Error Handling Patterns
- **HTTP Exceptions**: Proper status codes with user-friendly messages
- **Scraping Failures**: Graceful fallbacks, no user-facing errors
- **Database Errors**: Transaction rollback with detailed logging
- **Validation Errors**: Clear field-level error messages

### Scheduling Pattern
- **APScheduler**: Daily price refresh at 3:00 AM local time
- **Batch Processing**: Configurable batch sizes for respectful scraping
- **Exponential Backoff**: Retry logic for failed scraping attempts
- **Progress Tracking**: Detailed logging of batch job progress

### Real-time Communication Pattern (NEEDS IMPLEMENTATION)
- **Current**: HTMX polling every 5 seconds during jobs (inefficient)
- **Target**: Server-Side Events (SSE) for real-time job status updates
- **Event Types**: job_started, job_progress, job_completed, job_failed
- **Connection Management**: EventSource with automatic reconnection
- **Performance**: Eliminates unnecessary polling requests

### Security Patterns
- **Environment Variables**: All secrets in .env files
- **URL Sanitization**: Token redaction in all logged URLs
- **Input Validation**: Pydantic schemas for all API inputs
- **CORS**: Configured for local development, production-ready

## Data Flow Relationships
```
Card (1) ←→ (N) CollectionEntry ←→ (N) PriceSnapshot
Card (1) ←→ (1) PriceChartingLink ←→ (N) PriceSnapshot
```

**Key Relationships**:
- One Card can have multiple CollectionEntries (different conditions/variants)
- One Card can have multiple PriceSnapshots (historical pricing)
- One Card has one PriceChartingLink (PC product mapping)
- CollectionEntry tracks user-specific data (quantity, condition, notes)
- PriceSnapshot tracks market data over time from PriceCharting

## Architecture Benefits

### Simplified Maintenance
- **Single Data Source**: No API coordination or fallback logic
- **Consistent Data Format**: All data follows PriceCharting structure
- **Reduced Dependencies**: Fewer external service integrations
- **Predictable Performance**: No variable API response times

### Enhanced Reliability
- **Direct Scraping**: Less dependent on API availability
- **Local Caching**: Reduced external requests
- **Graceful Degradation**: App works without pricing when needed
- **Consistent User Experience**: Uniform data presentation

### Development Efficiency
- **Faster Iteration**: Single integration point to maintain
- **Easier Testing**: Mock single service instead of multiple APIs
- **Clear Data Flow**: Straightforward request/response patterns
- **Reduced Complexity**: Fewer edge cases and error scenarios
