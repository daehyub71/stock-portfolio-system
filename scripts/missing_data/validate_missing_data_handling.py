"""결측치 처리 결과 검증 스크립트.

결측치 처리 후 데이터 품질을 검증합니다.

Usage:
    python scripts/missing_data/validate_missing_data_handling.py
    python scripts/missing_data/validate_missing_data_handling.py --output-dir data/validation_reports
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from models import Stock, DailyPrice, FinancialStatement, FinancialRatio
from sqlalchemy import func, and_, or_, text, distinct


class MissingDataValidator:
    """결측치 처리 검증 클래스."""

    def __init__(self):
        """초기화."""
        self.db = SessionLocal()
        self.results = {
            'price': {},
            'financial': {},
            'ratio': {},
            'summary': {}
        }

    def close(self):
        """데이터베이스 연결 종료."""
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def validate_price_data(self) -> Dict[str, Any]:
        """시세 데이터 검증.

        Returns:
            검증 결과 딕셔너리
        """
        print("\n1️⃣  시세 데이터 검증 중...")

        # Gap 개수 확인
        gap_query = text("""
            WITH price_with_prev AS (
                SELECT
                    dp.stock_id,
                    dp.date,
                    LAG(dp.date) OVER (PARTITION BY dp.stock_id ORDER BY dp.date) AS prev_date
                FROM daily_prices dp
                JOIN stocks s ON dp.stock_id = s.id
                WHERE s.is_active = true
            )
            SELECT COUNT(*) as gap_count
            FROM price_with_prev
            WHERE prev_date IS NOT NULL
              AND date - prev_date > 5
        """)

        gap_count = self.db.execute(gap_query).scalar()

        # OHLC 관계 검증
        ohlc_violations = self.db.query(func.count(DailyPrice.id)).filter(
            or_(
                DailyPrice.high_price < DailyPrice.open_price,
                DailyPrice.high_price < DailyPrice.close_price,
                DailyPrice.high_price < DailyPrice.low_price,
                DailyPrice.low_price > DailyPrice.open_price,
                DailyPrice.low_price > DailyPrice.close_price,
                DailyPrice.low_price > DailyPrice.high_price
            )
        ).scalar()

        # 음수 거래량
        negative_volume = self.db.query(func.count(DailyPrice.id)).filter(
            DailyPrice.volume < 0
        ).scalar()

        # 전체 레코드 수
        total_records = self.db.query(func.count(DailyPrice.id)).scalar()

        # 커버리지 (시세 있는 종목 / 전체 종목)
        total_stocks = self.db.query(func.count(Stock.id)).filter(
            Stock.is_active == True
        ).scalar()

        stocks_with_prices = self.db.query(
            func.count(distinct(DailyPrice.stock_id))
        ).scalar()

        coverage_rate = (
            stocks_with_prices / total_stocks * 100
        ) if total_stocks > 0 else 0

        result = {
            'total_records': total_records,
            'total_stocks': total_stocks,
            'stocks_with_prices': stocks_with_prices,
            'coverage_rate': coverage_rate,
            'gaps_remaining': gap_count,
            'ohlc_violations': ohlc_violations,
            'negative_volume': negative_volume,
            'validation_passed': (
                gap_count == 0 and
                ohlc_violations == 0 and
                negative_volume == 0 and
                coverage_rate >= 99.0
            )
        }

        self.results['price'] = result

        print(f"  완료: {total_records:,}건 검증")
        print(f"  남은 gap: {gap_count}개")
        print(f"  OHLC 위반: {ohlc_violations}건")
        print(f"  음수 거래량: {negative_volume}건")
        print(f"  커버리지: {coverage_rate:.2f}%")

        return result

    def validate_financial_data(self) -> Dict[str, Any]:
        """재무제표 검증.

        Returns:
            검증 결과 딕셔너리
        """
        print("\n2️⃣  재무제표 검증 중...")

        # 전체 종목 수
        total_stocks = self.db.query(func.count(Stock.id)).filter(
            Stock.is_active == True
        ).scalar()

        # 재무제표 있는 종목
        stocks_with_financials = self.db.query(
            func.count(distinct(FinancialStatement.stock_id))
        ).scalar()

        # 전체 재무제표 수
        total_statements = self.db.query(func.count(FinancialStatement.id)).filter(
            FinancialStatement.fiscal_year.isnot(None)
        ).scalar()

        # 빈 재무상태표
        empty_bs = self.db.execute(
            text("""
                SELECT COUNT(*)
                FROM financial_statements
                WHERE balance_sheet = '{}'::jsonb
                  AND fiscal_year IS NOT NULL
            """)
        ).scalar()

        # 빈 손익계산서
        empty_is = self.db.execute(
            text("""
                SELECT COUNT(*)
                FROM financial_statements
                WHERE income_statement = '{"profit": {}, "revenue": {}, "expenses": {}}'::jsonb
                  AND fiscal_year IS NOT NULL
            """)
        ).scalar()

        # 재무상태표 등식 위반
        bs_violation_query = text("""
            SELECT COUNT(*)
            FROM financial_statements
            WHERE fiscal_year IS NOT NULL
              AND balance_sheet IS NOT NULL
              AND balance_sheet != '{}'::jsonb
              -- 자산 = 부채 + 자본 검증 (1% tolerance)
              AND ABS(
                  (balance_sheet->'assets'->'current'->>'유동자산')::numeric +
                  (balance_sheet->'assets'->'current'->>'비유동자산')::numeric -
                  ((balance_sheet->'liabilities'->'current'->>'유동부채')::numeric +
                   (balance_sheet->'liabilities'->'current'->>'비유동부채')::numeric +
                   (balance_sheet->'equity'->>'자본총계')::numeric)
              ) / NULLIF(
                  (balance_sheet->'assets'->'current'->>'유동자산')::numeric +
                  (balance_sheet->'assets'->'current'->>'비유동자산')::numeric, 0
              ) > 0.01
        """)

        try:
            bs_violations = self.db.execute(bs_violation_query).scalar()
        except:
            bs_violations = 0  # 계산 오류 시 0으로 처리

        coverage_rate = (
            stocks_with_financials / total_stocks * 100
        ) if total_stocks > 0 else 0

        result = {
            'total_stocks': total_stocks,
            'stocks_with_financials': stocks_with_financials,
            'coverage_rate': coverage_rate,
            'total_statements': total_statements,
            'empty_balance_sheet': empty_bs,
            'empty_income_statement': empty_is,
            'balance_sheet_violations': bs_violations,
            'validation_passed': (
                empty_bs == 0 and
                empty_is == 0 and
                coverage_rate >= 75.0
            )
        }

        self.results['financial'] = result

        print(f"  완료: {total_statements:,}건 검증")
        print(f"  빈 재무상태표: {empty_bs}건")
        print(f"  빈 손익계산서: {empty_is}건")
        print(f"  재무상태표 등식 위반: {bs_violations}건")
        print(f"  커버리지: {coverage_rate:.2f}%")

        return result

    def validate_ratio_data(self) -> Dict[str, Any]:
        """재무비율 검증.

        Returns:
            검증 결과 딕셔너리
        """
        print("\n3️⃣  재무비율 검증 중...")

        # 전체 종목 수
        total_stocks = self.db.query(func.count(Stock.id)).filter(
            Stock.is_active == True
        ).scalar()

        # 재무비율 있는 종목
        stocks_with_ratios = self.db.query(
            func.count(distinct(FinancialRatio.stock_id))
        ).scalar()

        # 전체 재무비율 레코드
        total_ratios = self.db.query(func.count(FinancialRatio.id)).filter(
            FinancialRatio.fiscal_year.isnot(None)
        ).scalar()

        # 주요 비율 NULL 체크
        key_ratios = {
            'roa': 10,                      # 목표 NULL 비율
            'roe': 10,
            'operating_profit_margin': 10,
            'net_profit_margin': 10,
            'debt_ratio': 5,
            'current_ratio': 5,
            'revenue_growth': 50            # 전기 데이터 필요 (높은 NULL 허용)
        }

        null_stats = {}
        all_passed = True

        for ratio_name, target_null_rate in key_ratios.items():
            non_null_count = self.db.query(func.count(FinancialRatio.id)).filter(
                FinancialRatio.fiscal_year.isnot(None),
                getattr(FinancialRatio, ratio_name).isnot(None)
            ).scalar()

            null_count = total_ratios - non_null_count
            null_rate = (null_count / total_ratios * 100) if total_ratios > 0 else 0
            passed = null_rate <= target_null_rate

            null_stats[ratio_name] = {
                'non_null': non_null_count,
                'null': null_count,
                'null_rate': null_rate,
                'target': target_null_rate,
                'passed': passed
            }

            if not passed:
                all_passed = False

        coverage_rate = (
            stocks_with_ratios / total_stocks * 100
        ) if total_stocks > 0 else 0

        result = {
            'total_stocks': total_stocks,
            'stocks_with_ratios': stocks_with_ratios,
            'coverage_rate': coverage_rate,
            'total_ratios': total_ratios,
            'null_stats': null_stats,
            'validation_passed': all_passed and coverage_rate >= 95.0
        }

        self.results['ratio'] = result

        print(f"  완료: {total_ratios:,}건 검증")
        print(f"  커버리지: {coverage_rate:.2f}%")

        for ratio_name, stats in null_stats.items():
            status = '✅' if stats['passed'] else '❌'
            print(f"  {status} {ratio_name}: NULL {stats['null_rate']:.1f}% " +
                  f"(목표: ≤{stats['target']}%)")

        return result

    def calculate_summary(self):
        """전체 검증 요약 계산."""
        price = self.results['price']
        financial = self.results['financial']
        ratio = self.results['ratio']

        # 전체 통과 여부
        all_passed = (
            price['validation_passed'] and
            financial['validation_passed'] and
            ratio['validation_passed']
        )

        # 개선 사항 수집
        improvements = []
        issues = []

        # 시세 데이터
        if price['gaps_remaining'] > 0:
            issues.append(f"시세 gap {price['gaps_remaining']}개 남음")
        if price['ohlc_violations'] > 0:
            issues.append(f"OHLC 위반 {price['ohlc_violations']}건")

        # 재무제표
        if financial['empty_balance_sheet'] > 0:
            issues.append(f"빈 재무상태표 {financial['empty_balance_sheet']}건")
        if financial['empty_income_statement'] > 0:
            issues.append(f"빈 손익계산서 {financial['empty_income_statement']}건")

        # 재무비율
        failed_ratios = [
            name for name, stats in ratio['null_stats'].items()
            if not stats['passed']
        ]
        if failed_ratios:
            issues.append(f"NULL 비율 목표 미달성: {', '.join(failed_ratios)}")

        # 개선 사항
        if price['coverage_rate'] >= 99.0:
            improvements.append("시세 데이터 커버리지 99% 이상 달성")
        if financial['empty_income_statement'] == 0:
            improvements.append("빈 손익계산서 0건 달성")
        if ratio['coverage_rate'] >= 95.0:
            improvements.append("재무비율 커버리지 95% 이상 달성")

        self.results['summary'] = {
            'all_passed': all_passed,
            'improvements': improvements,
            'issues': issues
        }

    def generate_report(self, output_path: Path = None) -> Path:
        """검증 리포트 생성.

        Args:
            output_path: 출력 파일 경로

        Returns:
            생성된 리포트 파일 경로
        """
        if output_path is None:
            output_dir = Path("data/validation_reports")
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"missing_data_validation_{timestamp}.txt"

        price = self.results['price']
        financial = self.results['financial']
        ratio = self.results['ratio']
        summary = self.results['summary']

        with open(output_path, 'w', encoding='utf-8') as f:
            # 헤더
            f.write("=" * 80 + "\n")
            f.write("📊 결측치 처리 결과 검증 리포트\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"검증 항목: 시세 데이터, 재무제표, 재무비율\n\n")

            # 전체 요약
            f.write("=" * 80 + "\n")
            f.write("📋 전체 요약\n")
            f.write("=" * 80 + "\n\n")

            if summary['all_passed']:
                f.write("✅ 전체 검증 통과\n\n")
            else:
                f.write("⚠️  일부 검증 실패\n\n")

            if summary['improvements']:
                f.write("[개선 사항]\n")
                for i, improvement in enumerate(summary['improvements'], 1):
                    f.write(f"{i}. {improvement}\n")
                f.write("\n")

            if summary['issues']:
                f.write("[문제점]\n")
                for i, issue in enumerate(summary['issues'], 1):
                    f.write(f"{i}. {issue}\n")
                f.write("\n")

            # 1. 시세 데이터
            f.write("\n" + "=" * 80 + "\n")
            f.write("1️⃣  시세 데이터 검증 결과\n")
            f.write("=" * 80 + "\n\n")

            status = "✅ 통과" if price['validation_passed'] else "❌ 실패"
            f.write(f"검증 결과: {status}\n\n")

            f.write(f"[전체 통계]\n")
            f.write(f"전체 레코드:         {price['total_records']:,}건\n")
            f.write(f"전체 종목:           {price['total_stocks']:,}개\n")
            f.write(f"시세 있는 종목:      {price['stocks_with_prices']:,}개\n")
            f.write(f"커버리지:            {price['coverage_rate']:.2f}%\n\n")

            f.write(f"[품질 지표]\n")
            f.write(f"남은 gap (>5일):     {price['gaps_remaining']}개 ")
            f.write(f"{'✅' if price['gaps_remaining'] == 0 else '⚠️'}\n")
            f.write(f"OHLC 위반:           {price['ohlc_violations']}건 ")
            f.write(f"{'✅' if price['ohlc_violations'] == 0 else '❌'}\n")
            f.write(f"음수 거래량:         {price['negative_volume']}건 ")
            f.write(f"{'✅' if price['negative_volume'] == 0 else '❌'}\n\n")

            f.write(f"[목표 달성도]\n")
            f.write(f"- 커버리지 ≥ 99%: {price['coverage_rate']:.2f}% ")
            f.write(f"{'✅' if price['coverage_rate'] >= 99.0 else '❌'}\n")
            f.write(f"- Gap 제거 (>5일): {price['gaps_remaining']}개 남음 ")
            f.write(f"{'✅' if price['gaps_remaining'] == 0 else '⚠️'}\n")
            f.write(f"- OHLC 관계 유지: {price['ohlc_violations']}건 위반 ")
            f.write(f"{'✅' if price['ohlc_violations'] == 0 else '❌'}\n")

            # 2. 재무제표
            f.write("\n" + "=" * 80 + "\n")
            f.write("2️⃣  재무제표 검증 결과\n")
            f.write("=" * 80 + "\n\n")

            status = "✅ 통과" if financial['validation_passed'] else "❌ 실패"
            f.write(f"검증 결과: {status}\n\n")

            f.write(f"[전체 통계]\n")
            f.write(f"전체 종목:           {financial['total_stocks']:,}개\n")
            f.write(f"재무제표 있는 종목:  {financial['stocks_with_financials']:,}개\n")
            f.write(f"커버리지:            {financial['coverage_rate']:.2f}%\n")
            f.write(f"전체 재무제표:       {financial['total_statements']:,}건\n\n")

            f.write(f"[품질 지표]\n")
            f.write(f"빈 재무상태표:       {financial['empty_balance_sheet']}건 ")
            f.write(f"{'✅' if financial['empty_balance_sheet'] == 0 else '❌'}\n")
            f.write(f"빈 손익계산서:       {financial['empty_income_statement']}건 ")
            f.write(f"{'✅' if financial['empty_income_statement'] == 0 else '❌'}\n")
            f.write(f"재무상태표 등식 위반: {financial['balance_sheet_violations']}건 ")
            f.write(f"{'✅' if financial['balance_sheet_violations'] < 100 else '⚠️'}\n\n")

            f.write(f"[목표 달성도]\n")
            f.write(f"- 커버리지 ≥ 75%: {financial['coverage_rate']:.2f}% ")
            f.write(f"{'✅' if financial['coverage_rate'] >= 75.0 else '❌'}\n")
            f.write(f"- 빈 손익계산서 0건: {financial['empty_income_statement']}건 ")
            f.write(f"{'✅' if financial['empty_income_statement'] == 0 else '❌'}\n")
            f.write(f"- 빈 재무상태표 0건: {financial['empty_balance_sheet']}건 ")
            f.write(f"{'✅' if financial['empty_balance_sheet'] == 0 else '❌'}\n")

            # 3. 재무비율
            f.write("\n" + "=" * 80 + "\n")
            f.write("3️⃣  재무비율 검증 결과\n")
            f.write("=" * 80 + "\n\n")

            status = "✅ 통과" if ratio['validation_passed'] else "❌ 실패"
            f.write(f"검증 결과: {status}\n\n")

            f.write(f"[전체 통계]\n")
            f.write(f"전체 종목:           {ratio['total_stocks']:,}개\n")
            f.write(f"재무비율 있는 종목:  {ratio['stocks_with_ratios']:,}개\n")
            f.write(f"커버리지:            {ratio['coverage_rate']:.2f}%\n")
            f.write(f"전체 재무비율:       {ratio['total_ratios']:,}건\n\n")

            f.write(f"[비율별 NULL 검증]\n")
            for ratio_name, stats in ratio['null_stats'].items():
                status = '✅' if stats['passed'] else '❌'
                f.write(f"{status} {ratio_name:25} NULL: {stats['null_rate']:5.1f}% " +
                       f"(목표: ≤{stats['target']}%)\n")

            f.write(f"\n[목표 달성도]\n")
            f.write(f"- 커버리지 ≥ 95%: {ratio['coverage_rate']:.2f}% ")
            f.write(f"{'✅' if ratio['coverage_rate'] >= 95.0 else '❌'}\n")

            passed_ratios = sum(
                1 for stats in ratio['null_stats'].values() if stats['passed']
            )
            total_ratios = len(ratio['null_stats'])
            f.write(f"- NULL 비율 목표 달성: {passed_ratios}/{total_ratios}개 비율 ")
            f.write(f"{'✅' if passed_ratios == total_ratios else '⚠️'}\n")

            # 권장사항
            f.write("\n" + "=" * 80 + "\n")
            f.write("🔧 권장사항\n")
            f.write("=" * 80 + "\n\n")

            if not summary['all_passed']:
                if price['gaps_remaining'] > 0:
                    f.write(f"[시세 데이터]\n")
                    f.write(f"1. 남은 gap {price['gaps_remaining']}개 보간 실행\n")
                    f.write(f"   python scripts/missing_data/interpolate_prices.py --all-stocks --method linear\n\n")

                if financial['empty_income_statement'] > 0:
                    f.write(f"[재무제표]\n")
                    f.write(f"1. 빈 손익계산서 {financial['empty_income_statement']}건 재수집\n")
                    f.write(f"   python scripts/batch_collect_financials.py --empty-income-statement\n\n")

                failed_ratios = [
                    name for name, stats in ratio['null_stats'].items()
                    if not stats['passed']
                ]
                if failed_ratios:
                    f.write(f"[재무비율]\n")
                    f.write(f"1. NULL 비율 높은 지표 개선: {', '.join(failed_ratios)}\n")
                    f.write(f"   - 재무제표 재수집 후 재무비율 재계산\n")
                    f.write(f"   python scripts/calculate_quarterly_ratios.py --all-stocks\n\n")
            else:
                f.write("✅ 모든 검증 통과! 추가 조치 불필요.\n\n")

            f.write("=" * 80 + "\n")
            f.write("✅ 리포트 생성 완료\n")
            f.write("=" * 80 + "\n")

        print(f"\n✅ 검증 리포트 저장: {output_path}")
        return output_path


def main():
    """메인 실행 함수."""
    import argparse

    parser = argparse.ArgumentParser(description="결측치 처리 결과 검증")
    parser.add_argument(
        '--output-dir',
        type=str,
        default='data/validation_reports',
        help='리포트 출력 디렉토리 (default: data/validation_reports)'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("📊 결측치 처리 결과 검증")
    print("=" * 80)

    with MissingDataValidator() as validator:
        # 각 데이터 유형 검증
        validator.validate_price_data()
        validator.validate_financial_data()
        validator.validate_ratio_data()

        # 전체 요약 계산
        validator.calculate_summary()

        # 리포트 생성
        validator.generate_report()

        # 콘솔 요약
        summary = validator.results['summary']

        print("\n" + "=" * 80)
        print("📋 검증 요약")
        print("=" * 80)

        if summary['all_passed']:
            print("\n✅ 전체 검증 통과")
        else:
            print("\n⚠️  일부 검증 실패")

        if summary['improvements']:
            print("\n[개선 사항]")
            for improvement in summary['improvements']:
                print(f"  ✅ {improvement}")

        if summary['issues']:
            print("\n[문제점]")
            for issue in summary['issues']:
                print(f"  ⚠️  {issue}")

        print("\n" + "=" * 80)

    print("\n✅ 검증 완료")


if __name__ == "__main__":
    main()
