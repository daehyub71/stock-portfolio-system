"""30개 랜덤 종목 재무비율 계산 및 품질 검증.

재무제표가 있는 종목 중 30개를 랜덤 샘플링하여:
1. 재무비율 계산 실행
2. 계산 결과 품질 검증
3. 이상치 및 오류 탐지
4. 상세 리포트 생성
"""

import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import func, and_

from db.connection import SessionLocal
from models import Stock, FinancialStatement, FinancialRatio
from calculators.financial_ratio_calculator import FinancialRatioCalculator


class RandomSampleValidator:
    """랜덤 샘플 재무비율 검증기."""

    def __init__(self, sample_size: int = 30):
        """
        Args:
            sample_size: 샘플링할 종목 수
        """
        self.sample_size = sample_size
        self.db = SessionLocal()
        self.calculator = FinancialRatioCalculator()

        # 검증 결과 저장
        self.results: Dict = {
            'total_stocks': 0,
            'total_quarters': 0,
            'successful_quarters': 0,
            'failed_quarters': 0,
            'stocks': [],
            'anomalies': [],
            'errors': []
        }

    def close(self):
        """데이터베이스 연결 종료."""
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def select_random_stocks(self) -> List[Stock]:
        """재무제표가 있는 종목 중 랜덤 샘플링.

        Returns:
            랜덤 선택된 종목 리스트
        """
        logger.info(f"Selecting {self.sample_size} random stocks with financial statements...")

        # 재무제표가 있는 종목만 선택
        stocks_with_financials = (
            self.db.query(Stock)
            .join(FinancialStatement, Stock.id == FinancialStatement.stock_id)
            .filter(Stock.is_active == True)
            .distinct()
            .all()
        )

        logger.info(f"Found {len(stocks_with_financials)} stocks with financial statements")

        if len(stocks_with_financials) < self.sample_size:
            logger.warning(
                f"Only {len(stocks_with_financials)} stocks available, "
                f"selecting all instead of {self.sample_size}"
            )
            return stocks_with_financials

        # 랜덤 샘플링
        random_stocks = random.sample(stocks_with_financials, self.sample_size)

        logger.info(f"Selected {len(random_stocks)} random stocks")
        return random_stocks

    def calculate_stock_ratios(self, stock: Stock) -> Dict:
        """종목의 모든 분기 재무비율 계산.

        Args:
            stock: 종목 객체

        Returns:
            계산 결과 딕셔너리
        """
        result = {
            'ticker': stock.ticker,
            'name': stock.name,
            'market': stock.market.value,
            'quarters': [],
            'total_quarters': 0,
            'successful_quarters': 0,
            'failed_quarters': 0,
            'anomalies': []
        }

        # 재무제표 조회 (최근 3년)
        statements = (
            self.db.query(FinancialStatement)
            .filter(FinancialStatement.stock_id == stock.id)
            .order_by(
                FinancialStatement.fiscal_year.desc(),
                FinancialStatement.fiscal_quarter.desc()
            )
            .all()
        )

        result['total_quarters'] = len(statements)

        for stmt in statements:
            quarter_result = self._calculate_quarter(stock, stmt)
            result['quarters'].append(quarter_result)

            if quarter_result['success']:
                result['successful_quarters'] += 1
            else:
                result['failed_quarters'] += 1

            # 이상치 탐지
            anomalies = self._detect_anomalies(quarter_result)
            if anomalies:
                result['anomalies'].extend(anomalies)

        return result

    def _calculate_quarter(self, stock: Stock, stmt: FinancialStatement) -> Dict:
        """단일 분기 재무비율 계산.

        Args:
            stock: 종목 객체
            stmt: 재무제표 객체

        Returns:
            분기 계산 결과
        """
        quarter_label = (
            f"{stmt.fiscal_year}Q{stmt.fiscal_quarter}"
            if stmt.fiscal_quarter
            else f"{stmt.fiscal_year}연간"
        )

        result = {
            'fiscal_year': stmt.fiscal_year,
            'fiscal_quarter': stmt.fiscal_quarter,
            'label': quarter_label,
            'success': False,
            'ratios': {},
            'error': None
        }

        try:
            # 전기 재무제표 조회 (성장률 계산용)
            prev_stmt = self._get_previous_statement(stock.id, stmt)

            # 재무비율 계산
            ratios = self.calculator.calculate_all_ratios(
                balance_sheet=stmt.balance_sheet,
                income_statement=stmt.income_statement,
                prev_balance_sheet=prev_stmt.balance_sheet if prev_stmt else None,
                prev_income_statement=prev_stmt.income_statement if prev_stmt else None
            )

            result['ratios'] = {k: float(v) if v else None for k, v in ratios.items()}
            result['success'] = True

            # 계산된 비율 수 카운트
            calculated_count = sum(1 for v in ratios.values() if v is not None)
            result['calculated_count'] = calculated_count

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"{stock.ticker} {quarter_label} calculation failed: {e}")

        return result

    def _get_previous_statement(
        self,
        stock_id: int,
        current_stmt: FinancialStatement
    ) -> Optional[FinancialStatement]:
        """전기 재무제표 조회.

        Args:
            stock_id: 종목 ID
            current_stmt: 현재 재무제표

        Returns:
            전기 재무제표 또는 None
        """
        if current_stmt.fiscal_quarter:
            # 분기 보고서: 전년 동분기
            prev_year = current_stmt.fiscal_year - 1
            prev_quarter = current_stmt.fiscal_quarter
        else:
            # 연간 보고서: 전년 연간
            prev_year = current_stmt.fiscal_year - 1
            prev_quarter = None

        prev_stmt = (
            self.db.query(FinancialStatement)
            .filter(
                and_(
                    FinancialStatement.stock_id == stock_id,
                    FinancialStatement.fiscal_year == prev_year,
                    FinancialStatement.fiscal_quarter == prev_quarter
                )
            )
            .first()
        )

        return prev_stmt

    def _detect_anomalies(self, quarter_result: Dict) -> List[Dict]:
        """이상치 탐지.

        Args:
            quarter_result: 분기 계산 결과

        Returns:
            이상치 리스트
        """
        anomalies = []
        ratios = quarter_result.get('ratios', {})

        if not ratios:
            return anomalies

        # 이상치 탐지 규칙
        checks = [
            ('gross_profit_margin', 0, 100, '매출총이익률이 0-100% 범위를 벗어남'),
            ('operating_profit_margin', -100, 100, '영업이익률이 정상 범위를 벗어남'),
            ('net_profit_margin', -100, 100, '순이익률이 정상 범위를 벗어남'),
            ('roa', -50, 50, 'ROA가 정상 범위를 벗어남'),
            ('current_ratio', 0, 1000, '유동비율이 정상 범위를 벗어남'),
            ('debt_ratio', 0, 1000, '부채비율이 정상 범위를 벗어남'),
            ('equity_ratio', 0, 100, '자기자본비율이 0-100% 범위를 벗어남'),
        ]

        for ratio_name, min_val, max_val, message in checks:
            value = ratios.get(ratio_name)
            if value is not None and (value < min_val or value > max_val):
                anomalies.append({
                    'quarter': quarter_result['label'],
                    'ratio': ratio_name,
                    'value': value,
                    'expected_range': f'{min_val}~{max_val}',
                    'message': message
                })

        return anomalies

    def save_ratios_to_db(self, stock: Stock, quarter_result: Dict):
        """계산된 재무비율을 DB에 저장.

        Args:
            stock: 종목 객체
            quarter_result: 분기 계산 결과
        """
        if not quarter_result['success']:
            return

        fiscal_year = quarter_result['fiscal_year']
        fiscal_quarter = quarter_result['fiscal_quarter']
        ratios = quarter_result['ratios']

        # 기존 레코드 조회
        existing = (
            self.db.query(FinancialRatio)
            .filter(
                and_(
                    FinancialRatio.stock_id == stock.id,
                    FinancialRatio.fiscal_year == fiscal_year,
                    FinancialRatio.fiscal_quarter == fiscal_quarter
                )
            )
            .first()
        )

        if existing:
            # 업데이트
            for key, value in ratios.items():
                if value is not None and hasattr(existing, key):
                    setattr(existing, key, value)
            logger.debug(f"Updated {stock.ticker} {quarter_result['label']}")
        else:
            # 신규 생성
            ratio_obj = FinancialRatio(
                stock_id=stock.id,
                fiscal_year=fiscal_year,
                fiscal_quarter=fiscal_quarter,
                **ratios
            )
            self.db.add(ratio_obj)
            logger.debug(f"Created {stock.ticker} {quarter_result['label']}")

        self.db.commit()

    def run_validation(self, save_to_db: bool = True) -> Dict:
        """전체 검증 실행.

        Args:
            save_to_db: 계산 결과를 DB에 저장할지 여부

        Returns:
            검증 결과 딕셔너리
        """
        logger.info("=" * 80)
        logger.info(f"Starting random sample validation (size={self.sample_size})")
        logger.info("=" * 80)

        # 랜덤 종목 선택
        stocks = self.select_random_stocks()
        self.results['total_stocks'] = len(stocks)

        # 각 종목별 계산
        for i, stock in enumerate(stocks, 1):
            logger.info(f"\n[{i}/{len(stocks)}] Processing {stock.ticker} {stock.name}...")

            try:
                stock_result = self.calculate_stock_ratios(stock)
                self.results['stocks'].append(stock_result)

                # DB 저장
                if save_to_db:
                    for quarter_result in stock_result['quarters']:
                        self.save_ratios_to_db(stock, quarter_result)

                # 통계 업데이트
                self.results['total_quarters'] += stock_result['total_quarters']
                self.results['successful_quarters'] += stock_result['successful_quarters']
                self.results['failed_quarters'] += stock_result['failed_quarters']

                # 이상치 수집
                if stock_result['anomalies']:
                    self.results['anomalies'].extend([
                        {
                            'ticker': stock.ticker,
                            'name': stock.name,
                            **anomaly
                        }
                        for anomaly in stock_result['anomalies']
                    ])

                logger.info(
                    f"  ✓ {stock.ticker}: {stock_result['successful_quarters']}/"
                    f"{stock_result['total_quarters']} quarters successful"
                )

            except Exception as e:
                error_msg = f"{stock.ticker} {stock.name}: {str(e)}"
                self.results['errors'].append(error_msg)
                logger.error(f"  ✗ {error_msg}")

        logger.info("\n" + "=" * 80)
        logger.info("Validation completed")
        logger.info("=" * 80)

        return self.results

    def print_summary(self):
        """검증 결과 요약 출력."""
        results = self.results

        print("\n" + "=" * 80)
        print("📊 랜덤 샘플 검증 결과")
        print("=" * 80)

        print(f"\n[전체 통계]")
        print(f"  검증 종목:       {results['total_stocks']}개")
        print(f"  총 분기:         {results['total_quarters']}개")
        print(f"  성공:            {results['successful_quarters']}개")
        print(f"  실패:            {results['failed_quarters']}개")

        if results['total_quarters'] > 0:
            success_rate = (results['successful_quarters'] / results['total_quarters']) * 100
            print(f"  성공률:          {success_rate:.1f}%")

        # 종목별 상세 결과
        print(f"\n[종목별 결과]")
        for stock_result in results['stocks']:
            status = "✅" if stock_result['failed_quarters'] == 0 else "⚠️"
            print(
                f"  {status} {stock_result['ticker']:6} {stock_result['name']:15} "
                f"({stock_result['market']:6}) | "
                f"{stock_result['successful_quarters']}/{stock_result['total_quarters']} 분기 성공"
            )

            if stock_result['anomalies']:
                print(f"      이상치: {len(stock_result['anomalies'])}건")

        # 이상치 리포트
        if results['anomalies']:
            print(f"\n[이상치 탐지] {len(results['anomalies'])}건")
            print("-" * 80)

            # 최대 10개만 출력
            for i, anomaly in enumerate(results['anomalies'][:10], 1):
                print(
                    f"  {i}. {anomaly['ticker']} {anomaly['quarter']}: "
                    f"{anomaly['ratio']}={anomaly['value']:.2f} "
                    f"(정상범위: {anomaly['expected_range']})"
                )

            if len(results['anomalies']) > 10:
                print(f"  ... 외 {len(results['anomalies']) - 10}건")

        # 에러 리포트
        if results['errors']:
            print(f"\n[에러 발생] {len(results['errors'])}건")
            print("-" * 80)
            for i, error in enumerate(results['errors'][:5], 1):
                print(f"  {i}. {error}")

            if len(results['errors']) > 5:
                print(f"  ... 외 {len(results['errors']) - 5}건")

        print("\n" + "=" * 80)

    def save_report(self, output_path: Optional[Path] = None):
        """검증 결과를 파일로 저장.

        Args:
            output_path: 출력 파일 경로 (기본: data/validation_reports/)
        """
        if output_path is None:
            output_dir = Path("data/validation_reports")
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"random_sample_validation_{timestamp}.txt"

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("랜덤 샘플 재무비율 검증 리포트\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"샘플 크기: {self.sample_size}개 종목\n\n")

            # 전체 통계
            f.write("[전체 통계]\n")
            f.write(f"검증 종목:       {self.results['total_stocks']}개\n")
            f.write(f"총 분기:         {self.results['total_quarters']}개\n")
            f.write(f"성공:            {self.results['successful_quarters']}개\n")
            f.write(f"실패:            {self.results['failed_quarters']}개\n")

            if self.results['total_quarters'] > 0:
                success_rate = (
                    self.results['successful_quarters'] /
                    self.results['total_quarters']
                ) * 100
                f.write(f"성공률:          {success_rate:.1f}%\n\n")

            # 종목별 상세
            f.write("\n[종목별 상세 결과]\n")
            f.write("-" * 80 + "\n")

            for stock_result in self.results['stocks']:
                f.write(
                    f"\n{stock_result['ticker']} {stock_result['name']} "
                    f"({stock_result['market']})\n"
                )
                f.write(
                    f"  성공: {stock_result['successful_quarters']}/"
                    f"{stock_result['total_quarters']} 분기\n"
                )

                # 분기별 상세
                for quarter in stock_result['quarters']:
                    status = "✅" if quarter['success'] else "❌"
                    f.write(f"    {status} {quarter['label']}")

                    if quarter['success']:
                        calculated = quarter.get('calculated_count', 0)
                        f.write(f" - {calculated}/10 지표 계산\n")

                        # 주요 지표 출력
                        ratios = quarter['ratios']
                        if ratios.get('roa'):
                            f.write(f"        ROA: {ratios['roa']:.2f}%")
                        if ratios.get('operating_profit_margin'):
                            f.write(f", 영업이익률: {ratios['operating_profit_margin']:.2f}%")
                        if ratios.get('debt_ratio'):
                            f.write(f", 부채비율: {ratios['debt_ratio']:.2f}%")
                        f.write("\n")
                    else:
                        f.write(f" - Error: {quarter.get('error', 'Unknown')}\n")

                # 이상치
                if stock_result['anomalies']:
                    f.write(f"  ⚠️  이상치: {len(stock_result['anomalies'])}건\n")
                    for anomaly in stock_result['anomalies']:
                        f.write(
                            f"      {anomaly['quarter']} {anomaly['ratio']}: "
                            f"{anomaly['value']:.2f} (범위: {anomaly['expected_range']})\n"
                        )

            # 이상치 전체 목록
            if self.results['anomalies']:
                f.write("\n\n[이상치 전체 목록]\n")
                f.write("-" * 80 + "\n")
                for anomaly in self.results['anomalies']:
                    f.write(
                        f"{anomaly['ticker']} {anomaly['name']} {anomaly['quarter']}: "
                        f"{anomaly['ratio']}={anomaly['value']:.2f} "
                        f"({anomaly['message']})\n"
                    )

            # 에러 전체 목록
            if self.results['errors']:
                f.write("\n\n[에러 전체 목록]\n")
                f.write("-" * 80 + "\n")
                for error in self.results['errors']:
                    f.write(f"{error}\n")

        logger.info(f"Report saved to: {output_path}")
        print(f"\n📄 상세 리포트 저장: {output_path}")


def main():
    """메인 실행 함수."""
    import argparse

    parser = argparse.ArgumentParser(
        description="30개 랜덤 종목 재무비율 계산 및 품질 검증"
    )
    parser.add_argument(
        '--sample-size',
        type=int,
        default=30,
        help="샘플링할 종목 수 (기본: 30)"
    )
    parser.add_argument(
        '--no-save',
        action='store_true',
        help="DB에 저장하지 않고 검증만 수행"
    )
    parser.add_argument(
        '--seed',
        type=int,
        help="랜덤 시드 (재현 가능한 샘플링)"
    )

    args = parser.parse_args()

    # 랜덤 시드 설정
    if args.seed:
        random.seed(args.seed)
        logger.info(f"Random seed set to: {args.seed}")

    # 검증 실행
    with RandomSampleValidator(sample_size=args.sample_size) as validator:
        results = validator.run_validation(save_to_db=not args.no_save)
        validator.print_summary()
        validator.save_report()

    logger.info("\n✅ Validation completed successfully")


if __name__ == "__main__":
    main()
