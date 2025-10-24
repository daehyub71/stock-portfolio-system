# Day 18: 이상치 탐지 및 처리

**날짜**: 2025-10-24
**작업 시간**: 약 2시간

## 목표

통계적 방법으로 재무비율 데이터의 이상치를 탐지하고, 이를 삭제하지 않고 플래깅하여 데이터 품질 관리에 활용합니다.

## 완료된 작업

### 1. IQR/Z-score 기반 이상치 탐지 로직 구현

**파일**: `calculators/outlier_detector.py`

구현된 탐지 방법:
- **IQR (Interquartile Range)**: Q1 - 1.5*IQR ~ Q3 + 1.5*IQR 범위 벗어난 값
- **Z-score**: |z-score| > 3인 값
- **Modified Z-score**: MAD (Median Absolute Deviation) 기반, 비정규 분포에 robust
- **Combined**: IQR과 Z-score 모두에서 이상치로 판정된 값만 최종 이상치로 결정

핵심 기능:
```python
class OutlierDetector:
    def detect_by_iqr(values) -> List[OutlierResult]
    def detect_by_zscore(values) -> List[OutlierResult]
    def detect_by_modified_zscore(values) -> List[OutlierResult]
    def detect_combined(values) -> List[OutlierResult]  # 보수적 접근
```

이상치 심각도 분류:
- **Low**: IQR distance < 1.0 또는 |Z-score| < 4.0
- **Medium**: IQR distance 1.0-2.0 또는 |Z-score| 4.0-5.0
- **High**: IQR distance > 2.0 또는 |Z-score| > 5.0

### 2. 이상치 플래깅 시스템 구현

**파일**: `scripts/outlier_detection/flag_outliers.py`

이상치를 **삭제하지 않고 플래깅**하여 데이터 무결성 유지:

```python
class OutlierFlagger:
    def detect_outliers_for_field(field, ticker=None)
    def detect_all_outliers(ticker=None)
    def save_outlier_flags(output_path)
    def update_database_flags()  # JSONB outlier_flags 컬럼 사용
```

검사 대상 재무비율 (15개):
- **수익성**: ROE, ROA, ROIC, 매출총이익률, 영업이익률, 순이익률
- **안정성**: 부채비율, 부채자본비율, 유동비율, 당좌비율
- **활동성**: 자산회전율, 재고회전율
- **성장성**: 매출액증가율, 영업이익증가율, 순이익증가율

사용법:
```bash
# 모든 재무비율 이상치 탐지
python scripts/outlier_detection/flag_outliers.py --method combined

# 특정 지표만 검사
python scripts/outlier_detection/flag_outliers.py --method iqr --ratio roe

# 특정 종목만 검사
python scripts/outlier_detection/flag_outliers.py --ticker 005930

# 데이터베이스 업데이트
python scripts/outlier_detection/flag_outliers.py --method combined --update-db
```

### 3. 이상치 리포트 생성

**파일**: `scripts/outlier_detection/generate_outlier_report.py`

생성되는 리포트 섹션:
1. **전체 요약**: 이상치 포함 레코드 수, 총 이상치 필드 수
2. **심각도별 분석**: Low/Medium/High 분포, 필드별 심각도
3. **지표별 분석**: 이상치가 많은 지표 Top 20, 통계 정보
4. **종목별 분석**: 이상치가 많은 종목 Top 30
5. **High Severity 목록**: 심각한 이상치 Top 50
6. **수동 검토 권장 항목**: 우선 검토가 필요한 항목

사용법:
```bash
# 리포트 생성
python scripts/outlier_detection/generate_outlier_report.py

# 커스텀 입출력
python scripts/outlier_detection/generate_outlier_report.py \
    --input data/outliers/outlier_flags.json \
    --output reports/outlier_report.txt
```

### 4. 수동 검토 항목 추출

**파일**: `scripts/outlier_detection/extract_manual_review.py`

우선순위별 수동 검토 항목:

**Priority 1**: High severity + 핵심 지표
- ROE, ROA, 영업이익률, 순이익률, 부채비율, 유동비율

**Priority 2**: 동일 종목에서 여러 지표 이상치 (3개 이상)
- 동시다발적 이상치는 데이터 품질 이슈 가능성

**Priority 3**: 여러 기간에 걸친 지속적 이상치
- 반복되는 이상치는 구조적 문제 또는 회계 오류 가능성

**Priority 4**: Z-score 절대값 5 이상
- 극단적인 이상치

출력 형식:
- JSON: 상세 정보 포함
- CSV: 스프레드시트에서 바로 검토 가능

사용법:
```bash
# 모든 우선순위 추출
python scripts/outlier_detection/extract_manual_review.py

# 특정 우선순위만
python scripts/outlier_detection/extract_manual_review.py --priority 1

# 출력 경로 지정
python scripts/outlier_detection/extract_manual_review.py \
    --output-json data/review/manual_review.json \
    --output-csv data/review/manual_review.csv
```

## 아키텍처 설계

### 이상치 탐지 파이프라인

```
1. 재무비율 데이터 수집
   └─> DB에서 재무비율 조회 (fiscal_year IS NOT NULL)

2. 필드별 이상치 탐지
   └─> OutlierDetector.detect() 실행
       ├─> IQR 방법
       ├─> Z-score 방법
       └─> Combined (보수적)

3. 이상치 플래깅
   └─> OutlierFlagger.outlier_flags 저장
       ├─> JSON 파일로 내보내기
       └─> (선택) DB outlier_flags JSONB 컬럼 업데이트

4. 리포트 생성
   └─> OutlierReportGenerator.generate_report()
       ├─> 심각도별 분석
       ├─> 지표별 분석
       └─> 종목별 분석

5. 수동 검토 항목 추출
   └─> ManualReviewExtractor.extract_all()
       ├─> Priority 1-4 분류
       └─> JSON/CSV 출력
```

### 데이터 플로우

```
Financial Ratios DB
  |
  ├─> OutlierFlagger.detect_all_outliers()
  |     |
  |     └─> OutlierDetector.detect()
  |           └─> OutlierResult[]
  |
  ├─> outlier_flags.json
  |     |
  |     ├─> OutlierReportGenerator
  |     |     └─> outlier_report.txt
  |     |
  |     └─> ManualReviewExtractor
  |           └─> manual_review.json/csv
  |
  └─> (선택) financial_ratios.outlier_flags JSONB 업데이트
```

## 기술적 의사결정

### 1. 이상치 삭제 vs 플래깅

**선택**: 플래깅 (Flagging)

**이유**:
- 이상치가 실제 극단적인 사업 상황을 반영할 수 있음
- 데이터 무결성 유지
- 사후 분석 및 모델 개선에 활용 가능
- 필요시 분석에서 제외하는 유연성 확보

### 2. Combined 방법 사용

**선택**: IQR + Z-score Combined (기본값)

**이유**:
- IQR: 극단값에 robust, 비대칭 분포 처리
- Z-score: 통계적 유의성 제공
- Combined: False Positive 최소화 (보수적 접근)
- 사용자가 필요에 따라 개별 방법 선택 가능

### 3. 심각도 분류

**Low/Medium/High** 3단계 분류

**목적**:
- 검토 우선순위 결정
- 리소스 효율적 배분
- High severity만 선별 검토 가능

### 4. JSONB 컬럼 사용

```sql
ALTER TABLE financial_ratios
ADD COLUMN outlier_flags JSONB;
```

**장점**:
- 유연한 구조 (필드별 이상치 정보)
- 인덱싱 가능 (GIN index)
- 쿼리 가능 (WHERE outlier_flags ? 'roe')

## 검증 기준

### 이상치 탐지율: 3-5% 목표

일반적으로 정규분포에서:
- Z-score > 3: 약 0.3% (극단적 이상치)
- IQR 방법: 약 0.7% (mild outliers)
- Combined: 더 보수적 (False Positive 최소화)

재무 데이터 특성상 3-5%는 적절한 범위:
- 극단적 사업 상황 (대규모 적자, 구조조정 등)
- 회계 기준 변경
- 특수 산업 특성

### 검증 항목

1. ✅ 이상치 탐지 로직 구현 완료
2. ✅ 플래깅 시스템 구현 완료
3. ✅ 리포트 생성 시스템 완료
4. ✅ 수동 검토 항목 추출 완료
5. ⏳ 실제 데이터 적용 (재무비율 재계산 후 실행 예정)

## 사용 예제

### 전체 워크플로우

```bash
# 1. Priority 3 완료 확인 (2021, 2020 재무제표 수집)
python -c "from db.connection import SessionLocal; from models import FinancialStatement; from sqlalchemy import func; db = SessionLocal(); print(f'2021: {db.query(func.count(FinancialStatement.id)).filter(FinancialStatement.fiscal_year == 2021).scalar()}건'); print(f'2020: {db.query(func.count(FinancialStatement.id)).filter(FinancialStatement.fiscal_year == 2020).scalar()}건')"

# 2. 재무비율 재계산 (ROE 포함)
python scripts/calculate_quarterly_ratios.py --all-stocks

# 3. 이상치 탐지 및 플래깅
python scripts/outlier_detection/flag_outliers.py --method combined

# 4. 리포트 생성
python scripts/outlier_detection/generate_outlier_report.py

# 5. 수동 검토 항목 추출
python scripts/outlier_detection/extract_manual_review.py

# 6. CSV 파일로 검토
open data/outliers/manual_review_*.csv
```

### 특정 종목 검증

```bash
# 삼성전자 이상치 검사
python scripts/outlier_detection/flag_outliers.py --ticker 005930

# 리포트 확인
cat data/outliers/outlier_report_*.txt | grep "005930"
```

## 다음 단계

### Day 19-20: 백테스팅 프레임워크 구축

1. **전략 정의 인터페이스** 설계
2. **백테스팅 엔진** 구현
3. **성과 지표** 계산 (샤프 비율, MDD 등)
4. **결과 시각화** (Streamlit 대시보드)

### 데이터 품질 개선

Priority 3 완료로 얻은 이점:
- 2020-2024년 4개년 데이터 확보
- revenue_growth NULL 비율 51.7% → ~25% 감소 예상
- YoY 성장률 계산 가능
- 장기 트렌드 분석 가능

## 파일 구조

```
calculators/
  └── outlier_detector.py              # 이상치 탐지 로직

scripts/outlier_detection/
  ├── flag_outliers.py                 # 이상치 플래깅
  ├── generate_outlier_report.py       # 리포트 생성
  └── extract_manual_review.py         # 수동 검토 항목 추출

data/outliers/                          # 이상치 데이터 (gitignore)
  ├── outlier_flags.json                # 플래그 데이터
  ├── outlier_report_*.txt              # 리포트
  ├── manual_review_*.json              # 수동 검토 (JSON)
  └── manual_review_*.csv               # 수동 검토 (CSV)

docs/
  └── DAY18_OUTLIER_DETECTION.md        # 이 문서
```

## 성과

- ✅ **Task 18.1 완료**: IQR/Z-score 기반 이상치 탐지 로직 구현
- ✅ **Task 18.2 완료**: 이상치 플래깅 시스템 (삭제하지 않고 표시)
- ✅ **Task 18.3 완료**: 이상치 리포트 생성 (종목별, 지표별)
- ✅ **Task 18.4 완료**: 수동 검토가 필요한 항목 추출
- ⏳ **검증 대기**: 재무비율 재계산 후 실제 데이터 적용 예정

---

**작성자**: Claude Code
**최종 수정**: 2025-10-24
