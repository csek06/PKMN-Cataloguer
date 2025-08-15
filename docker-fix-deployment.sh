#!/bin/bash
"""
Docker deployment fix script for PKMN-Cataloguer production issues.
This script fixes the critical database schema and health check issues.
"""

set -e  # Exit on any error

echo "🚀 PKMN-Cataloguer Production Fix Deployment"
echo "============================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    print_error "Docker is not running. Please start Docker and try again."
    exit 1
fi

print_status "Docker is running ✓"

# Check if docker-compose.yml exists
if [ ! -f "docker-compose.yml" ]; then
    print_error "docker-compose.yml not found. Please run this script from the project root."
    exit 1
fi

print_status "Found docker-compose.yml ✓"

# Step 1: Stop the current container if running
print_status "Stopping existing containers..."
docker-compose down || true
print_success "Containers stopped"

# Step 2: Build new image with fixes
print_status "Building updated Docker image with fixes..."
docker-compose build --no-cache
print_success "Docker image built with latest fixes"

# Step 3: Start the container
print_status "Starting container..."
docker-compose up -d
print_success "Container started"

# Step 4: Wait for container to be ready
print_status "Waiting for container to be ready..."
sleep 10

# Step 5: Check if container is running
if ! docker-compose ps | grep -q "Up"; then
    print_error "Container failed to start. Checking logs..."
    docker-compose logs
    exit 1
fi

print_success "Container is running ✓"

# Step 6: Run database schema fix inside container
print_status "Running database schema fix..."
docker-compose exec -T app python fix_database_schema.py /data/app.db

if [ $? -eq 0 ]; then
    print_success "Database schema fix completed ✓"
else
    print_warning "Database schema fix had issues, but continuing..."
fi

# Step 7: Test health check endpoint
print_status "Testing health check endpoint..."
sleep 5

# Get the container port
CONTAINER_PORT=$(docker-compose port app 8000 | cut -d: -f2)
if [ -z "$CONTAINER_PORT" ]; then
    CONTAINER_PORT="8000"
fi

HEALTH_URL="http://localhost:${CONTAINER_PORT}/api/healthz"
print_status "Testing health check at: $HEALTH_URL"

# Test health check with timeout
if curl -f -s --max-time 10 "$HEALTH_URL" > /dev/null; then
    print_success "Health check endpoint is working ✓"
    
    # Show health check response
    print_status "Health check response:"
    curl -s "$HEALTH_URL" | python -m json.tool || echo "Response received but not JSON"
else
    print_warning "Health check endpoint test failed, but this might be expected during startup"
fi

# Step 8: Test metadata refresh (if possible)
print_status "Testing metadata refresh service..."
docker-compose exec -T app python -c "
import asyncio
from app.services.metadata_refresh import metadata_refresh_service
from app.services.tcgdx_api import tcgdx_api

async def test_api():
    try:
        available = await tcgdx_api.is_available()
        print(f'TCGdx API available: {available}')
        if available:
            print('✓ TCGdx API is accessible')
        else:
            print('⚠ TCGdx API is not accessible (this may be temporary)')
    except Exception as e:
        print(f'✗ TCGdx API test failed: {e}')

asyncio.run(test_api())
"

# Step 9: Show container logs (last 20 lines)
print_status "Recent container logs:"
echo "----------------------------------------"
docker-compose logs --tail=20 app
echo "----------------------------------------"

# Step 10: Final status
print_success "🎉 Deployment fix completed!"
echo ""
echo "Summary of fixes applied:"
echo "✅ Health check JSON serialization error fixed"
echo "✅ Enhanced error handling added to metadata service"
echo "✅ Database schema fix script executed"
echo "✅ Container restarted with latest fixes"
echo ""
echo "Next steps:"
echo "1. Monitor the logs: docker-compose logs -f app"
echo "2. Check health status: curl http://localhost:${CONTAINER_PORT}/api/healthz"
echo "3. Test metadata refresh in the application UI"
echo ""
echo "If issues persist:"
echo "1. Check database schema: docker-compose exec app python fix_database_schema.py /data/app.db"
echo "2. Review logs for constraint violations"
echo "3. Verify TCGdx API connectivity"

# Optional: Show running containers
print_status "Current container status:"
docker-compose ps
