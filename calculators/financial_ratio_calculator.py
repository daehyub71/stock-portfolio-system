"""재무제표 기반 재무비율 계산기.

DART API로 수집한 재무제표 JSONB 데이터로부터 10개의 재무비율을 계산합니다.

계산 가능한 지표:
- 수익성 (5개): ROE, ROA, 매출총이익률, 영업이익률, 순이익률
- 안정성 (4개): 부채비율, 부채자본비율, 유동비율, 자기자본비율
- 활동성 (1개): 총자산회전율
- 성장성 (1개): 매출액 증가율 (다년도 데이터 필요)
"""

from typing import Dict, Optional, Tuple
from decimal import Decimal, InvalidOperation
from loguru import logger


class FinancialRatioCalculator:
    """재무제표 기반 재무비율 계산 클래스."""

    @staticmethod
    def _safe_divide(numerator: Optional[float], denominator: Optional[float],
                     multiply: float = 1.0) -> Optional[Decimal]:
        """안전한 나눗셈 (0으로 나누기 방지).

        Args:
            numerator: 분자
            denominator: 분모
            multiply: 곱셈 계수 (백분율 계산 시 100)

        Returns:
            계산 결과 (Decimal) 또는 None
        """
        try:
            if numerator is None or denominator is None:
                return None
            if denominator == 0:
                return None

            result = (float(numerator) / float(denominator)) * multiply
            return Decimal(str(round(result, 4)))
        except (TypeError, ValueError, InvalidOperation):
            return None

    @staticmethod
    def _extract_value(data: Optional[Dict], *keys) -> Optional[float]:
        """JSONB 딕셔너리에서 중첩된 키로 값 추출.

        Args:
            data: JSONB 딕셔너리
            *keys: 중첩된 키들 (예: 'assets', 'current', '유동자산')

        Returns:
            추출된 값 (float) 또는 None
        """
        if data is None:
            return None

        try:
            current = data
            for key in keys:
                if not isinstance(current, dict):
                    return None
                current = current.get(key)
                if current is None:
                    return None

            # 값이 딕셔너리면 첫 번째 값 반환 (단일 항목 가정)
            if isinstance(current, dict):
                values = list(current.values())
                return float(values[0]) if values else None

            return float(current)
        except (TypeError, ValueError, KeyError, IndexError):
            return None

    # ============================================
    # 수익성 지표 (Profitability Ratios)
    # ============================================

    def calculate_roe(self, balance_sheet: Dict, income_statement: Dict) -> Optional[Decimal]:
        """자기자본이익률 (Return on Equity, ROE).

        Formula: (당기순이익 / 자기자본) × 100

        Args:
            balance_sheet: 재무상태표 JSONB
            income_statement: 손익계산서 JSONB

        Returns:
            ROE (%) 또는 None
        """
        # 당기순이익 (연도별 다른 키 이름 처리)
        # 2024: profit.당기순이익
        # 2022-2023: profit.당기순이익(손실)
        net_income = (
            self._extract_value(income_statement, 'profit', '당기순이익') or
            self._extract_value(income_statement, 'profit', '당기순이익(손실)') or
            self._extract_value(income_statement, 'net_income', '당기순이익') or
            self._extract_value(income_statement, 'net_income') or
            self._extract_value(income_statement, '당기순이익')
        )

        # 자기자본
        equity = (
            self._extract_value(balance_sheet, 'equity', '자본총계') or
            self._extract_value(balance_sheet, 'equity') or
            self._extract_value(balance_sheet, '자본총계')
        )

        return self._safe_divide(net_income, equity, multiply=100)

    def calculate_roa(self, balance_sheet: Dict, income_statement: Dict) -> Optional[Decimal]:
        """총자산이익률 (Return on Assets, ROA).

        Formula: (당기순이익 / 자산총계) × 100

        Args:
            balance_sheet: 재무상태표 JSONB
            income_statement: 손익계산서 JSONB

        Returns:
            ROA (%) 또는 None
        """
        # 당기순이익 (연도별 다른 키 이름 처리)
        # 2024: profit.당기순이익
        # 2022-2023: profit.당기순이익(손실)
        net_income = (
            self._extract_value(income_statement, 'profit', '당기순이익') or
            self._extract_value(income_statement, 'profit', '당기순이익(손실)') or
            self._extract_value(income_statement, 'net_income', '당기순이익') or
            self._extract_value(income_statement, 'net_income') or
            self._extract_value(income_statement, '당기순이익')
        )

        # 자산총계
        total_assets = (
            self._extract_value(balance_sheet, 'equity', '자본총계')  # equity에 있을 수 있음
        )

        if total_assets is None:
            # 유동자산 + 비유동자산 (실제: 둘 다 current에 있음!)
            current_assets = self._extract_value(balance_sheet, 'assets', 'current', '유동자산')
            non_current_assets = self._extract_value(balance_sheet, 'assets', 'current', '비유동자산')  # current!

            if current_assets is not None and non_current_assets is not None:
                total_assets = current_assets + non_current_assets

        return self._safe_divide(net_income, total_assets, multiply=100)

    def calculate_gross_profit_margin(self, income_statement: Dict) -> Optional[Decimal]:
        """매출총이익률 (Gross Profit Margin).

        Formula: (매출총이익 / 매출액) × 100 또는 ((매출액 - 매출원가) / 매출액) × 100

        Args:
            income_statement: 손익계산서 JSONB

        Returns:
            매출총이익률 (%) 또는 None
        """
        # 매출액 (연도별 다른 키 이름 처리)
        # 2024: revenue.매출액
        # 2023: revenue.영업수익
        # 2022: revenue.수익(매출액)
        revenue = (
            self._extract_value(income_statement, 'revenue', '매출액') or
            self._extract_value(income_statement, 'revenue', '영업수익') or
            self._extract_value(income_statement, 'revenue', '수익(매출액)') or
            self._extract_value(income_statement, 'revenue') or
            self._extract_value(income_statement, '매출액')
        )

        # 매출총이익 (직접 제공되는 경우)
        gross_profit = self._extract_value(income_statement, 'revenue', '매출총이익')

        if gross_profit is not None and revenue is not None:
            return self._safe_divide(gross_profit, revenue, multiply=100)

        # 매출원가 (실제 구조: revenue.매출원가)
        cost_of_revenue = (
            self._extract_value(income_statement, 'revenue', '매출원가') or
            self._extract_value(income_statement, 'expenses', '매출원가') or
            self._extract_value(income_statement, 'cost_of_revenue', '매출원가') or
            self._extract_value(income_statement, '매출원가')
        )

        if revenue is None or cost_of_revenue is None:
            return None

        gross_profit = revenue - cost_of_revenue
        return self._safe_divide(gross_profit, revenue, multiply=100)

    def calculate_operating_profit_margin(self, income_statement: Dict) -> Optional[Decimal]:
        """영업이익률 (Operating Profit Margin).

        Formula: (영업이익 / 매출액) × 100

        Args:
            income_statement: 손익계산서 JSONB

        Returns:
            영업이익률 (%) 또는 None
        """
        # 매출액 (연도별 다른 키 이름 처리)
        # 2024: revenue.매출액
        # 2023: revenue.영업수익
        # 2022: revenue.수익(매출액)
        revenue = (
            self._extract_value(income_statement, 'revenue', '매출액') or
            self._extract_value(income_statement, 'revenue', '영업수익') or
            self._extract_value(income_statement, 'revenue', '수익(매출액)') or
            self._extract_value(income_statement, 'revenue') or
            self._extract_value(income_statement, '매출액')
        )

        # 영업이익 (실제 구조: profit.영업이익 또는 profit.영업이익(손실))
        # 2024/2023: profit.영업이익(손실)
        # 2022: profit.영업이익
        operating_income = (
            self._extract_value(income_statement, 'profit', '영업이익(손실)') or
            self._extract_value(income_statement, 'profit', '영업이익') or
            self._extract_value(income_statement, 'operating_income', '영업이익') or
            self._extract_value(income_statement, 'operating_income') or
            self._extract_value(income_statement, '영업이익')
        )

        return self._safe_divide(operating_income, revenue, multiply=100)

    def calculate_net_profit_margin(self, income_statement: Dict) -> Optional[Decimal]:
        """순이익률 (Net Profit Margin).

        Formula: (당기순이익 / 매출액) × 100

        Args:
            income_statement: 손익계산서 JSONB

        Returns:
            순이익률 (%) 또는 None
        """
        # 매출액 (연도별 다른 키 이름 처리)
        # 2024: revenue.매출액
        # 2023: revenue.영업수익
        # 2022: revenue.수익(매출액)
        revenue = (
            self._extract_value(income_statement, 'revenue', '매출액') or
            self._extract_value(income_statement, 'revenue', '영업수익') or
            self._extract_value(income_statement, 'revenue', '수익(매출액)') or
            self._extract_value(income_statement, 'revenue') or
            self._extract_value(income_statement, '매출액')
        )

        # 당기순이익 (연도별 다른 키 이름 처리)
        # 2024: profit.당기순이익
        # 2022-2023: profit.당기순이익(손실)
        net_income = (
            self._extract_value(income_statement, 'profit', '당기순이익') or
            self._extract_value(income_statement, 'profit', '당기순이익(손실)') or
            self._extract_value(income_statement, 'net_income', '당기순이익') or
            self._extract_value(income_statement, 'net_income') or
            self._extract_value(income_statement, '당기순이익')
        )

        return self._safe_divide(net_income, revenue, multiply=100)

    # ============================================
    # 안정성 지표 (Stability Ratios)
    # ============================================

    def calculate_debt_ratio(self, balance_sheet: Dict) -> Optional[Decimal]:
        """부채비율 (Debt Ratio).

        Formula: (부채총계 / 자기자본) × 100

        Args:
            balance_sheet: 재무상태표 JSONB

        Returns:
            부채비율 (%) 또는 None
        """
        # 부채총계
        total_liabilities = (
            self._extract_value(balance_sheet, 'liabilities', '부채총계') or
            self._extract_value(balance_sheet, '부채총계')
        )

        if total_liabilities is None:
            # 유동부채 + 비유동부채 (실제: 둘 다 current에 있음!)
            current_liabilities = self._extract_value(balance_sheet, 'liabilities', 'current', '유동부채')
            non_current_liabilities = (
                self._extract_value(balance_sheet, 'liabilities', 'current', '비유동부채') or  # 실제 위치
                self._extract_value(balance_sheet, 'liabilities', 'non_current', '비유동부채')
            )

            if current_liabilities is not None and non_current_liabilities is not None:
                total_liabilities = current_liabilities + non_current_liabilities

        # 자기자본
        equity = (
            self._extract_value(balance_sheet, 'equity', '자본총계') or
            self._extract_value(balance_sheet, 'equity') or
            self._extract_value(balance_sheet, '자본총계')
        )

        return self._safe_divide(total_liabilities, equity, multiply=100)

    def calculate_debt_to_equity(self, balance_sheet: Dict) -> Optional[Decimal]:
        """부채자본비율 (Debt to Equity).

        Formula: (부채총계 / 자기자본) × 100
        Note: 부채비율과 동일한 개념

        Args:
            balance_sheet: 재무상태표 JSONB

        Returns:
            부채자본비율 (%) 또는 None
        """
        return self.calculate_debt_ratio(balance_sheet)

    def calculate_current_ratio(self, balance_sheet: Dict) -> Optional[Decimal]:
        """유동비율 (Current Ratio).

        Formula: (유동자산 / 유동부채) × 100

        Args:
            balance_sheet: 재무상태표 JSONB

        Returns:
            유동비율 (%) 또는 None
        """
        # 유동자산 (실제 구조: assets.current.유동자산)
        current_assets = (
            self._extract_value(balance_sheet, 'assets', 'current', '유동자산') or
            self._extract_value(balance_sheet, 'current_assets', '유동자산') or
            self._extract_value(balance_sheet, '유동자산')
        )

        # 유동부채 (실제 구조: liabilities.current.유동부채)
        current_liabilities = (
            self._extract_value(balance_sheet, 'liabilities', 'current', '유동부채') or
            self._extract_value(balance_sheet, 'current_liabilities', '유동부채') or
            self._extract_value(balance_sheet, '유동부채')
        )

        return self._safe_divide(current_assets, current_liabilities, multiply=100)

    def calculate_equity_ratio(self, balance_sheet: Dict) -> Optional[Decimal]:
        """자기자본비율 (Equity Ratio).

        Formula: (자기자본 / 자산총계) × 100

        Args:
            balance_sheet: 재무상태표 JSONB

        Returns:
            자기자본비율 (%) 또는 None
        """
        # 자기자본 (실제 구조: equity.자본총계)
        equity = (
            self._extract_value(balance_sheet, 'equity', '자본총계') or
            self._extract_value(balance_sheet, 'equity') or
            self._extract_value(balance_sheet, '자본총계')
        )

        # 자산총계 (유동자산 + 비유동자산, 실제: 둘 다 current에!)
        total_assets = None
        current_assets = self._extract_value(balance_sheet, 'assets', 'current', '유동자산')
        non_current_assets = self._extract_value(balance_sheet, 'assets', 'current', '비유동자산')  # current!

        if current_assets is not None and non_current_assets is not None:
            total_assets = current_assets + non_current_assets

        return self._safe_divide(equity, total_assets, multiply=100)

    # ============================================
    # 활동성 지표 (Activity Ratios)
    # ============================================

    def calculate_asset_turnover(self, balance_sheet: Dict, income_statement: Dict,
                                 prev_balance_sheet: Optional[Dict] = None) -> Optional[Decimal]:
        """총자산회전율 (Total Asset Turnover).

        Formula: 매출액 / 평균자산
        평균자산 = (기초자산 + 기말자산) / 2

        Args:
            balance_sheet: 당기 재무상태표 JSONB
            income_statement: 손익계산서 JSONB
            prev_balance_sheet: 전기 재무상태표 JSONB (선택)

        Returns:
            총자산회전율 (회) 또는 None
        """
        # 매출액 (연도별 다른 키 이름 처리)
        # 2024: revenue.매출액
        # 2023: revenue.영업수익
        # 2022: revenue.수익(매출액)
        revenue = (
            self._extract_value(income_statement, 'revenue', '매출액') or
            self._extract_value(income_statement, 'revenue', '영업수익') or
            self._extract_value(income_statement, 'revenue', '수익(매출액)') or
            self._extract_value(income_statement, 'revenue') or
            self._extract_value(income_statement, '매출액')
        )

        # 당기 자산총계 (유동자산 + 비유동자산, 실제: 둘 다 current에!)
        total_assets = None
        current_assets = self._extract_value(balance_sheet, 'assets', 'current', '유동자산')
        non_current_assets = self._extract_value(balance_sheet, 'assets', 'current', '비유동자산')  # current!

        if current_assets is not None and non_current_assets is not None:
            total_assets = current_assets + non_current_assets

        # 평균자산 계산 (전기 데이터가 있으면)
        if prev_balance_sheet and total_assets is not None:
            prev_current = self._extract_value(prev_balance_sheet, 'assets', 'current', '유동자산')
            prev_non_current = self._extract_value(prev_balance_sheet, 'assets', 'current', '비유동자산')  # current!

            if prev_current is not None and prev_non_current is not None:
                prev_total_assets = prev_current + prev_non_current
                avg_assets = (total_assets + prev_total_assets) / 2
                return self._safe_divide(revenue, avg_assets)

        # 전기 데이터 없으면 당기 자산으로 계산
        return self._safe_divide(revenue, total_assets)

    # ============================================
    # 성장성 지표 (Growth Ratios)
    # ============================================

    def calculate_revenue_growth(self, income_statement: Dict,
                                 prev_income_statement: Optional[Dict] = None) -> Optional[Decimal]:
        """매출액 증가율 (Revenue Growth).

        Formula: ((당기매출액 - 전기매출액) / 전기매출액) × 100

        Args:
            income_statement: 당기 손익계산서 JSONB
            prev_income_statement: 전기 손익계산서 JSONB (필수)

        Returns:
            매출액 증가율 (%) 또는 None
        """
        if prev_income_statement is None:
            return None

        # 당기 매출액 (연도별 다른 키 이름 처리)
        # 2024: revenue.매출액
        # 2023: revenue.영업수익
        # 2022: revenue.수익(매출액)
        current_revenue = (
            self._extract_value(income_statement, 'revenue', '매출액') or
            self._extract_value(income_statement, 'revenue', '영업수익') or
            self._extract_value(income_statement, 'revenue', '수익(매출액)') or
            self._extract_value(income_statement, 'revenue') or
            self._extract_value(income_statement, '매출액')
        )

        # 전기 매출액 (연도별 다른 키 이름 처리)
        prev_revenue = (
            self._extract_value(prev_income_statement, 'revenue', '매출액') or
            self._extract_value(prev_income_statement, 'revenue', '영업수익') or
            self._extract_value(prev_income_statement, 'revenue', '수익(매출액)') or
            self._extract_value(prev_income_statement, 'revenue') or
            self._extract_value(prev_income_statement, '매출액')
        )

        if current_revenue is None or prev_revenue is None:
            return None

        growth = current_revenue - prev_revenue
        return self._safe_divide(growth, prev_revenue, multiply=100)

    # ============================================
    # 통합 계산 메서드
    # ============================================

    def calculate_all_ratios(
        self,
        balance_sheet: Dict,
        income_statement: Dict,
        prev_balance_sheet: Optional[Dict] = None,
        prev_income_statement: Optional[Dict] = None
    ) -> Dict[str, Optional[Decimal]]:
        """모든 재무비율 일괄 계산.

        Args:
            balance_sheet: 당기 재무상태표 JSONB
            income_statement: 당기 손익계산서 JSONB
            prev_balance_sheet: 전기 재무상태표 JSONB (선택)
            prev_income_statement: 전기 손익계산서 JSONB (선택)

        Returns:
            재무비율 딕셔너리 {ratio_name: value}
        """
        ratios = {}

        # 수익성 지표 (5개)
        ratios['roe'] = self.calculate_roe(balance_sheet, income_statement)
        ratios['roa'] = self.calculate_roa(balance_sheet, income_statement)
        ratios['gross_profit_margin'] = self.calculate_gross_profit_margin(income_statement)
        ratios['operating_profit_margin'] = self.calculate_operating_profit_margin(income_statement)
        ratios['net_profit_margin'] = self.calculate_net_profit_margin(income_statement)

        # 안정성 지표 (4개)
        ratios['debt_ratio'] = self.calculate_debt_ratio(balance_sheet)
        ratios['debt_to_equity'] = self.calculate_debt_to_equity(balance_sheet)
        ratios['current_ratio'] = self.calculate_current_ratio(balance_sheet)
        ratios['equity_ratio'] = self.calculate_equity_ratio(balance_sheet)

        # 활동성 지표 (1개)
        ratios['asset_turnover'] = self.calculate_asset_turnover(
            balance_sheet, income_statement, prev_balance_sheet
        )

        # 성장성 지표 (1개) - 전기 데이터 필요
        ratios['revenue_growth'] = self.calculate_revenue_growth(
            income_statement, prev_income_statement
        )

        # 계산 성공/실패 로깅
        success_count = sum(1 for v in ratios.values() if v is not None)
        logger.debug(f"Calculated {success_count}/11 ratios successfully")

        return ratios


# 테스트 코드
if __name__ == "__main__":
    # 삼성전자 재무제표 예시 (실제 데이터 구조)
    test_balance_sheet = {
        "assets": {
            "current": {"유동자산": 227062266000000.0},
            "non_current": {"비유동자산": 287469682000000.0}
        },
        "equity": {"자본총계": 402192070000000.0},
        "liabilities": {
            "current": {"유동부채": 93326299000000.0},
            "non_current": {"비유동부채": 19013579000000.0}
        }
    }

    test_income_statement = {
        "revenue": {"매출액": 258937605000000.0},
        "operating_income": {"영업이익": 54336341000000.0},
        "net_income": {"당기순이익": 23678361000000.0}
    }

    calculator = FinancialRatioCalculator()
    ratios = calculator.calculate_all_ratios(test_balance_sheet, test_income_statement)

    print("=" * 50)
    print("재무비율 계산 결과")
    print("=" * 50)

    print("\n[수익성 지표]")
    print(f"  ROE:              {ratios['roe']}%")
    print(f"  ROA:              {ratios['roa']}%")
    print(f"  매출총이익률:      계산 불가 (매출원가 없음)")
    print(f"  영업이익률:        {ratios['operating_profit_margin']}%")
    print(f"  순이익률:          {ratios['net_profit_margin']}%")

    print("\n[안정성 지표]")
    print(f"  부채비율:          {ratios['debt_ratio']}%")
    print(f"  유동비율:          {ratios['current_ratio']}%")
    print(f"  자기자본비율:      {ratios['equity_ratio']}%")

    print("\n[활동성 지표]")
    print(f"  총자산회전율:      {ratios['asset_turnover']}회")

    print("\n[성장성 지표]")
    print(f"  매출액 증가율:     {ratios['revenue_growth']} (전기 데이터 없음)")
