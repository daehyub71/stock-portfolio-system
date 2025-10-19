"""FinancialStatement model for corporate financial statements."""

from sqlalchemy import Column, Integer, String, Date, ForeignKey, Enum as SQLEnum, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from db.connection import Base
from models.base import TimestampMixin
import enum


class StatementType(enum.Enum):
    """Financial statement types."""
    ANNUAL = "annual"  # 사업보고서
    QUARTERLY = "quarterly"  # 분기보고서


class FinancialStatement(Base, TimestampMixin):
    """FinancialStatement model for corporate financial statements.

    Uses JSONB columns to store flexible financial data structure
    that can vary between companies and reporting periods.
    """

    __tablename__ = 'financial_statements'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey('stocks.id'), nullable=False, index=True, comment='Stock ID')
    report_date = Column(Date, nullable=False, index=True, comment='Reporting date (결산일)')
    statement_type = Column(SQLEnum(StatementType), nullable=False, comment='Statement type (annual/quarterly)')
    fiscal_year = Column(Integer, nullable=False, index=True, comment='Fiscal year (회계연도)')
    fiscal_quarter = Column(Integer, comment='Fiscal quarter (1-4, NULL for annual)')

    # Financial statement data stored as JSONB for flexibility
    # 재무상태표 (Balance Sheet)
    balance_sheet = Column(
        JSONB,
        comment='Balance sheet data: {assets: {current: {}, non_current: {}}, liabilities: {}, equity: {}}'
    )

    # 손익계산서 (Income Statement)
    income_statement = Column(
        JSONB,
        comment='Income statement data: {revenue: {}, expenses: {}, net_income: {}, operating_income: {}}'
    )

    # 현금흐름표 (Cash Flow Statement)
    cash_flow = Column(
        JSONB,
        comment='Cash flow statement data: {operating: {}, investing: {}, financing: {}}'
    )

    # 자본변동표 (Statement of Changes in Equity)
    equity_changes = Column(
        JSONB,
        comment='Statement of changes in equity'
    )

    # Relationship
    stock = relationship('Stock', back_populates='financial_statements')

    # Composite unique constraint
    __table_args__ = (
        Index(
            'idx_financial_statements_unique',
            'stock_id', 'report_date', 'statement_type',
            unique=True
        ),
        Index('idx_financial_statements_year_quarter', 'fiscal_year', 'fiscal_quarter'),
    )

    def __repr__(self):
        return (
            f"<FinancialStatement(stock_id={self.stock_id}, "
            f"report_date='{self.report_date}', type='{self.statement_type.value}')>"
        )
