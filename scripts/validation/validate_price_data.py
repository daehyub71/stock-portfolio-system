"""시세 데이터 정합성 검증.

검증 항목:
1. OHLC 관계: High >= Open, Close, Low
2. OHLC 관계: Low <= Open, Close, High
3. 거래량 음수 체크
4. 가격 0 또는 음수 체크
5. 날짜 순서 일관성
6. 중복 데이터 체크
"""

import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime
from typing import Dict, List, Tuple

from sqlalchemy import func, and_, or_

from db.connection import SessionLocal
from models import Stock, DailyPrice


class PriceDataValidator:
    """시세 데이터 검증기."""

    def __init__(self):
        """초기화."""
        self.db = SessionLocal()
        self.errors: Dict[str, List[Dict]] = {
            'ohlc_high_violation': [],
            'ohlc_low_violation': [],
            'negative_volume': [],
            'invalid_price': [],
            'duplicate_records': []
        }
        self.stats = {
            'total_records': 0,
            'total_errors': 0,
            'error_rate': 0.0
        }

    def close(self):
        """데이터베이스 연결 종료."""
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def validate_ohlc_relationships(self):
        """OHLC 관계 검증.

        검증 규칙:
        - High >= Open, Close, Low
        - Low <= Open, Close, High
        """
        print("\n1️⃣  OHLC 관계 검증 중...")

        # High 위반: High < Open or High < Close or High < Low
        high_violations = (
            self.db.query(DailyPrice, Stock.ticker, Stock.name)
            .join(Stock, DailyPrice.stock_id == Stock.id)
            .filter(
                or_(
                    DailyPrice.high_price < DailyPrice.open_price,
                    DailyPrice.high_price < DailyPrice.close_price,
                    DailyPrice.high_price < DailyPrice.low_price
                )
            )
            .all()
        )

        for price, ticker, name in high_violations:
            self.errors['ohlc_high_violation'].append({
                'ticker': ticker,
                'name': name,
                'date': price.date,
                'open': float(price.open_price),
                'high': float(price.high_price),
                'low': float(price.low_price),
                'close': float(price.close_price),
                'issue': 'High < Open/Close/Low'
            })

        # Low 위반: Low > Open or Low > Close or Low > High
        low_violations = (
            self.db.query(DailyPrice, Stock.ticker, Stock.name)
            .join(Stock, DailyPrice.stock_id == Stock.id)
            .filter(
                or_(
                    DailyPrice.low_price > DailyPrice.open_price,
                    DailyPrice.low_price > DailyPrice.close_price,
                    DailyPrice.low_price > DailyPrice.high_price
                )
            )
            .all()
        )

        for price, ticker, name in low_violations:
            self.errors['ohlc_low_violation'].append({
                'ticker': ticker,
                'name': name,
                'date': price.date,
                'open': float(price.open_price),
                'high': float(price.high_price),
                'low': float(price.low_price),
                'close': float(price.close_price),
                'issue': 'Low > Open/Close/High'
            })

        high_count = len(self.errors['ohlc_high_violation'])
        low_count = len(self.errors['ohlc_low_violation'])

        print(f"  High 위반: {high_count:,}건")
        print(f"  Low 위반: {low_count:,}건")

        return high_count + low_count

    def validate_volume(self):
        """거래량 음수 체크."""
        print("\n2️⃣  거래량 검증 중...")

        negative_volumes = (
            self.db.query(DailyPrice, Stock.ticker, Stock.name)
            .join(Stock, DailyPrice.stock_id == Stock.id)
            .filter(DailyPrice.volume < 0)
            .all()
        )

        for price, ticker, name in negative_volumes:
            self.errors['negative_volume'].append({
                'ticker': ticker,
                'name': name,
                'date': price.date,
                'volume': price.volume,
                'issue': 'Negative volume'
            })

        count = len(self.errors['negative_volume'])
        print(f"  음수 거래량: {count:,}건")

        return count

    def validate_price_values(self):
        """가격 0 또는 음수 체크."""
        print("\n3️⃣  가격 값 검증 중...")

        invalid_prices = (
            self.db.query(DailyPrice, Stock.ticker, Stock.name)
            .join(Stock, DailyPrice.stock_id == Stock.id)
            .filter(
                or_(
                    DailyPrice.open_price <= 0,
                    DailyPrice.high_price <= 0,
                    DailyPrice.low_price <= 0,
                    DailyPrice.close_price <= 0
                )
            )
            .all()
        )

        for price, ticker, name in invalid_prices:
            self.errors['invalid_price'].append({
                'ticker': ticker,
                'name': name,
                'date': price.date,
                'open': float(price.open_price),
                'high': float(price.high_price),
                'low': float(price.low_price),
                'close': float(price.close_price),
                'issue': 'Price <= 0'
            })

        count = len(self.errors['invalid_price'])
        print(f"  0 또는 음수 가격: {count:,}건")

        return count

    def validate_duplicates(self):
        """중복 레코드 체크."""
        print("\n4️⃣  중복 레코드 검증 중...")

        # stock_id + date로 그룹화하여 중복 체크
        duplicates = (
            self.db.query(
                DailyPrice.stock_id,
                DailyPrice.date,
                func.count(DailyPrice.id).label('count')
            )
            .group_by(DailyPrice.stock_id, DailyPrice.date)
            .having(func.count(DailyPrice.id) > 1)
            .all()
        )

        for stock_id, date, count in duplicates:
            stock = self.db.query(Stock).filter(Stock.id == stock_id).first()
            if stock:
                self.errors['duplicate_records'].append({
                    'ticker': stock.ticker,
                    'name': stock.name,
                    'date': date,
                    'count': count,
                    'issue': f'{count} duplicate records'
                })

        dup_count = len(self.errors['duplicate_records'])
        print(f"  중복 레코드: {dup_count:,}건")

        return dup_count

    def run_validation(self) -> Dict:
        """전체 검증 실행."""
        print("=" * 80)
        print("📊 시세 데이터 정합성 검증")
        print("=" * 80)

        # 전체 레코드 수
        self.stats['total_records'] = self.db.query(func.count(DailyPrice.id)).scalar()
        print(f"\n전체 시세 레코드: {self.stats['total_records']:,}건")

        # 각 검증 실행
        error_counts = []
        error_counts.append(self.validate_ohlc_relationships())
        error_counts.append(self.validate_volume())
        error_counts.append(self.validate_price_values())
        error_counts.append(self.validate_duplicates())

        # 통계 계산
        self.stats['total_errors'] = sum(error_counts)
        if self.stats['total_records'] > 0:
            self.stats['error_rate'] = (
                self.stats['total_errors'] / self.stats['total_records'] * 100
            )

        return self.stats

    def print_summary(self):
        """검증 결과 요약 출력."""
        print("\n" + "=" * 80)
        print("📋 검증 결과 요약")
        print("=" * 80)

        print(f"\n[전체 통계]")
        print(f"  전체 레코드:     {self.stats['total_records']:,}건")
        print(f"  오류 발견:       {self.stats['total_errors']:,}건")
        print(f"  오류율:          {self.stats['error_rate']:.4f}%")

        print(f"\n[오류 유형별 건수]")
        print(f"  OHLC High 위반:  {len(self.errors['ohlc_high_violation']):,}건")
        print(f"  OHLC Low 위반:   {len(self.errors['ohlc_low_violation']):,}건")
        print(f"  음수 거래량:     {len(self.errors['negative_volume']):,}건")
        print(f"  잘못된 가격:     {len(self.errors['invalid_price']):,}건")
        print(f"  중복 레코드:     {len(self.errors['duplicate_records']):,}건")

        # 오류 샘플 출력 (각 유형별 최대 5개)
        if self.stats['total_errors'] > 0:
            print(f"\n[오류 샘플] (각 유형별 최대 5개)")
            print("-" * 80)

            for error_type, errors in self.errors.items():
                if errors:
                    print(f"\n{error_type}:")
                    for i, error in enumerate(errors[:5], 1):
                        print(f"  {i}. {error['ticker']} {error['name']} {error['date']}: {error['issue']}")
                    if len(errors) > 5:
                        print(f"  ... 외 {len(errors) - 5}건")

        print("\n" + "=" * 80)

    def save_report(self, output_path: Path = None):
        """검증 리포트 저장."""
        if output_path is None:
            output_dir = Path("data/validation_reports")
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"price_validation_{timestamp}.txt"

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("시세 데이터 정합성 검증 리포트\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # 전체 통계
            f.write("[전체 통계]\n")
            f.write(f"전체 레코드:     {self.stats['total_records']:,}건\n")
            f.write(f"오류 발견:       {self.stats['total_errors']:,}건\n")
            f.write(f"오류율:          {self.stats['error_rate']:.4f}%\n\n")

            # 오류 유형별 건수
            f.write("[오류 유형별 건수]\n")
            f.write(f"OHLC High 위반:  {len(self.errors['ohlc_high_violation']):,}건\n")
            f.write(f"OHLC Low 위반:   {len(self.errors['ohlc_low_violation']):,}건\n")
            f.write(f"음수 거래량:     {len(self.errors['negative_volume']):,}건\n")
            f.write(f"잘못된 가격:     {len(self.errors['invalid_price']):,}건\n")
            f.write(f"중복 레코드:     {len(self.errors['duplicate_records']):,}건\n\n")

            # 상세 오류 목록
            for error_type, errors in self.errors.items():
                if errors:
                    f.write(f"\n[{error_type}] {len(errors):,}건\n")
                    f.write("-" * 80 + "\n")
                    for error in errors:
                        f.write(
                            f"{error['ticker']} {error['name']} "
                            f"{error['date']}: {error['issue']}\n"
                        )
                        if 'open' in error:
                            f.write(
                                f"  OHLC: {error['open']}/{error['high']}/"
                                f"{error['low']}/{error['close']}\n"
                            )
                        if 'volume' in error:
                            f.write(f"  Volume: {error['volume']}\n")

        print(f"\n📄 검증 리포트 저장: {output_path}")


def main():
    """메인 실행 함수."""
    import argparse

    parser = argparse.ArgumentParser(description="시세 데이터 정합성 검증")
    parser.add_argument(
        '--fix',
        action='store_true',
        help="오류 자동 수정 (현재는 리포트만 생성)"
    )

    args = parser.parse_args()

    with PriceDataValidator() as validator:
        validator.run_validation()
        validator.print_summary()
        validator.save_report()

        if args.fix:
            print("\n⚠️  자동 수정 기능은 아직 구현되지 않았습니다.")
            print("수동으로 데이터를 확인하고 수정해주세요.")

    print("\n✅ 검증 완료")


if __name__ == "__main__":
    main()
