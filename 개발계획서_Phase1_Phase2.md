# 한국 주식 투자 포트폴리오 시스템 개발계획서
## Phase 1 & Phase 2: 데이터 수집 및 통합

**작성일:** 2025-10-19
**버전:** 1.0
**프로젝트명:** Korean Stock Portfolio System

---

## 📋 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [Phase 1: 데이터 수집 아키텍처](#2-phase-1-데이터-수집-아키텍처)
3. [Phase 2: 데이터 통합 및 저장](#3-phase-2-데이터-통합-및-저장)
4. [기술 스택](#4-기술-스택)
5. [개발 일정](#5-개발-일정)
6. [리스크 관리](#6-리스크-관리)

---

## 1. 프로젝트 개요

### 1.1 목표

한국 주식 시장 전체 종목에 대한 **시세 데이터**와 **재무 데이터**를 자동으로 수집하고, 확장 가능한 데이터베이스에 저장하여 퀀트 투자 전략 개발의 기반을 마련합니다.

### 1.2 핵심 요구사항

- ✅ **시세 데이터**: 일봉/분봉 데이터 (KIS API 우선, 대체: KRX/네이버 금융)
- ✅ **재무 데이터**: 재무제표, 재무비율 (DART 우선, 대체: 금융감독원 전자공시)
- ✅ **종목 마스터**: KRX 상장 종목 리스트 (KRX OPEN API)
- ✅ **확장성**: PostgreSQL 기반, 추후 해외 주식/ETF/파생상품 확장 가능
- ✅ **자동화**: 일 1회 자동 데이터 수집 (cron/airflow)

### 1.3 최종 지향점

- 마법의 공식(Magic Formula), 밸류 투자 전략 등 퀀트 투자 전략 백테스트
- 실시간 종목 스크리닝 및 포트폴리오 리밸런싱 자동화

---

## 2. Phase 1: 데이터 수집 아키텍처

### 2.1 데이터 소스 전략

| 데이터 유형 | 우선순위 1 (Primary) | 우선순위 2 (Fallback) | 우선순위 3 (Backup) |
|------------|---------------------|----------------------|-------------------|
| **종목 리스트** | KRX OPEN API | KRX 정보데이터시스템 파일 다운로드 | 네이버 금융 크롤링 |
| **시세 데이터** | KIS Open API | KRX 시장정보 | 네이버 금융/야후 파이낸스 |
| **재무제표** | DART Open API | 금융감독원 전자공시 | FnGuide/Quantiwise (유료) |
| **재무비율** | DART (계산) | KRX 시장정보 | 직접 계산 |

### 2.2 Phase 1 세부 구현 계획

#### 2.2.1 종목 마스터 데이터 수집

**목표:** 전체 상장 종목 리스트 및 기본 정보 확보

**데이터 소스:**
- **Primary:** KRX OPEN API - [상장종목 검색](http://data.krx.co.kr)
  - 제공 항목: 종목코드, 종목명, 시장구분(KOSPI/KOSDAQ), 상장주식수, 섹터
  - API 키 불필요, 무료 사용 가능

**구현 상세:**

```python
# 파일 위치: stock-portfolio-system/collectors/krx_collector.py

import requests
import pandas as pd
from datetime import datetime

class KRXCollector:
    """KRX 상장 종목 정보 수집기"""

    BASE_URL = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

    def fetch_stock_list(self, market="ALL"):
        """
        상장 종목 리스트 조회

        Args:
            market: "KOSPI", "KOSDAQ", "ALL"

        Returns:
            pd.DataFrame: 종목 리스트
        """
        params = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT01901",
            "mktId": market,
            "trdDd": datetime.now().strftime("%Y%m%d")
        }

        response = requests.get(self.BASE_URL, params=params)
        data = response.json()

        df = pd.DataFrame(data['OutBlock_1'])

        # 컬럼명 매핑
        df = df.rename(columns={
            'ISU_SRT_CD': 'ticker',
            'ISU_ABBRV': 'name',
            'MKT_NM': 'market',
            'SECT_TP_NM': 'sector',
            'LIST_SHRS': 'listed_shares'
        })

        return df

    def fetch_stock_info_detail(self, ticker):
        """종목 상세 정보 조회"""
        # 업종, 상장일, 결산월 등 추가 정보
        pass
```

**수집 데이터:**
- 종목코드 (6자리)
- 종목명
- 시장구분 (KOSPI/KOSDAQ/KONEX)
- 업종 (대분류/중분류/소분류)
- 상장주식수
- 상장일
- 결산월

**저장 주기:** 주 1회 (월요일 오전 9시)

#### 2.2.2 시세 데이터 수집

**목표:** 일봉 OHLCV 데이터 수집 (최소 10년치)

**데이터 소스 전략:**

**Option 1: KIS Open API** (추천)

```python
# 파일 위치: stock-portfolio-system/collectors/kis_price_collector.py

import sys
sys.path.append('/Users/sunchulkim/src/kis-trading-mcp')
from server import inquery_stock_history

class KISPriceCollector:
    """한국투자증권 API 기반 시세 수집기"""

    async def fetch_daily_price(self, ticker, start_date, end_date):
        """
        일봉 데이터 조회

        Args:
            ticker: 종목코드 (예: "005930")
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)

        Returns:
            pd.DataFrame: OHLCV 데이터
        """
        result = await inquery_stock_history(ticker, start_date, end_date)

        df = pd.DataFrame(result['output2'])
        df = df.rename(columns={
            'stck_bsop_date': 'date',
            'stck_oprc': 'open',
            'stck_hgpr': 'high',
            'stck_lwpr': 'low',
            'stck_clpr': 'close',
            'acml_vol': 'volume'
        })

        # 데이터 타입 변환
        df['date'] = pd.to_datetime(df['date'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])

        return df
```

**KIS API 제약사항:**
- ⚠️ API 호출 제한: 1초 20건 (일일 제한 확인 필요)
- ⚠️ 과거 데이터: 일봉 최대 조회 기간 확인 필요 (예상: 1년 또는 100일)
- ✅ 해결방안: 기간을 나눠서 반복 호출 + Rate Limiting

**Option 2: KRX 시장정보** (Fallback)

```python
class KRXPriceCollector:
    """KRX 시장정보 기반 시세 수집기 (Fallback)"""

    def fetch_daily_price_from_krx(self, ticker, start_date, end_date):
        """
        KRX 개별종목 시세 조회
        URL: http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd
        """
        params = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT03501",
            "isuCd": ticker,
            "strtDd": start_date,
            "endDd": end_date
        }
        # 구현...
```

**수집 데이터:**
- 날짜 (YYYY-MM-DD)
- 시가/고가/저가/종가 (OHLC)
- 거래량/거래대금
- 수정주가 (액면분할/배당 반영)

**수집 전략:**
1. **초기 데이터:** 2014-01-01 ~ 현재 (10년치 백필)
2. **일 업데이트:** 매일 장 마감 후 (오후 4시) 당일 데이터 수집
3. **배치 크기:** 100종목씩 처리 (Rate Limit 고려)

#### 2.2.3 재무 데이터 수집

**목표:** 분기/연간 재무제표 및 재무비율 확보

**데이터 소스:** DART Open API (전자공시시스템)

**DART API 구조:**

```python
# 파일 위치: stock-portfolio-system/collectors/dart_collector.py

import requests
import json
from typing import Dict, List

class DARTCollector:
    """DART Open API 기반 재무 데이터 수집기"""

    BASE_URL = "https://opendart.fss.or.kr/api"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_corp_code(self, ticker: str) -> str:
        """
        종목코드 → DART 고유번호 변환

        Returns:
            str: DART corp_code (8자리)
        """
        url = f"{self.BASE_URL}/corpCode.xml"
        params = {"crtfc_key": self.api_key}

        # XML 파싱하여 corp_code 추출
        # DART에서 제공하는 corpCode.xml 다운로드 필요
        pass

    def fetch_financial_statement(
        self,
        corp_code: str,
        year: str,
        report_type: str = "11011",  # 사업보고서
        fs_div: str = "CFS"  # 연결재무제표
    ) -> Dict:
        """
        재무제표 조회

        Args:
            corp_code: DART 고유번호
            year: 사업연도 (YYYY)
            report_type: 보고서 코드
                - 11011: 사업보고서
                - 11012: 반기보고서
                - 11013: 1분기보고서
                - 11014: 3분기보고서
            fs_div: CFS(연결), OFS(개별)

        Returns:
            Dict: 재무제표 데이터
        """
        url = f"{self.BASE_URL}/fnlttSinglAcntAll.json"

        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bsns_year": year,
            "reprt_code": report_type,
            "fs_div": fs_div
        }

        response = requests.get(url, params=params)
        data = response.json()

        # 재무제표 파싱
        bs = self.parse_balance_sheet(data)  # 재무상태표
        is_ = self.parse_income_statement(data)  # 손익계산서
        cf = self.parse_cashflow_statement(data)  # 현금흐름표

        return {
            "balance_sheet": bs,
            "income_statement": is_,
            "cashflow_statement": cf
        }

    def parse_balance_sheet(self, data: Dict) -> Dict:
        """재무상태표 파싱"""
        # 주요 계정과목 추출
        accounts = {
            "total_assets": None,  # 자산총계
            "total_liabilities": None,  # 부채총계
            "total_equity": None,  # 자본총계
            "current_assets": None,  # 유동자산
            "non_current_assets": None,  # 비유동자산
            "current_liabilities": None,  # 유동부채
            "non_current_liabilities": None,  # 비유동부채
            "cash_and_equivalents": None,  # 현금및현금성자산
            "inventory": None,  # 재고자산
            "receivables": None,  # 매출채권
            "tangible_assets": None,  # 유형자산
            "intangible_assets": None,  # 무형자산
        }

        for item in data.get('list', []):
            account_nm = item['account_nm']
            amount = float(item['thstrm_amount'])  # 당기금액

            # 계정과목 매칭
            if '자산총계' in account_nm:
                accounts['total_assets'] = amount
            elif '부채총계' in account_nm:
                accounts['total_liabilities'] = amount
            # ... 나머지 계정과목 매칭

        return accounts

    def parse_income_statement(self, data: Dict) -> Dict:
        """손익계산서 파싱"""
        accounts = {
            "revenue": None,  # 매출액
            "operating_income": None,  # 영업이익
            "net_income": None,  # 당기순이익
            "ebitda": None,  # EBITDA
            "cost_of_sales": None,  # 매출원가
            "selling_admin_expenses": None,  # 판매관리비
            "interest_expense": None,  # 이자비용
            "tax_expense": None,  # 법인세비용
        }

        # 파싱 로직...
        return accounts

    def parse_cashflow_statement(self, data: Dict) -> Dict:
        """현금흐름표 파싱"""
        accounts = {
            "operating_cf": None,  # 영업활동현금흐름
            "investing_cf": None,  # 투자활동현금흐름
            "financing_cf": None,  # 재무활동현금흐름
            "free_cash_flow": None,  # 잉여현금흐름 (계산)
        }

        # 파싱 로직...
        return accounts
```

**DART API 특징:**
- ✅ **무료 사용**: API 키 발급만으로 무료 사용 가능
- ✅ **데이터 품질**: 공식 공시 데이터, 신뢰도 높음
- ⚠️ **호출 제한**: 분당 1,000건 (충분함)
- ⚠️ **과거 데이터**: 2015년 이후 전자공시 데이터
- ⚠️ **계정과목 표준화**: 기업마다 계정과목명이 다를 수 있음 → 매핑 테이블 필요

**수집 데이터:**

**재무상태표 (Balance Sheet):**
- 자산총계, 부채총계, 자본총계
- 유동자산, 비유동자산
- 유동부채, 비유동부채
- 현금성자산, 재고자산, 매출채권

**손익계산서 (Income Statement):**
- 매출액, 영업이익, 당기순이익
- EBITDA (계산: 영업이익 + 감가상각비)
- 매출원가, 판매관리비
- 이자비용, 법인세비용

**현금흐름표 (Cash Flow):**
- 영업/투자/재무 활동 현금흐름
- 잉여현금흐름 (FCF)

**수집 주기:**
- **연간 데이터**: 사업보고서 (매년 3월)
- **분기 데이터**: 1Q/3Q 보고서 (5월/11월)
- **반기 데이터**: 반기보고서 (8월)

#### 2.2.4 재무비율 계산

**목표:** 투자 전략에 필요한 핵심 재무비율 자동 계산

```python
# 파일 위치: stock-portfolio-system/calculators/financial_ratio_calculator.py

class FinancialRatioCalculator:
    """재무비율 계산기"""

    @staticmethod
    def calculate_ratios(bs, is_, cf, price_data) -> Dict:
        """
        주요 재무비율 계산

        Args:
            bs: 재무상태표 데이터
            is_: 손익계산서 데이터
            cf: 현금흐름표 데이터
            price_data: 시가총액 데이터

        Returns:
            Dict: 계산된 재무비율
        """
        ratios = {}

        # 1. 수익성 지표
        ratios['roe'] = is_['net_income'] / bs['total_equity']  # ROE
        ratios['roa'] = is_['net_income'] / bs['total_assets']  # ROA
        ratios['roic'] = is_['operating_income'] / (bs['total_assets'] - bs['current_liabilities'])  # ROIC
        ratios['operating_margin'] = is_['operating_income'] / is_['revenue']  # 영업이익률
        ratios['net_margin'] = is_['net_income'] / is_['revenue']  # 순이익률

        # 2. 안정성 지표
        ratios['debt_ratio'] = bs['total_liabilities'] / bs['total_equity']  # 부채비율
        ratios['current_ratio'] = bs['current_assets'] / bs['current_liabilities']  # 유동비율
        ratios['quick_ratio'] = (bs['current_assets'] - bs['inventory']) / bs['current_liabilities']  # 당좌비율

        # 3. 활동성 지표
        ratios['asset_turnover'] = is_['revenue'] / bs['total_assets']  # 자산회전율
        ratios['inventory_turnover'] = is_['cost_of_sales'] / bs['inventory']  # 재고자산회전율

        # 4. 성장성 지표 (YoY 비교 필요)
        # ratios['revenue_growth'] = ...
        # ratios['earnings_growth'] = ...

        # 5. 밸류에이션 지표 (시가총액 필요)
        market_cap = price_data['close'] * bs['outstanding_shares']
        ratios['per'] = market_cap / is_['net_income']  # PER
        ratios['pbr'] = market_cap / bs['total_equity']  # PBR
        ratios['psr'] = market_cap / is_['revenue']  # PSR
        ratios['pcr'] = market_cap / cf['operating_cf']  # PCR
        ratios['ev_ebitda'] = (market_cap + bs['total_liabilities'] - bs['cash_and_equivalents']) / is_['ebitda']  # EV/EBITDA

        # 6. 마법의 공식 지표
        ratios['earnings_yield'] = is_['operating_income'] / market_cap  # 이익수익률
        ratios['return_on_capital'] = is_['operating_income'] / (bs['total_assets'] - bs['current_liabilities'])  # 투하자본수익률

        return ratios
```

---

## 3. Phase 2: 데이터 통합 및 저장

### 3.1 데이터베이스 스키마 설계

**DBMS:** PostgreSQL 15+ (확장성, JSON 지원, 시계열 데이터 최적화)

#### 3.1.1 ERD (Entity-Relationship Diagram)

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│  stocks         │         │  daily_prices    │         │ financial_stmts │
├─────────────────┤         ├──────────────────┤         ├─────────────────┤
│ ticker (PK)     │────────<│ ticker (FK)      │         │ id (PK)         │
│ name            │         │ date (PK)        │         │ ticker (FK)     │────┐
│ market          │         │ open             │         │ report_date     │    │
│ sector          │         │ high             │         │ fiscal_year     │    │
│ listed_shares   │         │ low              │         │ fiscal_quarter  │    │
│ listing_date    │         │ close            │         │ report_type     │    │
│ fiscal_month    │         │ volume           │         │ fs_type         │    │
│ corp_code       │         │ trading_value    │         │ data (JSONB)    │    │
│ created_at      │         │ market_cap       │         │ created_at      │    │
│ updated_at      │         │ updated_at       │         │ updated_at      │    │
└─────────────────┘         └──────────────────┘         └─────────────────┘    │
                                                                                 │
                                                                                 │
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐   │
│ financial_ratios│         │  sectors         │         │ corp_code_map   │   │
├─────────────────┤         ├──────────────────┤         ├─────────────────┤   │
│ id (PK)         │<────────│ id (PK)          │         │ ticker (PK)     │<──┘
│ ticker (FK)     │         │ code             │         │ corp_code       │
│ report_date     │         │ name_kr          │         │ company_name    │
│ fiscal_year     │         │ name_en          │         │ updated_at      │
│ fiscal_quarter  │         │ parent_sector    │         └─────────────────┘
│ roe             │         │ created_at       │
│ roa             │         │ updated_at       │
│ roic            │         └──────────────────┘
│ per             │
│ pbr             │
│ debt_ratio      │
│ ... (30+ ratios)│
│ created_at      │
│ updated_at      │
└─────────────────┘
```

#### 3.1.2 테이블 정의

**1. stocks (종목 마스터)**

```sql
CREATE TABLE stocks (
    ticker VARCHAR(10) PRIMARY KEY,  -- 종목코드 (예: "005930")
    name VARCHAR(100) NOT NULL,      -- 종목명
    market VARCHAR(10) NOT NULL,     -- 시장구분 (KOSPI/KOSDAQ/KONEX)
    sector_id INT REFERENCES sectors(id),  -- 업종 코드
    listed_shares BIGINT,            -- 상장주식수
    listing_date DATE,               -- 상장일
    fiscal_month INT,                -- 결산월 (1~12)
    corp_code VARCHAR(8),            -- DART 고유번호
    is_active BOOLEAN DEFAULT TRUE,  -- 상장 여부
    delisting_date DATE,             -- 상장폐지일
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stocks_market ON stocks(market);
CREATE INDEX idx_stocks_sector ON stocks(sector_id);
CREATE INDEX idx_stocks_is_active ON stocks(is_active);
```

**2. daily_prices (일봉 시세)**

```sql
CREATE TABLE daily_prices (
    ticker VARCHAR(10) NOT NULL REFERENCES stocks(ticker),
    date DATE NOT NULL,
    open DECIMAL(12, 2) NOT NULL,
    high DECIMAL(12, 2) NOT NULL,
    low DECIMAL(12, 2) NOT NULL,
    close DECIMAL(12, 2) NOT NULL,
    volume BIGINT NOT NULL,
    trading_value BIGINT,            -- 거래대금
    market_cap BIGINT,               -- 시가총액 (종가 기준)
    adj_close DECIMAL(12, 2),        -- 수정종가
    PRIMARY KEY (ticker, date)
);

-- 파티셔닝 (년도별)
CREATE TABLE daily_prices_2024 PARTITION OF daily_prices
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');

CREATE TABLE daily_prices_2025 PARTITION OF daily_prices
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');

-- 인덱스
CREATE INDEX idx_daily_prices_date ON daily_prices(date);
CREATE INDEX idx_daily_prices_ticker_date ON daily_prices(ticker, date DESC);
```

**3. financial_statements (재무제표)**

```sql
CREATE TABLE financial_statements (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL REFERENCES stocks(ticker),
    report_date DATE NOT NULL,       -- 보고서 제출일
    fiscal_year INT NOT NULL,        -- 사업연도
    fiscal_quarter INT NOT NULL,     -- 분기 (1/2/3/4, 연간=4)
    report_type VARCHAR(10) NOT NULL,  -- '11011'(사업), '11012'(반기), '11013'(1Q), '11014'(3Q)
    fs_type VARCHAR(10) NOT NULL,    -- 'CFS'(연결), 'OFS'(개별)

    -- JSONB로 유연하게 저장 (계정과목 표준화 전)
    balance_sheet JSONB,             -- 재무상태표
    income_statement JSONB,          -- 손익계산서
    cashflow_statement JSONB,        -- 현금흐름표

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(ticker, fiscal_year, fiscal_quarter, report_type, fs_type)
);

CREATE INDEX idx_fs_ticker_year ON financial_statements(ticker, fiscal_year DESC);
CREATE INDEX idx_fs_report_date ON financial_statements(report_date DESC);
```

**4. financial_ratios (재무비율)**

```sql
CREATE TABLE financial_ratios (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL REFERENCES stocks(ticker),
    report_date DATE NOT NULL,
    fiscal_year INT NOT NULL,
    fiscal_quarter INT NOT NULL,

    -- 수익성 지표
    roe DECIMAL(10, 4),              -- 자기자본이익률
    roa DECIMAL(10, 4),              -- 총자산이익률
    roic DECIMAL(10, 4),             -- 투하자본이익률
    operating_margin DECIMAL(10, 4), -- 영업이익률
    net_margin DECIMAL(10, 4),       -- 순이익률

    -- 안정성 지표
    debt_ratio DECIMAL(10, 4),       -- 부채비율
    current_ratio DECIMAL(10, 4),    -- 유동비율
    quick_ratio DECIMAL(10, 4),      -- 당좌비율

    -- 활동성 지표
    asset_turnover DECIMAL(10, 4),   -- 자산회전율
    inventory_turnover DECIMAL(10, 4), -- 재고자산회전율

    -- 성장성 지표
    revenue_growth DECIMAL(10, 4),   -- 매출액 증가율 (YoY)
    earnings_growth DECIMAL(10, 4),  -- 순이익 증가율 (YoY)

    -- 밸류에이션 지표
    per DECIMAL(10, 4),              -- 주가수익비율
    pbr DECIMAL(10, 4),              -- 주가순자산비율
    psr DECIMAL(10, 4),              -- 주가매출액비율
    pcr DECIMAL(10, 4),              -- 주가현금흐름비율
    ev_ebitda DECIMAL(10, 4),        -- EV/EBITDA

    -- 마법의 공식 지표
    earnings_yield DECIMAL(10, 4),   -- 이익수익률 (EBIT/EV)
    return_on_capital DECIMAL(10, 4), -- 투하자본수익률

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(ticker, fiscal_year, fiscal_quarter)
);

CREATE INDEX idx_ratios_ticker_year ON financial_ratios(ticker, fiscal_year DESC);
CREATE INDEX idx_ratios_roe ON financial_ratios(roe DESC) WHERE roe IS NOT NULL;
CREATE INDEX idx_ratios_roic ON financial_ratios(roic DESC) WHERE roic IS NOT NULL;
```

**5. corp_code_map (종목코드-DART 매핑)**

```sql
CREATE TABLE corp_code_map (
    ticker VARCHAR(10) PRIMARY KEY REFERENCES stocks(ticker),
    corp_code VARCHAR(8) NOT NULL UNIQUE,  -- DART 고유번호
    company_name VARCHAR(200),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_corp_code ON corp_code_map(corp_code);
```

**6. sectors (업종 분류)**

```sql
CREATE TABLE sectors (
    id SERIAL PRIMARY KEY,
    code VARCHAR(10) UNIQUE NOT NULL,  -- 업종코드
    name_kr VARCHAR(100) NOT NULL,     -- 한글명
    name_en VARCHAR(100),              -- 영문명
    parent_sector_id INT REFERENCES sectors(id),  -- 상위 업종 (대분류/중분류/소분류)
    level INT NOT NULL,                -- 1: 대분류, 2: 중분류, 3: 소분류
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 예시 데이터
INSERT INTO sectors (code, name_kr, level) VALUES
('IT', '정보기술', 1),
('IT001', '반도체', 2),
('IT001001', '시스템반도체', 3);
```

### 3.2 데이터 정제 및 검증

#### 3.2.1 데이터 정제 파이프라인

```python
# 파일 위치: stock-portfolio-system/pipelines/data_cleaning_pipeline.py

class DataCleaningPipeline:
    """데이터 정제 파이프라인"""

    def clean_price_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """시세 데이터 정제"""
        # 1. 결측치 처리
        df = df.dropna(subset=['open', 'high', 'low', 'close', 'volume'])

        # 2. 이상치 제거
        # - 주가 < 0 제거
        df = df[df['close'] > 0]

        # - 비정상적인 변동률 (±30% 초과) 플래그
        df['price_change'] = df['close'].pct_change()
        df['is_abnormal'] = df['price_change'].abs() > 0.3

        # 3. 액면분할 조정
        # - 수정주가 계산 (배당/분할 반영)
        df = self.adjust_for_splits(df)

        # 4. 중복 제거
        df = df.drop_duplicates(subset=['ticker', 'date'], keep='last')

        return df

    def clean_financial_data(self, data: Dict) -> Dict:
        """재무 데이터 정제"""
        # 1. 계정과목 표준화
        standardized = self.standardize_accounts(data)

        # 2. 단위 통일 (백만원/억원 → 원)
        standardized = self.unify_units(standardized)

        # 3. 음수 처리 (부채는 양수로 표시)
        standardized = self.normalize_signs(standardized)

        return standardized

    def validate_financial_statement(self, bs, is_, cf) -> bool:
        """재무제표 검증"""
        # 1. 대차대조표 검증: 자산 = 부채 + 자본
        if abs(bs['total_assets'] - (bs['total_liabilities'] + bs['total_equity'])) > 1000:
            return False

        # 2. 손익계산서 검증: 매출액 > 0
        if is_['revenue'] <= 0:
            return False

        # 3. 현금흐름표 검증: 영업CF + 투자CF + 재무CF = 현금증감
        total_cf = cf['operating_cf'] + cf['investing_cf'] + cf['financing_cf']
        # 검증 로직...

        return True
```

#### 3.2.2 데이터 품질 모니터링

```python
class DataQualityMonitor:
    """데이터 품질 모니터링"""

    def check_data_completeness(self, ticker: str, start_date: str) -> Dict:
        """데이터 완전성 체크"""
        # 1. 시세 데이터 누락일 확인
        expected_dates = pd.date_range(start=start_date, end=datetime.now(), freq='B')
        actual_dates = self.db.query(f"SELECT date FROM daily_prices WHERE ticker='{ticker}'")

        missing_dates = set(expected_dates) - set(actual_dates)

        # 2. 재무 데이터 누락 확인
        expected_quarters = self.calculate_expected_quarters(start_date)
        actual_quarters = self.db.query(f"SELECT fiscal_year, fiscal_quarter FROM financial_statements WHERE ticker='{ticker}'")

        missing_quarters = set(expected_quarters) - set(actual_quarters)

        return {
            "missing_price_dates": missing_dates,
            "missing_financial_quarters": missing_quarters,
            "completeness_score": self.calculate_score(missing_dates, missing_quarters)
        }
```

### 3.3 ETL 파이프라인

```python
# 파일 위치: stock-portfolio-system/pipelines/etl_pipeline.py

from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'stock-portfolio',
    'depends_on_past': False,
    'start_date': datetime(2025, 1, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'daily_stock_data_pipeline',
    default_args=default_args,
    description='일일 주식 데이터 수집 파이프라인',
    schedule_interval='0 16 * * 1-5',  # 평일 오후 4시
    catchup=False
)

# Task 1: 종목 리스트 업데이트 (주 1회)
update_stock_list = PythonOperator(
    task_id='update_stock_list',
    python_callable=krx_collector.fetch_stock_list,
    dag=dag
)

# Task 2: 일봉 데이터 수집
fetch_daily_prices = PythonOperator(
    task_id='fetch_daily_prices',
    python_callable=kis_price_collector.fetch_all_daily_prices,
    dag=dag
)

# Task 3: 재무 데이터 업데이트 (분기별)
fetch_financial_data = PythonOperator(
    task_id='fetch_financial_data',
    python_callable=dart_collector.fetch_latest_financials,
    dag=dag
)

# Task 4: 재무비율 계산
calculate_ratios = PythonOperator(
    task_id='calculate_ratios',
    python_callable=ratio_calculator.calculate_all_ratios,
    dag=dag
)

# Task 5: 데이터 품질 체크
quality_check = PythonOperator(
    task_id='quality_check',
    python_callable=quality_monitor.run_checks,
    dag=dag
)

# Task Dependencies
update_stock_list >> fetch_daily_prices >> quality_check
fetch_financial_data >> calculate_ratios >> quality_check
```

---

## 4. 기술 스택

### 4.1 Backend

| 항목 | 기술 | 버전 | 용도 |
|------|------|------|------|
| **언어** | Python | 3.13+ | 데이터 수집/처리 |
| **프레임워크** | FastAPI | 0.109+ | REST API (선택사항) |
| **데이터베이스** | PostgreSQL | 15+ | 메인 데이터 저장소 |
| **ORM** | SQLAlchemy | 2.0+ | DB 접근 레이어 |
| **스케줄러** | Apache Airflow | 2.8+ | 배치 작업 관리 |
| **데이터 처리** | pandas | 2.1+ | 데이터 조작 |
| **HTTP 클라이언트** | httpx | 0.26+ | 비동기 API 호출 |

### 4.2 Infrastructure

| 항목 | 기술 | 용도 |
|------|------|------|
| **컨테이너** | Docker | 환경 표준화 |
| **오케스트레이션** | docker-compose | 로컬 개발 환경 |
| **캐싱** | Redis | API 응답 캐싱 (선택) |
| **로깅** | Python logging | 작업 로그 관리 |

### 4.3 Data Sources

| 데이터 | 소스 | API 키 필요 | 비용 |
|--------|------|------------|------|
| 종목 리스트 | KRX OPEN API | ❌ | 무료 |
| 시세 데이터 | KIS Open API | ✅ | 무료 |
| 재무 데이터 | DART Open API | ✅ | 무료 |

---

## 5. 개발 일정

### 5.1 Phase 1: 데이터 수집 아키텍처 (4주)

| 주차 | 작업 | 산출물 | 담당 |
|------|------|--------|------|
| **Week 1** | 환경 구축 및 API 연동 테스트 | - PostgreSQL DB 구축<br>- KRX/KIS/DART API 테스트 코드<br>- 프로젝트 구조 설계 | 개발자 |
| **Week 2** | 종목 마스터 & 시세 수집기 개발 | - KRXCollector 구현<br>- KISPriceCollector 구현<br>- daily_prices 테이블 데이터 적재 | 개발자 |
| **Week 3** | 재무 데이터 수집기 개발 | - DARTCollector 구현<br>- 재무제표 파서 구현<br>- financial_statements 테이블 적재 | 개발자 |
| **Week 4** | 재무비율 계산기 개발 | - FinancialRatioCalculator 구현<br>- 30+ 재무비율 계산 로직<br>- financial_ratios 테이블 적재 | 개발자 |

### 5.2 Phase 2: 데이터 통합 및 저장 (3주)

| 주차 | 작업 | 산출물 | 담당 |
|------|------|--------|------|
| **Week 5** | 데이터 정제 파이프라인 구축 | - DataCleaningPipeline 구현<br>- 이상치 처리 로직<br>- 수정주가 계산 | 개발자 |
| **Week 6** | ETL 자동화 (Airflow) | - DAG 작성 (일일/주간/분기별)<br>- 에러 핸들링 & 재시도<br>- 로깅 시스템 구축 | 개발자 |
| **Week 7** | 데이터 품질 관리 | - DataQualityMonitor 구현<br>- 완전성/일관성 체크<br>- 모니터링 대시보드 (선택) | 개발자 |

### 5.3 Milestone

- **Week 2 마감**: 최소 100개 종목 10년치 시세 데이터 수집 완료
- **Week 4 마감**: 최소 100개 종목 5년치 재무 데이터 수집 완료
- **Week 7 마감**: 전체 KOSPI/KOSDAQ 종목 데이터 자동 수집 시스템 가동

---

## 6. 리스크 관리

### 6.1 기술적 리스크

| 리스크 | 확률 | 영향도 | 대응 방안 |
|--------|------|--------|----------|
| **KIS API Rate Limit** | 높음 | 중 | - 백오프 알고리즘 구현<br>- KRX 시장정보로 Fallback<br>- 배치 크기 조절 (100종목/batch) |
| **DART 계정과목 불일치** | 중 | 높음 | - 계정과목 매핑 테이블 구축<br>- 정규표현식 기반 자동 매핑<br>- 수동 검증 프로세스 |
| **과거 데이터 누락** | 중 | 중 | - 여러 소스 교차 검증<br>- 네이버 금융/야후 파이낸스 보완 |
| **DB 용량 부족** | 낮음 | 높음 | - 파티셔닝 (연도별)<br>- 압축 (JSONB)<br>- 아카이빙 정책 (5년 이상 데이터) |

### 6.2 운영 리스크

| 리스크 | 확률 | 영향도 | 대응 방안 |
|--------|------|--------|----------|
| **API 키 만료/변경** | 중 | 높음 | - 환경변수 관리<br>- 키 만료 알림<br>- 자동 갱신 로직 |
| **거래 정지/상폐 종목** | 높음 | 낮음 | - is_active 플래그 관리<br>- 일일 종목 리스트 업데이트 |
| **재무제표 정정공시** | 중 | 중 | - 정정공시 감지<br>- 데이터 버전 관리 |

---

## 부록 A: 프로젝트 구조

```
stock-portfolio-system/
├── collectors/                 # 데이터 수집기
│   ├── krx_collector.py       # KRX 종목 리스트
│   ├── kis_price_collector.py # KIS 시세 데이터
│   ├── dart_collector.py      # DART 재무 데이터
│   └── base_collector.py      # 공통 베이스 클래스
│
├── calculators/               # 데이터 계산기
│   ├── financial_ratio_calculator.py
│   └── adjusted_price_calculator.py
│
├── pipelines/                 # ETL 파이프라인
│   ├── data_cleaning_pipeline.py
│   ├── etl_pipeline.py        # Airflow DAG
│   └── data_quality_monitor.py
│
├── models/                    # SQLAlchemy 모델
│   ├── stock.py
│   ├── daily_price.py
│   ├── financial_statement.py
│   └── financial_ratio.py
│
├── db/                        # 데이터베이스
│   ├── connection.py          # DB 연결 관리
│   ├── migrations/            # Alembic 마이그레이션
│   └── schema.sql             # 초기 스키마
│
├── config/                    # 설정 파일
│   ├── config.yaml            # 전역 설정
│   └── db_config.yaml         # DB 설정
│
├── scripts/                   # 유틸리티 스크립트
│   ├── init_db.py             # DB 초기화
│   ├── backfill_data.py       # 과거 데이터 백필
│   └── test_api.py            # API 연결 테스트
│
├── tests/                     # 테스트
│   ├── test_collectors.py
│   ├── test_calculators.py
│   └── test_pipelines.py
│
├── docker/                    # Docker 설정
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── airflow/
│
├── requirements.txt           # Python 의존성
├── .env.example               # 환경변수 템플릿
├── README.md
└── 개발계획서_Phase1_Phase2.md
```

---

## 부록 B: 환경 변수 템플릿

```bash
# .env.example

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stock_portfolio
DB_USER=postgres
DB_PASSWORD=your_password

# KIS API
KIS_APP_KEY=your_kis_app_key
KIS_APP_SECRET=your_kis_app_secret
KIS_ACCOUNT_TYPE=VIRTUAL  # VIRTUAL or REAL

# DART API
DART_API_KEY=your_dart_api_key

# Airflow
AIRFLOW_HOME=/path/to/airflow
AIRFLOW_UID=50000

# Logging
LOG_LEVEL=INFO
LOG_FILE_PATH=/var/log/stock-portfolio/
```

---

## 부록 C: 참고 자료

### API 문서
- KRX OPEN API: http://data.krx.co.kr/comm/bldAttendant/getBldAttendant.cmd?pageFirstCall=Y&menuId=05010201
- KIS Developers: https://apiportal.koreainvestment.com/
- DART Open API: https://opendart.fss.or.kr/intro/main.do

### 기술 문서
- PostgreSQL 파티셔닝: https://www.postgresql.org/docs/current/ddl-partitioning.html
- SQLAlchemy ORM: https://docs.sqlalchemy.org/en/20/
- Apache Airflow: https://airflow.apache.org/docs/

### 재무 분석
- 마법의 공식 (Magic Formula): Joel Greenblatt의 투자 전략
- 재무비율 정의: 한국거래소 공식 가이드

---

**문서 버전:** 1.0
**최종 수정:** 2025-10-19
**작성자:** Stock Portfolio System Team
