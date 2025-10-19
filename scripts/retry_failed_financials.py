#!/usr/bin/env python3
"""실패한 종목 재무제표 재수집 스크립트.

순차 실행으로 API Rate Limit 회피.
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from collectors.dart_collector import DARTCollector
from db.connection import SessionLocal
from models import Stock

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class RetryCollector:
    """실패 종목 재수집 클래스."""

    def __init__(self, years: List[int], rate_limit_delay: float = 0.3):
        """
        Args:
            years: 수집할 연도 목록
            rate_limit_delay: API 호출 간 대기 시간 (초)
        """
        self.years = years
        self.rate_limit_delay = rate_limit_delay
        self.collector = DARTCollector()
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'no_corp_code': 0,
            'no_data': 0,
            'api_error': 0,
            'start_time': None,
            'end_time': None,
        }

    def load_failed_stocks(self) -> List[Dict]:
        """실패 종목 목록 로드."""
        failed_file = project_root / 'data' / 'retry' / 'failed_stocks.json'

        if not failed_file.exists():
            logger.error(f"실패 종목 파일이 없습니다: {failed_file}")
            return []

        with open(failed_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        stocks = data.get('stocks', [])
        logger.info(f"실패 종목 로드: {len(stocks)}개")
        return stocks

    def get_corp_code(self, ticker: str) -> str:
        """DB에서 corp_code 조회."""
        db = SessionLocal()
        try:
            stock = db.query(Stock).filter(Stock.ticker == ticker).first()
            if stock and hasattr(stock, 'corp_code'):
                return stock.corp_code
            return None
        finally:
            db.close()

    def collect_stock(self, stock_info: Dict) -> bool:
        """단일 종목 재무제표 수집."""
        ticker = stock_info['ticker']
        name = stock_info['name']

        # corp_code 조회
        corp_code = self.get_corp_code(ticker)
        if not corp_code:
            logger.warning(f"  ⚠️  {ticker} ({name}): corp_code 없음")
            self.stats['no_corp_code'] += 1
            return False

        success_count = 0

        # 각 연도별 수집
        for year in self.years:
            try:
                # Rate limiting
                time.sleep(self.rate_limit_delay)

                result = self.collector.collect_and_save(
                    ticker=ticker,
                    years=[year]
                )

                if result['success']:
                    success_count += result.get('saved_count', 0)

            except Exception as e:
                logger.debug(f"  {ticker} ({year}): {str(e)}")
                self.stats['api_error'] += 1
                continue

        # 결과 판정
        if success_count > 0:
            logger.info(f"  ✅ {ticker} ({name}): {success_count}건 수집")
            self.stats['success'] += 1
            return True
        else:
            logger.debug(f"  ❌ {ticker} ({name}): 데이터 없음")
            self.stats['no_data'] += 1
            return False

    def collect_all(self):
        """전체 실패 종목 재수집."""
        failed_stocks = self.load_failed_stocks()

        if not failed_stocks:
            logger.error("수집할 종목이 없습니다.")
            return

        self.stats['total'] = len(failed_stocks)
        self.stats['start_time'] = datetime.now()

        logger.info("=" * 80)
        logger.info(f"재수집 시작 - 총 {len(failed_stocks)}개 종목")
        logger.info(f"수집 연도: {self.years}")
        logger.info(f"Rate Limit: {self.rate_limit_delay}초/종목")
        logger.info("=" * 80)

        # 순차 수집
        for i, stock_info in enumerate(failed_stocks, 1):
            ticker = stock_info['ticker']
            name = stock_info['name']

            logger.info(f"[{i}/{len(failed_stocks)}] Processing {ticker} ({name})...")

            self.collect_stock(stock_info)

            # 진행 상황 출력 (매 100개)
            if i % 100 == 0:
                elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
                rate = i / elapsed if elapsed > 0 else 0
                remaining = (len(failed_stocks) - i) / rate if rate > 0 else 0

                logger.info("")
                logger.info(f"진행 상황: {i}/{len(failed_stocks)} ({i/len(failed_stocks)*100:.1f}%)")
                logger.info(f"성공: {self.stats['success']} | 실패: {i - self.stats['success']}")
                logger.info(f"처리 속도: {rate:.1f}개/초 | 남은 시간: {int(remaining)}초")
                logger.info("")

        self.stats['end_time'] = datetime.now()
        self.stats['failed'] = self.stats['total'] - self.stats['success']

        self.print_summary()
        self.save_retry_report()

    def print_summary(self):
        """최종 결과 출력."""
        elapsed = (self.stats['end_time'] - self.stats['start_time']).total_seconds()

        logger.info("")
        logger.info("=" * 80)
        logger.info("재수집 완료")
        logger.info("=" * 80)
        logger.info(f"총 종목 수: {self.stats['total']}")
        logger.info(f"성공: {self.stats['success']}")
        logger.info(f"실패: {self.stats['failed']}")
        logger.info("")
        logger.info(f"실패 원인:")
        logger.info(f"  - corp_code 없음: {self.stats['no_corp_code']}개")
        logger.info(f"  - 데이터 없음: {self.stats['no_data']}개")
        logger.info(f"  - API 오류: {self.stats['api_error']}개")
        logger.info("")
        logger.info(f"소요 시간: {int(elapsed)}초 ({elapsed/60:.1f}분)")
        logger.info(f"성공률: {self.stats['success']/self.stats['total']*100:.1f}%")
        logger.info("=" * 80)

    def save_retry_report(self):
        """재수집 리포트 저장."""
        report_dir = project_root / 'data' / 'retry'
        report_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = report_dir / f'retry_report_{timestamp}.json'

        report = {
            'timestamp': timestamp,
            'stats': {
                'total': self.stats['total'],
                'success': self.stats['success'],
                'failed': self.stats['failed'],
                'success_rate': f"{self.stats['success']/self.stats['total']*100:.1f}%",
            },
            'failure_reasons': {
                'no_corp_code': self.stats['no_corp_code'],
                'no_data': self.stats['no_data'],
                'api_error': self.stats['api_error'],
            },
            'execution_time': {
                'start': self.stats['start_time'].isoformat(),
                'end': self.stats['end_time'].isoformat(),
                'duration_seconds': int((self.stats['end_time'] - self.stats['start_time']).total_seconds()),
            }
        }

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"리포트 저장: {report_file}")


def main():
    """메인 실행 함수."""
    import argparse

    parser = argparse.ArgumentParser(description='실패 종목 재무제표 재수집')
    parser.add_argument(
        '--years',
        nargs='+',
        type=int,
        default=[2024, 2023],
        help='수집할 연도 (기본값: 2024 2023)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=0.3,
        help='API 호출 간 대기 시간 (초, 기본값: 0.3)'
    )

    args = parser.parse_args()

    collector = RetryCollector(
        years=args.years,
        rate_limit_delay=args.delay
    )

    try:
        collector.collect_all()
    except KeyboardInterrupt:
        logger.warning("\n\n사용자에 의해 중단되었습니다.")
        collector.print_summary()
        sys.exit(1)


if __name__ == '__main__':
    main()
