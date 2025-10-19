"""DailyPrice model for OHLCV stock price data."""

from sqlalchemy import Column, Integer, String, Date, Numeric, BigInteger, ForeignKey, Index
from sqlalchemy.orm import relationship
from db.connection import Base
from models.base import TimestampMixin


class DailyPrice(Base, TimestampMixin):
    """DailyPrice model for daily OHLCV stock price data.

    Note: This model is prepared for future partitioning by date.
    Partitioning can be implemented using PostgreSQL's native partitioning
    or using pg_partman extension for automatic partition management.
    """

    __tablename__ = 'daily_prices'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey('stocks.id'), nullable=False, index=True, comment='Stock ID')
    date = Column(Date, nullable=False, index=True, comment='Trading date')

    # OHLCV data
    open_price = Column(Numeric(10, 2), nullable=False, comment='Opening price')
    high_price = Column(Numeric(10, 2), nullable=False, comment='Highest price')
    low_price = Column(Numeric(10, 2), nullable=False, comment='Lowest price')
    close_price = Column(Numeric(10, 2), nullable=False, comment='Closing price')
    volume = Column(BigInteger, nullable=False, comment='Trading volume')

    # Additional trading data
    trading_value = Column(BigInteger, comment='Trading value (amount in KRW)')
    market_cap = Column(BigInteger, comment='Market capitalization')
    shares_outstanding = Column(BigInteger, comment='Total shares outstanding')

    # Price change metrics
    change_amount = Column(Numeric(10, 2), comment='Price change amount from previous day')
    change_rate = Column(Numeric(6, 2), comment='Price change rate (%) from previous day')

    # Relationship
    stock = relationship('Stock', back_populates='daily_prices')

    # Composite unique constraint: one price record per stock per date
    __table_args__ = (
        Index('idx_daily_prices_stock_date', 'stock_id', 'date', unique=True),
        Index('idx_daily_prices_date_stock', 'date', 'stock_id'),  # For date-range queries
    )

    def __repr__(self):
        return f"<DailyPrice(stock_id={self.stock_id}, date='{self.date}', close={self.close_price})>"
