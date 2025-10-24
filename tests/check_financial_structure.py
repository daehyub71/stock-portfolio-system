"""재무제표 JSONB 구조 확인 스크립트."""

import sys
from pathlib import Path
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from models import FinancialStatement, Stock
from sqlalchemy import func

db = SessionLocal()

try:
    # 삼성전자 재무제표 조회
    stmt = db.query(FinancialStatement).join(Stock).filter(
        Stock.ticker == '005930'
    ).order_by(FinancialStatement.fiscal_year.desc()).first()

    if stmt:
        print('=' * 70)
        print(f'종목: {stmt.stock.ticker} {stmt.stock.name}')
        print(f'분기: {stmt.fiscal_year}Q{stmt.fiscal_quarter if stmt.fiscal_quarter else "연간"}')
        print(f'보고일: {stmt.report_date}')
        print('=' * 70)

        print('\n[재무상태표 구조]')
        if stmt.balance_sheet:
            print(json.dumps(stmt.balance_sheet, indent=2, ensure_ascii=False))
        else:
            print('데이터 없음')

        print('\n' + '=' * 70)
        print('[손익계산서 구조]')
        if stmt.income_statement:
            print(json.dumps(stmt.income_statement, indent=2, ensure_ascii=False))
        else:
            print('데이터 없음')

        print('\n' + '=' * 70)
        print('[현금흐름표 구조]')
        if stmt.cash_flow:
            print(json.dumps(stmt.cash_flow, indent=2, ensure_ascii=False)[:500] + '...')
        else:
            print('데이터 없음')
    else:
        print('삼성전자 재무제표 데이터가 없습니다.')

    print('\n' + '=' * 70)
    print('[재무제표 보유 현황]')

    # 전체 재무제표 수
    total_stmts = db.query(func.count(FinancialStatement.id)).scalar()
    print(f'전체 재무제표: {total_stmts:,}건')

    # 종목 수
    total_stocks = db.query(func.count(func.distinct(FinancialStatement.stock_id))).scalar()
    print(f'재무제표 보유 종목: {total_stocks:,}개')

    # JSONB 필드별 NULL 체크
    bs_null = db.query(func.count(FinancialStatement.id)).filter(
        FinancialStatement.balance_sheet == None
    ).scalar()
    is_null = db.query(func.count(FinancialStatement.id)).filter(
        FinancialStatement.income_statement == None
    ).scalar()

    print(f'\n재무상태표 NULL: {bs_null:,}건 ({bs_null/total_stmts*100:.1f}%)')
    print(f'손익계산서 NULL: {is_null:,}건 ({is_null/total_stmts*100:.1f}%)')

finally:
    db.close()
