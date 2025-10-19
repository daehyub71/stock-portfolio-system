"""FinancialRatio model for calculated financial ratios."""

from sqlalchemy import Column, Integer, Date, Numeric, ForeignKey, Index
from sqlalchemy.orm import relationship
from db.connection import Base
from models.base import TimestampMixin


class FinancialRatio(Base, TimestampMixin):
    """FinancialRatio model for 30+ calculated financial ratios.

    Ratios are calculated from financial statements and stored
    for efficient querying and historical analysis.
    """

    __tablename__ = 'financial_ratios'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey('stocks.id'), nullable=False, index=True, comment='Stock ID')
    report_date = Column(Date, nullable=False, index=True, comment='Reporting date')
    fiscal_year = Column(Integer, nullable=False, index=True, comment='Fiscal year')
    fiscal_quarter = Column(Integer, comment='Fiscal quarter (1-4, NULL for annual)')

    # 수익성 지표 (Profitability Ratios)
    roe = Column(Numeric(10, 4), comment='자기자본이익률 (Return on Equity, %)')
    roa = Column(Numeric(10, 4), comment='총자산이익률 (Return on Assets, %)')
    roic = Column(Numeric(10, 4), comment='투하자본이익률 (Return on Invested Capital, %)')
    gross_profit_margin = Column(Numeric(10, 4), comment='매출총이익률 (Gross Profit Margin, %)')
    operating_profit_margin = Column(Numeric(10, 4), comment='영업이익률 (Operating Profit Margin, %)')
    net_profit_margin = Column(Numeric(10, 4), comment='순이익률 (Net Profit Margin, %)')
    ebitda_margin = Column(Numeric(10, 4), comment='EBITDA 마진 (EBITDA Margin, %)')

    # 성장성 지표 (Growth Ratios)
    revenue_growth = Column(Numeric(10, 4), comment='매출액 증가율 (Revenue Growth, %)')
    operating_income_growth = Column(Numeric(10, 4), comment='영업이익 증가율 (Operating Income Growth, %)')
    net_income_growth = Column(Numeric(10, 4), comment='순이익 증가율 (Net Income Growth, %)')
    eps_growth = Column(Numeric(10, 4), comment='EPS 증가율 (EPS Growth, %)')
    total_asset_growth = Column(Numeric(10, 4), comment='총자산 증가율 (Total Asset Growth, %)')

    # 안정성 지표 (Stability Ratios)
    debt_ratio = Column(Numeric(10, 4), comment='부채비율 (Debt Ratio, %)')
    debt_to_equity = Column(Numeric(10, 4), comment='부채자본비율 (Debt to Equity, %)')
    current_ratio = Column(Numeric(10, 4), comment='유동비율 (Current Ratio, %)')
    quick_ratio = Column(Numeric(10, 4), comment='당좌비율 (Quick Ratio, %)')
    interest_coverage = Column(Numeric(10, 4), comment='이자보상배율 (Interest Coverage Ratio)')
    equity_ratio = Column(Numeric(10, 4), comment='자기자본비율 (Equity Ratio, %)')

    # 활동성 지표 (Activity Ratios)
    asset_turnover = Column(Numeric(10, 4), comment='총자산회전율 (Total Asset Turnover)')
    inventory_turnover = Column(Numeric(10, 4), comment='재고자산회전율 (Inventory Turnover)')
    receivables_turnover = Column(Numeric(10, 4), comment='매출채권회전율 (Receivables Turnover)')
    payables_turnover = Column(Numeric(10, 4), comment='매입채무회전율 (Payables Turnover)')

    # 시장가치 지표 (Market Value Ratios)
    per = Column(Numeric(10, 4), comment='주가수익비율 (Price to Earnings Ratio)')
    pbr = Column(Numeric(10, 4), comment='주가순자산비율 (Price to Book Ratio)')
    pcr = Column(Numeric(10, 4), comment='주가현금흐름비율 (Price to Cash Flow Ratio)')
    psr = Column(Numeric(10, 4), comment='주가매출액비율 (Price to Sales Ratio)')
    ev_to_ebitda = Column(Numeric(10, 4), comment='EV/EBITDA')
    dividend_yield = Column(Numeric(10, 4), comment='배당수익률 (Dividend Yield, %)')
    dividend_payout_ratio = Column(Numeric(10, 4), comment='배당성향 (Dividend Payout Ratio, %)')

    # 주요 절대값 지표 (Absolute Value Metrics)
    eps = Column(Numeric(12, 2), comment='주당순이익 (Earnings Per Share, KRW)')
    bps = Column(Numeric(12, 2), comment='주당순자산 (Book value Per Share, KRW)')
    ebitda = Column(Numeric(15, 2), comment='EBITDA (KRW)')

    # Relationship
    stock = relationship('Stock', back_populates='financial_ratios')

    # Composite unique constraint
    __table_args__ = (
        Index(
            'idx_financial_ratios_unique',
            'stock_id', 'report_date', 'fiscal_quarter',
            unique=True
        ),
        Index('idx_financial_ratios_year_quarter', 'fiscal_year', 'fiscal_quarter'),
    )

    def __repr__(self):
        return (
            f"<FinancialRatio(stock_id={self.stock_id}, "
            f"report_date='{self.report_date}', ROE={self.roe}, PER={self.per})>"
        )
