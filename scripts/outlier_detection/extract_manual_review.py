#!/usr/bin/env python3
"""수동 검토가 필요한 이상치 항목 추출 스크립트.

이상치 중에서 수동 검토가 필요한 항목을 우선순위별로 추출합니다.

Priority:
    1. High severity + 핵심 지표 (ROE, ROA, 영업이익률 등)
    2. 동일 종목에서 여러 지표 이상치 (3개 이상)
    3. 여러 기간에 걸친 지속적 이상치
    4. Z-score 절대값 5 이상

Usage:
    python scripts/outlier_detection/extract_manual_review.py
    python scripts/outlier_detection/extract_manual_review.py --priority high
"""

import sys
from pathlib import Path
import argparse
import json
from typing import Dict, List, Tuple
from collections import defaultdict
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger


# 핵심 재무비율 (우선 검토 대상)
CRITICAL_RATIOS = [
    'roe',  # 자기자본이익률
    'roa',  # 총자산이익률
    'operating_profit_margin',  # 영업이익률
    'net_profit_margin',  # 순이익률
    'debt_ratio',  # 부채비율
    'current_ratio',  # 유동비율
]


class ManualReviewExtractor:
    """수동 검토 항목 추출 클래스."""

    def __init__(self, outlier_flags_path: str):
        """Initialize ManualReviewExtractor.

        Args:
            outlier_flags_path: 이상치 플래그 JSON 파일 경로
        """
        with open(outlier_flags_path, 'r', encoding='utf-8') as f:
            self.outlier_flags = json.load(f)

        self.review_items = []

    def extract_high_severity_critical(self) -> List[Dict]:
        """Priority 1: High severity + 핵심 지표 이상치 추출.

        Returns:
            추출된 항목 리스트
        """
        logger.info("Extracting Priority 1: High severity + critical ratios...")

        items = []
        for ratio_id, info in self.outlier_flags.items():
            for field, outlier_info in info['fields'].items():
                if (outlier_info['severity'] == 'high' and
                    field in CRITICAL_RATIOS):

                    items.append({
                        'priority': 1,
                        'category': 'High Severity + Critical Ratio',
                        'ratio_id': ratio_id,
                        'ticker': info['ticker'],
                        'name': info['name'],
                        'fiscal_year': info['fiscal_year'],
                        'fiscal_quarter': info['fiscal_quarter'],
                        'field': field,
                        'value': outlier_info['value'],
                        'severity': outlier_info['severity'],
                        'reason': outlier_info['reason'],
                        'z_score': outlier_info.get('z_score'),
                        'iqr_distance': outlier_info.get('iqr_distance')
                    })

        logger.info(f"Found {len(items)} Priority 1 items")
        return items

    def extract_multi_field_outliers(self, min_fields: int = 3) -> List[Dict]:
        """Priority 2: 동일 종목에서 여러 지표 이상치 추출.

        Args:
            min_fields: 최소 필드 수 (기본 3개)

        Returns:
            추출된 항목 리스트
        """
        logger.info(f"Extracting Priority 2: Stocks with {min_fields}+ outlier fields...")

        # 종목별 이상치 필드 집계
        stock_outliers = defaultdict(list)
        for ratio_id, info in self.outlier_flags.items():
            if len(info['fields']) >= min_fields:
                key = (info['ticker'], info['fiscal_year'], info['fiscal_quarter'])
                stock_outliers[key].append((ratio_id, info))

        items = []
        for (ticker, year, quarter), ratio_infos in stock_outliers.items():
            for ratio_id, info in ratio_infos:
                # 모든 필드를 하나의 항목으로 추가
                items.append({
                    'priority': 2,
                    'category': f'Multiple Fields ({len(info["fields"])})',
                    'ratio_id': ratio_id,
                    'ticker': info['ticker'],
                    'name': info['name'],
                    'fiscal_year': info['fiscal_year'],
                    'fiscal_quarter': info['fiscal_quarter'],
                    'field_count': len(info['fields']),
                    'fields': list(info['fields'].keys()),
                    'outlier_details': info['fields']
                })

        logger.info(f"Found {len(items)} Priority 2 items")
        return items

    def extract_persistent_outliers(self) -> List[Dict]:
        """Priority 3: 여러 기간에 걸친 지속적 이상치 추출.

        Returns:
            추출된 항목 리스트
        """
        logger.info("Extracting Priority 3: Persistent outliers...")

        # 종목별 기간 집계
        stock_periods = defaultdict(lambda: defaultdict(list))
        for ratio_id, info in self.outlier_flags.items():
            ticker = info['ticker']
            period = (info['fiscal_year'], info['fiscal_quarter'])
            for field in info['fields'].keys():
                stock_periods[ticker][field].append((period, ratio_id, info))

        items = []
        for ticker, field_periods in stock_periods.items():
            for field, period_data in field_periods.items():
                if len(period_data) >= 2:  # 2개 이상 기간
                    for period, ratio_id, info in period_data:
                        items.append({
                            'priority': 3,
                            'category': f'Persistent ({len(period_data)} periods)',
                            'ratio_id': ratio_id,
                            'ticker': info['ticker'],
                            'name': info['name'],
                            'fiscal_year': info['fiscal_year'],
                            'fiscal_quarter': info['fiscal_quarter'],
                            'field': field,
                            'period_count': len(period_data),
                            'value': info['fields'][field]['value'],
                            'severity': info['fields'][field]['severity'],
                            'reason': info['fields'][field]['reason']
                        })

        logger.info(f"Found {len(items)} Priority 3 items")
        return items

    def extract_extreme_zscore(self, threshold: float = 5.0) -> List[Dict]:
        """Priority 4: Z-score 절대값이 매우 큰 이상치 추출.

        Args:
            threshold: Z-score 임계값 (기본 5.0)

        Returns:
            추출된 항목 리스트
        """
        logger.info(f"Extracting Priority 4: Extreme Z-scores (|z| > {threshold})...")

        items = []
        for ratio_id, info in self.outlier_flags.items():
            for field, outlier_info in info['fields'].items():
                z_score = outlier_info.get('z_score')
                if z_score and abs(z_score) > threshold:
                    items.append({
                        'priority': 4,
                        'category': f'Extreme Z-score',
                        'ratio_id': ratio_id,
                        'ticker': info['ticker'],
                        'name': info['name'],
                        'fiscal_year': info['fiscal_year'],
                        'fiscal_quarter': info['fiscal_quarter'],
                        'field': field,
                        'value': outlier_info['value'],
                        'severity': outlier_info['severity'],
                        'z_score': z_score,
                        'reason': outlier_info['reason']
                    })

        logger.info(f"Found {len(items)} Priority 4 items")
        return items

    def extract_all(self) -> List[Dict]:
        """모든 우선순위의 수동 검토 항목 추출.

        Returns:
            전체 추출된 항목 리스트 (우선순위 순으로 정렬)
        """
        logger.info("=== Extracting all manual review items ===")

        items = []

        # Priority 1
        items.extend(self.extract_high_severity_critical())

        # Priority 2
        items.extend(self.extract_multi_field_outliers())

        # Priority 3
        items.extend(self.extract_persistent_outliers())

        # Priority 4
        items.extend(self.extract_extreme_zscore())

        # 우선순위와 Z-score로 정렬
        items.sort(key=lambda x: (
            x['priority'],
            -abs(x.get('z_score', 0)) if x.get('z_score') else 0
        ))

        logger.info(f"\n=== Total manual review items: {len(items)} ===")
        return items

    def save_to_json(self, items: List[Dict], output_path: str):
        """추출된 항목을 JSON 파일로 저장.

        Args:
            items: 추출된 항목 리스트
            output_path: 출력 파일 경로
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)

        logger.info(f"Manual review items saved to: {output_file}")

    def save_to_csv(self, items: List[Dict], output_path: str):
        """추출된 항목을 CSV 파일로 저장.

        Args:
            items: 추출된 항목 리스트
            output_path: 출력 파일 경로
        """
        import csv

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            if not items:
                return

            # CSV 헤더
            fieldnames = [
                'priority', 'category', 'ticker', 'name',
                'fiscal_year', 'fiscal_quarter', 'field',
                'value', 'severity', 'z_score', 'reason'
            ]

            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()

            for item in items:
                quarter = f"Q{item['fiscal_quarter']}" if item.get('fiscal_quarter') else "연간"
                writer.writerow({
                    'priority': item['priority'],
                    'category': item['category'],
                    'ticker': item['ticker'],
                    'name': item['name'],
                    'fiscal_year': item['fiscal_year'],
                    'fiscal_quarter': quarter,
                    'field': item.get('field', ''),
                    'value': item.get('value', ''),
                    'severity': item.get('severity', ''),
                    'z_score': f"{item['z_score']:.2f}" if item.get('z_score') else '',
                    'reason': item.get('reason', '')
                })

        logger.info(f"Manual review items saved to: {output_file}")


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(
        description="Extract manual review items from outlier flags"
    )

    parser.add_argument(
        "--input",
        type=str,
        default="data/outliers/outlier_flags.json",
        help="Input outlier flags JSON file"
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Output JSON file path (default: auto-generated)"
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default=None,
        help="Output CSV file path (default: auto-generated)"
    )
    parser.add_argument(
        "--priority",
        type=str,
        choices=['all', '1', '2', '3', '4'],
        default='all',
        help="Extract specific priority only (default: all)"
    )

    args = parser.parse_args()

    # 입력 파일 확인
    if not Path(args.input).exists():
        logger.error(f"Input file not found: {args.input}")
        logger.info("Please run flag_outliers.py first to generate outlier flags.")
        sys.exit(1)

    # 출력 파일 경로 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output_json is None:
        args.output_json = f"data/outliers/manual_review_{timestamp}.json"
    if args.output_csv is None:
        args.output_csv = f"data/outliers/manual_review_{timestamp}.csv"

    try:
        extractor = ManualReviewExtractor(args.input)

        # 추출
        if args.priority == 'all':
            items = extractor.extract_all()
        elif args.priority == '1':
            items = extractor.extract_high_severity_critical()
        elif args.priority == '2':
            items = extractor.extract_multi_field_outliers()
        elif args.priority == '3':
            items = extractor.extract_persistent_outliers()
        elif args.priority == '4':
            items = extractor.extract_extreme_zscore()

        # 저장
        extractor.save_to_json(items, args.output_json)
        extractor.save_to_csv(items, args.output_csv)

        # 요약 출력
        priority_counts = defaultdict(int)
        for item in items:
            priority_counts[item['priority']] += 1

        print("\n" + "=" * 80)
        print("수동 검토 항목 추출 완료")
        print("=" * 80)
        print(f"\n총 {len(items):,}개 항목 추출")
        print("\n우선순위별:")
        for priority in sorted(priority_counts.keys()):
            print(f"  Priority {priority}: {priority_counts[priority]:,}개")

        print(f"\n출력 파일:")
        print(f"  JSON: {args.output_json}")
        print(f"  CSV:  {args.output_csv}")
        print("=" * 80)

        logger.info("\n✓ Manual review extraction completed successfully")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
