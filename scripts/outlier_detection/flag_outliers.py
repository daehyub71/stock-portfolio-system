#!/usr/bin/env python3
"""재무비율 이상치 플래깅 스크립트.

이상치를 탐지하고 데이터베이스에 플래깅합니다.
이상치는 삭제하지 않고 표시만 하여 데이터 품질 관리에 활용합니다.

Usage:
    python scripts/outlier_detection/flag_outliers.py --method combined
    python scripts/outlier_detection/flag_outliers.py --method iqr --ratio roe
    python scripts/outlier_detection/flag_outliers.py --ticker 005930
"""

import sys
from pathlib import Path
import argparse
from typing import Dict, List
from decimal import Decimal

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from models import FinancialRatio, Stock
from calculators.outlier_detector import OutlierDetector, OutlierMethod
from sqlalchemy import and_, func, text
from loguru import logger
import json


# 검사할 재무비율 필드
RATIO_FIELDS = [
    'roe', 'roa', 'roic',
    'gross_profit_margin', 'operating_profit_margin', 'net_profit_margin',
    'debt_ratio', 'debt_to_equity', 'current_ratio', 'quick_ratio',
    'asset_turnover', 'inventory_turnover',
    'revenue_growth', 'operating_income_growth', 'net_income_growth'
]


class OutlierFlagger:
    """이상치 플래깅 클래스."""

    def __init__(
        self,
        method: OutlierMethod = OutlierMethod.COMBINED,
        iqr_multiplier: float = 1.5,
        zscore_threshold: float = 3.0
    ):
        """Initialize OutlierFlagger.

        Args:
            method: 이상치 탐지 방법
            iqr_multiplier: IQR multiplier
            zscore_threshold: Z-score threshold
        """
        self.db = SessionLocal()
        self.detector = OutlierDetector(
            iqr_multiplier=iqr_multiplier,
            zscore_threshold=zscore_threshold
        )
        self.method = method
        self.outlier_flags = {}  # {ratio_id: {field: outlier_info}}

    def close(self):
        """Close database session."""
        self.db.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def detect_outliers_for_field(
        self,
        field: str,
        ticker: str = None
    ) -> Dict:
        """특정 필드의 이상치 탐지.

        Args:
            field: 재무비율 필드명 (예: 'roe', 'operating_profit_margin')
            ticker: 특정 종목만 검사 (선택)

        Returns:
            탐지 결과 딕셔너리
        """
        logger.info(f"Detecting outliers for field: {field}")

        # 데이터 조회
        query = self.db.query(FinancialRatio, Stock).join(
            Stock, FinancialRatio.stock_id == Stock.id
        ).filter(
            FinancialRatio.fiscal_year.isnot(None),
            getattr(FinancialRatio, field).isnot(None)
        )

        if ticker:
            query = query.filter(Stock.ticker == ticker)

        ratios = query.all()

        if not ratios:
            logger.warning(f"No data found for field: {field}")
            return {}

        logger.info(f"Found {len(ratios)} ratios for field: {field}")

        # 값 추출 (Decimal을 float로 변환)
        values = []
        ratio_objects = []
        for ratio, stock in ratios:
            value = getattr(ratio, field)
            if value is not None:
                values.append(float(value))
                ratio_objects.append((ratio, stock))

        if not values:
            return {}

        # 이상치 탐지
        results = self.detector.detect(values, method=self.method)

        # 이상치 플래깅
        outlier_count = 0
        for i, result in enumerate(results):
            if result.is_outlier:
                ratio, stock = ratio_objects[i]
                outlier_count += 1

                # 이상치 정보 저장
                if ratio.id not in self.outlier_flags:
                    self.outlier_flags[ratio.id] = {
                        'ticker': stock.ticker,
                        'name': stock.name,
                        'fiscal_year': ratio.fiscal_year,
                        'fiscal_quarter': ratio.fiscal_quarter,
                        'fields': {}
                    }

                self.outlier_flags[ratio.id]['fields'][field] = {
                    'value': result.value,
                    'severity': result.severity,
                    'reason': result.reason,
                    'z_score': result.z_score,
                    'iqr_distance': result.iqr_distance
                }

        # 요약 통계
        summary = self.detector.get_summary(results)
        summary['field'] = field
        summary['outlier_count'] = outlier_count

        logger.info(
            f"Field {field}: {outlier_count}/{len(ratios)} outliers "
            f"({outlier_count/len(ratios)*100:.1f}%)"
        )

        return summary

    def detect_all_outliers(self, ticker: str = None) -> Dict:
        """모든 재무비율 필드의 이상치 탐지.

        Args:
            ticker: 특정 종목만 검사 (선택)

        Returns:
            전체 탐지 결과 딕셔너리
        """
        logger.info("=== Starting outlier detection for all fields ===")

        summaries = {}
        for field in RATIO_FIELDS:
            try:
                summary = self.detect_outliers_for_field(field, ticker=ticker)
                if summary:
                    summaries[field] = summary
            except Exception as e:
                logger.error(f"Error detecting outliers for {field}: {e}")

        # 전체 요약
        total_ratios = len(set(self.outlier_flags.keys()))
        total_outlier_fields = sum(
            len(info['fields']) for info in self.outlier_flags.values()
        )

        logger.info(f"\n=== Outlier Detection Summary ===")
        logger.info(f"Total ratios with outliers: {total_ratios}")
        logger.info(f"Total outlier fields: {total_outlier_fields}")

        return {
            'summaries': summaries,
            'total_ratios_with_outliers': total_ratios,
            'total_outlier_fields': total_outlier_fields,
            'outlier_flags': self.outlier_flags
        }

    def save_outlier_flags(self, output_path: str):
        """이상치 플래그를 파일로 저장.

        Args:
            output_path: 출력 파일 경로
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.outlier_flags, f, indent=2, ensure_ascii=False)

        logger.info(f"Outlier flags saved to: {output_file}")

    def update_database_flags(self):
        """데이터베이스에 이상치 플래그 업데이트.

        Note: 현재 FinancialRatio 모델에 outlier_flags JSONB 컬럼이 필요합니다.
              마이그레이션이 필요한 경우 별도로 실행해야 합니다.
        """
        # outlier_flags 컬럼이 존재하는지 확인
        try:
            # Test query
            self.db.execute(
                text("SELECT outlier_flags FROM financial_ratios LIMIT 1")
            )
        except Exception:
            logger.warning(
                "outlier_flags column does not exist in financial_ratios table. "
                "Skipping database update. Run migration first."
            )
            return

        logger.info("Updating outlier flags in database...")

        update_count = 0
        for ratio_id, flag_info in self.outlier_flags.items():
            try:
                ratio = self.db.query(FinancialRatio).filter(
                    FinancialRatio.id == ratio_id
                ).first()

                if ratio:
                    # JSONB 형식으로 저장
                    ratio.outlier_flags = flag_info['fields']
                    update_count += 1

                    if update_count % 100 == 0:
                        self.db.commit()
                        logger.info(f"Updated {update_count} ratios...")

            except Exception as e:
                logger.error(f"Error updating ratio {ratio_id}: {e}")
                self.db.rollback()

        self.db.commit()
        logger.info(f"✓ Updated {update_count} ratios with outlier flags")


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(
        description="Detect and flag outliers in financial ratios"
    )

    parser.add_argument(
        "--method",
        type=str,
        choices=['iqr', 'zscore', 'modified_zscore', 'combined'],
        default='combined',
        help="Outlier detection method (default: combined)"
    )
    parser.add_argument(
        "--ratio",
        type=str,
        choices=RATIO_FIELDS + ['all'],
        default='all',
        help="Specific ratio field to check (default: all)"
    )
    parser.add_argument(
        "--ticker",
        type=str,
        help="Specific ticker to check (optional)"
    )
    parser.add_argument(
        "--iqr-multiplier",
        type=float,
        default=1.5,
        help="IQR multiplier (default: 1.5)"
    )
    parser.add_argument(
        "--zscore-threshold",
        type=float,
        default=3.0,
        help="Z-score threshold (default: 3.0)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/outliers/outlier_flags.json",
        help="Output file path for outlier flags"
    )
    parser.add_argument(
        "--update-db",
        action="store_true",
        help="Update database with outlier flags"
    )

    args = parser.parse_args()

    # 방법 변환
    method_map = {
        'iqr': OutlierMethod.IQR,
        'zscore': OutlierMethod.ZSCORE,
        'modified_zscore': OutlierMethod.MODIFIED_ZSCORE,
        'combined': OutlierMethod.COMBINED
    }
    method = method_map[args.method]

    try:
        with OutlierFlagger(
            method=method,
            iqr_multiplier=args.iqr_multiplier,
            zscore_threshold=args.zscore_threshold
        ) as flagger:

            logger.info(f"Using method: {args.method}")
            logger.info(f"IQR multiplier: {args.iqr_multiplier}")
            logger.info(f"Z-score threshold: {args.zscore_threshold}")

            if args.ratio == 'all':
                # 모든 비율 검사
                result = flagger.detect_all_outliers(ticker=args.ticker)
            else:
                # 특정 비율만 검사
                summary = flagger.detect_outliers_for_field(
                    args.ratio,
                    ticker=args.ticker
                )
                result = {
                    'summaries': {args.ratio: summary},
                    'total_ratios_with_outliers': len(flagger.outlier_flags),
                    'total_outlier_fields': sum(
                        len(info['fields']) for info in flagger.outlier_flags.values()
                    ),
                    'outlier_flags': flagger.outlier_flags
                }

            # 결과 저장
            flagger.save_outlier_flags(args.output)

            # 데이터베이스 업데이트 (선택)
            if args.update_db:
                flagger.update_database_flags()

            logger.info("\n✓ Outlier detection completed successfully")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
