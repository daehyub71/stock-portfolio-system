"""CorpCodeMap model for mapping between ticker symbols and corporate codes."""

from sqlalchemy import Column, Integer, String, Index
from db.connection import Base
from models.base import TimestampMixin


class CorpCodeMap(Base, TimestampMixin):
    """CorpCodeMap model for mapping ticker symbols to DART corp_code.

    DART (전자공시시스템) uses corp_code while stock exchanges use ticker symbols.
    This table maintains the mapping between the two identifier systems.
    """

    __tablename__ = 'corp_code_map'

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), unique=True, nullable=False, index=True, comment='Stock ticker symbol (e.g., 005930)')
    corp_code = Column(String(20), unique=True, nullable=False, index=True, comment='DART corporate code (8 digits)')
    corp_name = Column(String(200), nullable=False, comment='Corporate name (Korean)')
    stock_name = Column(String(100), comment='Stock name (Korean, may differ from corp_name)')
    modify_date = Column(String(8), comment='DART modification date (YYYYMMDD)')

    __table_args__ = (
        Index('idx_corp_code_map_ticker', 'ticker'),
        Index('idx_corp_code_map_corp_code', 'corp_code'),
    )

    def __repr__(self):
        return f"<CorpCodeMap(ticker='{self.ticker}', corp_code='{self.corp_code}', name='{self.corp_name}')>"
