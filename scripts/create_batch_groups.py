#!/usr/bin/env python3
"""종목을 배치 그룹으로 분할하는 스크립트.

전체 종목을 5개 그룹으로 나누어 배치 수집을 준비합니다.
각 그룹은 약 500개 종목으로 구성됩니다.

Usage:
    python scripts/create_batch_groups.py
"""

import sys
from pathlib import Path
import json
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from models import Stock, CorpCodeMap, FinancialStatement
from sqlalchemy import func


def print_header(title: str):
    """Print formatted header."""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + f" {title:^66} " + "║")
    print("╚" + "═" * 68 + "╝")
    print()


def print_section(title: str):
    """Print section separator."""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def get_stocks_to_collect(db):
    """재무제표 수집이 필요한 종목 리스트를 가져옵니다.

    Args:
        db: Database session

    Returns:
        List of tuples (ticker, name, corp_code)
    """
    # Corp code가 있는 활성 종목
    stocks_with_corpcode = db.query(
        Stock.ticker,
        Stock.name,
        CorpCodeMap.corp_code
    ).join(
        CorpCodeMap, Stock.ticker == CorpCodeMap.ticker
    ).filter(
        Stock.is_active == True
    ).order_by(
        Stock.ticker
    ).all()

    return stocks_with_corpcode


def create_batch_groups(stocks, group_size=500):
    """종목 리스트를 그룹으로 분할합니다.

    Args:
        stocks: List of (ticker, name, corp_code) tuples
        group_size: Size of each group (default: 500)

    Returns:
        List of groups, each containing stock info
    """
    groups = []
    total = len(stocks)
    num_groups = (total + group_size - 1) // group_size  # Ceiling division

    for i in range(num_groups):
        start_idx = i * group_size
        end_idx = min((i + 1) * group_size, total)
        group_stocks = stocks[start_idx:end_idx]

        groups.append({
            'group_id': i + 1,
            'start_index': start_idx + 1,
            'end_index': end_idx,
            'size': len(group_stocks),
            'tickers': [s[0] for s in group_stocks],
            'stocks': [
                {
                    'ticker': s[0],
                    'name': s[1],
                    'corp_code': s[2]
                }
                for s in group_stocks
            ]
        })

    return groups


def save_groups_to_file(groups, output_dir):
    """그룹 정보를 JSON 파일로 저장합니다.

    Args:
        groups: List of group dictionaries
        output_dir: Output directory path
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save summary
    summary = {
        'created_at': datetime.now().isoformat(),
        'total_stocks': sum(g['size'] for g in groups),
        'num_groups': len(groups),
        'group_size': 500,
        'groups': [
            {
                'group_id': g['group_id'],
                'start_index': g['start_index'],
                'end_index': g['end_index'],
                'size': g['size']
            }
            for g in groups
        ]
    }

    summary_path = output_dir / 'batch_groups_summary.json'
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"✅ Summary saved: {summary_path}")

    # Save each group
    for group in groups:
        group_path = output_dir / f"group_{group['group_id']}.json"
        with open(group_path, 'w', encoding='utf-8') as f:
            json.dump(group, f, ensure_ascii=False, indent=2)

        print(f"✅ Group {group['group_id']} saved: {group_path} ({group['size']} stocks)")


def main():
    """메인 함수."""
    print_header("배치 그룹 생성")
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    db = SessionLocal()

    try:
        print_section("Step 1: 수집 대상 종목 조회")

        stocks = get_stocks_to_collect(db)
        print(f"✅ 수집 가능 종목 수: {len(stocks):,}")

        # 이미 수집된 종목 확인
        collected_stocks = db.query(
            func.distinct(Stock.ticker)
        ).join(
            FinancialStatement, Stock.id == FinancialStatement.stock_id
        ).all()

        collected_tickers = {s[0] for s in collected_stocks}
        print(f"✅ 이미 수집된 종목 수: {len(collected_tickers):,}")

        # 미수집 종목만 필터링
        stocks_to_collect = [
            s for s in stocks if s[0] not in collected_tickers
        ]

        print(f"✅ 수집 필요 종목 수: {len(stocks_to_collect):,}")

        if len(stocks_to_collect) == 0:
            print("\n⚠️  수집할 종목이 없습니다!")
            return

        print_section("Step 2: 그룹 분할")

        groups = create_batch_groups(stocks_to_collect, group_size=500)

        print(f"✅ 총 {len(groups)}개 그룹 생성")
        print(f"\n그룹별 종목 수:")
        for group in groups:
            print(f"  - Group {group['group_id']}: {group['size']} stocks "
                  f"(종목 {group['start_index']}-{group['end_index']})")

        print_section("Step 3: 파일 저장")

        output_dir = project_root / 'data' / 'batch_groups'
        save_groups_to_file(groups, output_dir)

        # 샘플 표시
        print_section("샘플 데이터")
        print("Group 1 첫 10개 종목:")
        for i, stock in enumerate(groups[0]['stocks'][:10], 1):
            print(f"  {i}. {stock['ticker']} - {stock['name']}")

        print("\n" + "=" * 70)
        print("✅ 배치 그룹 생성 완료!")
        print("=" * 70)
        print(f"\n결과:")
        print(f"  - 총 종목 수: {len(stocks_to_collect):,}")
        print(f"  - 그룹 수: {len(groups)}")
        print(f"  - 그룹당 평균 종목 수: {len(stocks_to_collect) / len(groups):.0f}")
        print(f"  - 저장 위치: {output_dir}")
        print(f"\n다음 단계:")
        print(f"  1. 배치 수집 스크립트 실행:")
        print(f"     python scripts/batch_collect_financials.py --group 1")
        print(f"  2. 진행 상황 모니터링:")
        print(f"     tail -f logs/batch_collection.log")
        print("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    main()
