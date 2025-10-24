#!/usr/bin/env python3
"""이상치 탐지 모듈.

IQR (Interquartile Range)와 Z-score 방법을 사용하여 재무비율의 이상치를 탐지합니다.
이상치는 삭제하지 않고 플래깅하여 데이터 품질 관리에 활용합니다.

Methods:
    - IQR Method: Q1 - 1.5*IQR 또는 Q3 + 1.5*IQR 범위를 벗어난 값
    - Z-score Method: |z-score| > 3인 값
    - Modified Z-score: MAD (Median Absolute Deviation) 기반
"""

from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import numpy as np
from dataclasses import dataclass
from enum import Enum


class OutlierMethod(Enum):
    """이상치 탐지 방법."""
    IQR = "iqr"
    ZSCORE = "zscore"
    MODIFIED_ZSCORE = "modified_zscore"
    COMBINED = "combined"  # IQR + Z-score 조합


@dataclass
class OutlierResult:
    """이상치 탐지 결과."""
    value: float
    is_outlier: bool
    method: OutlierMethod
    reason: str
    severity: str  # 'low', 'medium', 'high'
    z_score: Optional[float] = None
    iqr_distance: Optional[float] = None


class OutlierDetector:
    """재무비율 이상치 탐지 클래스.

    IQR과 Z-score 방법을 사용하여 재무비율 데이터의 이상치를 탐지합니다.

    Attributes:
        iqr_multiplier: IQR 방법의 multiplier (기본 1.5)
        zscore_threshold: Z-score 임계값 (기본 3.0)
        modified_zscore_threshold: Modified Z-score 임계값 (기본 3.5)
    """

    def __init__(
        self,
        iqr_multiplier: float = 1.5,
        zscore_threshold: float = 3.0,
        modified_zscore_threshold: float = 3.5
    ):
        """Initialize OutlierDetector.

        Args:
            iqr_multiplier: IQR 방법의 multiplier (1.5 = mild outliers, 3.0 = extreme outliers)
            zscore_threshold: Z-score 임계값 (일반적으로 3.0)
            modified_zscore_threshold: Modified Z-score 임계값 (일반적으로 3.5)
        """
        self.iqr_multiplier = iqr_multiplier
        self.zscore_threshold = zscore_threshold
        self.modified_zscore_threshold = modified_zscore_threshold

    def detect_by_iqr(self, values: List[float]) -> List[OutlierResult]:
        """IQR (Interquartile Range) 방법으로 이상치 탐지.

        IQR = Q3 - Q1
        Lower bound = Q1 - 1.5 * IQR
        Upper bound = Q3 + 1.5 * IQR

        Args:
            values: 검사할 값들의 리스트

        Returns:
            이상치 탐지 결과 리스트
        """
        if not values or len(values) < 4:
            return []

        # NaN과 무한대 제거
        clean_values = [v for v in values if np.isfinite(v)]
        if len(clean_values) < 4:
            return []

        # Q1, Q3, IQR 계산
        q1 = np.percentile(clean_values, 25)
        q3 = np.percentile(clean_values, 75)
        iqr = q3 - q1

        lower_bound = q1 - self.iqr_multiplier * iqr
        upper_bound = q3 + self.iqr_multiplier * iqr

        results = []
        for value in values:
            if not np.isfinite(value):
                continue

            is_outlier = value < lower_bound or value > upper_bound

            if is_outlier:
                # 이상치의 심각도 계산
                if value < lower_bound:
                    distance = (lower_bound - value) / iqr if iqr > 0 else 0
                    reason = f"Lower outlier (Q1 - {self.iqr_multiplier}*IQR)"
                else:
                    distance = (value - upper_bound) / iqr if iqr > 0 else 0
                    reason = f"Upper outlier (Q3 + {self.iqr_multiplier}*IQR)"

                # 심각도 결정
                if distance < 1.0:
                    severity = 'low'
                elif distance < 2.0:
                    severity = 'medium'
                else:
                    severity = 'high'
            else:
                distance = 0
                reason = "Normal"
                severity = 'low'

            results.append(OutlierResult(
                value=value,
                is_outlier=is_outlier,
                method=OutlierMethod.IQR,
                reason=reason,
                severity=severity,
                iqr_distance=distance
            ))

        return results

    def detect_by_zscore(self, values: List[float]) -> List[OutlierResult]:
        """Z-score 방법으로 이상치 탐지.

        Z-score = (x - mean) / std
        일반적으로 |Z-score| > 3이면 이상치로 간주

        Args:
            values: 검사할 값들의 리스트

        Returns:
            이상치 탐지 결과 리스트
        """
        if not values or len(values) < 3:
            return []

        # NaN과 무한대 제거
        clean_values = [v for v in values if np.isfinite(v)]
        if len(clean_values) < 3:
            return []

        # 평균과 표준편차 계산
        mean = np.mean(clean_values)
        std = np.std(clean_values, ddof=1)

        if std == 0:
            return []

        results = []
        for value in values:
            if not np.isfinite(value):
                continue

            z_score = (value - mean) / std
            is_outlier = abs(z_score) > self.zscore_threshold

            if is_outlier:
                reason = f"Z-score = {z_score:.2f} (threshold = {self.zscore_threshold})"

                # 심각도 결정
                abs_z = abs(z_score)
                if abs_z < 4.0:
                    severity = 'low'
                elif abs_z < 5.0:
                    severity = 'medium'
                else:
                    severity = 'high'
            else:
                reason = "Normal"
                severity = 'low'

            results.append(OutlierResult(
                value=value,
                is_outlier=is_outlier,
                method=OutlierMethod.ZSCORE,
                reason=reason,
                severity=severity,
                z_score=z_score
            ))

        return results

    def detect_by_modified_zscore(self, values: List[float]) -> List[OutlierResult]:
        """Modified Z-score 방법으로 이상치 탐지.

        MAD (Median Absolute Deviation) 기반 방법으로
        정규분포를 따르지 않는 데이터에 더 robust합니다.

        Modified Z-score = 0.6745 * (x - median) / MAD

        Args:
            values: 검사할 값들의 리스트

        Returns:
            이상치 탐지 결과 리스트
        """
        if not values or len(values) < 3:
            return []

        # NaN과 무한대 제거
        clean_values = [v for v in values if np.isfinite(v)]
        if len(clean_values) < 3:
            return []

        # 중앙값 계산
        median = np.median(clean_values)

        # MAD 계산
        mad = np.median([abs(v - median) for v in clean_values])

        if mad == 0:
            return []

        results = []
        for value in values:
            if not np.isfinite(value):
                continue

            # Modified Z-score 계산
            modified_z = 0.6745 * (value - median) / mad
            is_outlier = abs(modified_z) > self.modified_zscore_threshold

            if is_outlier:
                reason = f"Modified Z-score = {modified_z:.2f} (threshold = {self.modified_zscore_threshold})"

                # 심각도 결정
                abs_mz = abs(modified_z)
                if abs_mz < 5.0:
                    severity = 'low'
                elif abs_mz < 7.0:
                    severity = 'medium'
                else:
                    severity = 'high'
            else:
                reason = "Normal"
                severity = 'low'

            results.append(OutlierResult(
                value=value,
                is_outlier=is_outlier,
                method=OutlierMethod.MODIFIED_ZSCORE,
                reason=reason,
                severity=severity,
                z_score=modified_z
            ))

        return results

    def detect_combined(self, values: List[float]) -> List[OutlierResult]:
        """IQR과 Z-score를 결합하여 이상치 탐지.

        두 방법 모두에서 이상치로 판정된 경우에만 최종 이상치로 결정합니다.
        이는 False Positive를 줄이는 보수적인 접근입니다.

        Args:
            values: 검사할 값들의 리스트

        Returns:
            이상치 탐지 결과 리스트
        """
        if not values or len(values) < 4:
            return []

        # 각 방법으로 탐지
        iqr_results = self.detect_by_iqr(values)
        zscore_results = self.detect_by_zscore(values)

        if not iqr_results or not zscore_results:
            return []

        # 결과 결합
        combined_results = []
        for i, value in enumerate(values):
            if i >= len(iqr_results) or i >= len(zscore_results):
                continue

            iqr_outlier = iqr_results[i].is_outlier
            z_outlier = zscore_results[i].is_outlier

            # 두 방법 모두 이상치로 판정한 경우
            is_outlier = iqr_outlier and z_outlier

            if is_outlier:
                reason = f"Both IQR and Z-score methods detected outlier"
                severity = max(
                    iqr_results[i].severity,
                    zscore_results[i].severity,
                    key=lambda x: {'low': 1, 'medium': 2, 'high': 3}[x]
                )
            else:
                reason = "Normal (not confirmed by both methods)"
                severity = 'low'

            combined_results.append(OutlierResult(
                value=value,
                is_outlier=is_outlier,
                method=OutlierMethod.COMBINED,
                reason=reason,
                severity=severity,
                z_score=zscore_results[i].z_score,
                iqr_distance=iqr_results[i].iqr_distance
            ))

        return combined_results

    def detect(
        self,
        values: List[float],
        method: OutlierMethod = OutlierMethod.COMBINED
    ) -> List[OutlierResult]:
        """지정된 방법으로 이상치 탐지.

        Args:
            values: 검사할 값들의 리스트
            method: 사용할 탐지 방법

        Returns:
            이상치 탐지 결과 리스트
        """
        if method == OutlierMethod.IQR:
            return self.detect_by_iqr(values)
        elif method == OutlierMethod.ZSCORE:
            return self.detect_by_zscore(values)
        elif method == OutlierMethod.MODIFIED_ZSCORE:
            return self.detect_by_modified_zscore(values)
        elif method == OutlierMethod.COMBINED:
            return self.detect_combined(values)
        else:
            raise ValueError(f"Unknown outlier detection method: {method}")

    def get_summary(self, results: List[OutlierResult]) -> Dict:
        """이상치 탐지 결과 요약.

        Args:
            results: 이상치 탐지 결과 리스트

        Returns:
            요약 통계 딕셔너리
        """
        if not results:
            return {}

        total = len(results)
        outliers = [r for r in results if r.is_outlier]
        outlier_count = len(outliers)

        severity_counts = {
            'low': len([r for r in outliers if r.severity == 'low']),
            'medium': len([r for r in outliers if r.severity == 'medium']),
            'high': len([r for r in outliers if r.severity == 'high'])
        }

        return {
            'total': total,
            'outliers': outlier_count,
            'outlier_rate': (outlier_count / total * 100) if total > 0 else 0,
            'severity_counts': severity_counts,
            'method': results[0].method.value if results else None
        }
