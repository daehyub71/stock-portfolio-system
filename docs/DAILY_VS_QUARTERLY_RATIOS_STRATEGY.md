# 일별 vs 분기별 재무비율 데이터 통합 전략

## 🎯 문제 정의

### 데이터 시간 단위 불일치

| 데이터 소스 | 시간 단위 | 업데이트 주기 | 예시 |
|-----------|---------|-------------|------|
| **pykrx 재무비율** | 일별 (Daily) | 매 거래일 | 2025-01-20, 2025-01-21, ... |
| **DART 재무제표** | 분기별 (Quarterly) | 분기 1회 | 2024Q4, 2025Q1, ... |

**핵심 이슈**:
- pykrx: PER, PBR, ROE 등 → **매일** 변동 (주가 변동 반영)
- DART 계산: ROA, 부채비율 등 → **분기당 1건** (재무제표 발표 시점)

❓ **어떻게 두 가지를 하나의 `financial_ratios` 테이블에 저장할 것인가?**

---

## 💡 해결 방안 (3가지 전략 비교)

### ✅ **전략 1: 하이브리드 저장 (권장)**

**개념**: 일별 데이터와 분기별 데이터를 같은 테이블에 저장하되, 필드 조합으로 구분

#### 저장 구조

```python
# 예시 1: pykrx 일별 데이터 (2025-01-20)
FinancialRatio(
    stock_id=1,
    date=date(2025, 1, 20),           # 일별 날짜
    report_date=None,                 # NULL
    fiscal_year=None,                 # NULL
    fiscal_quarter=None,              # NULL
    per=15.2,                         # pykrx 데이터
    pbr=1.8,
    roe=12.5,
    roa=None,                         # 분기 데이터는 NULL
    debt_ratio=None,                  # 분기 데이터는 NULL
)

# 예시 2: DART 분기별 데이터 (2024Q4)
FinancialRatio(
    stock_id=1,
    date=date(2024, 12, 31),          # 분기 마지막 날 (대표일)
    report_date=date(2025, 2, 14),    # 실제 보고서 발표일
    fiscal_year=2024,                 # 회계연도
    fiscal_quarter=4,                 # 4분기
    per=None,                         # 일별 데이터는 NULL
    pbr=None,
    roe=None,
    roa=8.5,                          # 재무제표 계산
    debt_ratio=45.2,                  # 재무제표 계산
    operating_profit_margin=21.3,     # 재무제표 계산
)
```

#### 장점
- ✅ 단일 테이블로 관리 간편
- ✅ 기존 모델 구조 활용 가능 (`date`, `report_date`, `fiscal_year`, `fiscal_quarter` 이미 존재)
- ✅ 쿼리 시 조건문으로 쉽게 필터링

#### 단점
- ❌ NULL 값이 많아 저장 효율성 낮음
- ❌ 일별/분기별 혼재로 데이터 이해도 낮음

#### 쿼리 예시

```python
from db.connection import SessionLocal
from models import Stock, FinancialRatio
from sqlalchemy import and_

db = SessionLocal()

# 1. pykrx 일별 데이터만 조회
daily_ratios = db.query(FinancialRatio).filter(
    FinancialRatio.stock_id == 1,
    FinancialRatio.fiscal_year == None,  # 분기 정보 없음
    FinancialRatio.date >= date(2025, 1, 1)
).all()

# 2. DART 분기별 데이터만 조회
quarterly_ratios = db.query(FinancialRatio).filter(
    FinancialRatio.stock_id == 1,
    FinancialRatio.fiscal_year != None,  # 분기 정보 있음
    FinancialRatio.fiscal_year == 2024
).all()

# 3. 특정 날짜의 "최신" 분기 데이터 가져오기 (백필링)
latest_quarterly = db.query(FinancialRatio).filter(
    FinancialRatio.stock_id == 1,
    FinancialRatio.fiscal_year != None,
    FinancialRatio.date <= date(2025, 1, 20)  # 해당 날짜 이전 최신 분기
).order_by(FinancialRatio.date.desc()).first()

db.close()
```

---

### 🔄 **전략 2: 백필링 (Backfilling)**

**개념**: 분기별 재무비율을 계산한 후, 해당 분기의 **모든 거래일에 동일한 값을 복사**

#### 저장 구조

```python
# 2024Q4 재무비율을 계산 (2024-12-31 기준)
# → 2024-10-01 ~ 2024-12-31 모든 거래일에 복사

for trading_day in get_trading_days("20241001", "20241231"):
    FinancialRatio(
        stock_id=1,
        date=trading_day,                 # 각 거래일
        report_date=date(2025, 2, 14),    # 보고서 발표일
        fiscal_year=2024,
        fiscal_quarter=4,
        per=15.2,                         # pykrx (거래일마다 다름)
        pbr=1.8,                          # pykrx (거래일마다 다름)
        roa=8.5,                          # DART (분기 내 동일)
        debt_ratio=45.2,                  # DART (분기 내 동일)
        operating_profit_margin=21.3,     # DART (분기 내 동일)
    )
```

#### 장점
- ✅ 일별 조회 시 pykrx + DART 데이터를 한 번에 가져올 수 있음
- ✅ 시계열 분석 시 결측치 없음
- ✅ 백테스팅/투자 전략 구현 시 편리 (매일 모든 지표 사용 가능)

#### 단점
- ❌ 데이터 중복으로 저장 공간 증가 (분기당 약 60일 × 10개 지표)
- ❌ 재무제표 수정 시 60일치 레코드 모두 업데이트 필요
- ❌ "실제로는 변하지 않은 값"을 일별로 저장하는 논리적 모순

#### 구현 예시

```python
def backfill_quarterly_ratios(stock_id: int, fiscal_year: int, fiscal_quarter: int):
    """분기별 재무비율을 해당 분기 모든 거래일에 백필링"""

    # 1. 분기 기간 계산
    start_date, end_date = get_quarter_dates(fiscal_year, fiscal_quarter)

    # 2. 재무제표 기반 비율 계산
    ratios = calculate_ratios_from_statements(stock_id, fiscal_year, fiscal_quarter)

    # 3. 거래일 목록 가져오기
    trading_days = get_trading_days_from_pykrx(start_date, end_date)

    # 4. 각 거래일마다 레코드 생성/업데이트
    for day in trading_days:
        # 기존 pykrx 데이터가 있으면 업데이트, 없으면 생성
        ratio = db.query(FinancialRatio).filter(
            FinancialRatio.stock_id == stock_id,
            FinancialRatio.date == day
        ).first()

        if ratio:
            # 업데이트 (pykrx 데이터는 유지, DART 데이터만 추가)
            ratio.fiscal_year = fiscal_year
            ratio.fiscal_quarter = fiscal_quarter
            ratio.roa = ratios['roa']
            ratio.debt_ratio = ratios['debt_ratio']
            # ...
        else:
            # 신규 생성 (pykrx 없는 경우 - 드물음)
            ratio = FinancialRatio(
                stock_id=stock_id,
                date=day,
                fiscal_year=fiscal_year,
                fiscal_quarter=fiscal_quarter,
                roa=ratios['roa'],
                debt_ratio=ratios['debt_ratio'],
                # ...
            )
            db.add(ratio)

    db.commit()
```

---

### 🗂️ **전략 3: 테이블 분리**

**개념**: `daily_ratios`와 `quarterly_ratios` 두 개의 테이블로 완전 분리

#### 스키마 설계

```python
# 테이블 1: daily_ratios (pykrx 데이터)
class DailyRatio(Base):
    __tablename__ = 'daily_ratios'

    id = Column(Integer, primary_key=True)
    stock_id = Column(Integer, ForeignKey('stocks.id'))
    date = Column(Date, nullable=False)

    # pykrx 지표만
    per = Column(Numeric(10, 4))
    pbr = Column(Numeric(10, 4))
    eps = Column(Numeric(12, 2))
    bps = Column(Numeric(12, 2))
    div = Column(Numeric(10, 4))
    dps = Column(Numeric(12, 2))
    roe = Column(Numeric(10, 4))
    payout_ratio = Column(Numeric(10, 4))

    __table_args__ = (
        Index('idx_daily_ratios_stock_date', 'stock_id', 'date', unique=True),
    )

# 테이블 2: quarterly_ratios (DART 계산)
class QuarterlyRatio(Base):
    __tablename__ = 'quarterly_ratios'

    id = Column(Integer, primary_key=True)
    stock_id = Column(Integer, ForeignKey('stocks.id'))
    report_date = Column(Date, nullable=False)
    fiscal_year = Column(Integer, nullable=False)
    fiscal_quarter = Column(Integer, nullable=False)

    # 재무제표 계산 지표만
    roa = Column(Numeric(10, 4))
    debt_ratio = Column(Numeric(10, 4))
    current_ratio = Column(Numeric(10, 4))
    operating_profit_margin = Column(Numeric(10, 4))
    # ... (10개 지표)

    __table_args__ = (
        Index('idx_quarterly_ratios_stock_year_quarter',
              'stock_id', 'fiscal_year', 'fiscal_quarter', unique=True),
    )
```

#### 장점
- ✅ 명확한 데이터 분리 (일별 vs 분기별)
- ✅ NULL 값 없음 (저장 효율성 높음)
- ✅ 각 테이블에 최적화된 인덱스 설계 가능

#### 단점
- ❌ 조회 시 JOIN 필요 (복잡도 증가)
- ❌ 두 테이블 관리 필요 (마이그레이션, 백업 등)
- ❌ 백테스팅 시 매번 JOIN 쿼리 실행 (성능 저하)

#### 조회 예시

```python
# 특정 날짜의 모든 지표 조회 (복잡한 JOIN 필요)
from sqlalchemy import and_, func

result = db.query(
    DailyRatio,
    QuarterlyRatio
).outerjoin(
    QuarterlyRatio,
    and_(
        DailyRatio.stock_id == QuarterlyRatio.stock_id,
        # 서브쿼리: 해당 날짜 이전 최신 분기 찾기
        QuarterlyRatio.id == db.query(QuarterlyRatio.id).filter(
            QuarterlyRatio.stock_id == DailyRatio.stock_id,
            QuarterlyRatio.report_date <= DailyRatio.date
        ).order_by(QuarterlyRatio.report_date.desc()).limit(1).scalar_subquery()
    )
).filter(
    DailyRatio.stock_id == 1,
    DailyRatio.date == date(2025, 1, 20)
).first()
```

---

## 📊 전략 비교표

| 기준 | 전략 1: 하이브리드 | 전략 2: 백필링 | 전략 3: 테이블 분리 |
|-----|-----------------|--------------|-----------------|
| **구현 난이도** | ⭐⭐ 중간 | ⭐⭐⭐ 높음 | ⭐⭐⭐⭐ 매우 높음 |
| **저장 효율성** | ⭐⭐ 중간 (NULL 많음) | ⭐ 낮음 (중복 많음) | ⭐⭐⭐⭐ 높음 |
| **조회 성능** | ⭐⭐⭐ 좋음 | ⭐⭐⭐⭐ 매우 좋음 | ⭐⭐ 중간 (JOIN) |
| **백테스팅 편의성** | ⭐⭐ 중간 | ⭐⭐⭐⭐ 매우 좋음 | ⭐ 낮음 |
| **데이터 일관성** | ⭐⭐⭐ 좋음 | ⭐⭐ 중간 | ⭐⭐⭐⭐ 매우 좋음 |
| **유지보수** | ⭐⭐⭐ 쉬움 | ⭐⭐ 중간 | ⭐ 어려움 |

---

## ✅ 권장 전략: **하이브리드 + 선택적 백필링**

### 📋 구현 방안

#### Phase 1: 하이브리드 저장 (당장)

**일별 데이터** (pykrx):
```python
# batch_collect_ratios.py (현재 방식 유지)
FinancialRatio(
    stock_id=stock.id,
    date=ratio_date,              # 일별
    fiscal_year=None,             # NULL
    fiscal_quarter=None,          # NULL
    per=row['PER'],
    pbr=row['PBR'],
    roe=row['ROE'],
    # 분기 지표는 NULL
    roa=None,
    debt_ratio=None,
)
```

**분기별 데이터** (DART 계산):
```python
# scripts/calculate_financial_ratios.py (신규 구현)
FinancialRatio(
    stock_id=stock.id,
    date=quarter_end_date,        # 분기 마지막 날 (예: 2024-12-31)
    report_date=actual_report_date,  # 실제 발표일 (예: 2025-02-14)
    fiscal_year=2024,
    fiscal_quarter=4,
    # 일별 지표는 NULL
    per=None,
    pbr=None,
    # 분기 계산 지표
    roa=8.5,
    debt_ratio=45.2,
    operating_profit_margin=21.3,
)
```

#### Phase 2: 뷰(View) 생성 - 조회 편의성

백테스팅/분석용 가상 테이블 생성:

```sql
CREATE VIEW vw_daily_combined_ratios AS
SELECT
    dr.stock_id,
    dr.date,
    dr.per,
    dr.pbr,
    dr.roe,
    dr.eps,
    dr.bps,
    dr.div,
    dr.dps,
    dr.payout_ratio,
    -- 해당 날짜 이전 최신 분기 데이터 조인
    qr.roa,
    qr.debt_ratio,
    qr.current_ratio,
    qr.operating_profit_margin,
    qr.net_profit_margin,
    qr.gross_profit_margin,
    qr.equity_ratio,
    qr.debt_to_equity,
    qr.asset_turnover,
    qr.revenue_growth,
    qr.fiscal_year,
    qr.fiscal_quarter
FROM financial_ratios dr
LEFT JOIN LATERAL (
    SELECT *
    FROM financial_ratios
    WHERE stock_id = dr.stock_id
      AND fiscal_year IS NOT NULL
      AND date <= dr.date
    ORDER BY date DESC
    LIMIT 1
) qr ON TRUE
WHERE dr.fiscal_year IS NULL  -- 일별 데이터만
ORDER BY dr.stock_id, dr.date;
```

**사용 예시**:
```python
# SQLAlchemy로 뷰 조회
from sqlalchemy import text

query = text("""
    SELECT * FROM vw_daily_combined_ratios
    WHERE stock_id = :stock_id
      AND date BETWEEN :start_date AND :end_date
    ORDER BY date
""")

result = db.execute(query, {
    "stock_id": 1,
    "start_date": "2024-01-01",
    "end_date": "2024-12-31"
}).fetchall()

# 결과: 각 거래일마다 pykrx 일별 지표 + 해당 시점 최신 분기 지표
```

#### Phase 3: 필요시 백테스팅 테이블 생성 (선택적)

분석/백테스팅 성능이 중요한 경우에만:

```python
# 별도 테이블 생성 (materialized view 개념)
class BacktestingRatio(Base):
    """백테스팅용 일별 통합 재무비율 (백필링 적용)"""

    __tablename__ = 'backtesting_ratios'

    id = Column(Integer, primary_key=True)
    stock_id = Column(Integer, ForeignKey('stocks.id'))
    date = Column(Date, nullable=False)

    # 일별 지표 (pykrx)
    per = Column(Numeric(10, 4))
    pbr = Column(Numeric(10, 4))
    roe = Column(Numeric(10, 4))

    # 분기 지표 (백필링)
    roa = Column(Numeric(10, 4))
    debt_ratio = Column(Numeric(10, 4))
    fiscal_year = Column(Integer)
    fiscal_quarter = Column(Integer)

    __table_args__ = (
        Index('idx_backtesting_ratios_stock_date', 'stock_id', 'date', unique=True),
    )

# 정기적으로 뷰 데이터를 물리 테이블로 복사
def materialize_backtesting_ratios():
    db.execute(text("""
        INSERT INTO backtesting_ratios
        SELECT * FROM vw_daily_combined_ratios
        ON CONFLICT (stock_id, date) DO UPDATE SET ...
    """))
    db.commit()
```

---

## 🔧 구현 단계별 가이드

### Step 1: 현재 상태 유지 (pykrx 일별 수집)

```bash
# 이미 완료된 작업 - 변경 없음
python scripts/batch_collect_ratios.py --all --years 3
```

### Step 2: 분기별 재무비율 계산 구현 (Day 14-15)

```bash
# 신규 스크립트 작성
# scripts/calculate_quarterly_ratios.py

python scripts/calculate_quarterly_ratios.py --stock-id 1 --year 2024 --quarter 4
```

**저장 로직**:
```python
def calculate_and_save_quarterly_ratios(stock_id, fiscal_year, fiscal_quarter):
    """분기별 재무비율 계산 및 저장"""

    # 1. 재무제표 조회
    stmt = db.query(FinancialStatement).filter(
        FinancialStatement.stock_id == stock_id,
        FinancialStatement.fiscal_year == fiscal_year,
        FinancialStatement.fiscal_quarter == fiscal_quarter
    ).first()

    if not stmt:
        return None

    # 2. 재무비율 계산
    ratios = {
        'roa': calculate_roa(stmt),
        'debt_ratio': calculate_debt_ratio(stmt),
        'current_ratio': calculate_current_ratio(stmt),
        # ... 10개 지표
    }

    # 3. 분기 마지막 날짜 계산
    quarter_end = get_quarter_end_date(fiscal_year, fiscal_quarter)

    # 4. 저장 (분기별 단일 레코드)
    ratio_record = FinancialRatio(
        stock_id=stock_id,
        date=quarter_end,              # 분기 마지막 날
        report_date=stmt.report_date,  # 실제 발표일
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        **ratios                       # 계산된 10개 지표
    )

    db.add(ratio_record)
    db.commit()

    return ratio_record
```

### Step 3: 뷰 생성 (조회 편의성)

```bash
# 마이그레이션 스크립트
python scripts/create_combined_ratios_view.py
```

### Step 4: 백테스팅 API 구현

```python
# api/backtesting.py

def get_ratios_for_backtest(stock_id: int, start_date: date, end_date: date):
    """백테스팅용 일별 통합 재무비율 조회"""

    query = text("""
        SELECT * FROM vw_daily_combined_ratios
        WHERE stock_id = :stock_id
          AND date BETWEEN :start_date AND :end_date
        ORDER BY date
    """)

    result = db.execute(query, {
        "stock_id": stock_id,
        "start_date": start_date,
        "end_date": end_date
    }).fetchall()

    return result
```

---

## 📈 데이터 사용 예시

### 사용 사례 1: 특정 날짜의 모든 지표 조회

```python
from datetime import date

# 2025-01-20 기준 삼성전자의 모든 재무비율
ratios = db.execute(text("""
    SELECT * FROM vw_daily_combined_ratios
    WHERE stock_id = (SELECT id FROM stocks WHERE ticker = '005930')
      AND date = '2025-01-20'
""")).fetchone()

print(f"PER: {ratios.per}")          # pykrx 일별
print(f"ROE: {ratios.roe}")          # pykrx 일별
print(f"ROA: {ratios.roa}")          # 2024Q4 분기 데이터
print(f"부채비율: {ratios.debt_ratio}")  # 2024Q4 분기 데이터
print(f"적용 분기: {ratios.fiscal_year}Q{ratios.fiscal_quarter}")
```

### 사용 사례 2: 시계열 분석 (6개월)

```python
# 2024-07-01 ~ 2024-12-31 삼성전자 시계열 데이터
ratios = db.execute(text("""
    SELECT date, per, pbr, roe, roa, debt_ratio, fiscal_quarter
    FROM vw_daily_combined_ratios
    WHERE stock_id = (SELECT id FROM stocks WHERE ticker = '005930')
      AND date BETWEEN '2024-07-01' AND '2024-12-31'
    ORDER BY date
""")).fetchall()

# 결과 예시:
# date         per   pbr  roe   roa   debt_ratio  fiscal_quarter
# 2024-07-01  15.2  1.8  12.5  8.3   45.0        2  (2024Q2 적용)
# 2024-07-02  15.3  1.8  12.5  8.3   45.0        2
# ...
# 2024-10-01  15.5  1.9  12.5  8.5   44.8        3  (2024Q3 적용)
# 2024-10-02  15.4  1.9  12.5  8.5   44.8        3
```

### 사용 사례 3: 백테스팅 전략

```python
# 저PBR + 고ROE + 낮은부채비율 종목 선정
candidates = db.execute(text("""
    SELECT stock_id, date, per, pbr, roe, debt_ratio
    FROM vw_daily_combined_ratios
    WHERE date = '2024-12-31'
      AND pbr < 1.0              -- 저PBR
      AND roe > 10.0             -- 고ROE
      AND debt_ratio < 50.0      -- 낮은 부채비율
    ORDER BY roe DESC
    LIMIT 20
""")).fetchall()
```

---

## 🎯 최종 권장사항

### ✅ 단기 (Week 3-4): 하이브리드 저장

1. **pykrx 일별 수집 계속** (현재 방식 유지)
   - `fiscal_year = NULL`로 저장

2. **DART 분기별 계산 구현** (Day 14-15)
   - 분기당 1건, `fiscal_year != NULL`로 저장
   - 10개 재무비율 계산

3. **뷰 생성** (조회 편의성)
   - `vw_daily_combined_ratios` 생성
   - 백테스팅/분석 시 사용

### 🚀 중장기 (Week 5+): 성능 최적화

4. **백테스팅 테이블 생성** (필요 시)
   - Materialized view 개념
   - 일별 조회 성능 최적화

5. **정기 업데이트 스케줄**
   - Airflow DAG로 자동화
   - 분기 발표 후 자동 계산/백필링

---

## 📚 참고 자료

- [FINANCIAL_RATIOS_COMPARISON.md](./FINANCIAL_RATIOS_COMPARISON.md) - 재무비율 계산 가능성 비교
- [PostgreSQL LATERAL JOIN 문서](https://www.postgresql.org/docs/current/queries-table-expressions.html#QUERIES-LATERAL)
- [SQLAlchemy Views 가이드](https://docs.sqlalchemy.org/en/20/core/selectable.html#sqlalchemy.schema.Table)

---

**작성일**: 2025-01-21
**버전**: 1.0
