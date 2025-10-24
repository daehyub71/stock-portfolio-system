#!/usr/bin/env python3
"""이상치 리포트 생성 스크립트.

이상치 탐지 결과를 읽기 쉬운 리포트로 생성합니다.
종목별, 지표별 이상치를 분석하고 시각화합니다.

Usage:
    python scripts/outlier_detection/generate_outlier_report.py
    python scripts/outlier_detection/generate_outlier_report.py --input data/outliers/outlier_flags.json
"""

import sys
from pathlib import Path
import argparse
import json
from datetime import datetime
from typing import Dict, List
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger


class OutlierReportGenerator:
    """이상치 리포트 생성 클래스."""

    def __init__(self, outlier_flags_path: str):
        """Initialize OutlierReportGenerator.

        Args:
            outlier_flags_path: 이상치 플래그 JSON 파일 경로
        """
        with open(outlier_flags_path, 'r', encoding='utf-8') as f:
            self.outlier_flags = json.load(f)

        self.report_lines = []

    def add_line(self, line: str = ""):
        """리포트에 라인 추가.

        Args:
            line: 추가할 라인
        """
        self.report_lines.append(line)

    def add_header(self, title: str, level: int = 1):
        """리포트에 헤더 추가.

        Args:
            title: 헤더 제목
            level: 헤더 레벨 (1, 2, 3)
        """
        if level == 1:
            self.add_line("=" * 80)
            self.add_line(title.center(80))
            self.add_line("=" * 80)
        elif level == 2:
            self.add_line()
            self.add_line("-" * 80)
            self.add_line(title)
            self.add_line("-" * 80)
        else:
            self.add_line()
            self.add_line(f"### {title}")

    def generate_summary(self):
        """전체 요약 생성."""
        self.add_header("이상치 탐지 리포트", level=1)
        self.add_line()
        self.add_line(f"생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.add_line()

        # 기본 통계
        total_ratios = len(self.outlier_flags)
        total_outlier_fields = sum(
            len(info['fields']) for info in self.outlier_flags.values()
        )

        self.add_header("1. 전체 요약", level=2)
        self.add_line(f"  • 이상치를 포함한 재무비율 레코드: {total_ratios:,}개")
        self.add_line(f"  • 총 이상치 필드 수: {total_outlier_fields:,}개")
        self.add_line(f"  • 평균 이상치 필드/레코드: {total_outlier_fields/total_ratios:.2f}개")

    def generate_by_severity(self):
        """심각도별 이상치 분석."""
        self.add_header("2. 심각도별 이상치 분석", level=2)

        severity_counts = {'low': 0, 'medium': 0, 'high': 0}
        severity_by_field = defaultdict(lambda: {'low': 0, 'medium': 0, 'high': 0})

        for ratio_id, info in self.outlier_flags.items():
            for field, outlier_info in info['fields'].items():
                severity = outlier_info['severity']
                severity_counts[severity] += 1
                severity_by_field[field][severity] += 1

        # 전체 심각도
        total = sum(severity_counts.values())
        self.add_line()
        self.add_line("전체 심각도 분포:")
        self.add_line(f"  • Low:    {severity_counts['low']:6,}개 ({severity_counts['low']/total*100:5.1f}%)")
        self.add_line(f"  • Medium: {severity_counts['medium']:6,}개 ({severity_counts['medium']/total*100:5.1f}%)")
        self.add_line(f"  • High:   {severity_counts['high']:6,}개 ({severity_counts['high']/total*100:5.1f}%)")

        # 필드별 심각도
        self.add_line()
        self.add_line("필드별 심각도 분포:")
        for field in sorted(severity_by_field.keys()):
            counts = severity_by_field[field]
            field_total = sum(counts.values())
            high_pct = counts['high'] / field_total * 100 if field_total > 0 else 0
            self.add_line(
                f"  {field:25} | Total: {field_total:4,} | "
                f"High: {counts['high']:3,} ({high_pct:5.1f}%) | "
                f"Med: {counts['medium']:3,} | Low: {counts['low']:3,}"
            )

    def generate_by_field(self):
        """지표별 이상치 분석."""
        self.add_header("3. 지표별 이상치 분석", level=2)

        field_counts = defaultdict(int)
        field_values = defaultdict(list)

        for ratio_id, info in self.outlier_flags.items():
            for field, outlier_info in info['fields'].items():
                field_counts[field] += 1
                field_values[field].append(outlier_info['value'])

        # 필드별 통계
        self.add_line()
        self.add_line("지표별 이상치 개수 (상위 20개):")
        self.add_line()
        self.add_line(f"{'지표':25} | {'개수':>6} | {'최소값':>12} | {'최대값':>12} | {'평균':>12}")
        self.add_line("-" * 80)

        sorted_fields = sorted(field_counts.items(), key=lambda x: x[1], reverse=True)
        for field, count in sorted_fields[:20]:
            values = field_values[field]
            min_val = min(values)
            max_val = max(values)
            avg_val = sum(values) / len(values)

            self.add_line(
                f"{field:25} | {count:6,} | {min_val:12.2f} | {max_val:12.2f} | {avg_val:12.2f}"
            )

    def generate_by_stock(self, top_n: int = 30):
        """종목별 이상치 분석.

        Args:
            top_n: 상위 N개 종목만 표시
        """
        self.add_header("4. 종목별 이상치 분석", level=2)

        stock_counts = defaultdict(lambda: {'name': '', 'count': 0, 'fields': set()})

        for ratio_id, info in self.outlier_flags.items():
            ticker = info['ticker']
            name = info['name']
            field_count = len(info['fields'])

            stock_counts[ticker]['name'] = name
            stock_counts[ticker]['count'] += field_count
            stock_counts[ticker]['fields'].update(info['fields'].keys())

        # 종목별 통계
        self.add_line()
        self.add_line(f"이상치가 많은 종목 (상위 {top_n}개):")
        self.add_line()
        self.add_line(f"{'순위':>4} | {'종목코드':8} | {'종목명':20} | {'이상치 수':>8} | 주요 필드")
        self.add_line("-" * 100)

        sorted_stocks = sorted(
            stock_counts.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )

        for rank, (ticker, info) in enumerate(sorted_stocks[:top_n], 1):
            fields_str = ', '.join(sorted(info['fields'])[:5])
            if len(info['fields']) > 5:
                fields_str += f" ... ({len(info['fields'])}개)"

            self.add_line(
                f"{rank:4} | {ticker:8} | {info['name']:20} | {info['count']:8,} | {fields_str}"
            )

    def generate_high_severity_list(self, limit: int = 50):
        """High severity 이상치 목록.

        Args:
            limit: 표시할 최대 개수
        """
        self.add_header("5. High Severity 이상치 목록", level=2)

        high_outliers = []
        for ratio_id, info in self.outlier_flags.items():
            for field, outlier_info in info['fields'].items():
                if outlier_info['severity'] == 'high':
                    high_outliers.append({
                        'ticker': info['ticker'],
                        'name': info['name'],
                        'year': info['fiscal_year'],
                        'quarter': info['fiscal_quarter'],
                        'field': field,
                        'value': outlier_info['value'],
                        'reason': outlier_info['reason'],
                        'z_score': outlier_info.get('z_score'),
                        'iqr_distance': outlier_info.get('iqr_distance')
                    })

        self.add_line()
        self.add_line(f"High severity 이상치 (상위 {limit}개):")
        self.add_line()
        self.add_line(
            f"{'종목':8} | {'종목명':15} | {'연도':5} | {'분기':4} | "
            f"{'지표':20} | {'값':>12} | {'Z-Score':>9}"
        )
        self.add_line("-" * 100)

        # Z-score 절대값 기준으로 정렬
        high_outliers.sort(
            key=lambda x: abs(x['z_score']) if x['z_score'] else 0,
            reverse=True
        )

        for outlier in high_outliers[:limit]:
            quarter = f"Q{outlier['quarter']}" if outlier['quarter'] else "연간"
            z_score_str = f"{outlier['z_score']:9.2f}" if outlier['z_score'] else "N/A".rjust(9)

            self.add_line(
                f"{outlier['ticker']:8} | {outlier['name']:15} | {outlier['year']:5} | {quarter:4} | "
                f"{outlier['field']:20} | {outlier['value']:12.2f} | {z_score_str}"
            )

    def generate_manual_review_list(self):
        """수동 검토가 필요한 항목 목록."""
        self.add_header("6. 수동 검토 권장 항목", level=2)

        self.add_line()
        self.add_line("다음 항목들은 수동 검토를 권장합니다:")
        self.add_line()

        # 1. High severity 이상치
        high_count = sum(
            1 for info in self.outlier_flags.values()
            for outlier_info in info['fields'].values()
            if outlier_info['severity'] == 'high'
        )
        self.add_line(f"1. High severity 이상치: {high_count:,}개")

        # 2. 동일 종목에서 여러 지표 이상치
        multi_field_stocks = [
            (ticker, info['name'], len(info['fields']))
            for ticker, info in {
                info['ticker']: info
                for info in self.outlier_flags.values()
            }.items()
            if len(info['fields']) >= 3
        ]
        self.add_line(f"2. 3개 이상 지표 이상치 종목: {len(multi_field_stocks):,}개")

        # 3. 핵심 지표 이상치
        critical_fields = ['roe', 'roa', 'operating_profit_margin', 'net_profit_margin', 'debt_ratio']
        critical_outliers = sum(
            1 for info in self.outlier_flags.values()
            for field in info['fields'].keys()
            if field in critical_fields
        )
        self.add_line(f"3. 핵심 지표 이상치: {critical_outliers:,}개")

        # 4. 여러 분기에 걸친 이상치
        stocks_with_multiple_periods = defaultdict(set)
        for info in self.outlier_flags.values():
            ticker = info['ticker']
            period = (info['fiscal_year'], info['fiscal_quarter'])
            stocks_with_multiple_periods[ticker].add(period)

        persistent_outliers = [
            (ticker, len(periods))
            for ticker, periods in stocks_with_multiple_periods.items()
            if len(periods) >= 2
        ]
        self.add_line(f"4. 여러 기간 이상치 종목: {len(persistent_outliers):,}개")

        self.add_line()
        self.add_line("자세한 내용은 위의 섹션들을 참조하세요.")

    def generate_report(self) -> str:
        """전체 리포트 생성.

        Returns:
            생성된 리포트 문자열
        """
        logger.info("Generating outlier report...")

        self.generate_summary()
        self.generate_by_severity()
        self.generate_by_field()
        self.generate_by_stock()
        self.generate_high_severity_list()
        self.generate_manual_review_list()

        self.add_line()
        self.add_line("=" * 80)
        self.add_line("리포트 끝")
        self.add_line("=" * 80)

        return "\n".join(self.report_lines)

    def save_report(self, output_path: str):
        """리포트를 파일로 저장.

        Args:
            output_path: 출력 파일 경로
        """
        report = self.generate_report()

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)

        logger.info(f"Report saved to: {output_file}")


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(
        description="Generate outlier detection report"
    )

    parser.add_argument(
        "--input",
        type=str,
        default="data/outliers/outlier_flags.json",
        help="Input outlier flags JSON file"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output report file path (default: auto-generated with timestamp)"
    )

    args = parser.parse_args()

    # 입력 파일 확인
    if not Path(args.input).exists():
        logger.error(f"Input file not found: {args.input}")
        logger.info("Please run flag_outliers.py first to generate outlier flags.")
        sys.exit(1)

    # 출력 파일 경로 생성
    if args.output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"data/outliers/outlier_report_{timestamp}.txt"

    try:
        # 리포트 생성
        generator = OutlierReportGenerator(args.input)
        generator.save_report(args.output)

        # 콘솔에도 출력
        print(generator.generate_report())

        logger.info("\n✓ Outlier report generated successfully")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
