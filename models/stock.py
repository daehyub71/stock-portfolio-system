"""Stock model for individual stock information."""

from sqlalchemy import Column, Integer, String, Date, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from db.connection import Base
from models.base import TimestampMixin
import enum


class MarketType(enum.Enum):
    """Stock market types in Korea."""
    KOSPI = "KOSPI"
    KOSDAQ = "KOSDAQ"
    KONEX = "KONEX"


class Stock(Base, TimestampMixin):
    """Stock model for individual stock information."""

    __tablename__ = 'stocks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), unique=True, nullable=False, index=True, comment='Stock ticker symbol (e.g., 005930)')
    name = Column(String(100), nullable=False, comment='Stock name (Korean)')
    name_en = Column(String(100), comment='Stock name (English)')
    market = Column(SQLEnum(MarketType), nullable=False, index=True, comment='Market type (KOSPI/KOSDAQ/KONEX)')
    sector_id = Column(Integer, ForeignKey('sectors.id'), nullable=True, index=True, comment='Sector ID')
    listing_date = Column(Date, comment='Listing date on the market')
    delisting_date = Column(Date, comment='Delisting date (NULL if active)')
    is_active = Column(Boolean, default=True, nullable=False, index=True, comment='Is currently trading')

    # Relationships
    sector = relationship('Sector', back_populates='stocks')
    daily_prices = relationship('DailyPrice', back_populates='stock', cascade='all, delete-orphan')
    financial_statements = relationship('FinancialStatement', back_populates='stock', cascade='all, delete-orphan')
    financial_ratios = relationship('FinancialRatio', back_populates='stock', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Stock(ticker='{self.ticker}', name='{self.name}', market='{self.market.value}')>"
