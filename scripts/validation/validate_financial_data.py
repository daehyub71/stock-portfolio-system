"""재무 데이터 정합성 검증.

검증 항목:
1. 재무상태표 등식: 자산 = 부채 + 자본
2. 손익계산서 일관성: 매출총이익 = 매출액 - 매출원가
3. JSONB 데이터 구조 검증
4. 필수 계정과목 존재 여부
5. 중복 재무제표 체크
"""

import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime
from typing import Dict, List

from sqlalchemy import func, and_

from db.connection import SessionLocal
from models import Stock, FinancialStatement


class FinancialDataValidator:
    """재무 데이터 검증기."""

    def __init__(self, tolerance: float = 0.01):
        """초기화.

        Args:
            tolerance: 등식 오차 허용범위 (1% = 0.01)
        """
        self.db = SessionLocal()
        self.tolerance = tolerance
        self.errors: Dict[str, List[Dict]] = {
            'balance_sheet_equation': [],
            'income_statement_equation': [],
            'empty_balance_sheet': [],
            'empty_income_statement': [],
            'missing_key_accounts': [],
            'duplicate_statements': []
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

    def _extract_balance_sheet_totals(self, bs: dict) -> tuple:
        """재무상태표에서 자산, 부채, 자본 총계 추출."""
        if not bs or not isinstance(bs, dict):
            return None, None, None

        # 자산 총계
        assets = bs.get('assets', {})
        if isinstance(assets, dict):
            current_assets = assets.get('current', {})
            total_assets = (
                current_assets.get('유동자산', 0) +
                current_assets.get('비유동자산', 0)
            )
            # 대체 키
            if total_assets == 0:
                total_assets = assets.get('자산총계', 0)
        else:
            total_assets = 0

        # 부채 총계
        liabilities = bs.get('liabilities', {})
        if isinstance(liabilities, dict):
            current_liabs = liabilities.get('current', {})
            total_liabilities = (
                current_liabs.get('유동부채', 0) +
                current_liabs.get('비유동부채', 0)
            )
            # 대체 키
            if total_liabilities == 0:
                total_liabilities = liabilities.get('부채총계', 0)
        else:
            total_liabilities = 0

        # 자본 총계
        equity = bs.get('equity', {})
        if isinstance(equity, dict):
            total_equity = equity.get('자본총계', 0)
        else:
            total_equity = 0

        return total_assets, total_liabilities, total_equity

    def validate_balance_sheet_equation(self):
        """재무상태표 등식 검증: 자산 = 부채 + 자본."""
        print("\n1️⃣  재무상태표 등식 검증 중...")

        statements = (
            self.db.query(FinancialStatement, Stock.ticker, Stock.name)
            .join(Stock, FinancialStatement.stock_id == Stock.id)
            .filter(FinancialStatement.fiscal_year.isnot(None))
            .all()
        )

        violation_count = 0

        for stmt, ticker, name in statements:
            assets, liabilities, equity = self._extract_balance_sheet_totals(
                stmt.balance_sheet
            )

            if assets is None or assets == 0:
                continue

            # 등식 검증: |자산 - (부채 + 자본)| / 자산 <= tolerance
            difference = abs(assets - (liabilities + equity))
            if assets > 0:
                error_rate = difference / assets
                if error_rate > self.tolerance:
                    violation_count += 1
                    self.errors['balance_sheet_equation'].append({
                        'ticker': ticker,
                        'name': name,
                        'fiscal_year': stmt.fiscal_year,
                        'fiscal_quarter': stmt.fiscal_quarter,
                        'assets': float(assets),
                        'liabilities': float(liabilities),
                        'equity': float(equity),
                        'difference': float(difference),
                        'error_rate': float(error_rate * 100),
                        'issue': f'자산≠부채+자본 (오차: {error_rate*100:.2f}%)'
                    })

        print(f"  등식 위반: {violation_count:,}건")
        return violation_count

    def validate_income_statement(self):
        """손익계산서 일관성 검증."""
        print("\n2️⃣  손익계산서 일관성 검증 중...")

        statements = (
            self.db.query(FinancialStatement, Stock.ticker, Stock.name)
            .join(Stock, FinancialStatement.stock_id == Stock.id)
            .filter(FinancialStatement.fiscal_year.isnot(None))
            .all()
        )

        violation_count = 0

        for stmt, ticker, name in statements:
            is_data = stmt.income_statement
            if not is_data or not isinstance(is_data, dict):
                continue

            # 매출액, 매출원가, 매출총이익 추출
            revenue = is_data.get('revenue', {})
            if isinstance(revenue, dict):
                sales = (
                    revenue.get('매출액', 0) or
                    revenue.get('영업수익', 0) or
                    revenue.get('수익(매출액)', 0)
                )
                cogs = revenue.get('매출원가', 0)
                gross_profit = revenue.get('매출총이익', 0)

                # 매출총이익 = 매출액 - 매출원가 검증
                if sales > 0 and cogs > 0 and gross_profit > 0:
                    expected_gross_profit = sales - cogs
                    difference = abs(gross_profit - expected_gross_profit)
                    error_rate = difference / sales if sales > 0 else 0

                    if error_rate > self.tolerance:
                        violation_count += 1
                        self.errors['income_statement_equation'].append({
                            'ticker': ticker,
                            'name': name,
                            'fiscal_year': stmt.fiscal_year,
                            'fiscal_quarter': stmt.fiscal_quarter,
                            'sales': float(sales),
                            'cogs': float(cogs),
                            'gross_profit': float(gross_profit),
                            'expected': float(expected_gross_profit),
                            'difference': float(difference),
                            'error_rate': float(error_rate * 100),
                            'issue': f'매출총이익≠매출액-매출원가 (오차: {error_rate*100:.2f}%)'
                        })

        print(f"  손익계산서 오류: {violation_count:,}건")
        return violation_count

    def validate_empty_statements(self):
        """빈 재무제표 검증."""
        print("\n3️⃣  빈 재무제표 검증 중...")

        statements = (
            self.db.query(FinancialStatement, Stock.ticker, Stock.name)
            .join(Stock, FinancialStatement.stock_id == Stock.id)
            .filter(FinancialStatement.fiscal_year.isnot(None))
            .all()
        )

        empty_bs_count = 0
        empty_is_count = 0

        for stmt, ticker, name in statements:
            # 빈 재무상태표
            if not stmt.balance_sheet or len(stmt.balance_sheet) == 0:
                empty_bs_count += 1
                self.errors['empty_balance_sheet'].append({
                    'ticker': ticker,
                    'name': name,
                    'fiscal_year': stmt.fiscal_year,
                    'fiscal_quarter': stmt.fiscal_quarter,
                    'issue': 'Empty balance sheet'
                })

            # 빈 손익계산서
            is_empty = (
                not stmt.income_statement or
                stmt.income_statement == {'profit': {}, 'revenue': {}, 'expenses': {}}
            )
            if is_empty:
                empty_is_count += 1
                self.errors['empty_income_statement'].append({
                    'ticker': ticker,
                    'name': name,
                    'fiscal_year': stmt.fiscal_year,
                    'fiscal_quarter': stmt.fiscal_quarter,
                    'issue': 'Empty income statement'
                })

        print(f"  빈 재무상태표: {empty_bs_count:,}건")
        print(f"  빈 손익계산서: {empty_is_count:,}건")

        return empty_bs_count + empty_is_count

    def validate_duplicates(self):
        """중복 재무제표 체크."""
        print("\n4️⃣  중복 재무제표 검증 중...")

        # stock_id + fiscal_year + fiscal_quarter로 그룹화하여 중복 체크
        duplicates = (
            self.db.query(
                FinancialStatement.stock_id,
                FinancialStatement.fiscal_year,
                FinancialStatement.fiscal_quarter,
                func.count(FinancialStatement.id).label('count')
            )
            .group_by(
                FinancialStatement.stock_id,
                FinancialStatement.fiscal_year,
                FinancialStatement.fiscal_quarter
            )
            .having(func.count(FinancialStatement.id) > 1)
            .all()
        )

        for stock_id, year, quarter, count in duplicates:
            stock = self.db.query(Stock).filter(Stock.id == stock_id).first()
            if stock:
                self.errors['duplicate_statements'].append({
                    'ticker': stock.ticker,
                    'name': stock.name,
                    'fiscal_year': year,
                    'fiscal_quarter': quarter,
                    'count': count,
                    'issue': f'{count} duplicate records'
                })

        dup_count = len(self.errors['duplicate_statements'])
        print(f"  중복 재무제표: {dup_count:,}건")

        return dup_count

    def run_validation(self) -> Dict:
        """전체 검증 실행."""
        print("=" * 80)
        print("📊 재무 데이터 정합성 검증")
        print("=" * 80)

        # 전체 레코드 수
        self.stats['total_records'] = self.db.query(
            func.count(FinancialStatement.id)
        ).filter(FinancialStatement.fiscal_year.isnot(None)).scalar()

        print(f"\n전체 재무제표: {self.stats['total_records']:,}건")
        print(f"오차 허용범위: {self.tolerance * 100}%")

        # 각 검증 실행
        error_counts = []
        error_counts.append(self.validate_balance_sheet_equation())
        error_counts.append(self.validate_income_statement())
        error_counts.append(self.validate_empty_statements())
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
        print(f"  전체 레코드:           {self.stats['total_records']:,}건")
        print(f"  오류 발견:             {self.stats['total_errors']:,}건")
        print(f"  오류율:                {self.stats['error_rate']:.4f}%")

        print(f"\n[오류 유형별 건수]")
        print(f"  재무상태표 등식 위반:  {len(self.errors['balance_sheet_equation']):,}건")
        print(f"  손익계산서 오류:       {len(self.errors['income_statement_equation']):,}건")
        print(f"  빈 재무상태표:         {len(self.errors['empty_balance_sheet']):,}건")
        print(f"  빈 손익계산서:         {len(self.errors['empty_income_statement']):,}건")
        print(f"  중복 재무제표:         {len(self.errors['duplicate_statements']):,}건")

        # 오류 샘플 출력 (각 유형별 최대 5개)
        if self.stats['total_errors'] > 0:
            print(f"\n[오류 샘플] (각 유형별 최대 5개)")
            print("-" * 80)

            for error_type, errors in self.errors.items():
                if errors:
                    print(f"\n{error_type}:")
                    for i, error in enumerate(errors[:5], 1):
                        quarter = f"Q{error['fiscal_quarter']}" if error.get('fiscal_quarter') else '연간'
                        print(
                            f"  {i}. {error['ticker']} {error['name']} "
                            f"{error['fiscal_year']}{quarter}: {error['issue']}"
                        )
                    if len(errors) > 5:
                        print(f"  ... 외 {len(errors) - 5}건")

        print("\n" + "=" * 80)

    def save_report(self, output_path: Path = None):
        """검증 리포트 저장."""
        if output_path is None:
            output_dir = Path("data/validation_reports")
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"financial_validation_{timestamp}.txt"

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("재무 데이터 정합성 검증 리포트\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"오차 허용범위: {self.tolerance * 100}%\n\n")

            # 전체 통계
            f.write("[전체 통계]\n")
            f.write(f"전체 레코드:           {self.stats['total_records']:,}건\n")
            f.write(f"오류 발견:             {self.stats['total_errors']:,}건\n")
            f.write(f"오류율:                {self.stats['error_rate']:.4f}%\n\n")

            # 오류 유형별 건수
            f.write("[오류 유형별 건수]\n")
            f.write(f"재무상태표 등식 위반:  {len(self.errors['balance_sheet_equation']):,}건\n")
            f.write(f"손익계산서 오류:       {len(self.errors['income_statement_equation']):,}건\n")
            f.write(f"빈 재무상태표:         {len(self.errors['empty_balance_sheet']):,}건\n")
            f.write(f"빈 손익계산서:         {len(self.errors['empty_income_statement']):,}건\n")
            f.write(f"중복 재무제표:         {len(self.errors['duplicate_statements']):,}건\n\n")

            # 상세 오류 목록
            for error_type, errors in self.errors.items():
                if errors:
                    f.write(f"\n[{error_type}] {len(errors):,}건\n")
                    f.write("-" * 80 + "\n")
                    for error in errors:
                        quarter = f"Q{error['fiscal_quarter']}" if error.get('fiscal_quarter') else '연간'
                        f.write(
                            f"{error['ticker']} {error['name']} "
                            f"{error['fiscal_year']}{quarter}: {error['issue']}\n"
                        )
                        if 'assets' in error:
                            f.write(
                                f"  자산: {error['assets']:,.0f}, "
                                f"부채: {error['liabilities']:,.0f}, "
                                f"자본: {error['equity']:,.0f}\n"
                            )
                        if 'sales' in error:
                            f.write(
                                f"  매출액: {error['sales']:,.0f}, "
                                f"매출원가: {error['cogs']:,.0f}, "
                                f"매출총이익: {error['gross_profit']:,.0f}\n"
                            )

        print(f"\n📄 검증 리포트 저장: {output_path}")


def main():
    """메인 실행 함수."""
    import argparse

    parser = argparse.ArgumentParser(description="재무 데이터 정합성 검증")
    parser.add_argument(
        '--tolerance',
        type=float,
        default=0.01,
        help="오차 허용범위 (기본: 0.01 = 1%%)"
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help="오류 자동 수정 (현재는 리포트만 생성)"
    )

    args = parser.parse_args()

    with FinancialDataValidator(tolerance=args.tolerance) as validator:
        validator.run_validation()
        validator.print_summary()
        validator.save_report()

        if args.fix:
            print("\n⚠️  자동 수정 기능은 아직 구현되지 않았습니다.")
            print("수동으로 데이터를 확인하고 수정해주세요.")

    print("\n✅ 검증 완료")


if __name__ == "__main__":
    main()
