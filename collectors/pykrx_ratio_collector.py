"""PyKRX 기반 재무비율 수집기.

pykrx를 사용하여 KRX 공식 재무비율 데이터(PER, PBR, EPS, BPS, DIV, DPS)를 수집하고,
추가 지표(ROE, 배당성향 등)를 계산합니다.

Features:
- PER, PBR, EPS, BPS, DIV, DPS 수집 (pykrx)
- ROE, 배당성향 자동 계산
- 기간별 일별/월별 데이터 수집
- 데이터베이스 자동 저장
"""

import time
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pykrx import stock
import pandas as pd
from db.connection import SessionLocal
from models import Stock, FinancialRatio
from sqlalchemy import and_
from loguru import logger

# Configure logger
logger.add(
    "logs/pykrx_ratio_collector_{time}.log",
    rotation="1 day",
    retention="30 days",
    level="INFO"
)


class PyKRXRatioCollector:
    """pykrx를 통한 재무비율 데이터 수집 클래스.

    Features:
    - KRX 공식 재무비율 수집 (PER, PBR, EPS, BPS, DIV, DPS)
    - 추가 지표 계산 (ROE, 배당성향)
    - 일별/월별 데이터 수집
    - 자동 데이터베이스 저장
    """

    def __init__(self, db_session=None):
        """Initialize PyKRXRatioCollector.

        Args:
            db_session: SQLAlchemy session. If None, creates new session.
        """
        self.db = db_session or SessionLocal()
        self._own_session = db_session is None

        logger.info("PyKRXRatioCollector initialized")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def close(self):
        """Close database session if owned."""
        if self._own_session and self.db:
            self.db.close()
            logger.info("Database session closed")

    def collect_daily_ratios(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """특정 종목의 일별 재무비율 수집.

        Args:
            ticker: 종목코드 (예: "005930")
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)

        Returns:
            DataFrame with columns: date, BPS, PER, PBR, EPS, DIV, DPS, ROE, payout_ratio
        """
        try:
            logger.info(f"Collecting ratios for {ticker}: {start_date} ~ {end_date}")

            # pykrx로 데이터 수집
            df = stock.get_market_fundamental(start_date, end_date, ticker)

            if df is None or df.empty:
                logger.warning(f"No data for {ticker}")
                return pd.DataFrame()

            # 인덱스를 컬럼으로 변환
            df = df.reset_index()
            df.rename(columns={'날짜': 'date'}, inplace=True)

            # 추가 지표 계산
            df = self._calculate_additional_ratios(df)

            logger.info(f"Collected {len(df)} records for {ticker}")
            return df

        except Exception as e:
            logger.error(f"Error collecting ratios for {ticker}: {e}")
            return pd.DataFrame()

    def collect_all_stocks_ratios(
        self,
        date: str,
        market: str = "ALL"
    ) -> pd.DataFrame:
        """특정 날짜 전체 종목의 재무비율 수집.

        Args:
            date: 날짜 (YYYYMMDD)
            market: 시장 구분 (KOSPI/KOSDAQ/KONEX/ALL)

        Returns:
            DataFrame with all stocks' ratios
        """
        try:
            logger.info(f"Collecting all stocks ratios for {date} ({market})")

            # pykrx로 데이터 수집
            df = stock.get_market_fundamental(date, market=market)

            if df is None or df.empty:
                logger.warning(f"No data for {date}")
                return pd.DataFrame()

            # 인덱스(티커)를 컬럼으로 변환
            df = df.reset_index()
            df.rename(columns={'티커': 'ticker'}, inplace=True)

            # 날짜 추가
            df['date'] = pd.to_datetime(date)

            # 추가 지표 계산
            df = self._calculate_additional_ratios(df)

            logger.info(f"Collected {len(df)} stocks for {date}")
            return df

        except Exception as e:
            logger.error(f"Error collecting ratios for {date}: {e}")
            return pd.DataFrame()

    def _calculate_additional_ratios(self, df: pd.DataFrame) -> pd.DataFrame:
        """추가 재무비율 계산.

        Args:
            df: pykrx에서 수집한 DataFrame

        Returns:
            추가 지표가 포함된 DataFrame
        """
        # ROE (자기자본이익률) = EPS / BPS × 100
        df['ROE'] = (df['EPS'] / df['BPS'] * 100).round(2)

        # 배당성향 (Payout Ratio) = DPS / EPS × 100
        df['payout_ratio'] = (df['DPS'] / df['EPS'] * 100).round(2)

        # 무한대, NaN 처리
        df.replace([float('inf'), -float('inf')], None, inplace=True)
        df.fillna(0, inplace=True)

        return df

    def save_to_database(
        self,
        ticker: str,
        ratios_df: pd.DataFrame
    ) -> int:
        """재무비율 데이터를 데이터베이스에 저장.

        Args:
            ticker: 종목코드
            ratios_df: 재무비율 DataFrame

        Returns:
            저장된 레코드 수
        """
        if ratios_df.empty:
            logger.warning(f"No data to save for {ticker}")
            return 0

        try:
            # 종목 조회
            stock_obj = self.db.query(Stock).filter(Stock.ticker == ticker).first()

            if not stock_obj:
                logger.warning(f"Stock {ticker} not found in database")
                return 0

            saved_count = 0

            for _, row in ratios_df.iterrows():
                # 날짜 변환
                if isinstance(row['date'], str):
                    ratio_date = datetime.strptime(row['date'], '%Y%m%d').date()
                else:
                    ratio_date = row['date'].date() if hasattr(row['date'], 'date') else row['date']

                # 기존 데이터 확인
                existing = self.db.query(FinancialRatio).filter(
                    and_(
                        FinancialRatio.stock_id == stock_obj.id,
                        FinancialRatio.date == ratio_date
                    )
                ).first()

                if existing:
                    # 업데이트
                    existing.bps = float(row['BPS']) if row['BPS'] else None
                    existing.per = float(row['PER']) if row['PER'] else None
                    existing.pbr = float(row['PBR']) if row['PBR'] else None
                    existing.eps = float(row['EPS']) if row['EPS'] else None
                    existing.div = float(row['DIV']) if row['DIV'] else None
                    existing.dps = float(row['DPS']) if row['DPS'] else None
                    existing.roe = float(row['ROE']) if row['ROE'] else None
                    existing.payout_ratio = float(row['payout_ratio']) if row['payout_ratio'] else None
                else:
                    # 새 레코드 생성
                    ratio = FinancialRatio(
                        stock_id=stock_obj.id,
                        date=ratio_date,
                        bps=float(row['BPS']) if row['BPS'] else None,
                        per=float(row['PER']) if row['PER'] else None,
                        pbr=float(row['PBR']) if row['PBR'] else None,
                        eps=float(row['EPS']) if row['EPS'] else None,
                        div=float(row['DIV']) if row['DIV'] else None,
                        dps=float(row['DPS']) if row['DPS'] else None,
                        roe=float(row['ROE']) if row['ROE'] else None,
                        payout_ratio=float(row['payout_ratio']) if row['payout_ratio'] else None
                    )
                    self.db.add(ratio)

                saved_count += 1

            self.db.commit()
            logger.info(f"Saved {saved_count} ratio records for {ticker}")
            return saved_count

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving ratios for {ticker}: {e}")
            return 0

    def collect_and_save(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> int:
        """재무비율 수집 및 저장 (통합 메서드).

        Args:
            ticker: 종목코드
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)

        Returns:
            저장된 레코드 수
        """
        # 수집
        ratios_df = self.collect_daily_ratios(ticker, start_date, end_date)

        if ratios_df.empty:
            return 0

        # 저장
        return self.save_to_database(ticker, ratios_df)

    def get_missing_dates(
        self,
        ticker: str,
        start_date: date,
        end_date: date
    ) -> List[date]:
        """누락된 날짜 확인.

        Args:
            ticker: 종목코드
            start_date: 시작일
            end_date: 종료일

        Returns:
            누락된 날짜 리스트
        """
        try:
            # 종목 조회
            stock_obj = self.db.query(Stock).filter(Stock.ticker == ticker).first()

            if not stock_obj:
                logger.warning(f"Stock {ticker} not found")
                return []

            # 기존 데이터 날짜 조회
            existing_dates = self.db.query(FinancialRatio.date).filter(
                and_(
                    FinancialRatio.stock_id == stock_obj.id,
                    FinancialRatio.date >= start_date,
                    FinancialRatio.date <= end_date
                )
            ).all()

            existing_dates = {d[0] for d in existing_dates}

            # 전체 날짜 범위 생성 (영업일만)
            all_dates = pd.date_range(start=start_date, end=end_date, freq='B').date

            # 누락된 날짜
            missing_dates = [d for d in all_dates if d not in existing_dates]

            logger.info(f"{ticker}: {len(missing_dates)} missing dates found")
            return missing_dates

        except Exception as e:
            logger.error(f"Error checking missing dates for {ticker}: {e}")
            return []


# 테스트 코드
if __name__ == "__main__":
    # 사용 예시
    with PyKRXRatioCollector() as collector:
        # 삼성전자 최근 1개월 재무비율 수집
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")

        saved = collector.collect_and_save("005930", start_date, end_date)
        print(f"Saved {saved} records")
