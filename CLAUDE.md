# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Stock Portfolio System for Korean stock markets (KOSPI/KOSDAQ). Collects price data, financial statements from DART API, and stores in PostgreSQL with 33+ financial ratios for analysis and backtesting.

**Tech Stack**: Python 3.13 + SQLAlchemy 2.0 + PostgreSQL 15 + pykrx + httpx

## Quick Start

```bash
# Always activate venv first
source venv/bin/activate

# Test database connection
python -c "from db.connection import test_connection; test_connection()"

# Initialize database (first time only)
python scripts/init_db.py

# Test API connections
python scripts/test_kis_api.py    # KIS API (requires credentials)
python scripts/test_krx_api.py    # KRX API (public, no auth)
python scripts/test_dart_api.py   # DART API (requires key)

# Collect data
python scripts/collect_stocks.py                    # Collect stock list from KRX
python scripts/batch_collect_prices.py              # Collect 10-year price data (pykrx)
python scripts/batch_collect_financials.py          # Collect financial statements (DART)
```

## Environment Variables

Required `.env` file (see `.env.example`):

```bash
# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stock_portfolio
DB_USER=your_username
DB_PASSWORD=                    # Empty for peer authentication on macOS

# KIS API (한국투자증권) - https://apiportal.koreainvestment.com/
KIS_APP_KEY=your_key
KIS_APP_SECRET=your_secret
KIS_ACCOUNT_TYPE=VIRTUAL        # VIRTUAL or REAL

# DART API (전자공시) - https://opendart.fss.or.kr/
DART_API_KEY=your_key

# Logging
LOG_LEVEL=INFO
LOG_FILE_PATH=./logs/
ENVIRONMENT=development
```

## Database Architecture

### Schema Design

The database uses SQLAlchemy ORM with a hierarchical structure:

```
sectors (업종 분류)
  ↓ (one-to-many)
stocks (종목 정보)
  ↓ (one-to-many)
  ├── daily_prices (OHLCV 시세 데이터)
  ├── financial_statements (재무제표 - JSONB)
  ├── financial_ratios (33개 재무비율)
  └── corp_code_map (ticker ↔ DART corp_code 매핑)
```

### Key Models

All models inherit from `Base` (SQLAlchemy declarative base) and `TimestampMixin` (created_at, updated_at).

**Location**: `models/`

- **Stock** (`models/stock.py`): Core stock entity with ticker, name, market (KOSPI/KOSDAQ/KONEX), sector_id, listing/delisting dates
- **DailyPrice** (`models/daily_price.py`): OHLCV data with composite unique index on (stock_id, date)
- **FinancialStatement** (`models/financial_statement.py`): Uses PostgreSQL JSONB for flexible financial data storage (balance_sheet, income_statement, cash_flow, equity_changes)
- **FinancialRatio** (`models/financial_ratio.py`): 33 calculated ratios (ROE, ROA, PER, PBR, debt ratio, etc.)
- **Sector** (`models/sector.py`): Hierarchical sector classification with parent_id self-reference
- **CorpCodeMap** (`models/corp_code_map.py`): Maps ticker symbols to DART corp_code for API queries

### Database Connection

**Module**: `db/connection.py`

- Creates SQLAlchemy engine with connection pooling (QueuePool: pool_size=10, max_overflow=20)
- Provides `SessionLocal` factory for database sessions
- Use `get_db()` generator for dependency injection patterns
- `test_connection()` verifies PostgreSQL connectivity and prints version

## Data Collection System

### Three Data Collectors

**Location**: `collectors/`

1. **KRXCollector** (`collectors/krx_collector.py`)
   - Uses `pykrx` library for public KRX data
   - Collects stock lists (KOSPI, KOSDAQ, KONEX)
   - No authentication required
   - No rate limits

2. **PyKRXPriceCollector** (`collectors/pykrx_price_collector.py`)
   - Uses `pykrx` for historical price data (OHLCV)
   - Can collect 10+ years of data efficiently
   - No authentication required
   - No rate limits
   - **Preferred for bulk price collection** over KIS API

3. **KISPriceCollector** (`collectors/kis_collector.py`)
   - Uses Korea Investment Securities (KIS) API
   - OAuth 2.0 authentication with token refresh
   - Rate limit: 20 requests/second (enforced with 0.05s interval)
   - Requires KIS_APP_KEY, KIS_APP_SECRET
   - Use for real-time data; prefer pykrx for historical bulk collection

4. **DARTCollector** (`collectors/dart_collector.py`)
   - Uses DART (전자공시) OpenAPI
   - Collects financial statements (annual/quarterly)
   - Rate limit: ~5 requests/second recommended
   - Requires DART_API_KEY
   - Stores data in JSONB format for flexibility

### Batch Collection Scripts

**Location**: `scripts/`

- **`batch_collect_prices.py`**: Collects 10-year price data using pykrx with checkpoint/resume support
- **`batch_collect_financials.py`**: Collects financial statements from DART with batching and retry logic
- **`create_batch_groups.py`**: Creates stock groups for parallel batch processing
- **`retry_failed_financials.py`**: Retries failed financial data collections

**Batch Architecture**:
- Groups stocks into batches (stored in `data/batch_groups/` or `data/price_groups/`)
- Checkpoint system saves progress to `data/checkpoints/` as JSON
- Can resume interrupted collections from last checkpoint
- Tracks statistics: total_stocks, successful_stocks, failed_stocks, errors

### Monitoring & Quality

- **`monitor_collection.py`**: Real-time monitoring dashboard for batch collection progress
- **`monitor_prices.py`**: Price data collection monitoring
- **`data_quality_check.py`**: Validates collected data integrity
- Quality reports saved to `data/quality_reports/`

## Common Development Tasks

### Database Operations

```bash
# Recreate all tables (WARNING: drops existing data)
python scripts/init_db.py

# Check what tables exist
python -c "
from db.connection import engine
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text('SELECT tablename FROM pg_tables WHERE schemaname = \\'public\\' ORDER BY tablename'))
    for row in result:
        print(f'  ✓ {row[0]}')
"

# Query stock count by market
python -c "
from db.connection import SessionLocal
from models import Stock
from sqlalchemy import func
db = SessionLocal()
result = db.query(Stock.market, func.count(Stock.id)).group_by(Stock.market).all()
for market, count in result:
    print(f'{market.value}: {count} stocks')
db.close()
"
```

### Running Collectors

```bash
# Collect all stock lists (KOSPI + KOSDAQ)
python scripts/collect_stocks.py

# Collect for specific market
python scripts/collect_stocks.py --market KOSPI
python scripts/collect_stocks.py --market KOSDAQ

# Collect 10-year price data (uses pykrx - recommended)
python scripts/batch_collect_prices.py --group-id 1 --start-date 20150101 --end-date 20250101

# Collect financial statements from DART
python scripts/batch_collect_financials.py --group-id 1

# Monitor collection progress
python scripts/monitor_collection.py --group-id 1
```

### Testing API Connections

Before running collectors, test API connectivity:

```bash
# Test KRX (public API - no auth needed)
python scripts/test_krx_api.py

# Test KIS API (requires credentials in .env)
python scripts/test_kis_api.py

# Test DART API (requires DART_API_KEY in .env)
python scripts/test_dart_api.py
```

## Architecture Patterns

### Session Management

Collectors use context managers for automatic session cleanup:

```python
from collectors import PyKRXPriceCollector

# Recommended pattern - auto-closes session
with PyKRXPriceCollector() as collector:
    collector.collect_price_data(ticker="005930", start_date="20240101", end_date="20241231")

# Manual session management (not recommended)
collector = PyKRXPriceCollector()
try:
    # ... use collector
finally:
    collector.close()
```

### Error Handling & Retry Logic

All collectors implement:
- Automatic retry on transient failures (network errors, rate limits)
- Checkpoint system to resume interrupted batch operations
- Comprehensive logging to `logs/` directory with daily rotation

### Logging

Uses `loguru` for structured logging:
- Individual log files per collector in `logs/`
- Daily rotation with 30-day retention
- Format: `[timestamp] | [level] | [message]`

## Data Directory Structure

```
data/
├── batch_groups/          # Stock groups for financial data collection
├── price_groups/          # Stock groups for price data collection
├── checkpoints/           # Checkpoint files for resumable collections
├── dart/                  # DART API responses and metadata
├── quality_reports/       # Data quality validation reports
└── retry/                 # Failed collection retry tracking
```

## Rate Limiting & API Quotas

**KIS API**:
- Limit: 20 requests/second (enforced in `KISPriceCollector.REQUEST_INTERVAL = 0.05s`)
- Token expires after ~24 hours (auto-refresh implemented)

**DART API**:
- No official limit, but ~5 requests/second recommended to avoid throttling
- Implemented in `DARTCollector` with configurable delay

**pykrx** (KRX public data):
- No authentication required
- No rate limits
- **Preferred for historical data collection**

## Testing

```bash
# Run all tests (when implemented)
pytest

# Run specific test module
pytest tests/test_collectors.py -v

# Run with coverage
pytest --cov=. --cov-report=html
```

## Database GUI Tools

Recommended: **TablePlus** (https://tableplus.com/)

Connection settings:
- Host: `localhost`
- Port: `5432`
- Database: `stock_portfolio`
- User: `<your_macOS_username>`
- Password: (leave empty for peer authentication)

See [docs/TABLEPLUS_CONNECTION.md](docs/TABLEPLUS_CONNECTION.md) for detailed setup.

## Important Notes

### PostgreSQL Setup (macOS)

```bash
# Install PostgreSQL 15
brew install postgresql@15
brew services start postgresql@15

# Create database
createdb stock_portfolio

# Check if running
brew services list | grep postgresql
```

### Python Version

**Requires Python 3.13**. Dependencies are tested with Python 3.13 (see `requirements.txt`).

```bash
python --version  # Should be 3.13.x
```

### Financial Ratios (33 total)

**Calculated in**: `calculators/` (to be implemented)

- **Profitability**: ROE, ROA, ROIC, gross profit margin, operating margin, net margin, EBITDA margin
- **Growth**: Revenue growth, operating income growth, net income growth, EPS growth, asset growth
- **Stability**: Debt ratio, debt-to-equity, current ratio, quick ratio, interest coverage, equity ratio
- **Activity**: Asset turnover, inventory turnover, receivables turnover, payables turnover
- **Market Value**: PER, PBR, PCR, PSR, EV/EBITDA, dividend yield, payout ratio

### JSONB Usage in Financial Statements

Financial data is stored in PostgreSQL JSONB columns for flexibility:

```python
# Example structure
balance_sheet = {
    "assets": {
        "current": {"cash": 1000000, "inventory": 500000},
        "non_current": {"ppe": 2000000}
    },
    "liabilities": {...},
    "equity": {...}
}

# Query with JSONB operators
from sqlalchemy import text
result = db.execute(
    text("SELECT balance_sheet->>'assets' FROM financial_statements WHERE stock_id = :id"),
    {"id": stock_id}
)
```

## Development Workflow

1. **Always activate venv**: `source venv/bin/activate`
2. **Test DB connection**: `python -c "from db.connection import test_connection; test_connection()"`
3. **Initialize DB** (first time): `python scripts/init_db.py`
4. **Collect stock list**: `python scripts/collect_stocks.py`
5. **Collect price data**: `python scripts/batch_collect_prices.py`
6. **Collect financials**: `python scripts/batch_collect_financials.py`
7. **Monitor progress**: `python scripts/monitor_collection.py` or check `logs/`

## Project Status

**Current Phase**: Phase 1 - Data Collection (Week 1-3)
- ✅ Day 1-2: Database design and models
- ✅ Day 3-7: Price data collection (KIS + pykrx)
- 🚧 Financial data collection from DART in progress

See [README.md](README.md) for full roadmap and [docs/](docs/) for detailed documentation.
