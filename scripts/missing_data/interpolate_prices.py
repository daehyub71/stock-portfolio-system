"""시세 데이터 결측치 보간 스크립트.

시세 데이터의 결측치를 선형 보간(linear interpolation) 또는
forward fill 방식으로 처리합니다.

Usage:
    python scripts/missing_data/interpolate_prices.py --ticker 005930
    python scripts/missing_data/interpolate_prices.py --ticker 005930 --method linear
    python scripts/missing_data/interpolate_prices.py --ticker 005930 --method ffill
    python scripts/missing_data/interpolate_prices.py --all-stocks --method linear --dry-run
    python scripts/missing_data/interpolate_prices.py --all-stocks --method ffill --min-gap 5
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from models import Stock, DailyPrice
from sqlalchemy import and_, func, desc, asc


class PriceInterpolator:
    """시세 데이터 보간 클래스."""

    def __init__(self, dry_run: bool = False):
        """초기화.

        Args:
            dry_run: True면 실제 DB 업데이트 없이 시뮬레이션만 수행
        """
        self.db = SessionLocal()
        self.dry_run = dry_run
        self.stats = {
            'total_stocks': 0,
            'stocks_processed': 0,
            'gaps_found': 0,
            'gaps_filled': 0,
            'records_inserted': 0,
            'errors': []
        }

    def close(self):
        """데이터베이스 연결 종료."""
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def find_gaps(
        self,
        ticker: str,
        min_gap_days: int = 2
    ) -> List[Tuple[datetime.date, datetime.date, int]]:
        """특정 종목의 시세 데이터 gap 찾기.

        Args:
            ticker: 종목 코드
            min_gap_days: 최소 gap 일수 (이 값 이상만 반환)

        Returns:
            (시작일, 종료일, gap 일수) 튜플 리스트
        """
        stock = self.db.query(Stock).filter(Stock.ticker == ticker).first()
        if not stock:
            return []

        # 시세 데이터 날짜 순으로 조회
        prices = (
            self.db.query(DailyPrice.date)
            .filter(DailyPrice.stock_id == stock.id)
            .order_by(DailyPrice.date)
            .all()
        )

        if len(prices) < 2:
            return []

        gaps = []
        for i in range(len(prices) - 1):
            prev_date = prices[i].date
            curr_date = prices[i + 1].date
            gap_days = (curr_date - prev_date).days - 1

            if gap_days >= min_gap_days:
                gaps.append((prev_date, curr_date, gap_days))

        return gaps

    def linear_interpolate(
        self,
        ticker: str,
        start_date: datetime.date,
        end_date: datetime.date
    ) -> List[DailyPrice]:
        """선형 보간으로 결측치 채우기.

        Args:
            ticker: 종목 코드
            start_date: 시작일 (이 날짜의 데이터는 존재)
            end_date: 종료일 (이 날짜의 데이터는 존재)

        Returns:
            보간된 DailyPrice 객체 리스트
        """
        stock = self.db.query(Stock).filter(Stock.ticker == ticker).first()
        if not stock:
            return []

        # 시작일과 종료일의 시세 데이터 가져오기
        start_price = (
            self.db.query(DailyPrice)
            .filter(
                DailyPrice.stock_id == stock.id,
                DailyPrice.date == start_date
            )
            .first()
        )

        end_price = (
            self.db.query(DailyPrice)
            .filter(
                DailyPrice.stock_id == stock.id,
                DailyPrice.date == end_date
            )
            .first()
        )

        if not start_price or not end_price:
            return []

        # 보간할 날짜 리스트 생성 (주말 제외)
        interpolated = []
        current_date = start_date + timedelta(days=1)
        total_days = (end_date - start_date).days

        if total_days <= 1:
            return []

        while current_date < end_date:
            # 주말 제외 (토요일=5, 일요일=6)
            if current_date.weekday() < 5:
                # 선형 보간 비율 계산
                days_from_start = (current_date - start_date).days
                ratio = days_from_start / total_days

                # OHLCV 선형 보간
                interpolated_price = DailyPrice(
                    stock_id=stock.id,
                    date=current_date,
                    open_price=self._interpolate_value(
                        start_price.open_price,
                        end_price.open_price,
                        ratio
                    ),
                    high_price=self._interpolate_value(
                        start_price.high_price,
                        end_price.high_price,
                        ratio
                    ),
                    low_price=self._interpolate_value(
                        start_price.low_price,
                        end_price.low_price,
                        ratio
                    ),
                    close_price=self._interpolate_value(
                        start_price.close_price,
                        end_price.close_price,
                        ratio
                    ),
                    volume=int(
                        float(start_price.volume) * (1 - ratio) +
                        float(end_price.volume) * ratio
                    )
                )

                interpolated.append(interpolated_price)

            current_date += timedelta(days=1)

        return interpolated

    def _interpolate_value(
        self,
        start_value: Decimal,
        end_value: Decimal,
        ratio: float
    ) -> Decimal:
        """선형 보간 계산.

        Args:
            start_value: 시작 값
            end_value: 종료 값
            ratio: 보간 비율 (0~1)

        Returns:
            보간된 값
        """
        result = float(start_value) * (1 - ratio) + float(end_value) * ratio
        return Decimal(str(round(result, 2)))

    def forward_fill(
        self,
        ticker: str,
        start_date: datetime.date,
        end_date: datetime.date
    ) -> List[DailyPrice]:
        """Forward fill 방식으로 결측치 채우기.

        Args:
            ticker: 종목 코드
            start_date: 시작일 (이 날짜의 데이터는 존재)
            end_date: 종료일 (이 날짜의 데이터는 존재)

        Returns:
            forward fill된 DailyPrice 객체 리스트
        """
        stock = self.db.query(Stock).filter(Stock.ticker == ticker).first()
        if not stock:
            return []

        # 시작일의 시세 데이터 가져오기
        start_price = (
            self.db.query(DailyPrice)
            .filter(
                DailyPrice.stock_id == stock.id,
                DailyPrice.date == start_date
            )
            .first()
        )

        if not start_price:
            return []

        # forward fill: 이전 값 그대로 사용
        filled = []
        current_date = start_date + timedelta(days=1)

        while current_date < end_date:
            # 주말 제외
            if current_date.weekday() < 5:
                filled_price = DailyPrice(
                    stock_id=stock.id,
                    date=current_date,
                    open_price=start_price.close_price,  # 이전 종가로 시작
                    high_price=start_price.close_price,
                    low_price=start_price.close_price,
                    close_price=start_price.close_price,
                    volume=0  # 거래량은 0으로
                )

                filled.append(filled_price)

            current_date += timedelta(days=1)

        return filled

    def interpolate_stock(
        self,
        ticker: str,
        method: str = 'linear',
        min_gap_days: int = 2
    ) -> Dict[str, Any]:
        """특정 종목의 시세 데이터 보간.

        Args:
            ticker: 종목 코드
            method: 보간 방법 ('linear' 또는 'ffill')
            min_gap_days: 최소 gap 일수 (이 값 이상만 보간)

        Returns:
            보간 결과 딕셔너리
        """
        print(f"\n종목 {ticker} 보간 중 (방법: {method})...")

        # gap 찾기
        gaps = self.find_gaps(ticker, min_gap_days)

        if not gaps:
            print(f"  gap 없음")
            return {
                'ticker': ticker,
                'gaps_found': 0,
                'gaps_filled': 0,
                'records_inserted': 0
            }

        print(f"  {len(gaps)}개 gap 발견")

        gaps_filled = 0
        records_inserted = 0

        for start_date, end_date, gap_days in gaps:
            print(f"    gap: {start_date} → {end_date} ({gap_days}일)")

            # 보간 방법 선택
            if method == 'linear':
                interpolated = self.linear_interpolate(ticker, start_date, end_date)
            elif method == 'ffill':
                interpolated = self.forward_fill(ticker, start_date, end_date)
            else:
                raise ValueError(f"Unknown method: {method}")

            if interpolated:
                if not self.dry_run:
                    # DB에 삽입 (bulk insert)
                    try:
                        self.db.bulk_save_objects(interpolated)
                        self.db.commit()
                        print(f"      ✅ {len(interpolated)}건 삽입")
                    except Exception as e:
                        self.db.rollback()
                        print(f"      ❌ 에러: {e}")
                        self.stats['errors'].append({
                            'ticker': ticker,
                            'gap': (start_date, end_date),
                            'error': str(e)
                        })
                        continue
                else:
                    print(f"      (dry-run) {len(interpolated)}건 삽입 예정")

                gaps_filled += 1
                records_inserted += len(interpolated)

        result = {
            'ticker': ticker,
            'gaps_found': len(gaps),
            'gaps_filled': gaps_filled,
            'records_inserted': records_inserted
        }

        self.stats['stocks_processed'] += 1
        self.stats['gaps_found'] += len(gaps)
        self.stats['gaps_filled'] += gaps_filled
        self.stats['records_inserted'] += records_inserted

        return result

    def interpolate_all_stocks(
        self,
        method: str = 'linear',
        min_gap_days: int = 2,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """전체 종목의 시세 데이터 보간.

        Args:
            method: 보간 방법 ('linear' 또는 'ffill')
            min_gap_days: 최소 gap 일수
            limit: 처리할 최대 종목 수 (None이면 전체)

        Returns:
            전체 보간 결과 통계
        """
        print(f"\n전체 종목 시세 보간 시작 (방법: {method}, 최소 gap: {min_gap_days}일)")
        if self.dry_run:
            print("⚠️  DRY RUN 모드: 실제 DB 업데이트 없음")

        # 시세 데이터가 있는 종목 조회
        stocks = (
            self.db.query(Stock.ticker)
            .join(DailyPrice, Stock.id == DailyPrice.stock_id)
            .filter(Stock.is_active == True)
            .distinct()
            .limit(limit) if limit else
            self.db.query(Stock.ticker)
            .join(DailyPrice, Stock.id == DailyPrice.stock_id)
            .filter(Stock.is_active == True)
            .distinct()
        ).all()

        self.stats['total_stocks'] = len(stocks)

        print(f"처리 대상: {len(stocks)}개 종목")

        for i, (ticker,) in enumerate(stocks, 1):
            if i % 100 == 0:
                print(f"\n진행: {i}/{len(stocks)} ({i/len(stocks)*100:.1f}%)")

            try:
                self.interpolate_stock(ticker, method, min_gap_days)
            except Exception as e:
                print(f"  ❌ {ticker} 오류: {e}")
                self.stats['errors'].append({
                    'ticker': ticker,
                    'error': str(e)
                })

        return self.stats

    def print_summary(self):
        """보간 결과 요약 출력."""
        print("\n" + "=" * 80)
        print("📊 시세 데이터 보간 요약")
        print("=" * 80)

        print(f"\n[전체 통계]")
        print(f"처리 대상 종목:      {self.stats['total_stocks']:,}개")
        print(f"처리 완료 종목:      {self.stats['stocks_processed']:,}개")
        print(f"발견된 gap:          {self.stats['gaps_found']:,}개")
        print(f"보간 완료 gap:       {self.stats['gaps_filled']:,}개")
        print(f"삽입된 레코드:       {self.stats['records_inserted']:,}건")

        if self.stats['errors']:
            print(f"\n[오류]")
            print(f"오류 발생:           {len(self.stats['errors'])}건")
            for i, error in enumerate(self.stats['errors'][:10], 1):
                print(f"  {i}. {error['ticker']}: {error['error']}")
            if len(self.stats['errors']) > 10:
                print(f"  ... 외 {len(self.stats['errors']) - 10}건")

        completion_rate = (
            self.stats['gaps_filled'] / self.stats['gaps_found'] * 100
            if self.stats['gaps_found'] > 0 else 0
        )

        print(f"\n[성공률]")
        print(f"gap 보간 성공률:     {completion_rate:.2f}%")

        if self.dry_run:
            print(f"\n⚠️  DRY RUN 모드: 실제 DB 업데이트 없음")

        print("\n" + "=" * 80)


def main():
    """메인 실행 함수."""
    import argparse

    parser = argparse.ArgumentParser(description="시세 데이터 결측치 보간")
    parser.add_argument(
        '--ticker',
        type=str,
        help='보간할 종목 코드 (지정하지 않으면 전체 종목)'
    )
    parser.add_argument(
        '--all-stocks',
        action='store_true',
        help='전체 종목 보간'
    )
    parser.add_argument(
        '--method',
        type=str,
        choices=['linear', 'ffill'],
        default='linear',
        help='보간 방법 (linear: 선형 보간, ffill: forward fill) (default: linear)'
    )
    parser.add_argument(
        '--min-gap',
        type=int,
        default=2,
        help='최소 gap 일수 (이 값 이상만 보간) (default: 2)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='처리할 최대 종목 수 (전체 종목 보간 시)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='실제 DB 업데이트 없이 시뮬레이션만 수행'
    )

    args = parser.parse_args()

    if not args.ticker and not args.all_stocks:
        parser.error("--ticker 또는 --all-stocks 중 하나를 지정해야 합니다")

    print("=" * 80)
    print("📊 시세 데이터 결측치 보간")
    print("=" * 80)
    print(f"보간 방법: {args.method}")
    print(f"최소 gap: {args.min_gap}일")
    if args.dry_run:
        print("모드: DRY RUN (실제 업데이트 없음)")

    with PriceInterpolator(dry_run=args.dry_run) as interpolator:
        if args.ticker:
            # 단일 종목 보간
            result = interpolator.interpolate_stock(
                ticker=args.ticker,
                method=args.method,
                min_gap_days=args.min_gap
            )
            print(f"\n결과: {result}")
        elif args.all_stocks:
            # 전체 종목 보간
            interpolator.interpolate_all_stocks(
                method=args.method,
                min_gap_days=args.min_gap,
                limit=args.limit
            )

        # 요약 출력
        interpolator.print_summary()

    print("\n✅ 보간 완료")


if __name__ == "__main__":
    main()
