"""결측치 탐지 스크립트.

시세 데이터, 재무제표, 재무비율의 결측치를 탐지하고 분석합니다.

Usage:
    python scripts/missing_data/detect_missing_data.py
    python scripts/missing_data/detect_missing_data.py --data-type price
    python scripts/missing_data/detect_missing_data.py --data-type financial
    python scripts/missing_data/detect_missing_data.py --data-type ratio
    python scripts/missing_data/detect_missing_data.py --output-dir data/missing_data_reports
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple
from collections import defaultdict

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from models import Stock, DailyPrice, FinancialStatement, FinancialRatio
from sqlalchemy import func, and_, or_, text, distinct


class MissingDataDetector:
    """결측치 탐지 클래스."""

    def __init__(self):
        """초기화."""
        self.db = SessionLocal()
        self.missing_data = {
            'price': {},
            'financial': {},
            'ratio': {}
        }

    def close(self):
        """데이터베이스 연결 종료."""
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def detect_price_missing_data(self) -> Dict[str, Any]:
        """시세 데이터 결측치 탐지.

        Returns:
            결측치 정보 딕셔너리
        """
        print("\n1️⃣  시세 데이터 결측치 탐지 중...")

        # 전체 종목 수
        total_stocks = self.db.query(func.count(Stock.id)).filter(
            Stock.is_active == True
        ).scalar()

        # 시세 데이터가 있는 종목 수
        stocks_with_prices = self.db.query(
            func.count(distinct(DailyPrice.stock_id))
        ).scalar()

        # 시세 데이터가 없는 종목 수
        stocks_without_prices = total_stocks - stocks_with_prices

        # 시세 데이터가 없는 종목 리스트 (상위 20개)
        stocks_no_price = (
            self.db.query(Stock.ticker, Stock.name, Stock.market)
            .outerjoin(DailyPrice, Stock.id == DailyPrice.stock_id)
            .filter(Stock.is_active == True, DailyPrice.id == None)
            .limit(20)
            .all()
        )

        # 날짜 범위별 결측치 분석
        # 최소/최대 날짜
        date_range = self.db.query(
            func.min(DailyPrice.date),
            func.max(DailyPrice.date)
        ).first()

        min_date, max_date = date_range if date_range else (None, None)

        # 종목별 시세 레코드 수 통계
        price_count_stats = self.db.query(
            func.count(DailyPrice.id).label('price_count'),
            func.count(distinct(DailyPrice.stock_id)).label('stock_count')
        ).first()

        total_prices = price_count_stats.price_count if price_count_stats else 0
        avg_prices_per_stock = (
            total_prices / stocks_with_prices if stocks_with_prices > 0 else 0
        )

        # 시세 레코드가 적은 종목 (평균의 50% 미만)
        threshold = avg_prices_per_stock * 0.5
        stocks_low_prices = (
            self.db.query(
                Stock.ticker,
                Stock.name,
                func.count(DailyPrice.id).label('price_count')
            )
            .join(DailyPrice, Stock.id == DailyPrice.stock_id)
            .filter(Stock.is_active == True)
            .group_by(Stock.id, Stock.ticker, Stock.name)
            .having(func.count(DailyPrice.id) < threshold)
            .order_by(func.count(DailyPrice.id))
            .limit(20)
            .all()
        )

        # 거래일 연속성 체크 (gap 분석)
        # 5일 이상 시세 누락된 케이스 찾기 (간략 버전)
        gaps = self._find_price_gaps(limit=20)

        result = {
            'total_stocks': total_stocks,
            'stocks_with_prices': stocks_with_prices,
            'stocks_without_prices': stocks_without_prices,
            'stocks_no_price_list': stocks_no_price,
            'date_range': (min_date, max_date),
            'total_prices': total_prices,
            'avg_prices_per_stock': avg_prices_per_stock,
            'stocks_low_prices': stocks_low_prices,
            'price_gaps': gaps,
            'coverage_rate': (
                stocks_with_prices / total_stocks * 100
            ) if total_stocks > 0 else 0
        }

        self.missing_data['price'] = result

        print(f"  완료: {total_stocks}개 종목 분석")
        print(f"  시세 있음: {stocks_with_prices}개 ({result['coverage_rate']:.2f}%)")
        print(f"  시세 없음: {stocks_without_prices}개")
        print(f"  평균 시세 레코드: {avg_prices_per_stock:.0f}건/종목")

        return result

    def _find_price_gaps(self, limit: int = 20) -> List[Dict[str, Any]]:
        """시세 데이터 gap 찾기 (간략 버전).

        Args:
            limit: 반환할 최대 gap 수

        Returns:
            gap 정보 리스트
        """
        # 각 종목별로 날짜 간격이 5일 이상인 케이스 찾기
        # PostgreSQL LAG 함수 사용
        query = text("""
            WITH price_with_prev AS (
                SELECT
                    dp.stock_id,
                    s.ticker,
                    s.name,
                    dp.date,
                    LAG(dp.date) OVER (PARTITION BY dp.stock_id ORDER BY dp.date) AS prev_date
                FROM daily_prices dp
                JOIN stocks s ON dp.stock_id = s.id
                WHERE s.is_active = true
            ),
            gaps AS (
                SELECT
                    stock_id,
                    ticker,
                    name,
                    prev_date,
                    date,
                    date - prev_date AS gap_days
                FROM price_with_prev
                WHERE prev_date IS NOT NULL
                  AND date - prev_date > 5
            )
            SELECT
                ticker,
                name,
                prev_date,
                date,
                gap_days
            FROM gaps
            ORDER BY gap_days DESC
            LIMIT :limit
        """)

        result = self.db.execute(query, {'limit': limit}).fetchall()

        gaps = []
        for row in result:
            gaps.append({
                'ticker': row.ticker,
                'name': row.name,
                'prev_date': row.prev_date,
                'current_date': row.date,
                'gap_days': row.gap_days
            })

        return gaps

    def detect_financial_missing_data(self) -> Dict[str, Any]:
        """재무제표 데이터 결측치 탐지.

        Returns:
            결측치 정보 딕셔너리
        """
        print("\n2️⃣  재무제표 데이터 결측치 탐지 중...")

        # 전체 종목 수
        total_stocks = self.db.query(func.count(Stock.id)).filter(
            Stock.is_active == True
        ).scalar()

        # 재무제표가 있는 종목 수
        stocks_with_financials = self.db.query(
            func.count(distinct(FinancialStatement.stock_id))
        ).scalar()

        # 재무제표가 없는 종목 수
        stocks_without_financials = total_stocks - stocks_with_financials

        # 재무제표가 없는 종목 리스트 (상위 20개)
        stocks_no_financial = (
            self.db.query(Stock.ticker, Stock.name, Stock.market)
            .outerjoin(FinancialStatement, Stock.id == FinancialStatement.stock_id)
            .filter(Stock.is_active == True, FinancialStatement.id == None)
            .limit(20)
            .all()
        )

        # 재무제표 통계
        total_statements = self.db.query(func.count(FinancialStatement.id)).filter(
            FinancialStatement.fiscal_year.isnot(None)
        ).scalar()

        avg_statements_per_stock = (
            total_statements / stocks_with_financials
            if stocks_with_financials > 0 else 0
        )

        # 재무제표 레코드가 적은 종목 (평균의 50% 미만)
        threshold = avg_statements_per_stock * 0.5
        stocks_low_financials = (
            self.db.query(
                Stock.ticker,
                Stock.name,
                func.count(FinancialStatement.id).label('stmt_count')
            )
            .join(FinancialStatement, Stock.id == FinancialStatement.stock_id)
            .filter(
                Stock.is_active == True,
                FinancialStatement.fiscal_year.isnot(None)
            )
            .group_by(Stock.id, Stock.ticker, Stock.name)
            .having(func.count(FinancialStatement.id) < threshold)
            .order_by(func.count(FinancialStatement.id))
            .limit(20)
            .all()
        )

        # JSONB 필드 내부 결측치 분석
        # 빈 재무상태표
        empty_balance_sheet = self.db.execute(
            text("""
                SELECT COUNT(*)
                FROM financial_statements
                WHERE balance_sheet = '{}'::jsonb
                  AND fiscal_year IS NOT NULL
            """)
        ).scalar()

        # 빈 손익계산서
        empty_income_statement = self.db.execute(
            text("""
                SELECT COUNT(*)
                FROM financial_statements
                WHERE income_statement = '{"profit": {}, "revenue": {}, "expenses": {}}'::jsonb
                  AND fiscal_year IS NOT NULL
            """)
        ).scalar()

        # 빈 현금흐름표
        empty_cash_flow = self.db.execute(
            text("""
                SELECT COUNT(*)
                FROM financial_statements
                WHERE cash_flow = '{}'::jsonb
                  AND fiscal_year IS NOT NULL
            """)
        ).scalar()

        result = {
            'total_stocks': total_stocks,
            'stocks_with_financials': stocks_with_financials,
            'stocks_without_financials': stocks_without_financials,
            'stocks_no_financial_list': stocks_no_financial,
            'total_statements': total_statements,
            'avg_statements_per_stock': avg_statements_per_stock,
            'stocks_low_financials': stocks_low_financials,
            'empty_balance_sheet': empty_balance_sheet,
            'empty_income_statement': empty_income_statement,
            'empty_cash_flow': empty_cash_flow,
            'coverage_rate': (
                stocks_with_financials / total_stocks * 100
            ) if total_stocks > 0 else 0
        }

        self.missing_data['financial'] = result

        print(f"  완료: {total_stocks}개 종목 분석")
        print(f"  재무제표 있음: {stocks_with_financials}개 ({result['coverage_rate']:.2f}%)")
        print(f"  재무제표 없음: {stocks_without_financials}개")
        print(f"  평균 재무제표 레코드: {avg_statements_per_stock:.1f}건/종목")

        return result

    def detect_ratio_missing_data(self) -> Dict[str, Any]:
        """재무비율 데이터 결측치 탐지.

        Returns:
            결측치 정보 딕셔너리
        """
        print("\n3️⃣  재무비율 데이터 결측치 탐지 중...")

        # 전체 종목 수
        total_stocks = self.db.query(func.count(Stock.id)).filter(
            Stock.is_active == True
        ).scalar()

        # 재무비율이 있는 종목 수
        stocks_with_ratios = self.db.query(
            func.count(distinct(FinancialRatio.stock_id))
        ).scalar()

        # 재무비율이 없는 종목 수
        stocks_without_ratios = total_stocks - stocks_with_ratios

        # 재무비율이 없는 종목 리스트 (상위 20개)
        stocks_no_ratio = (
            self.db.query(Stock.ticker, Stock.name, Stock.market)
            .outerjoin(FinancialRatio, Stock.id == FinancialRatio.stock_id)
            .filter(Stock.is_active == True, FinancialRatio.id == None)
            .limit(20)
            .all()
        )

        # 재무비율 통계
        total_ratios = self.db.query(func.count(FinancialRatio.id)).filter(
            FinancialRatio.fiscal_year.isnot(None)
        ).scalar()

        avg_ratios_per_stock = (
            total_ratios / stocks_with_ratios
            if stocks_with_ratios > 0 else 0
        )

        # 주요 비율별 NULL 비율 분석
        key_ratios = [
            'roa', 'roe', 'roic',
            'gross_profit_margin', 'operating_profit_margin', 'net_profit_margin',
            'debt_ratio', 'current_ratio', 'equity_ratio',
            'asset_turnover', 'revenue_growth'
        ]

        null_stats = {}
        for ratio_name in key_ratios:
            non_null_count = self.db.query(func.count(FinancialRatio.id)).filter(
                FinancialRatio.fiscal_year.isnot(None),
                getattr(FinancialRatio, ratio_name).isnot(None)
            ).scalar()

            null_count = total_ratios - non_null_count
            null_rate = (null_count / total_ratios * 100) if total_ratios > 0 else 0

            null_stats[ratio_name] = {
                'non_null': non_null_count,
                'null': null_count,
                'null_rate': null_rate
            }

        # 전체 NULL 비율 (모든 비율 필드)
        total_fields = len(key_ratios)
        total_checks = total_ratios * total_fields
        total_nulls = sum(stats['null'] for stats in null_stats.values())
        overall_null_rate = (total_nulls / total_checks * 100) if total_checks > 0 else 0

        result = {
            'total_stocks': total_stocks,
            'stocks_with_ratios': stocks_with_ratios,
            'stocks_without_ratios': stocks_without_ratios,
            'stocks_no_ratio_list': stocks_no_ratio,
            'total_ratios': total_ratios,
            'avg_ratios_per_stock': avg_ratios_per_stock,
            'null_stats': null_stats,
            'total_nulls': total_nulls,
            'overall_null_rate': overall_null_rate,
            'coverage_rate': (
                stocks_with_ratios / total_stocks * 100
            ) if total_stocks > 0 else 0
        }

        self.missing_data['ratio'] = result

        print(f"  완료: {total_stocks}개 종목 분석")
        print(f"  재무비율 있음: {stocks_with_ratios}개 ({result['coverage_rate']:.2f}%)")
        print(f"  재무비율 없음: {stocks_without_ratios}개")
        print(f"  전체 NULL 비율: {overall_null_rate:.2f}%")

        return result

    def generate_report(self, output_path: Path = None) -> Path:
        """결측치 분석 리포트 생성.

        Args:
            output_path: 출력 파일 경로

        Returns:
            생성된 리포트 파일 경로
        """
        if output_path is None:
            output_dir = Path("data/missing_data_reports")
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"missing_data_report_{timestamp}.txt"

        price_data = self.missing_data['price']
        financial_data = self.missing_data['financial']
        ratio_data = self.missing_data['ratio']

        with open(output_path, 'w', encoding='utf-8') as f:
            # 헤더
            f.write("=" * 80 + "\n")
            f.write("📊 결측치 탐지 리포트\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"분석 대상: 시세 데이터, 재무제표, 재무비율\n\n")

            # 전체 요약
            f.write("=" * 80 + "\n")
            f.write("📋 전체 요약\n")
            f.write("=" * 80 + "\n\n")

            total_stocks = price_data['total_stocks']
            f.write(f"전체 종목 수:        {total_stocks:,}개\n\n")

            f.write(f"[데이터 유형별 커버리지]\n")
            f.write(f"시세 데이터:         {price_data['stocks_with_prices']:,}개 " +
                   f"({price_data['coverage_rate']:.2f}%)\n")
            f.write(f"재무제표:            {financial_data['stocks_with_financials']:,}개 " +
                   f"({financial_data['coverage_rate']:.2f}%)\n")
            f.write(f"재무비율:            {ratio_data['stocks_with_ratios']:,}개 " +
                   f"({ratio_data['coverage_rate']:.2f}%)\n\n")

            # 1. 시세 데이터 결측치
            f.write("\n" + "=" * 80 + "\n")
            f.write("1️⃣  시세 데이터 결측치 분석\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"[전체 통계]\n")
            f.write(f"시세 있는 종목:      {price_data['stocks_with_prices']:,}개\n")
            f.write(f"시세 없는 종목:      {price_data['stocks_without_prices']:,}개\n")
            f.write(f"커버리지:            {price_data['coverage_rate']:.2f}%\n")
            f.write(f"전체 시세 레코드:    {price_data['total_prices']:,}건\n")
            f.write(f"평균 레코드/종목:    {price_data['avg_prices_per_stock']:.0f}건\n\n")

            if price_data['date_range'][0] and price_data['date_range'][1]:
                f.write(f"[시세 데이터 기간]\n")
                f.write(f"시작일:              {price_data['date_range'][0]}\n")
                f.write(f"종료일:              {price_data['date_range'][1]}\n")
                days_diff = (price_data['date_range'][1] - price_data['date_range'][0]).days
                f.write(f"기간:                {days_diff:,}일\n\n")

            # 시세 없는 종목
            if price_data['stocks_no_price_list']:
                f.write(f"[시세 없는 종목 (상위 20개)]\n")
                for ticker, name, market in price_data['stocks_no_price_list']:
                    f.write(f"  {ticker:6} {name:20} ({market.value})\n")
                f.write("\n")

            # 시세 레코드 적은 종목
            if price_data['stocks_low_prices']:
                f.write(f"[시세 레코드 부족 종목 (평균의 50% 미만, 상위 20개)]\n")
                for ticker, name, count in price_data['stocks_low_prices']:
                    f.write(f"  {ticker:6} {name:20} {count:4}건\n")
                f.write("\n")

            # 시세 gap
            if price_data['price_gaps']:
                f.write(f"[시세 데이터 Gap (5일 이상 누락, 상위 20개)]\n")
                for gap in price_data['price_gaps']:
                    f.write(f"  {gap['ticker']:6} {gap['name']:20} " +
                           f"{gap['prev_date']} → {gap['current_date']} " +
                           f"({gap['gap_days']}일 누락)\n")
                f.write("\n")

            # 2. 재무제표 결측치
            f.write("\n" + "=" * 80 + "\n")
            f.write("2️⃣  재무제표 결측치 분석\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"[전체 통계]\n")
            f.write(f"재무제표 있는 종목:  {financial_data['stocks_with_financials']:,}개\n")
            f.write(f"재무제표 없는 종목:  {financial_data['stocks_without_financials']:,}개\n")
            f.write(f"커버리지:            {financial_data['coverage_rate']:.2f}%\n")
            f.write(f"전체 재무제표:       {financial_data['total_statements']:,}건\n")
            f.write(f"평균 재무제표/종목:  {financial_data['avg_statements_per_stock']:.1f}건\n\n")

            f.write(f"[JSONB 필드 결측치]\n")
            f.write(f"빈 재무상태표:       {financial_data['empty_balance_sheet']:,}건\n")
            f.write(f"빈 손익계산서:       {financial_data['empty_income_statement']:,}건\n")
            f.write(f"빈 현금흐름표:       {financial_data['empty_cash_flow']:,}건\n\n")

            # 재무제표 없는 종목
            if financial_data['stocks_no_financial_list']:
                f.write(f"[재무제표 없는 종목 (상위 20개)]\n")
                for ticker, name, market in financial_data['stocks_no_financial_list']:
                    f.write(f"  {ticker:6} {name:20} ({market.value})\n")
                f.write("\n")

            # 재무제표 레코드 적은 종목
            if financial_data['stocks_low_financials']:
                f.write(f"[재무제표 레코드 부족 종목 (평균의 50% 미만, 상위 20개)]\n")
                for ticker, name, count in financial_data['stocks_low_financials']:
                    f.write(f"  {ticker:6} {name:20} {count:2}건\n")
                f.write("\n")

            # 3. 재무비율 결측치
            f.write("\n" + "=" * 80 + "\n")
            f.write("3️⃣  재무비율 결측치 분석\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"[전체 통계]\n")
            f.write(f"재무비율 있는 종목:  {ratio_data['stocks_with_ratios']:,}개\n")
            f.write(f"재무비율 없는 종목:  {ratio_data['stocks_without_ratios']:,}개\n")
            f.write(f"커버리지:            {ratio_data['coverage_rate']:.2f}%\n")
            f.write(f"전체 재무비율:       {ratio_data['total_ratios']:,}건\n")
            f.write(f"평균 재무비율/종목:  {ratio_data['avg_ratios_per_stock']:.1f}건\n")
            f.write(f"전체 NULL 비율:      {ratio_data['overall_null_rate']:.2f}%\n\n")

            # 비율별 NULL 통계
            f.write(f"[비율별 NULL 통계]\n")
            for ratio_name, stats in ratio_data['null_stats'].items():
                status = '✅' if stats['null_rate'] < 10 else '⚠️' if stats['null_rate'] < 50 else '❌'
                f.write(f"{status} {ratio_name:25} NULL: {stats['null']:5,}건 " +
                       f"({stats['null_rate']:5.1f}%)\n")
            f.write("\n")

            # 재무비율 없는 종목
            if ratio_data['stocks_no_ratio_list']:
                f.write(f"[재무비율 없는 종목 (상위 20개)]\n")
                for ticker, name, market in ratio_data['stocks_no_ratio_list']:
                    f.write(f"  {ticker:6} {name:20} ({market.value})\n")
                f.write("\n")

            # 권장사항
            f.write("\n" + "=" * 80 + "\n")
            f.write("🔧 결측치 처리 권장사항\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"[우선순위 1: 시세 데이터]\n")
            f.write(f"1. 시세 없는 종목 {price_data['stocks_without_prices']}개 재수집\n")
            f.write(f"   - pykrx 재수집 스크립트 실행\n")
            f.write(f"2. 시세 gap 보간 (선형 보간 또는 forward fill)\n")
            f.write(f"   - scripts/missing_data/interpolate_prices.py\n\n")

            f.write(f"[우선순위 2: 재무제표]\n")
            f.write(f"1. 재무제표 없는 종목 {financial_data['stocks_without_financials']}개 재수집\n")
            f.write(f"   - DART API 재수집\n")
            f.write(f"2. 빈 JSONB 필드 처리\n")
            f.write(f"   - 빈 재무상태표: {financial_data['empty_balance_sheet']}건\n")
            f.write(f"   - 빈 손익계산서: {financial_data['empty_income_statement']}건\n\n")

            f.write(f"[우선순위 3: 재무비율]\n")
            f.write(f"1. 재무비율 없는 종목 {ratio_data['stocks_without_ratios']}개 계산\n")
            f.write(f"   - scripts/calculate_quarterly_ratios.py 실행\n")
            f.write(f"2. NULL 비율 높은 지표 개선\n")

            high_null_ratios = [
                name for name, stats in ratio_data['null_stats'].items()
                if stats['null_rate'] > 50
            ]
            if high_null_ratios:
                f.write(f"   - 50% 이상 NULL: {', '.join(high_null_ratios)}\n")

            medium_null_ratios = [
                name for name, stats in ratio_data['null_stats'].items()
                if 10 < stats['null_rate'] <= 50
            ]
            if medium_null_ratios:
                f.write(f"   - 10-50% NULL: {', '.join(medium_null_ratios)}\n")

            f.write("\n" + "=" * 80 + "\n")
            f.write("✅ 리포트 생성 완료\n")
            f.write("=" * 80 + "\n")

        print(f"\n✅ 결측치 분석 리포트 저장: {output_path}")
        return output_path


def main():
    """메인 실행 함수."""
    import argparse

    parser = argparse.ArgumentParser(description="결측치 탐지 스크립트")
    parser.add_argument(
        '--data-type',
        type=str,
        choices=['price', 'financial', 'ratio', 'all'],
        default='all',
        help='분석할 데이터 유형 (default: all)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='data/missing_data_reports',
        help='리포트 출력 디렉토리 (default: data/missing_data_reports)'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("📊 결측치 탐지 스크립트")
    print("=" * 80)

    with MissingDataDetector() as detector:
        # 데이터 유형별 분석
        if args.data_type in ['price', 'all']:
            detector.detect_price_missing_data()

        if args.data_type in ['financial', 'all']:
            detector.detect_financial_missing_data()

        if args.data_type in ['ratio', 'all']:
            detector.detect_ratio_missing_data()

        # 리포트 생성
        detector.generate_report()

    print("\n✅ 결측치 탐지 완료")


if __name__ == "__main__":
    main()
