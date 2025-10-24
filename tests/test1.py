"""재무비율 통합 뷰 테스트 스크립트."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from sqlalchemy import text

db = SessionLocal()

try:
    # 특정 날짜의 모든 재무비율 조회
    result = db.execute(text('''
        SELECT * FROM vw_daily_combined_ratios
        WHERE ticker = '005930' AND date = '2024-12-31'
    ''')).fetchone()

    if result:
        print("=" * 60)
        print("삼성전자 (005930) 2024-12-31 재무비율")
        print("=" * 60)
        print(f"\n[일별 pykrx 데이터]")
        print(f"  PER:  {result.per}")
        print(f"  PBR:  {result.pbr}")
        print(f"  ROE:  {result.roe_pykrx}%")
        print(f"  EPS:  {result.eps:,}원" if result.eps else "  EPS:  N/A")
        print(f"  BPS:  {result.bps:,}원" if result.bps else "  BPS:  N/A")

        print(f"\n[분기 재무제표 계산 데이터]")
        if result.fiscal_year:
            quarter_label = f"{result.fiscal_year}" if result.fiscal_quarter is None else f"{result.fiscal_year}Q{result.fiscal_quarter}"
            print(f"  적용 분기: {quarter_label}")
            print(f"  ROA:              {result.roa}%" if result.roa else "  ROA:              N/A")
            print(f"  영업이익률:        {result.operating_profit_margin}%" if result.operating_profit_margin else "  영업이익률:        N/A")
            print(f"  순이익률:          {result.net_profit_margin}%" if result.net_profit_margin else "  순이익률:          N/A")
            print(f"  부채비율:          {result.debt_ratio}%" if result.debt_ratio else "  부채비율:          N/A")
            print(f"  유동비율:          {result.current_ratio}%" if result.current_ratio else "  유동비율:          N/A")
            print(f"  자기자본비율:      {result.equity_ratio}%" if result.equity_ratio else "  자기자본비율:      N/A")
            print(f"  총자산회전율:      {result.asset_turnover}회" if result.asset_turnover else "  총자산회전율:      N/A")
            print(f"  매출액 증가율:     {result.revenue_growth}%" if result.revenue_growth else "  매출액 증가율:     N/A")
        else:
            print("  분기 재무비율 데이터 없음")

        print("=" * 60)
    else:
        print("데이터를 찾을 수 없습니다.")
        print("\n확인 사항:")
        print("1. vw_daily_combined_ratios 뷰가 생성되었는지 확인:")
        print("   python scripts/create_combined_ratios_view.py")
        print("\n2. 005930 종목의 일별 pykrx 데이터가 있는지 확인")
        print("\n3. 2024-12-31 데이터가 있는지 확인")

except Exception as e:
    print(f"오류 발생: {e}")
    import traceback
    traceback.print_exc()

finally:
    db.close()