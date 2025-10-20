# 재무비율 수집 가이드

pykrx 기반 재무비율 수집 시스템 사용 설명서

## 📊 수집 가능한 지표

### pykrx에서 직접 제공
- **PER** (Price to Earnings Ratio) - 주가수익비율
- **PBR** (Price to Book Ratio) - 주가순자산비율
- **EPS** (Earnings Per Share) - 주당순이익
- **BPS** (Book value Per Share) - 주당순자산
- **DIV** (Dividend Yield) - 배당수익률 (%)
- **DPS** (Dividend Per Share) - 주당배당금

### 자동 계산 지표
- **ROE** (Return on Equity) = EPS / BPS × 100
- **Payout Ratio** (배당성향) = DPS / EPS × 100

## 🚀 사용 방법

### 1. 재무비율 수집 (신규)

#### 최근 3년 전체 종목 수집
```bash
python scripts/collect_financial_ratios.py --years 3
```

#### 특정 기간 수집
```bash
python scripts/collect_financial_ratios.py --start 20200101 --end 20250118
```

#### 특정 종목만 수집
```bash
# 삼성전자 최근 5년
python scripts/collect_financial_ratios.py --ticker 005930 --years 5
```

#### 특정 시장만 수집
```bash
# KOSPI 종목만 최근 3년
python scripts/collect_financial_ratios.py --market KOSPI --years 3

# KOSDAQ 종목만
python scripts/collect_financial_ratios.py --market KOSDAQ --years 3
```

#### 중단 후 재개
```bash
# 체크포인트에서 재개
python scripts/collect_financial_ratios.py --years 3 --resume
```

### 2. 시세 데이터 증분 업데이트

#### 전체 종목 업데이트 (오늘까지)
```bash
python scripts/update_incremental_prices.py
```

#### 최근 N일만 업데이트
```bash
# 최근 7일만 체크하여 업데이트
python scripts/update_incremental_prices.py --days 7

# 최근 30일만
python scripts/update_incremental_prices.py --days 30
```

#### 특정 종목만 업데이트
```bash
python scripts/update_incremental_prices.py --ticker 005930
```

#### 특정 시장만 업데이트
```bash
python scripts/update_incremental_prices.py --market KOSPI
```

## 📋 데이터 수집 전략

### 권장 수집 주기

#### 재무비율 (financial_ratios)
- **일별 업데이트**: 영업일 종료 후 (PER, PBR 등은 주가 변동에 따라 매일 변함)
- **수집 기간**: 최소 3년, 권장 5년
- **빈도**: 주 1회 또는 월 1회 (과거 데이터는 변하지 않음)

```bash
# 매주 월요일 실행 (cron)
0 9 * * 1 cd /path/to/project && python scripts/collect_financial_ratios.py --days 7
```

#### 시세 데이터 (daily_prices)
- **일별 업데이트**: 영업일 종료 후
- **수집 시간**: 오후 4시 이후 (장 마감 후)

```bash
# 매일 오후 4시 30분 실행 (cron)
30 16 * * 1-5 cd /path/to/project && python scripts/update_incremental_prices.py
```

## 🗂️ 데이터베이스 구조

### financial_ratios 테이블

```sql
CREATE TABLE financial_ratios (
    id SERIAL PRIMARY KEY,
    stock_id INTEGER NOT NULL,
    date DATE NOT NULL,                      -- 데이터 날짜 (일별)

    -- pykrx 제공 지표
    per NUMERIC(10, 4),                      -- 주가수익비율
    pbr NUMERIC(10, 4),                      -- 주가순자산비율
    eps NUMERIC(12, 2),                      -- 주당순이익 (원)
    bps NUMERIC(12, 2),                      -- 주당순자산 (원)
    div NUMERIC(10, 4),                      -- 배당수익률 (%)
    dps NUMERIC(12, 2),                      -- 주당배당금 (원)

    -- 계산 지표
    roe NUMERIC(10, 4),                      -- ROE (%)
    payout_ratio NUMERIC(10, 4),            -- 배당성향 (%)

    created_at TIMESTAMP,
    updated_at TIMESTAMP,

    UNIQUE(stock_id, date)                   -- 종목당 일별 1건
);
```

## 💡 활용 예시

### Python에서 데이터 조회

```python
from db.connection import SessionLocal
from models import Stock, FinancialRatio
from sqlalchemy import desc

db = SessionLocal()

# 삼성전자 최근 재무비율 조회
stock = db.query(Stock).filter(Stock.ticker == '005930').first()

ratios = db.query(FinancialRatio).filter(
    FinancialRatio.stock_id == stock.id
).order_by(desc(FinancialRatio.date)).limit(10).all()

for ratio in ratios:
    print(f"{ratio.date}: PER={ratio.per}, PBR={ratio.pbr}, ROE={ratio.roe}")

db.close()
```

### SQL로 조회

```sql
-- 삼성전자 최근 30일 재무비율
SELECT
    date,
    per,
    pbr,
    roe,
    eps,
    bps,
    div
FROM financial_ratios fr
JOIN stocks s ON fr.stock_id = s.id
WHERE s.ticker = '005930'
ORDER BY date DESC
LIMIT 30;
```

### 평균 PER/PBR 조회

```sql
-- KOSPI 전체 평균 PER, PBR (최신 날짜)
SELECT
    AVG(fr.per) as avg_per,
    AVG(fr.pbr) as avg_pbr,
    COUNT(*) as stock_count
FROM financial_ratios fr
JOIN stocks s ON fr.stock_id = s.id
WHERE s.market = 'KOSPI'
  AND fr.date = (SELECT MAX(date) FROM financial_ratios)
  AND fr.per > 0 AND fr.per < 100;  -- 이상치 제거
```

## 🔍 데이터 품질 확인

### 수집 현황 확인

```python
from db.connection import SessionLocal
from models import FinancialRatio
from sqlalchemy import func

db = SessionLocal()

# 전체 레코드 수
total = db.query(func.count(FinancialRatio.id)).scalar()
print(f"총 재무비율 레코드: {total:,}건")

# 종목별 레코드 수
stock_counts = db.query(
    func.count(func.distinct(FinancialRatio.stock_id))
).scalar()
print(f"재무비율 데이터가 있는 종목: {stock_counts:,}개")

# 날짜 범위
date_range = db.query(
    func.min(FinancialRatio.date),
    func.max(FinancialRatio.date)
).first()
print(f"데이터 기간: {date_range[0]} ~ {date_range[1]}")

db.close()
```

## 🚨 주의사항

### 1. pykrx 데이터 특성
- **ROE는 제공되지 않음**: EPS/BPS로 계산
- **ROIC, 부채비율 등**: pykrx에서 제공하지 않음 (DART 재무제표로 계산 필요)
- **예측치**: 제공되지 않음 (과거 실적만)

### 2. 데이터 정확성
- pykrx는 KRX 공식 데이터를 사용하므로 신뢰도가 높음
- 단, PER/PBR은 주가 변동에 따라 매일 변함
- 재무제표 발표일에 EPS/BPS가 업데이트됨

### 3. Rate Limiting
- pykrx는 KRX 공개 데이터이므로 API 제한 없음
- 단, 서버 부하 방지를 위해 0.1초 간격 설정

### 4. 체크포인트
- 수집 중 중단 시 `data/checkpoints/ratio_collection_checkpoint.json` 저장
- `--resume` 옵션으로 재개 가능
- 완료 후 자동 삭제

## 📊 Streamlit 대시보드에서 확인

재무비율 수집 후 Streamlit 대시보드에서 확인:

```bash
./run_dashboard.sh
```

- **데이터 품질 점검** 페이지에서 재무비율 커버리지 확인
- **데이터베이스 개요** 페이지에서 `financial_ratios` 테이블 확인

## 🔧 문제 해결

### "No data collected" 경고
- 해당 종목이 상장폐지되었거나 데이터 없음
- 날짜 범위를 확인 (주말/공휴일 제외)

### pykrx 설치 오류
```bash
pip install --upgrade pykrx
```

### 데이터베이스 오류
```bash
# 테이블 재생성 (주의: 기존 데이터 삭제됨)
python scripts/init_db.py
```

## 📚 참고 자료

- [pykrx GitHub](https://github.com/sharebook-kr/pykrx)
- [pykrx 문서](https://github.com/sharebook-kr/pykrx/wiki)
- [KRX 정보데이터시스템](https://data.krx.co.kr)

---

**작성일**: 2025-01-20
**버전**: 1.0
