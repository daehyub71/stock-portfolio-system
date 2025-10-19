"""Sector model for stock categorization with hierarchical structure."""

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from db.connection import Base
from models.base import TimestampMixin


class Sector(Base, TimestampMixin):
    """Sector model supporting hierarchical structure (industry > sector > sub-sector)."""

    __tablename__ = 'sectors'

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), unique=True, nullable=False, index=True, comment='Sector code (e.g., IT, FIN)')
    name = Column(String(100), nullable=False, comment='Sector name (Korean)')
    name_en = Column(String(100), comment='Sector name (English)')
    level = Column(Integer, nullable=False, comment='Hierarchy level (1=Industry, 2=Sector, 3=Sub-sector)')
    parent_id = Column(Integer, ForeignKey('sectors.id'), nullable=True, index=True, comment='Parent sector ID')

    # Self-referential relationship for hierarchy
    parent = relationship('Sector', remote_side=[id], backref='children')

    # Relationship to stocks
    stocks = relationship('Stock', back_populates='sector')

    def __repr__(self):
        return f"<Sector(code='{self.code}', name='{self.name}', level={self.level})>"
