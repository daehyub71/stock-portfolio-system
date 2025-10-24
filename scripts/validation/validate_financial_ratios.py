"""재무비율 이상치 탐지 및 검증.

검증 항목:
1. 재무비율 범위 검증 (정상 범위 이탈)
2. 극단적 이상치 탐지
3. NULL 비율 체크
4. 통계적 이상치 탐지 (IQR 방식)
"""

import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime
from typing import Dict, List, Tuple

from sqlalchemy import func, and_

from db.connection import SessionLocal
from models import Stock, FinancialRatio


class FinancialRatioValidator:
    """재무비율 검증기."""

    # 재무비율 정상 범위 정의 (min, max)
    RATIO_RANGES = {
        'roa': (-50, 50),                       # ROA: -50% ~ 50%
        'gross_profit_margin': (-100, 100),     # 매출총이익률: -100% ~ 100%
        'operating_profit_margin': (-100, 100), # 영업이익률: -100% ~ 100%
        'net_profit_margin': (-100, 100),       # 순이익률: -100% ~ 100%
        'debt_ratio': (0, 1000),                # 부채비율: 0% ~ 1000%
        'current_ratio': (0, 1000),             # 유동비율: 0% ~ 1000%
        'equity_ratio': (0, 100),               # 자기자본비율: 0% ~ 100%
        'asset_turnover': (0, 20),              # 총자산회전율: 0 ~ 20회
        'revenue_growth': (-100, 1000),         # 매출액증가율: -100% ~ 1000%
    }

    def __init__(self):
        """초기화."""
        self.db = SessionLocal()
        self.errors: Dict[str, List[Dict]] = {
            'out_of_range': [],
            'extreme_outliers': [],
            'high_null_ratio': []
        }
        self.stats = {
            'total_records': 0,
            'total_ratios_checked': 0,
            'out_of_range': 0,
            'extreme_outliers': 0,
            'error_rate': 0.0
        }

    def close(self):
        """데이터베이스 연결 종료."""
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def validate_ratio_ranges(self):
        """재무비율 범위 검증."""
        print("\n1️⃣  재무비율 범위 검증 중...")

        ratios_data = (
            self.db.query(FinancialRatio, Stock.ticker, Stock.name)
            .join(Stock, FinancialRatio.stock_id == Stock.id)
            .filter(FinancialRatio.fiscal_year.isnot(None))
            .all()
        )

        violation_count = 0

        for ratio, ticker, name in ratios_data:
            for ratio_name, (min_val, max_val) in self.RATIO_RANGES.items():
                value = getattr(ratio, ratio_name)

                if value is not None:
                    self.stats['total_ratios_checked'] += 1

                    if value < min_val or value > max_val:
                        violation_count += 1
                        self.errors['out_of_range'].append({
                            'ticker': ticker,
                            'name': name,
                            'fiscal_year': ratio.fiscal_year,
                            'fiscal_quarter': ratio.fiscal_quarter,
                            'ratio_name': ratio_name,
                            'value': float(value),
                            'expected_range': f'{min_val}~{max_val}',
                            'issue': f'{ratio_name} out of range: {value:.2f}'
                        })

        self.stats['out_of_range'] = violation_count
        print(f"  범위 초과: {violation_count:,}건")

        return violation_count

    def detect_extreme_outliers(self):
        """극단적 이상치 탐지 (IQR 방식)."""
        print("\n2️⃣  극단적 이상치 탐지 중...")

        outlier_count = 0

        for ratio_name in self.RATIO_RANGES.keys():
            # 해당 비율의 전체 데이터 조회
            values_query = (
                self.db.query(
                    FinancialRatio,
                    Stock.ticker,
                    Stock.name,
                    getattr(FinancialRatio, ratio_name).label('value')
                )
                .join(Stock, FinancialRatio.stock_id == Stock.id)
                .filter(
                    and_(
                        FinancialRatio.fiscal_year.isnot(None),
                        getattr(FinancialRatio, ratio_name).isnot(None)
                    )
                )
                .all()
            )

            if len(values_query) < 10:  # 데이터가 너무 적으면 스킵
                continue

            # 값만 추출
            values = [float(row.value) for row in values_query]
            values.sort()

            # Q1, Q3, IQR 계산
            n = len(values)
            q1_idx = n // 4
            q3_idx = (3 * n) // 4
            q1 = values[q1_idx]
            q3 = values[q3_idx]
            iqr = q3 - q1

            # 이상치 범위: Q1 - 3*IQR ~ Q3 + 3*IQR (극단적 이상치)
            lower_bound = q1 - 3 * iqr
            upper_bound = q3 + 3 * iqr

            # 이상치 탐지
            for row in values_query:
                value = float(row.value)
                if value < lower_bound or value > upper_bound:
                    outlier_count += 1
                    self.errors['extreme_outliers'].append({
                        'ticker': row.ticker,
                        'name': row.name,
                        'fiscal_year': row.FinancialRatio.fiscal_year,
                        'fiscal_quarter': row.FinancialRatio.fiscal_quarter,
                        'ratio_name': ratio_name,
                        'value': value,
                        'q1': q1,
                        'q3': q3,
                        'iqr': iqr,
                        'bounds': f'{lower_bound:.2f}~{upper_bound:.2f}',
                        'issue': f'{ratio_name} extreme outlier: {value:.2f}'
                    })

        self.stats['extreme_outliers'] = outlier_count
        print(f"  극단적 이상치: {outlier_count:,}건")

        return outlier_count

    def check_null_ratios(self):
        """NULL 비율 체크."""
        print("\n3️⃣  NULL 비율 체크 중...")

        total_records = self.db.query(func.count(FinancialRatio.id)).filter(
            FinancialRatio.fiscal_year.isnot(None)
        ).scalar()

        print(f"\n  재무비율별 NULL 비율:")
        high_null_count = 0

        for ratio_name in self.RATIO_RANGES.keys():
            non_null_count = self.db.query(func.count(FinancialRatio.id)).filter(
                and_(
                    FinancialRatio.fiscal_year.isnot(None),
                    getattr(FinancialRatio, ratio_name).isnot(None)
                )
            ).scalar()

            null_count = total_records - non_null_count
            null_rate = (null_count / total_records * 100) if total_records > 0 else 0

            status = '✅' if null_rate < 10 else '⚠️' if null_rate < 50 else '❌'
            print(f"    {status} {ratio_name:25} NULL: {null_count:5,}건 ({null_rate:5.1f}%)")

            if null_rate > 10:
                high_null_count += 1
                self.errors['high_null_ratio'].append({
                    'ratio_name': ratio_name,
                    'null_count': null_count,
                    'total_count': total_records,
                    'null_rate': null_rate,
                    'issue': f'High NULL ratio: {null_rate:.1f}%'
                })

        print(f"\n  NULL 비율 높은 지표: {high_null_count}개")

        return high_null_count

    def run_validation(self) -> Dict:
        """전체 검증 실행."""
        print("=" * 80)
        print("📊 재무비율 이상치 검증")
        print("=" * 80)

        # 전체 레코드 수
        self.stats['total_records'] = self.db.query(
            func.count(FinancialRatio.id)
        ).filter(FinancialRatio.fiscal_year.isnot(None)).scalar()

        print(f"\n전체 재무비율 레코드: {self.stats['total_records']:,}건")

        # 각 검증 실행
        self.validate_ratio_ranges()
        self.detect_extreme_outliers()
        self.check_null_ratios()

        # 통계 계산
        total_errors = (
            self.stats['out_of_range'] +
            self.stats['extreme_outliers']
        )
        if self.stats['total_ratios_checked'] > 0:
            self.stats['error_rate'] = (
                total_errors / self.stats['total_ratios_checked'] * 100
            )

        return self.stats

    def print_summary(self):
        """검증 결과 요약 출력."""
        print("\n" + "=" * 80)
        print("📋 검증 결과 요약")
        print("=" * 80)

        print(f"\n[전체 통계]")
        print(f"  전체 레코드:         {self.stats['total_records']:,}건")
        print(f"  체크된 비율 수:      {self.stats['total_ratios_checked']:,}개")
        print(f"  범위 초과:           {self.stats['out_of_range']:,}건")
        print(f"  극단적 이상치:       {self.stats['extreme_outliers']:,}건")
        print(f"  오류율:              {self.stats['error_rate']:.4f}%")

        # 오류 샘플 출력 (각 유형별 최대 10개)
        if self.stats['out_of_range'] > 0 or self.stats['extreme_outliers'] > 0:
            print(f"\n[이상치 샘플] (각 유형별 최대 10개)")
            print("-" * 80)

            # 범위 초과
            if self.errors['out_of_range']:
                print(f"\n범위 초과 ({len(self.errors['out_of_range'])}건):")
                for i, error in enumerate(self.errors['out_of_range'][:10], 1):
                    quarter = f"Q{error['fiscal_quarter']}" if error.get('fiscal_quarter') else '연간'
                    print(
                        f"  {i}. {error['ticker']} {error['name']} "
                        f"{error['fiscal_year']}{quarter}: "
                        f"{error['ratio_name']}={error['value']:.2f} "
                        f"(정상범위: {error['expected_range']})"
                    )
                if len(self.errors['out_of_range']) > 10:
                    print(f"  ... 외 {len(self.errors['out_of_range']) - 10}건")

            # 극단적 이상치
            if self.errors['extreme_outliers']:
                print(f"\n극단적 이상치 ({len(self.errors['extreme_outliers'])}건):")
                for i, error in enumerate(self.errors['extreme_outliers'][:10], 1):
                    quarter = f"Q{error['fiscal_quarter']}" if error.get('fiscal_quarter') else '연간'
                    print(
                        f"  {i}. {error['ticker']} {error['name']} "
                        f"{error['fiscal_year']}{quarter}: "
                        f"{error['ratio_name']}={error['value']:.2f} "
                        f"(IQR 범위: {error['bounds']})"
                    )
                if len(self.errors['extreme_outliers']) > 10:
                    print(f"  ... 외 {len(self.errors['extreme_outliers']) - 10}건")

        print("\n" + "=" * 80)

    def save_report(self, output_path: Path = None):
        """검증 리포트 저장."""
        if output_path is None:
            output_dir = Path("data/validation_reports")
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"ratio_validation_{timestamp}.txt"

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("재무비율 이상치 검증 리포트\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # 전체 통계
            f.write("[전체 통계]\n")
            f.write(f"전체 레코드:         {self.stats['total_records']:,}건\n")
            f.write(f"체크된 비율 수:      {self.stats['total_ratios_checked']:,}개\n")
            f.write(f"범위 초과:           {self.stats['out_of_range']:,}건\n")
            f.write(f"극단적 이상치:       {self.stats['extreme_outliers']:,}건\n")
            f.write(f"오류율:              {self.stats['error_rate']:.4f}%\n\n")

            # 범위 정의
            f.write("[재무비율 정상 범위]\n")
            for ratio_name, (min_val, max_val) in self.RATIO_RANGES.items():
                f.write(f"{ratio_name:25} {min_val} ~ {max_val}\n")
            f.write("\n")

            # NULL 비율
            if self.errors['high_null_ratio']:
                f.write("[NULL 비율 높은 지표]\n")
                for error in self.errors['high_null_ratio']:
                    f.write(
                        f"{error['ratio_name']:25} "
                        f"NULL: {error['null_count']:,}/{error['total_count']:,} "
                        f"({error['null_rate']:.1f}%)\n"
                    )
                f.write("\n")

            # 상세 이상치 목록
            if self.errors['out_of_range']:
                f.write(f"\n[범위 초과] {len(self.errors['out_of_range']):,}건\n")
                f.write("-" * 80 + "\n")
                for error in self.errors['out_of_range']:
                    quarter = f"Q{error['fiscal_quarter']}" if error.get('fiscal_quarter') else '연간'
                    f.write(
                        f"{error['ticker']} {error['name']} "
                        f"{error['fiscal_year']}{quarter}: "
                        f"{error['ratio_name']}={error['value']:.2f} "
                        f"(정상범위: {error['expected_range']})\n"
                    )

            if self.errors['extreme_outliers']:
                f.write(f"\n[극단적 이상치] {len(self.errors['extreme_outliers']):,}건\n")
                f.write("-" * 80 + "\n")
                for error in self.errors['extreme_outliers']:
                    quarter = f"Q{error['fiscal_quarter']}" if error.get('fiscal_quarter') else '연간'
                    f.write(
                        f"{error['ticker']} {error['name']} "
                        f"{error['fiscal_year']}{quarter}: "
                        f"{error['ratio_name']}={error['value']:.2f} "
                        f"(IQR 범위: {error['bounds']})\n"
                    )

        print(f"\n📄 검증 리포트 저장: {output_path}")


def main():
    """메인 실행 함수."""
    import argparse

    parser = argparse.ArgumentParser(description="재무비율 이상치 검증")
    parser.add_argument(
        '--recalculate',
        action='store_true',
        help="이상치 재계산 (현재는 리포트만 생성)"
    )

    args = parser.parse_args()

    with FinancialRatioValidator() as validator:
        validator.run_validation()
        validator.print_summary()
        validator.save_report()

        if args.recalculate:
            print("\n⚠️  자동 재계산 기능은 아직 구현되지 않았습니다.")
            print("scripts/calculate_quarterly_ratios.py를 사용하여 수동으로 재계산해주세요.")

    print("\n✅ 검증 완료")


if __name__ == "__main__":
    main()
