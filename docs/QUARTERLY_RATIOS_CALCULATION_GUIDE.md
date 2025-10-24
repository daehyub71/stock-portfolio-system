# 재무제표 기반 분기별 재무비율 계산 가이드

Day 14-15 작업: 재무제표 JSONB 데이터로부터 10개의 추가 재무비율을 계산하고 하이브리드 전략으로 저장합니다.

---

## 📋 목차

1. [개요](#개요)
2. [시스템 아키텍처](#시스템-아키텍처)
3. [설치 및 설정](#설치-및-설정)
4. [사용 방법](#사용-방법)
5. [데이터 구조](#데이터-구조)
6. [조회 및 분석](#조회-및-분석)
7. [트러블슈팅](#트러블슈팅)

---

## 개요

### 계산 가능한 재무비율 (10개)

| 카테고리 | 지표 | 필드명 | 계산 공식 |
|---------|-----|--------|----------|
| **수익성 (4개)** | | | |
| | ROA (총자산이익률) | `roa` | (당기순이익 / 자산총계) × 100 |
| | 매출총이익률 | `gross_profit_margin` | ((매출액 - 매출원가) / 매출액) × 100 |
| | 영업이익률 | `operating_profit_margin` | (영업이익 / 매출액) × 100 |
| | 순이익률 | `net_profit_margin` | (당기순이익 / 매출액) × 100 |
| **안정성 (4개)** | | | |
| | 부채비율 | `debt_ratio` | (부채총계 / 자기자본) × 100 |
| | 부채자본비율 | `debt_to_equity` | (부채총계 / 자기자본) × 100 |
| | 유동비율 | `current_ratio` | (유동자산 / 유동부채) × 100 |
| | 자기자본비율 | `equity_ratio` | (자기자본 / 자산총계) × 100 |
| **활동성 (1개)** | | | |
| | 총자산회전율 | `asset_turnover` | 매출액 / 평균자산 |
| **성장성 (1개)** | | | |
| | 매출액 증가율 | `revenue_growth` | ((당기매출액 - 전기매출액) / 전기매출액) × 100 |

### 하이브리드 저장 전략

**일별 pykrx 데이터** (기존):
- PER, PBR, ROE 등 → 매일 변동
- `fiscal_year = NULL`로 구분

**분기별 재무제표 계산 데이터** (신규):
- ROA, 부채비율 등 → 분기당 1건
- `fiscal_year != NULL`로 구분

**통합 조회**:
- PostgreSQL 뷰 `vw_daily_combined_ratios` 사용
- 일별 데이터 + 해당 시점 최신 분기 데이터 자동 조인

---

## 시스템 아키텍처

### 데이터 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                     financial_ratios 테이블                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [pykrx 일별 데이터]                                          │
│  ├─ date: 2025-01-20                                        │
│  ├─ fiscal_year: NULL ← 일별 데이터 구분자                     │
│  ├─ per: 15.2                                               │
│  ├─ pbr: 1.8                                                │
│  ├─ roe: 12.5                                               │
│  ├─ roa: NULL (분기 지표)                                    │
│  └─ debt_ratio: NULL (분기 지표)                             │
│                                                             │
│  [재무제표 분기별 데이터]                                      │
│  ├─ date: 2024-12-31 (분기 마지막 날)                         │
│  ├─ fiscal_year: 2024 ← 분기 데이터 구분자                    │
│  ├─ fiscal_quarter: 4                                       │
│  ├─ report_date: 2025-02-14 (실제 발표일)                    │
│  ├─ per: NULL (일별 지표)                                    │
│  ├─ pbr: NULL (일별 지표)                                    │
│  ├─ roa: 8.5                                                │
│  └─ debt_ratio: 45.2                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                            ↓
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              vw_daily_combined_ratios 뷰                     │
│              (일별 + 분기 데이터 통합 조회)                     │
├─────────────────────────────────────────────────────────────┤
│  date: 2025-01-20                                           │
│  per: 15.2 (pykrx 일별)                                      │
│  pbr: 1.8 (pykrx 일별)                                       │
│  roe_pykrx: 12.5 (pykrx 일별)                                │
│  roa: 8.5 (2024Q4 분기 데이터)                                │
│  debt_ratio: 45.2 (2024Q4 분기 데이터)                        │
│  fiscal_year: 2024                                          │
│  fiscal_quarter: 4                                          │
└─────────────────────────────────────────────────────────────┘
```

### 핵심 컴포넌트

1. **`FinancialRatioCalculator`** ([calculators/financial_ratio_calculator.py](../calculators/financial_ratio_calculator.py))
   - 재무제표 JSONB에서 10개 재무비율 계산
   - 안전한 나눗셈 (0으로 나누기 방지)
   - 중첩된 JSONB 키 추출

2. **`calculate_quarterly_ratios.py`** ([scripts/calculate_quarterly_ratios.py](../scripts/calculate_quarterly_ratios.py))
   - 재무비율 계산 및 저장 스크립트
   - 단일/전체 종목, 단일/전체 분기 지원
   - 전기 데이터 자동 조회 (성장률 계산)

3. **`vw_daily_combined_ratios`** (PostgreSQL 뷰)
   - 일별 pykrx 데이터 + 최신 분기 재무제표 데이터 자동 조인
   - 백테스팅/분석용 통합 조회

---

## 설치 및 설정

### 1. 가상환경 활성화

```bash
source venv/bin/activate
```

### 2. 의존성 확인

필요한 패키지는 이미 설치되어 있습니다:
- `sqlalchemy`
- `psycopg2-binary`
- `loguru`

### 3. 데이터 확인

재무제표 데이터가 수집되어 있어야 합니다:

```bash
# 재무제표 수집 현황 확인
python -c "
from db.connection import SessionLocal
from models import Stock, FinancialStatement
from sqlalchemy import func

db = SessionLocal()

# 종목별 재무제표 수
stmt_count = db.query(func.count(func.distinct(FinancialStatement.stock_id))).scalar()
total_stmts = db.query(func.count(FinancialStatement.id)).scalar()

print(f'재무제표 보유 종목: {stmt_count}개')
print(f'총 재무제표 레코드: {total_stmts}건')

db.close()
"
```

---

## 사용 방법

### Step 1: 계산기 테스트

먼저 계산 모듈이 제대로 작동하는지 테스트:

```bash
# 계산기 단독 테스트
python calculators/financial_ratio_calculator.py
```

**예상 출력**:
```
==================================================
재무비율 계산 결과
==================================================

[수익성 지표]
  ROA:              4.6006%
  매출총이익률:      계산 불가 (매출원가 없음)
  영업이익률:        20.9883%
  순이익률:          9.1456%

[안정성 지표]
  부채비율:          27.9268%
  유동비율:          243.3166%
  자기자본비율:      78.1633%

[활동성 지표]
  총자산회전율:      0.5031회

[성장성 지표]
  매출액 증가율:     None (전기 데이터 없음)
```

### Step 2: 단일 종목, 단일 분기 계산

```bash
# 삼성전자 2024년 4분기 재무비율 계산
python scripts/calculate_quarterly_ratios.py \
    --ticker 005930 \
    --year 2024 \
    --quarter 4
```

**예상 출력**:
```
============================================================
005930 2024Q4 재무비율 계산 결과
============================================================

보고일: 2025-02-14
분기말: 2024-12-31

[수익성 지표]
  ROA:              4.60%
  매출총이익률:      N/A
  영업이익률:        20.99%
  순이익률:          9.15%

[안정성 지표]
  부채비율:          27.93%
  부채자본비율:      27.93%
  유동비율:          243.32%
  자기자본비율:      78.16%

[활동성 지표]
  총자산회전율:      0.5031회

[성장성 지표]
  매출액 증가율:     -5.23% (전기 대비)
============================================================
```

### Step 3: 단일 종목, 전체 분기 계산

```bash
# 삼성전자의 모든 분기 재무비율 계산
python scripts/calculate_quarterly_ratios.py \
    --ticker 005930 \
    --all-quarters
```

**예상 출력**:
```
============================================================
005930 삼성전자 - 전체 분기 계산 완료
============================================================
총 분기:     12
성공:       12
실패:       0
성공률:     100.0%
============================================================
```

### Step 4: 전체 종목 계산 (시간 소요)

```bash
# 전체 종목, 전체 분기 계산 (오래 걸림)
python scripts/calculate_quarterly_ratios.py --all-stocks

# 2024년만 계산
python scripts/calculate_quarterly_ratios.py --all-stocks --year 2024

# 테스트용 (상위 10개 종목만)
python scripts/calculate_quarterly_ratios.py --all-stocks --limit 10
```

**예상 출력**:
```
============================================================
전체 종목 재무비율 계산 완료
============================================================
처리 종목:   1,206개
총 분기:     14,472개
성공:       13,890개
실패:       582개
성공률:     95.9%
============================================================
```

### Step 5: PostgreSQL 뷰 생성

```bash
# 통합 조회용 뷰 생성
python scripts/create_combined_ratios_view.py
```

**예상 출력**:
```
============================================================
뷰 생성 완료 - 샘플 데이터 (5건)
============================================================

종목: 005930 삼성전자
날짜: 2024-12-31
  [pykrx 일별] PER=15.2, PBR=1.8, ROE=12.5%
  [분기 계산] ROA=4.6%, 부채비율=27.9% (2024Q4)

...
```

---

## 데이터 구조

### 재무제표 JSONB 구조

재무제표는 유연한 JSONB 형식으로 저장됩니다:

#### 재무상태표 (Balance Sheet)

```json
{
  "assets": {
    "current": {
      "유동자산": 227062266000000.0
    },
    "non_current": {
      "비유동자산": 287469682000000.0
    }
  },
  "liabilities": {
    "current": {
      "유동부채": 93326299000000.0
    },
    "non_current": {
      "비유동부채": 19013579000000.0
    }
  },
  "equity": {
    "자본총계": 402192070000000.0
  }
}
```

#### 손익계산서 (Income Statement)

```json
{
  "revenue": {
    "매출액": 258937605000000.0
  },
  "operating_income": {
    "영업이익": 54336341000000.0
  },
  "net_income": {
    "당기순이익": 23678361000000.0
  }
}
```

### 계산 결과 저장 구조

**분기별 레코드** (financial_ratios 테이블):

| 필드 | 값 | 설명 |
|-----|-----|------|
| `stock_id` | 1 | 종목 ID |
| `date` | 2024-12-31 | 분기 마지막 날 |
| `report_date` | 2025-02-14 | 실제 보고서 발표일 |
| `fiscal_year` | 2024 | 회계연도 (분기 구분자) |
| `fiscal_quarter` | 4 | 분기 (1-4) |
| `roa` | 4.6006 | ROA (%) |
| `operating_profit_margin` | 20.9883 | 영업이익률 (%) |
| `debt_ratio` | 27.9268 | 부채비율 (%) |
| ... | ... | ... (10개 지표) |
| `per` | NULL | pykrx 일별 지표 (NULL) |
| `pbr` | NULL | pykrx 일별 지표 (NULL) |

---

## 조회 및 분석

### 기본 조회

#### 1. 특정 종목의 분기별 재무비율 조회

```python
from db.connection import SessionLocal
from models import Stock, FinancialRatio
from sqlalchemy import and_

db = SessionLocal()

# 삼성전자의 분기별 재무비율
ratios = db.query(FinancialRatio).join(Stock).filter(
    Stock.ticker == '005930',
    FinancialRatio.fiscal_year != None  # 분기 데이터만
).order_by(
    FinancialRatio.fiscal_year.desc(),
    FinancialRatio.fiscal_quarter.desc()
).all()

for ratio in ratios:
    print(f"{ratio.fiscal_year}Q{ratio.fiscal_quarter}: "
          f"ROA={ratio.roa}%, 부채비율={ratio.debt_ratio}%")

db.close()
```

#### 2. 뷰를 사용한 통합 조회

```python
from db.connection import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# 특정 날짜의 모든 재무비율 조회
result = db.execute(text("""
    SELECT
        ticker,
        stock_name,
        date,
        per,                    -- pykrx 일별
        pbr,                    -- pykrx 일별
        roe_pykrx,              -- pykrx 일별
        roa,                    -- 분기 계산
        debt_ratio,             -- 분기 계산
        operating_profit_margin,-- 분기 계산
        fiscal_year,
        fiscal_quarter
    FROM vw_daily_combined_ratios
    WHERE ticker = '005930'
      AND date = '2024-12-31'
""")).fetchone()

print(f"날짜: {result.date}")
print(f"PER: {result.per} (일별)")
print(f"PBR: {result.pbr} (일별)")
print(f"ROE: {result.roe_pykrx}% (일별)")
print(f"ROA: {result.roa}% (분기: {result.fiscal_year}Q{result.fiscal_quarter})")
print(f"부채비율: {result.debt_ratio}% (분기)")

db.close()
```

### 백테스팅 예시

#### 저PBR + 고ROE + 낮은부채비율 전략

```python
from db.connection import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# 2024-12-31 기준 투자 대상 종목 선정
candidates = db.execute(text("""
    SELECT
        ticker,
        stock_name,
        pbr,
        roe_pykrx,
        debt_ratio,
        current_ratio,
        operating_profit_margin
    FROM vw_daily_combined_ratios
    WHERE date = '2024-12-31'
      AND pbr < 1.0              -- 저PBR (저평가)
      AND roe_pykrx > 10.0       -- 고ROE (수익성 우수)
      AND debt_ratio < 50.0      -- 낮은 부채비율 (안정성)
      AND current_ratio > 100.0  -- 유동비율 양호
    ORDER BY roe_pykrx DESC
    LIMIT 20
""")).fetchall()

print(f"선정 종목: {len(candidates)}개\n")

for i, stock in enumerate(candidates, 1):
    print(f"{i}. {stock.ticker} {stock.stock_name}")
    print(f"   PBR={stock.pbr}, ROE={stock.roe_pykrx}%, "
          f"부채비율={stock.debt_ratio}%, 영업이익률={stock.operating_profit_margin}%")

db.close()
```

### 시계열 분석

#### 분기별 재무비율 추이 분석

```python
from db.connection import SessionLocal
from sqlalchemy import text
import pandas as pd
import matplotlib.pyplot as plt

db = SessionLocal()

# 삼성전자 최근 2년 분기별 재무비율 추이
data = db.execute(text("""
    SELECT
        date,
        fiscal_year,
        fiscal_quarter,
        roa,
        operating_profit_margin,
        net_profit_margin,
        debt_ratio,
        revenue_growth
    FROM financial_ratios
    WHERE stock_id = (SELECT id FROM stocks WHERE ticker = '005930')
      AND fiscal_year IS NOT NULL
      AND fiscal_year >= 2023
    ORDER BY fiscal_year, fiscal_quarter
""")).fetchall()

df = pd.DataFrame(data, columns=[
    'date', 'fiscal_year', 'fiscal_quarter', 'roa',
    'operating_profit_margin', 'net_profit_margin',
    'debt_ratio', 'revenue_growth'
])

# 분기 라벨 생성
df['quarter_label'] = df['fiscal_year'].astype(str) + 'Q' + df['fiscal_quarter'].astype(str)

# 시각화
fig, axes = plt.subplots(2, 2, figsize=(15, 10))

axes[0, 0].plot(df['quarter_label'], df['roa'], marker='o')
axes[0, 0].set_title('ROA 추이')
axes[0, 0].set_ylabel('%')

axes[0, 1].plot(df['quarter_label'], df['operating_profit_margin'], marker='o')
axes[0, 1].set_title('영업이익률 추이')
axes[0, 1].set_ylabel('%')

axes[1, 0].plot(df['quarter_label'], df['debt_ratio'], marker='o')
axes[1, 0].set_title('부채비율 추이')
axes[1, 0].set_ylabel('%')

axes[1, 1].plot(df['quarter_label'], df['revenue_growth'], marker='o')
axes[1, 1].set_title('매출액 증가율 추이')
axes[1, 1].set_ylabel('%')

plt.tight_layout()
plt.savefig('samsung_ratios_trend.png')
plt.show()

db.close()
```

---

## 트러블슈팅

### 문제 1: 재무비율 계산 시 NULL 값이 많음

**원인**: 재무제표 JSONB 데이터에 필요한 계정과목이 없음

**해결**:
1. 재무제표 데이터 구조 확인:
```python
from db.connection import SessionLocal
from models import FinancialStatement
import json

db = SessionLocal()
stmt = db.query(FinancialStatement).first()

print("재무상태표 구조:")
print(json.dumps(stmt.balance_sheet, indent=2, ensure_ascii=False))

print("\n손익계산서 구조:")
print(json.dumps(stmt.income_statement, indent=2, ensure_ascii=False))

db.close()
```

2. `FinancialRatioCalculator`의 `_extract_value()` 메서드 수정
   - JSONB 키 경로 조정
   - 대체 키 추가

### 문제 2: 전기 데이터 없어서 성장률 계산 불가

**원인**: 재무제표가 1-2분기만 수집됨

**해결**:
- DART 재무제표 재수집 (5년 × 4분기 = 20건)
```bash
python scripts/batch_collect_financials.py --all-stocks --years 5
```

### 문제 3: 뷰 조회 시 성능 저하

**원인**: LATERAL JOIN은 대량 데이터 조회 시 느릴 수 있음

**해결**:
1. 인덱스 확인:
```sql
-- 필요한 인덱스 확인
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'financial_ratios'
ORDER BY indexname;
```

2. Materialized View 생성 (물리적 테이블):
```sql
CREATE MATERIALIZED VIEW mv_daily_combined_ratios AS
SELECT * FROM vw_daily_combined_ratios;

-- 인덱스 추가
CREATE INDEX idx_mv_combined_stock_date
ON mv_daily_combined_ratios(stock_id, date);

-- 정기적으로 갱신
REFRESH MATERIALIZED VIEW mv_daily_combined_ratios;
```

### 문제 4: 매출원가 없어서 매출총이익률 계산 불가

**원인**: DART API 파싱 시 상세 계정과목 미수집

**해결**:
- `collectors/dart_collector.py` 개선 필요 (Week 4 작업)
- 현재는 9개 지표만 계산 가능 (매출총이익률 제외)

### 문제 5: 계산 결과가 pykrx ROE와 다름

**원인**: 계산 시점 차이 또는 공식 차이

**설명**:
- pykrx ROE: `EPS / BPS × 100` (일별 변동)
- 재무제표 ROE: `당기순이익 / 자기자본 × 100` (분기별)
- 정상적인 차이 - 두 값 모두 유효

---

## 다음 단계

### Week 4: 데이터 품질 개선

1. **DART 수집기 개선**
   - 상세 계정과목 파싱 (재고자산, 매출채권, 매출원가 등)
   - 5년 × 4분기 완전 수집

2. **추가 재무비율 계산**
   - ROIC, EBITDA Margin
   - Quick Ratio, Interest Coverage
   - Inventory/Receivables/Payables Turnover

### Week 5: Airflow 파이프라인

3. **자동화**
   - 분기 발표 후 자동 계산
   - 뷰 자동 갱신
   - 데이터 품질 체크

---

## 참고 문서

- [FINANCIAL_RATIOS_COMPARISON.md](./FINANCIAL_RATIOS_COMPARISON.md) - 재무비율 계산 가능성 비교
- [DAILY_VS_QUARTERLY_RATIOS_STRATEGY.md](./DAILY_VS_QUARTERLY_RATIOS_STRATEGY.md) - 하이브리드 전략 상세 설명
- [Task_분할서_Phase1_Phase2.md](../Task_분할서_Phase1_Phase2.md) - Day 14-15 작업 계획

---

**작성일**: 2025-01-21
**버전**: 1.0
**Day 14-15 작업 완료**
