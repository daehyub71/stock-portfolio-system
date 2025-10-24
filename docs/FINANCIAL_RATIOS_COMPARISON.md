# 재무비율 계산 가능성 비교 분석

`batch_collect_ratios.py`로 수집하는 재무비율과 재무제표 데이터로 추가 계산 가능한 재무비율을 구분합니다.

---

## 📊 전체 현황 요약

| 구분 | 개수 | 상태 |
|-----|------|------|
| **pykrx 직접 수집** | 6개 | ✅ 완료 (batch_collect_ratios.py) |
| **pykrx 데이터로 계산** | 2개 | ✅ 완료 (batch_collect_ratios.py) |
| **재무제표 기반 계산 가능** | 10개 | 🟢 구현 가능 (Day 14-15) |
| **재무제표 기반 (데이터 부족)** | 10개 | 🔴 불가능 (상세 계정과목 필요) |
| **시장 데이터 추가 필요** | 5개 | 🟡 보류 (주가, 시가총액 필요) |
| **총합** | 33개 | - |

---

## 1️⃣ pykrx로 수집 중인 재무비율 (8개)

### ✅ pykrx API에서 직접 수집 (6개)

**스크립트**: [`batch_collect_ratios.py`](../scripts/batch_collect_ratios.py) → [`collectors/pykrx_ratio_collector.py`](../collectors/pykrx_ratio_collector.py)

| # | 재무비율 | 영문명 | 필드명 | 수집 방법 |
|---|---------|--------|--------|----------|
| 1 | 주가수익비율 | Price to Earnings Ratio | `per` | `stock.get_market_fundamental()` |
| 2 | 주가순자산비율 | Price to Book Ratio | `pbr` | `stock.get_market_fundamental()` |
| 3 | 주당순이익 | Earnings Per Share | `eps` | `stock.get_market_fundamental()` |
| 4 | 주당순자산 | Book value Per Share | `bps` | `stock.get_market_fundamental()` |
| 5 | 배당수익률 | Dividend Yield | `div` | `stock.get_market_fundamental()` |
| 6 | 주당배당금 | Dividend Per Share | `dps` | `stock.get_market_fundamental()` |

**코드 예시**:
```python
# collectors/pykrx_ratio_collector.py:94
df = stock.get_market_fundamental(start_date, end_date, ticker)
# 반환: BPS, PER, PBR, EPS, DIV, DPS
```

### ✅ pykrx 데이터로 자동 계산 (2개)

**스크립트**: [`collectors/pykrx_ratio_collector.py`](../collectors/pykrx_ratio_collector.py) → `_calculate_additional_ratios()`

| # | 재무비율 | 영문명 | 필드명 | 계산 공식 |
|---|---------|--------|--------|----------|
| 7 | 자기자본이익률 | Return on Equity | `roe` | `EPS / BPS × 100` |
| 8 | 배당성향 | Dividend Payout Ratio | `payout_ratio` | `DPS / EPS × 100` |

**코드 예시**:
```python
# collectors/pykrx_ratio_collector.py:164-168
df['ROE'] = (df['EPS'] / df['BPS'] * 100).round(2)
df['payout_ratio'] = (df['DPS'] / df['EPS'] * 100).round(2)
```

**수집 현황** (2025-01-20 기준):
- ✅ 수집 완료: 1,299개 종목 (47%)
- 🚧 수집 중: 1,462개 종목 남음 (53%)

---

## 2️⃣ 재무제표 데이터로 추가 계산 가능 (10개)

### 🟢 구현 가능 - Day 14-15 작업 대상

**데이터 소스**: `financial_statements` 테이블 (DART API 수집)

현재 재무제표 데이터 구조 (JSONB):
```json
{
  "assets": {
    "current": {"유동자산": 227062266000000.0},
    "non_current": {"비유동자산": 287469682000000.0}
  },
  "equity": {"자본총계": 402192070000000.0},
  "liabilities": {
    "current": {"유동부채": 93326299000000.0},
    "non_current": {"비유동부채": 19013579000000.0}
  },
  "income_statement": {
    "revenue": {"매출액": 258937605000000.0},
    "operating_income": {"영업이익": 54336341000000.0},
    "net_income": {"당기순이익": 23678361000000.0}
  }
}
```

### A. 수익성 지표 (3개)

| # | 재무비율 | 필드명 | 계산 공식 | 필요 데이터 |
|---|---------|--------|----------|------------|
| 1 | 총자산이익률 | `roa` | `당기순이익 / 자산총계 × 100` | ✅ 보유 |
| 2 | 매출총이익률 | `gross_profit_margin` | `(매출액 - 매출원가) / 매출액 × 100` | ✅ 보유 |
| 3 | 영업이익률 | `operating_profit_margin` | `영업이익 / 매출액 × 100` | ✅ 보유 |
| 4 | 순이익률 | `net_profit_margin` | `당기순이익 / 매출액 × 100` | ✅ 보유 |

**참고**: ROE는 이미 pykrx에서 계산 중이므로 제외

### B. 안정성 지표 (4개)

| # | 재무비율 | 필드명 | 계산 공식 | 필요 데이터 |
|---|---------|--------|----------|------------|
| 5 | 부채비율 | `debt_ratio` | `부채총계 / 자기자본 × 100` | ✅ 보유 |
| 6 | 부채자본비율 | `debt_to_equity` | `부채총계 / 자기자본 × 100` | ✅ 보유 (debt_ratio와 동일) |
| 7 | 유동비율 | `current_ratio` | `유동자산 / 유동부채 × 100` | ✅ 보유 |
| 8 | 자기자본비율 | `equity_ratio` | `자기자본 / 자산총계 × 100` | ✅ 보유 |

### C. 활동성 지표 (1개)

| # | 재무비율 | 필드명 | 계산 공식 | 필요 데이터 |
|---|---------|--------|----------|------------|
| 9 | 총자산회전율 | `asset_turnover` | `매출액 / 평균자산` | ✅ 보유 (다년도 데이터 필요) |

### D. 성장성 지표 (2개)

**주의**: 성장률은 전년 동기 대비 데이터가 필요합니다.

| # | 재무비율 | 필드명 | 계산 공식 | 필요 데이터 |
|---|---------|--------|----------|------------|
| 10 | 매출액 증가율 | `revenue_growth` | `(당기매출액 - 전기매출액) / 전기매출액 × 100` | 🟡 다년도 필요 |

**현재 상태**: 재무제표 데이터가 평균 2-3건만 수집됨 (목표: 20건 = 5년 × 4분기)
→ 데이터 품질 개선 후 계산 가능

---

## 3️⃣ 재무제표 데이터 부족으로 계산 불가 (10개)

### 🔴 상세 계정과목 필요 (DART API 파싱 개선 필요)

현재 DART 수집기는 고수준 집계 항목만 수집:
- ✅ 현재: "유동자산", "비유동자산", "자본총계" 등 (3개 수준)
- ❌ 필요: "재고자산", "매출채권", "매입채무", "이자비용" 등 (20+ 세부 항목)

### A. 수익성 지표

| # | 재무비율 | 필드명 | 누락 데이터 | 개선 방법 |
|---|---------|--------|------------|----------|
| 1 | 투하자본이익률 | `roic` | 투하자본 = 자기자본 + 장기차입금 | DART 파싱 개선 |
| 2 | EBITDA 마진 | `ebitda_margin` | EBITDA = 영업이익 + 감가상각비 | DART 파싱 개선 |

### B. 안정성 지표

| # | 재무비율 | 필드명 | 누락 데이터 | 개선 방법 |
|---|---------|--------|------------|----------|
| 3 | 당좌비율 | `quick_ratio` | 당좌자산 = 유동자산 - 재고자산 | DART 파싱 개선 |
| 4 | 이자보상배율 | `interest_coverage` | 이자비용 | DART 파싱 개선 |

### C. 활동성 지표

| # | 재무비율 | 필드명 | 누락 데이터 | 개선 방법 |
|---|---------|--------|------------|----------|
| 5 | 재고자산회전율 | `inventory_turnover` | 재고자산 | DART 파싱 개선 |
| 6 | 매출채권회전율 | `receivables_turnover` | 매출채권 | DART 파싱 개선 |
| 7 | 매입채무회전율 | `payables_turnover` | 매입채무 | DART 파싱 개선 |

### D. 성장성 지표 (다년도 데이터 부족)

| # | 재무비율 | 필드명 | 누락 데이터 | 개선 방법 |
|---|---------|--------|------------|----------|
| 8 | 영업이익 증가율 | `operating_income_growth` | 전년도 영업이익 | 5년치 수집 |
| 9 | 순이익 증가율 | `net_income_growth` | 전년도 순이익 | 5년치 수집 |
| 10 | EPS 증가율 | `eps_growth` | 전년도 EPS | 5년치 수집 (또는 pykrx 활용) |

---

## 4️⃣ 시장 데이터 추가 필요 (5개)

### 🟡 주가 및 시가총액 데이터 필요

이 지표들은 재무제표만으로는 계산 불가능하며, **시장 데이터(주가, 거래량, 시가총액)**가 필요합니다.

| # | 재무비율 | 필드명 | 필요 데이터 | 데이터 소스 |
|---|---------|--------|------------|------------|
| 1 | 주가현금흐름비율 | `pcr` | 주가, 주당현금흐름(CFO/발행주식수) | pykrx + DART |
| 2 | 주가매출액비율 | `psr` | 주가, 주당매출액(매출액/발행주식수) | pykrx + DART |
| 3 | EV/EBITDA | `ev_to_ebitda` | 시가총액, 순차입금, EBITDA | pykrx + DART |
| 4 | EBITDA | `ebitda` | 영업이익, 감가상각비 | DART (파싱 개선 필요) |
| 5 | 총자산 증가율 | `total_asset_growth` | 전년도 총자산 | DART (다년도 수집) |

**참고**:
- `per`, `pbr`, `div`는 이미 pykrx에서 수집 중
- `dividend_yield`, `dividend_payout_ratio`도 pykrx 데이터로 계산 중

---

## 📋 Day 14-15 구현 우선순위

### ✅ Phase 1: 즉시 구현 가능 (10개)

재무제표 데이터만으로 계산 가능한 지표:

**수익성 (4개)**:
1. ROA (총자산이익률)
2. Gross Profit Margin (매출총이익률)
3. Operating Profit Margin (영업이익률)
4. Net Profit Margin (순이익률)

**안정성 (4개)**:
5. Debt Ratio (부채비율)
6. Debt to Equity (부채자본비율)
7. Current Ratio (유동비율)
8. Equity Ratio (자기자본비율)

**활동성 (1개)**:
9. Asset Turnover (총자산회전율)

**성장성 (1개)**:
10. Revenue Growth (매출액 증가율) - 다년도 데이터 있을 경우

### 🔴 Phase 2: 데이터 개선 후 구현 (10개)

DART API 파싱 개선 필요:
- ROIC, EBITDA Margin
- Quick Ratio, Interest Coverage
- Inventory/Receivables/Payables Turnover
- Operating/Net Income/EPS Growth (다년도 수집)

### 🟡 Phase 3: 시장 데이터 통합 후 구현 (5개)

주가 데이터 통합 필요:
- PCR, PSR, EV/EBITDA
- EBITDA (절댓값)
- Total Asset Growth

---

## 💡 권장 작업 순서

### Step 1: Phase 1 구현 (Day 14-15)

```bash
# 1. 재무비율 계산 모듈 생성
# calculators/financial_ratio_calculator.py

# 2. 10개 지표 계산 로직 구현
#    - ROA, 매출총이익률, 영업이익률, 순이익률
#    - 부채비율, 부채자본비율, 유동비율, 자기자본비율
#    - 총자산회전율
#    - 매출액 증가율 (가능한 경우)

# 3. 배치 계산 스크립트 작성
# scripts/calculate_financial_ratios.py

# 4. 테스트 (10개 샘플 종목)
pytest tests/test_ratio_calculator.py
```

### Step 2: 데이터 품질 개선 (Week 4)

```bash
# 1. DART 수집기 개선
#    - 상세 계정과목 파싱 추가
#    - 5년 × 4분기 = 20건 완전 수집

# 2. 재무제표 재수집
python scripts/batch_collect_financials.py --all --years 5

# 3. Phase 2 지표 계산
```

### Step 3: 시장 데이터 통합 (Week 5)

```bash
# 1. 주가 데이터와 재무제표 조인
# 2. Phase 3 지표 계산
```

---

## 🔍 데이터 현황 점검

### 재무제표 수집 현황

**쿼리**:
```python
from db.connection import SessionLocal
from models import Stock, FinancialStatement
from sqlalchemy import func

db = SessionLocal()

# 종목별 재무제표 데이터 수
result = db.query(
    Stock.ticker,
    Stock.name,
    func.count(FinancialStatement.id).label('stmt_count')
).join(FinancialStatement, Stock.id == FinancialStatement.stock_id
).group_by(Stock.id, Stock.ticker, Stock.name
).order_by(func.count(FinancialStatement.id).desc()
).limit(10).all()

for ticker, name, count in result:
    print(f"{ticker} {name}: {count}건")

db.close()
```

**예상 결과**:
- ✅ 우수: 20건 이상 (5년 × 4분기 완전 수집)
- 🟡 보통: 8-20건 (2-5년 부분 수집)
- 🔴 미흡: 8건 미만 (현재 평균 2-3건)

### 재무비율 수집 현황

**쿼리**:
```python
from db.connection import SessionLocal
from models import Stock, FinancialRatio
from sqlalchemy import func

db = SessionLocal()

# 종목별 재무비율 데이터 수
result = db.query(
    Stock.ticker,
    Stock.name,
    func.count(FinancialRatio.id).label('ratio_count')
).join(FinancialRatio, Stock.id == FinancialRatio.stock_id
).group_by(Stock.id, Stock.ticker, Stock.name
).order_by(func.count(FinancialRatio.id).desc()
).limit(10).all()

for ticker, name, count in result:
    print(f"{ticker} {name}: {count:,}건")

db.close()
```

**예상 결과**:
- ✅ 우수: 730건 이상 (3년 × 약 245 거래일)
- 🟡 보통: 365-730건 (1.5-3년)
- 🔴 미흡: 365건 미만 (1년 미만)

---

## 📚 참고 문서

- [FINANCIAL_RATIO_CALCULATION_FEASIBILITY.md](./FINANCIAL_RATIO_CALCULATION_FEASIBILITY.md) - 계산 가능성 상세 분석
- [BATCH_RATIO_COLLECTION.md](./BATCH_RATIO_COLLECTION.md) - pykrx 배치 수집 가이드
- [Task_분할서_Phase1_Phase2.md](../Task_분할서_Phase1_Phase2.md) - Day 14-15 작업 계획
- [PROJECT_CHECKLIST.md](../PROJECT_CHECKLIST.md) - 전체 진행 상황 체크리스트

---

## ✅ 결론

### 현재 보유 데이터로 구현 가능 (18개)
- pykrx 수집 완료: 8개 ✅
- 재무제표 기반 계산 가능: 10개 🟢

### 데이터 개선 필요 (15개)
- DART 파싱 개선 후: 10개 🔴
- 시장 데이터 통합 후: 5개 🟡

**총 33개 재무비율 중 55%를 현재 구현 가능**하며, 나머지 45%는 데이터 수집 개선이 필요합니다.

Day 14-15 작업으로 **10개의 추가 재무비율**을 즉시 구현할 수 있습니다.
