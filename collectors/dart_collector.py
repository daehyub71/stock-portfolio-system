"""DART (전자공시) 재무데이터 수집기.

DART OpenAPI를 사용하여 기업의 재무제표 데이터를 수집합니다.

Features:
- 사업보고서 (annual) 재무제표
- 분기보고서 (quarterly) 재무제표
- JSONB 형식으로 유연한 데이터 저장
- corp_code ↔ ticker 매핑
"""

import os
import time
import httpx
from datetime import datetime, date
from typing import List, Dict, Optional, Any
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from models import Stock, CorpCodeMap, FinancialStatement, StatementType
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class DARTCollector:
    """DART API를 통한 재무데이터 수집 클래스.

    Features:
    - 재무제표 조회 (재무상태표, 손익계산서, 현금흐름표)
    - JSONB 형식으로 저장
    - Rate limiting (초당 5건 권장)
    """

    DART_API_KEY = os.getenv("DART_API_KEY")
    BASE_URL = "https://opendart.fss.or.kr/api"

    # Rate limiting: 권장 초당 5건
    REQUEST_INTERVAL = 0.2  # 200ms

    def __init__(self, db_session=None):
        """Initialize DARTCollector.

        Args:
            db_session: SQLAlchemy session. If None, creates new session.
        """
        self.db = db_session or SessionLocal()
        self._own_session = db_session is None
        self._last_request_time = 0

        # Configure logger
        logger.add(
            "logs/dart_collector_{time}.log",
            rotation="1 day",
            retention="30 days",
            level="INFO"
        )

        if not self.DART_API_KEY:
            logger.warning("DART_API_KEY not found in environment variables")

        logger.info("DARTCollector initialized")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._own_session:
            self.db.close()

    def _rate_limit(self):
        """Rate limiting: Ensure we don't exceed recommended limits."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_INTERVAL:
            time.sleep(self.REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def get_corp_code(self, ticker: str) -> Optional[str]:
        """ticker로 corp_code 조회.

        Args:
            ticker: 종목코드 (e.g., "005930")

        Returns:
            corp_code or None if not found
        """
        corp_map = self.db.query(CorpCodeMap).filter_by(ticker=ticker).first()

        if corp_map:
            return corp_map.corp_code

        logger.warning(f"Corp code not found for ticker: {ticker}")
        return None

    def fetch_financial_statement(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = "11011"  # 11011: 사업보고서, 11012: 반기보고서, 11013: 1분기, 11014: 3분기
    ) -> Optional[Dict[str, Any]]:
        """재무제표 조회.

        Args:
            corp_code: 기업 고유번호 (8자리)
            bsns_year: 사업연도 (YYYY)
            reprt_code: 보고서 코드
                - 11011: 사업보고서 (annual)
                - 11012: 반기보고서
                - 11013: 1분기보고서
                - 11014: 3분기보고서

        Returns:
            Financial statement dictionary or None if failed
        """
        self._rate_limit()

        url = f"{self.BASE_URL}/fnlttSinglAcntAll.json"

        params = {
            "crtfc_key": self.DART_API_KEY,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": "CFS"  # CFS: 연결재무제표, OFS: 개별재무제표
        }

        try:
            logger.info(f"Fetching financial statement: {corp_code}, {bsns_year}, {reprt_code}")

            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, params=params)
                response.raise_for_status()

                result = response.json()

                # Check API response status
                if result.get("status") == "000":  # Success
                    data = result.get("list", [])
                    logger.info(f"Fetched {len(data)} financial items for {corp_code}")
                    return self._parse_financial_data(data)
                else:
                    error_msg = result.get("message", "Unknown error")
                    logger.error(f"DART API error for {corp_code}: {error_msg}")
                    return None

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching financial statement: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching financial statement: {e}")
            return None

    def _parse_financial_data(self, data: List[Dict]) -> Dict[str, Any]:
        """Parse DART financial statement response into structured format.

        Args:
            data: List of financial items from DART API

        Returns:
            Structured financial statement dictionary
        """
        financial_statement = {
            "balance_sheet": {
                "assets": {
                    "current": {},
                    "non_current": {}
                },
                "liabilities": {
                    "current": {},
                    "non_current": {}
                },
                "equity": {}
            },
            "income_statement": {
                "revenue": {},
                "expenses": {},
                "profit": {}
            },
            "cash_flow": {
                "operating": {},
                "investing": {},
                "financing": {}
            },
            "raw_data": []  # Store all items for reference
        }

        for item in data:
            account_nm = item.get("account_nm", "")  # 계정명
            sj_div = item.get("sj_div", "")  # 재무제표 구분
            thstrm_amount = item.get("thstrm_amount", "")  # 당기금액

            # Store raw data
            financial_statement["raw_data"].append({
                "account_nm": account_nm,
                "sj_div": sj_div,
                "thstrm_amount": thstrm_amount,
                "frmtrm_amount": item.get("frmtrm_amount", ""),  # 전기금액
                "bfefrmtrm_amount": item.get("bfefrmtrm_amount", "")  # 전전기금액
            })

            # Parse by statement type
            try:
                amount = float(thstrm_amount.replace(",", "")) if thstrm_amount else 0
            except (ValueError, AttributeError):
                amount = 0

            # 재무상태표 (BS: Balance Sheet)
            if sj_div == "BS":
                if "자산" in account_nm:
                    if "유동자산" in account_nm:
                        financial_statement["balance_sheet"]["assets"]["current"][account_nm] = amount
                    elif "비유동자산" in account_nm:
                        financial_statement["balance_sheet"]["assets"]["non_current"][account_nm] = amount
                elif "부채" in account_nm:
                    if "유동부채" in account_nm:
                        financial_statement["balance_sheet"]["liabilities"]["current"][account_nm] = amount
                    elif "비유동부채" in account_nm:
                        financial_statement["balance_sheet"]["liabilities"]["non_current"][account_nm] = amount
                elif "자본" in account_nm:
                    financial_statement["balance_sheet"]["equity"][account_nm] = amount

            # 손익계산서 (IS: Income Statement, CIS: Consolidated Income Statement)
            elif sj_div in ("IS", "CIS"):
                if "매출" in account_nm or "수익" in account_nm:
                    financial_statement["income_statement"]["revenue"][account_nm] = amount
                elif "비용" in account_nm or "원가" in account_nm:
                    financial_statement["income_statement"]["expenses"][account_nm] = amount
                elif "이익" in account_nm or "손실" in account_nm:
                    financial_statement["income_statement"]["profit"][account_nm] = amount

            # 현금흐름표 (CF: Cash Flow)
            elif sj_div == "CF":
                if "영업활동" in account_nm:
                    financial_statement["cash_flow"]["operating"][account_nm] = amount
                elif "투자활동" in account_nm:
                    financial_statement["cash_flow"]["investing"][account_nm] = amount
                elif "재무활동" in account_nm:
                    financial_statement["cash_flow"]["financing"][account_nm] = amount

        return financial_statement

    def save_financial_statement(
        self,
        ticker: str,
        financial_data: Dict[str, Any],
        report_date: date,
        statement_type: StatementType,
        fiscal_year: int,
        fiscal_quarter: Optional[int] = None
    ) -> bool:
        """재무제표를 데이터베이스에 저장.

        Args:
            ticker: 종목코드
            financial_data: Parsed financial statement data
            report_date: 보고서 기준일
            statement_type: 보고서 유형 (annual/quarterly)
            fiscal_year: 회계연도
            fiscal_quarter: 회계분기 (quarterly인 경우)

        Returns:
            True if saved successfully
        """
        try:
            # Get stock_id
            stock = self.db.query(Stock).filter_by(ticker=ticker).first()
            if not stock:
                logger.warning(f"Stock not found: {ticker}")
                return False

            # Check if already exists
            existing = self.db.query(FinancialStatement).filter_by(
                stock_id=stock.id,
                report_date=report_date,
                statement_type=statement_type
            ).first()

            if existing:
                # Update existing record
                existing.balance_sheet = financial_data.get("balance_sheet")
                existing.income_statement = financial_data.get("income_statement")
                existing.cash_flow = financial_data.get("cash_flow")
                existing.fiscal_year = fiscal_year
                existing.fiscal_quarter = fiscal_quarter
                logger.info(f"Updated financial statement for {ticker}")
            else:
                # Create new record
                new_statement = FinancialStatement(
                    stock_id=stock.id,
                    report_date=report_date,
                    statement_type=statement_type,
                    fiscal_year=fiscal_year,
                    fiscal_quarter=fiscal_quarter,
                    balance_sheet=financial_data.get("balance_sheet"),
                    income_statement=financial_data.get("income_statement"),
                    cash_flow=financial_data.get("cash_flow")
                )
                self.db.add(new_statement)
                logger.info(f"Saved new financial statement for {ticker}")

            self.db.commit()
            return True

        except Exception as e:
            logger.error(f"Error saving financial statement for {ticker}: {e}")
            self.db.rollback()
            return False

    def collect_and_save(
        self,
        ticker: str,
        years: List[int] = [2024, 2023, 2022]
    ) -> Dict[str, int]:
        """종목의 재무제표를 수집하고 저장 (원스텝).

        Args:
            ticker: 종목코드
            years: 수집할 연도 리스트

        Returns:
            Dictionary with collection statistics
        """
        logger.info(f"Starting financial statement collection for {ticker}")

        # Get corp_code
        corp_code = self.get_corp_code(ticker)
        if not corp_code:
            logger.error(f"Corp code not found for {ticker}")
            return {"fetched": 0, "saved": 0, "ticker": ticker}

        fetched_count = 0
        saved_count = 0

        for year in years:
            try:
                # Fetch annual report (사업보고서)
                financial_data = self.fetch_financial_statement(
                    corp_code=corp_code,
                    bsns_year=str(year),
                    reprt_code="11011"  # 사업보고서
                )

                if financial_data and financial_data.get("raw_data"):
                    fetched_count += 1

                    # Save to database
                    report_date = date(year, 12, 31)  # Assume fiscal year end
                    success = self.save_financial_statement(
                        ticker=ticker,
                        financial_data=financial_data,
                        report_date=report_date,
                        statement_type=StatementType.ANNUAL,
                        fiscal_year=year
                    )

                    if success:
                        saved_count += 1

            except Exception as e:
                logger.error(f"Error collecting {ticker} for year {year}: {e}")
                continue

        result = {
            "fetched": fetched_count,
            "saved": saved_count,
            "ticker": ticker
        }

        logger.info(f"Collection complete for {ticker}: {result}")
        return result
