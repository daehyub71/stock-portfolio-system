#!/usr/bin/env python3
"""데이터 품질 체크 스크립트.

수집된 재무제표 데이터의 품질을 검증합니다:
- 결측치 탐지
- 이상치 탐지
- 데이터 무결성 검증
- 재무제표 균형 검증

Usage:
    # 전체 품질 체크
    python scripts/data_quality_check.py

    # 특정 종목만 체크
    python scripts/data_quality_check.py --ticker 005930

    # 상세 리포트 생성
    python scripts/data_quality_check.py --detailed --output data/quality_reports/
"""

import sys
from pathlib import Path
import argparse
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import statistics

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from models import FinancialStatement, Stock
from sqlalchemy import func, and_


class DataQualityChecker:
    """데이터 품질 검증 클래스."""

    def __init__(self, output_dir: Optional[Path] = None, detailed: bool = False):
        """Initialize quality checker.

        Args:
            output_dir: Output directory for reports
            detailed: Generate detailed reports
        """
        self.output_dir = output_dir
        self.detailed = detailed
        self.db = SessionLocal()

        # Quality metrics
        self.issues = {
            'missing_data': [],
            'outliers': [],
            'balance_sheet_errors': [],
            'negative_values': [],
            'zero_values': [],
            'data_inconsistencies': []
        }

    def __del__(self):
        """Cleanup."""
        if hasattr(self, 'db'):
            self.db.close()

    def print_header(self, title: str):
        """Print formatted header.

        Args:
            title: Header title
        """
        print("\n")
        print("╔" + "═" * 78 + "╗")
        print("║" + f" {title:^76} " + "║")
        print("╚" + "═" * 78 + "╝")
        print()

    def print_section(self, title: str):
        """Print section separator.

        Args:
            title: Section title
        """
        print("\n" + "=" * 80)
        print(title)
        print("=" * 80)

    def check_missing_data(self, ticker: Optional[str] = None):
        """Check for missing data.

        Args:
            ticker: Specific ticker to check (optional)
        """
        self.print_section("1️⃣  결측치 검사")

        query = self.db.query(FinancialStatement).join(Stock)

        if ticker:
            query = query.filter(Stock.ticker == ticker)

        statements = query.all()

        missing_count = 0
        for stmt in statements:
            stock = self.db.query(Stock).filter_by(id=stmt.stock_id).first()
            ticker_name = f"{stock.ticker} ({stock.name})"

            issues = []

            # Check JSONB fields
            if not stmt.balance_sheet or stmt.balance_sheet == {}:
                issues.append("대차대조표 누락")

            if not stmt.income_statement or stmt.income_statement == {}:
                issues.append("손익계산서 누락")

            if not stmt.cash_flow or stmt.cash_flow == {}:
                issues.append("현금흐름표 누락")

            # Check critical balance sheet items
            if stmt.balance_sheet:
                bs = stmt.balance_sheet
                if not bs.get('assets') or not bs['assets'].get('current'):
                    issues.append("유동자산 데이터 없음")
                if not bs.get('liabilities'):
                    issues.append("부채 데이터 없음")
                if not bs.get('equity'):
                    issues.append("자본 데이터 없음")

            if issues:
                missing_count += 1
                self.issues['missing_data'].append({
                    'ticker': stock.ticker,
                    'name': stock.name,
                    'fiscal_year': stmt.fiscal_year,
                    'issues': issues
                })

                if self.detailed:
                    print(f"  ⚠️  {ticker_name} ({stmt.fiscal_year}): {', '.join(issues)}")

        print(f"\n총 {len(statements):,}개 재무제표 중 {missing_count:,}개에서 결측치 발견")

        if missing_count > 0:
            print(f"결측 비율: {missing_count / len(statements) * 100:.2f}%")
        else:
            print("✅ 결측치 없음")

    def check_balance_sheet_equation(self, ticker: Optional[str] = None):
        """Check balance sheet equation: Assets = Liabilities + Equity.

        Args:
            ticker: Specific ticker to check (optional)
        """
        self.print_section("2️⃣  재무제표 균형 검증 (자산 = 부채 + 자본)")

        query = self.db.query(FinancialStatement).join(Stock)

        if ticker:
            query = query.filter(Stock.ticker == ticker)

        statements = query.all()

        error_count = 0
        tolerance = 0.01  # 1% tolerance for rounding errors

        for stmt in statements:
            if not stmt.balance_sheet:
                continue

            stock = self.db.query(Stock).filter_by(id=stmt.stock_id).first()

            bs = stmt.balance_sheet

            # Extract total assets
            total_assets = None
            if bs.get('assets'):
                # Try to find total assets
                assets = bs['assets']
                if '자산총계' in assets:
                    total_assets = assets['자산총계']
                elif 'current' in assets and 'non_current' in assets:
                    # Calculate from sub-totals
                    current = assets['current'].get('유동자산', 0)
                    non_current = assets['non_current'].get('비유동자산', 0)
                    if current and non_current:
                        total_assets = current + non_current

            # Extract total liabilities and equity
            total_liabilities = None
            total_equity = None

            if bs.get('liabilities'):
                liabilities = bs['liabilities']
                if '부채총계' in liabilities:
                    total_liabilities = liabilities['부채총계']
                elif 'current' in liabilities and 'non_current' in liabilities:
                    current = liabilities['current'].get('유동부채', 0)
                    non_current = liabilities['non_current'].get('비유동부채', 0)
                    if current and non_current:
                        total_liabilities = current + non_current

            if bs.get('equity'):
                equity = bs['equity']
                if '자본총계' in equity:
                    total_equity = equity['자본총계']
                elif '지배기업 소유주지분' in equity:
                    total_equity = equity['지배기업 소유주지분']

            # Validate equation
            if total_assets and total_liabilities and total_equity:
                left_side = total_assets
                right_side = total_liabilities + total_equity

                difference = abs(left_side - right_side)
                relative_error = difference / left_side if left_side > 0 else float('inf')

                if relative_error > tolerance:
                    error_count += 1
                    self.issues['balance_sheet_errors'].append({
                        'ticker': stock.ticker,
                        'name': stock.name,
                        'fiscal_year': stmt.fiscal_year,
                        'total_assets': total_assets,
                        'total_liabilities': total_liabilities,
                        'total_equity': total_equity,
                        'difference': difference,
                        'relative_error': relative_error * 100
                    })

                    if self.detailed:
                        print(f"  ❌ {stock.ticker} ({stock.name}) {stmt.fiscal_year}:")
                        print(f"     자산: {total_assets:,.0f}")
                        print(f"     부채 + 자본: {right_side:,.0f}")
                        print(f"     차이: {difference:,.0f} ({relative_error * 100:.2f}%)")

        print(f"\n총 {len(statements):,}개 재무제표 중 {error_count:,}개에서 균형 오류 발견")

        if error_count > 0:
            print(f"오류 비율: {error_count / len(statements) * 100:.2f}%")
        else:
            print("✅ 모든 재무제표 균형 정상")

    def check_negative_values(self, ticker: Optional[str] = None):
        """Check for unexpected negative values.

        Args:
            ticker: Specific ticker to check (optional)
        """
        self.print_section("3️⃣  비정상 음수값 검사")

        query = self.db.query(FinancialStatement).join(Stock)

        if ticker:
            query = query.filter(Stock.ticker == ticker)

        statements = query.all()

        negative_count = 0

        # Items that should generally be positive
        positive_items = [
            '유동자산', '비유동자산', '자산총계',
            '유동부채', '비유동부채', '부채총계',
            '자본총계', '매출액', '자본금'
        ]

        for stmt in statements:
            if not stmt.balance_sheet:
                continue

            stock = self.db.query(Stock).filter_by(id=stmt.stock_id).first()
            negative_items = []

            # Check balance sheet
            bs = stmt.balance_sheet
            for item in positive_items:
                value = self._find_value_in_dict(bs, item)
                if value is not None and value < 0:
                    negative_items.append(f"{item}: {value:,.0f}")

            if negative_items:
                negative_count += 1
                self.issues['negative_values'].append({
                    'ticker': stock.ticker,
                    'name': stock.name,
                    'fiscal_year': stmt.fiscal_year,
                    'items': negative_items
                })

                if self.detailed:
                    print(f"  ⚠️  {stock.ticker} ({stock.name}) {stmt.fiscal_year}:")
                    for item in negative_items:
                        print(f"     - {item}")

        print(f"\n총 {len(statements):,}개 재무제표 중 {negative_count:,}개에서 비정상 음수값 발견")

        if negative_count > 0:
            print(f"비정상 비율: {negative_count / len(statements) * 100:.2f}%")
        else:
            print("✅ 비정상 음수값 없음")

    def check_outliers(self, ticker: Optional[str] = None):
        """Check for statistical outliers.

        Args:
            ticker: Specific ticker to check (optional)
        """
        self.print_section("4️⃣  이상치 탐지")

        query = self.db.query(FinancialStatement).join(Stock)

        if ticker:
            query = query.filter(Stock.ticker == ticker)

        statements = query.all()

        # Collect key financial metrics
        metrics = {
            'total_assets': [],
            'total_liabilities': [],
            'total_equity': []
        }

        data_map = []  # Store (value, statement) pairs

        for stmt in statements:
            if not stmt.balance_sheet:
                continue

            bs = stmt.balance_sheet
            stock = self.db.query(Stock).filter_by(id=stmt.stock_id).first()

            # Extract values
            total_assets = self._find_value_in_dict(bs, '자산총계')
            total_liabilities = self._find_value_in_dict(bs, '부채총계')
            total_equity = self._find_value_in_dict(bs, '자본총계')

            if total_assets:
                metrics['total_assets'].append(total_assets)
                data_map.append(('total_assets', total_assets, stock, stmt.fiscal_year))

            if total_liabilities:
                metrics['total_liabilities'].append(total_liabilities)

            if total_equity:
                metrics['total_equity'].append(total_equity)

        outlier_count = 0

        # Detect outliers using IQR method
        for metric_name, values in metrics.items():
            if len(values) < 10:  # Need sufficient data
                continue

            # Calculate IQR
            sorted_values = sorted(values)
            q1 = sorted_values[len(values) // 4]
            q3 = sorted_values[3 * len(values) // 4]
            iqr = q3 - q1

            lower_bound = q1 - 3 * iqr  # 3 * IQR for extreme outliers
            upper_bound = q3 + 3 * iqr

            # Find outliers
            for metric, value, stock, year in data_map:
                if metric != metric_name:
                    continue

                if value < lower_bound or value > upper_bound:
                    outlier_count += 1
                    self.issues['outliers'].append({
                        'ticker': stock.ticker,
                        'name': stock.name,
                        'fiscal_year': year,
                        'metric': metric_name,
                        'value': value,
                        'lower_bound': lower_bound,
                        'upper_bound': upper_bound
                    })

                    if self.detailed:
                        print(f"  📊 {stock.ticker} ({stock.name}) {year}:")
                        print(f"     {metric_name}: {value:,.0f}")
                        print(f"     정상 범위: {lower_bound:,.0f} ~ {upper_bound:,.0f}")

        print(f"\n총 {len(statements):,}개 재무제표 중 {outlier_count:,}개 이상치 발견")

        if outlier_count > 0:
            print(f"이상치 비율: {outlier_count / len(statements) * 100:.2f}%")
            print("ℹ️  참고: 대기업과 소기업의 규모 차이로 인한 통계적 이상치일 수 있습니다.")
        else:
            print("✅ 통계적 이상치 없음")

    def check_zero_values(self, ticker: Optional[str] = None):
        """Check for suspicious zero values.

        Args:
            ticker: Specific ticker to check (optional)
        """
        self.print_section("5️⃣  의심스러운 0값 검사")

        query = self.db.query(FinancialStatement).join(Stock)

        if ticker:
            query = query.filter(Stock.ticker == ticker)

        statements = query.all()

        zero_count = 0

        # Items that should rarely be zero
        critical_items = ['자산총계', '매출액', '자본총계']

        for stmt in statements:
            if not stmt.balance_sheet:
                continue

            stock = self.db.query(Stock).filter_by(id=stmt.stock_id).first()
            zero_items = []

            # Check balance sheet
            bs = stmt.balance_sheet
            for item in critical_items:
                value = self._find_value_in_dict(bs, item)
                if value is not None and value == 0:
                    zero_items.append(item)

            if zero_items:
                zero_count += 1
                self.issues['zero_values'].append({
                    'ticker': stock.ticker,
                    'name': stock.name,
                    'fiscal_year': stmt.fiscal_year,
                    'items': zero_items
                })

                if self.detailed:
                    print(f"  ⚠️  {stock.ticker} ({stock.name}) {stmt.fiscal_year}:")
                    print(f"     - {', '.join(zero_items)}")

        print(f"\n총 {len(statements):,}개 재무제표 중 {zero_count:,}개에서 의심스러운 0값 발견")

        if zero_count > 0:
            print(f"0값 비율: {zero_count / len(statements) * 100:.2f}%")
        else:
            print("✅ 의심스러운 0값 없음")

    def _find_value_in_dict(self, data: Dict, key: str) -> Optional[float]:
        """Recursively find a value in nested dictionary.

        Args:
            data: Dictionary to search
            key: Key to find

        Returns:
            Value if found, None otherwise
        """
        if not isinstance(data, dict):
            return None

        if key in data:
            return data[key]

        for v in data.values():
            if isinstance(v, dict):
                result = self._find_value_in_dict(v, key)
                if result is not None:
                    return result

        return None

    def generate_summary_report(self) -> Dict:
        """Generate summary report.

        Returns:
            Summary statistics
        """
        total_statements = self.db.query(FinancialStatement).count()

        summary = {
            'timestamp': datetime.now().isoformat(),
            'total_statements': total_statements,
            'issues_summary': {
                'missing_data': len(self.issues['missing_data']),
                'balance_sheet_errors': len(self.issues['balance_sheet_errors']),
                'negative_values': len(self.issues['negative_values']),
                'outliers': len(self.issues['outliers']),
                'zero_values': len(self.issues['zero_values'])
            },
            'total_issues': sum(len(v) for v in self.issues.values()),
            'quality_score': 0.0
        }

        # Calculate quality score (0-100)
        if total_statements > 0:
            issue_ratio = summary['total_issues'] / total_statements
            summary['quality_score'] = max(0, 100 - issue_ratio * 100)

        return summary

    def save_report(self, summary: Dict):
        """Save detailed report to file.

        Args:
            summary: Summary statistics
        """
        if not self.output_dir:
            return

        output_dir = Path(self.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = output_dir / f'quality_report_{timestamp}.json'

        report = {
            'summary': summary,
            'issues': self.issues
        }

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n📄 상세 리포트 저장: {report_file}")

    def run_all_checks(self, ticker: Optional[str] = None):
        """Run all quality checks.

        Args:
            ticker: Specific ticker to check (optional)
        """
        self.print_header("데이터 품질 검사")

        if ticker:
            print(f"종목: {ticker}")
        else:
            print("전체 종목 검사")

        # Run checks
        self.check_missing_data(ticker)
        self.check_balance_sheet_equation(ticker)
        self.check_negative_values(ticker)
        self.check_zero_values(ticker)
        self.check_outliers(ticker)

        # Generate summary
        summary = self.generate_summary_report()

        self.print_section("📊 종합 요약")

        print(f"총 재무제표 수: {summary['total_statements']:,}개")
        print(f"\n발견된 이슈:")
        print(f"  - 결측치: {summary['issues_summary']['missing_data']:,}개")
        print(f"  - 재무제표 균형 오류: {summary['issues_summary']['balance_sheet_errors']:,}개")
        print(f"  - 비정상 음수값: {summary['issues_summary']['negative_values']:,}개")
        print(f"  - 의심스러운 0값: {summary['issues_summary']['zero_values']:,}개")
        print(f"  - 통계적 이상치: {summary['issues_summary']['outliers']:,}개")
        print(f"\n총 이슈 수: {summary['total_issues']:,}개")
        print(f"데이터 품질 점수: {summary['quality_score']:.1f}/100")

        if summary['quality_score'] >= 90:
            print("\n✅ 우수한 데이터 품질")
        elif summary['quality_score'] >= 70:
            print("\n⚠️  양호한 데이터 품질 (일부 개선 필요)")
        else:
            print("\n❌ 데이터 품질 개선 필요")

        # Save report if output directory specified
        if self.output_dir:
            self.save_report(summary)

        print("\n" + "=" * 80)


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(
        description="Check data quality of financial statements"
    )

    parser.add_argument(
        "--ticker",
        type=str,
        help="Check specific ticker only"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed issue information"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output directory for detailed reports"
    )

    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else None

    checker = DataQualityChecker(output_dir=output_dir, detailed=args.detailed)

    try:
        checker.run_all_checks(ticker=args.ticker)
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
