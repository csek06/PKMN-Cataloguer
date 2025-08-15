# CRITICAL PRODUCTION FIXES - DEPLOYMENT INSTRUCTIONS

## 🚨 Critical Issues Identified

Based on the Docker logs provided, there are two critical production issues that need immediate attention:

### 1. Metadata Refresh Service Failure
- **Error**: `NOT NULL constraint failed: card.set_id`
- **Impact**: 25+ cards failing to update metadata (Charizard EX, Hydreigon EX, etc.)
- **Root Cause**: Database schema has NOT NULL constraints on set_id/set_name but application expects nullable fields

### 2. Health Check JSON Serialization Error
- **Error**: `Object of type datetime is not JSON serializable`
- **Impact**: Health check endpoint failing, system monitoring broken
- **Root Cause**: FastAPI JSONResponse cannot serialize datetime objects

## 🛠️ Files Modified (Ready for Deployment)

### Fixed Files:
1. **`app/api/routes_admin.py`** - Health check JSON serialization fix
2. **`app/services/metadata_refresh.py`** - Enhanced error handling and validation
3. **`fix_database_schema.py`** - Database schema fix script (NEW FILE)
4. **`docker-fix-deployment.sh`** - Automated deployment script (NEW FILE)

## 🚀 Deployment Steps for Docker Admin

### Option 1: Automated Deployment (Recommended)
```bash
# Run the automated deployment script
./docker-fix-deployment.sh
```

### Option 2: Manual Deployment Steps

#### Step 1: Stop and Rebuild Container
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

#### Step 2: Fix Database Schema (CRITICAL)
```bash
# Run the database fix inside the container
docker-compose exec app python fix_database_schema.py /data/app.db
```

#### Step 3: Verify Health Check
```bash
# Test the health check endpoint
curl http://localhost:8000/api/healthz
```

#### Step 4: Monitor Logs
```bash
# Watch for successful metadata updates
docker-compose logs -f app | grep metadata
```

## 🔍 Expected Results After Deployment

### Health Check Fix:
- ✅ `/api/healthz` endpoint returns proper JSON response
- ✅ No more "Object of type datetime is not JSON serializable" errors

### Database Schema Fix:
- ✅ `set_id` and `set_name` columns allow NULL values
- ✅ All existing data preserved during schema update
- ✅ Metadata refresh service can handle cards without set information

### Metadata Service Fix:
- ✅ Cards like "Charizard EX" (ID 32), "Hydreigon EX" (ID 33) will update successfully
- ✅ Enhanced error handling provides better diagnostics
- ✅ Constraint violations detected and logged properly

## 🧪 Verification Commands

### Test Health Check:
```bash
curl -s http://localhost:8000/api/healthz | python -m json.tool
```
**Expected**: Valid JSON response with status, database, and timestamp fields

### Test Database Schema:
```bash
docker-compose exec app python -c "
import sqlite3
conn = sqlite3.connect('/data/app.db')
cursor = conn.cursor()
cursor.execute('PRAGMA table_info(card)')
for col in cursor.fetchall():
    if col[1] in ['set_id', 'set_name']:
        print(f'{col[1]}: NOT NULL = {bool(col[3])}')
conn.close()
"
```
**Expected**: `set_id: NOT NULL = False` and `set_name: NOT NULL = False`

### Test Metadata Update:
```bash
# Check recent logs for successful metadata updates
docker-compose logs --tail=50 app | grep "metadata_card_updated"
```
**Expected**: Cards updating successfully without constraint errors

## 📋 Rollback Plan (If Needed)

If issues occur after deployment:

1. **Rollback Container**:
   ```bash
   docker-compose down
   # Deploy previous working image
   docker-compose up -d
   ```

2. **Database Backup**: The schema fix preserves all data, but if needed:
   ```bash
   # The fix creates a backup during the process
   # Check container logs for backup location
   docker-compose logs app | grep "backup"
   ```

## 🔧 Technical Details

### Database Schema Fix Details:
- **Safe Operation**: Creates new table, copies data, replaces old table
- **Transaction Protected**: Uses SQLite transactions for safety
- **Index Preservation**: Recreates all indexes after schema fix
- **Data Integrity**: Verifies fix with test insertion

### Health Check Fix Details:
- **Before**: `return JSONResponse(content=response.dict(), status_code=status_code)`
- **After**: Manual datetime serialization to ISO string format
- **Impact**: Fixes JSON serialization without changing response structure

### Enhanced Error Handling:
- **Constraint Detection**: Identifies NOT NULL constraint violations
- **Better Logging**: More detailed error messages for diagnostics
- **Validation**: Pre-database validation prevents constraint errors

## 📞 Support Information

If deployment issues occur:
1. **Check Logs**: `docker-compose logs app`
2. **Health Check**: `curl http://localhost:8000/api/healthz`
3. **Database Status**: Run verification commands above
4. **Rollback**: Use rollback plan if needed

All fixes are production-ready and have been tested for safety and data preservation.
