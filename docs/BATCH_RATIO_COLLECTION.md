# 그룹 기반 재무비율 배치 수집 가이드

대량의 종목 재무비율을 안정적으로 수집하기 위한 그룹 기반 배치 수집 시스템입니다.

## 목차

1. [개요](#개요)
2. [시스템 구조](#시스템-구조)
3. [사용 방법](#사용-방법)
4. [체크포인트 및 재개](#체크포인트-및-재개)
5. [실패 처리](#실패-처리)
6. [모니터링](#모니터링)

---

## 개요

### 왜 그룹 기반 수집인가?

전체 종목(2,500개 이상)을 한 번에 수집하면 다음 문제가 발생합니다:
- 네트워크 오류로 중간에 중단 시 처음부터 다시 시작
- 메모리 부족 위험
- 진행 상황 파악 어려움

**그룹 기반 수집의 장점:**
- ✅ 50개 단위로 나누어 안정적 수집
- ✅ 그룹별 체크포인트로 재개 가능
- ✅ 실패한 종목만 별도 관리
- ✅ 진행 상황 명확히 파악

### 수집 데이터

- **pykrx 직접 수집**: PER, PBR, EPS, BPS, DIV(배당수익률), DPS(주당배당금)
- **자동 계산**: ROE(자기자본이익률), Payout Ratio(배당성향)

---

## 시스템 구조

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 그룹 생성 (create_ratio_groups.py)                      │
│    - 전체 종목을 50개씩 그룹으로 분할                       │
│    - 미수집 종목만 필터링 가능                              │
│    - data/ratio_groups/ 에 JSON 파일 생성                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. 그룹별 배치 수집 (batch_collect_ratios.py)              │
│    - 그룹 파일을 읽어 순차 수집                             │
│    - 5개 종목마다 체크포인트 저장                           │
│    - 실패한 종목은 별도 파일에 기록                         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. 결과 확인                                                │
│    - data/checkpoints/ : 체크포인트 및 실패 목록           │
│    - logs/ : 상세 로그                                      │
│    - database : financial_ratios 테이블                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 사용 방법

### Step 1: 그룹 생성

#### 1-1. 미수집 종목만 그룹화 (권장)

```bash
# 2022년 이후 데이터가 없는 종목만 50개씩 그룹화
python scripts/create_ratio_groups.py --uncollected-only --group-size 50 --start-date 20220101
```

**출력 예시:**
```
======================================================================
재무비율 수집 그룹 생성
======================================================================
미수집 종목 조회 (기준일: 20220101)
미수집 종목: 2617개
총 2617개 종목을 53개 그룹으로 분할 (그룹당 50개)
  Group 1/53: 50개 종목 → ratio_group_001.json
  Group 2/53: 50개 종목 → ratio_group_002.json
  ...
  Group 53/53: 17개 종목 → ratio_group_053.json

메타데이터 저장: data/ratio_groups/ratio_groups_metadata.json
======================================================================
```

#### 1-2. 전체 종목 그룹화

```bash
# 전체 활성 종목을 100개씩 그룹화
python scripts/create_ratio_groups.py --group-size 100

# KOSPI만 그룹화
python scripts/create_ratio_groups.py --market KOSPI --group-size 50
```

### Step 2: 그룹별 수집 실행

#### 2-1. 단일 그룹 수집

```bash
# Group 1 수집 (최근 3년 데이터)
python scripts/batch_collect_ratios.py --group-id 1 --years 3

# Group 1 수집 (특정 기간)
python scripts/batch_collect_ratios.py --group-id 1 --start 20200101 --end 20250120
```

**출력 예시:**
```
======================================================================
그룹 기반 재무비율 배치 수집
======================================================================
수집 기간: 20220121 ~ 20250120
그룹 ID: 1

Loading group file: data/ratio_groups/ratio_group_001.json
Group 1: 50 stocks

[1/50] 365550 화인베스틸
  ✓ Saved 730 records
[2/50] 415640 포메탈
  ✓ Saved 721 records
...
  Progress: 5/50, Collected: 3,654 records
...
[50/50] 079430 현대퓨처넷
  ✓ Saved 730 records

======================================================================
Group 1 수집 완료
  - 성공: 48/50 종목
  - 실패: 2 종목
  - 총 레코드: 35,890건
======================================================================
```

#### 2-2. 전체 그룹 순차 수집

```bash
# 모든 그룹을 순차적으로 수집
python scripts/batch_collect_ratios.py --all --years 3
```

**주의사항:**
- 전체 그룹 수집은 수 시간이 소요될 수 있습니다
- 그룹 간 5초 대기 시간이 있어 서버 부하를 방지합니다

#### 2-3. 특정 그룹 범위만 수집

```bash
# Group 1~10만 수집하려면
for i in {1..10}; do
  python scripts/batch_collect_ratios.py --group-id $i --years 3
done
```

---

## 체크포인트 및 재개

### 체크포인트 시스템

- **저장 빈도**: 5개 종목마다 자동 저장
- **저장 위치**: `data/checkpoints/ratio_group_{group_id:03d}_checkpoint.json`
- **저장 내용**: 현재 진행 상황, 수집 통계, 실패 종목 수

### 중단 및 재개

#### 수동 중단 (Ctrl+C)

```bash
python scripts/batch_collect_ratios.py --group-id 1 --years 3
# ... 수집 중 ...
^C  # Ctrl+C로 중단

중단되었습니다. 체크포인트가 저장되었습니다.
재개하려면: python scripts/batch_collect_ratios.py --group-id 1 --years 3 --resume
```

#### 재개

```bash
# 마지막 체크포인트부터 재개
python scripts/batch_collect_ratios.py --group-id 1 --years 3 --resume
```

**출력 예시:**
```
Checkpoint loaded: 25/50
[26/50] 350520 롯데칠성
  ✓ Saved 730 records
...
```

---

## 실패 처리

### 실패 종목 확인

그룹 수집 완료 후 실패한 종목이 있으면 자동으로 기록됩니다:

**파일 위치**: `data/checkpoints/ratio_group_{group_id:03d}_failed.json`

**파일 내용 예시:**
```json
{
  "group_id": 1,
  "failed_count": 2,
  "failed_stocks": [
    {
      "ticker": "123456",
      "name": "테스트종목",
      "error": "No data available from pykrx"
    },
    {
      "ticker": "234567",
      "name": "샘플주식",
      "error": "Network timeout"
    }
  ]
}
```

### 실패 종목 재시도

#### 방법 1: 실패 목록 확인 후 개별 재시도

```bash
# 실패 목록 확인
cat data/checkpoints/ratio_group_001_failed.json

# 개별 종목 수집
python scripts/collect_financial_ratios.py --ticker 123456 --years 3
```

#### 방법 2: 미수집 종목만 새 그룹 생성

```bash
# 다시 미수집 종목 확인하여 그룹 생성
python scripts/create_ratio_groups.py --uncollected-only --group-size 50 --start-date 20220101

# 새로 생성된 그룹 수집
python scripts/batch_collect_ratios.py --group-id 1 --years 3
```

---

## 모니터링

### 1. 실시간 로그 확인

```bash
# 수집 중 로그 실시간 확인
tail -f logs/pykrx_ratio_collector_YYYYMMDD.log
```

### 2. 수집 통계 확인

```sql
-- 종목별 재무비율 데이터 수
SELECT
  s.ticker,
  s.name,
  COUNT(fr.id) as ratio_count,
  MIN(fr.date) as earliest_date,
  MAX(fr.date) as latest_date
FROM stocks s
LEFT JOIN financial_ratios fr ON s.id = fr.stock_id
WHERE s.is_active = true
GROUP BY s.id, s.ticker, s.name
ORDER BY ratio_count DESC
LIMIT 10;
```

```sql
-- 전체 수집 현황
SELECT
  CASE
    WHEN ratio_count = 0 THEN '미수집'
    WHEN ratio_count < 365 THEN '부분수집'
    ELSE '완전수집'
  END as status,
  COUNT(*) as stock_count
FROM (
  SELECT
    s.id,
    COUNT(fr.id) as ratio_count
  FROM stocks s
  LEFT JOIN financial_ratios fr ON s.id = fr.stock_id
  WHERE s.is_active = true
  GROUP BY s.id
) sub
GROUP BY status;
```

### 3. Streamlit 대시보드

```bash
# Week 3 체크 페이지에서 확인
./run_dashboard.sh

# 브라우저에서 "Week 3 Day 8-10" 페이지 확인
```

---

## 트러블슈팅

### Q1. "Group file not found" 오류

**원인**: 그룹 파일이 생성되지 않았습니다.

**해결**:
```bash
# 먼저 그룹 생성
python scripts/create_ratio_groups.py --uncollected-only --group-size 50
```

### Q2. 수집이 너무 느려요

**원인**: pykrx API 응답 시간이 종목마다 다릅니다.

**해결**:
- 짧은 기간으로 테스트: `--start 20240101` (1년만)
- 그룹 크기 조정: `--group-size 30` (더 작은 그룹)
- 정상 속도: 종목당 약 3~5초 소요

### Q3. 중복 데이터가 수집되나요?

**답변**: 아니요. `(stock_id, date)` unique 제약으로 자동 방지됩니다.

```python
# models/financial_ratio.py
__table_args__ = (
    UniqueConstraint('stock_id', 'date', name='idx_financial_ratios_stock_date'),
)
```

### Q4. 재개 시 체크포인트를 못 찾아요

**원인**: 체크포인트 파일이 삭제되었거나 다른 경로에 있습니다.

**확인**:
```bash
ls -la data/checkpoints/ratio_group_*_checkpoint.json
```

**해결**: 체크포인트 없이 처음부터 다시 수집하거나, 이미 수집된 데이터는 스킵됩니다.

---

## 권장 워크플로우

### 초기 전체 수집 (최초 1회)

```bash
# 1. 미수집 종목 그룹 생성 (3년치)
python scripts/create_ratio_groups.py --uncollected-only --group-size 50 --start-date 20220101

# 2. 전체 그룹 순차 수집
python scripts/batch_collect_ratios.py --all --years 3

# 3. 실패 종목 확인
ls data/checkpoints/ratio_group_*_failed.json

# 4. 실패 종목 재수집
python scripts/create_ratio_groups.py --uncollected-only --group-size 50 --start-date 20220101
python scripts/batch_collect_ratios.py --all --years 3
```

### 일일 업데이트

```bash
# 전체 종목 어제 데이터 수집
python scripts/collect_financial_ratios.py --start 20250119 --end 20250120
```

### 주간 업데이트

```bash
# 최근 7일 데이터 수집
python scripts/collect_financial_ratios.py --start 20250113 --end 20250120
```

---

## 파일 구조

```
stock-portfolio-system/
├── scripts/
│   ├── create_ratio_groups.py          # 그룹 생성 스크립트
│   ├── batch_collect_ratios.py         # 그룹 기반 배치 수집
│   └── collect_financial_ratios.py     # 단순 전체 수집 (레거시)
├── data/
│   ├── ratio_groups/                   # 그룹 파일
│   │   ├── ratio_groups_metadata.json  # 그룹 메타데이터
│   │   ├── ratio_group_001.json        # 그룹 1 (50개 종목)
│   │   ├── ratio_group_002.json        # 그룹 2 (50개 종목)
│   │   └── ...
│   └── checkpoints/                    # 체크포인트 및 실패 목록
│       ├── ratio_group_001_checkpoint.json
│       ├── ratio_group_001_failed.json
│       └── ...
└── logs/
    └── pykrx_ratio_collector_YYYYMMDD.log  # 수집 로그
```

---

## 성능 참고

- **그룹당 소요 시간**: 약 3~5분 (50개 종목, 3년 데이터 기준)
- **전체 소요 시간**: 약 4~5시간 (53개 그룹, 2,617개 종목 기준)
- **데이터 크기**: 종목당 약 730건 (3년 = 약 730 거래일)
- **총 레코드 수**: 약 1,900,000건 (2,617개 종목 × 730건)

---

## 참고 문서

- [FINANCIAL_RATIOS_COLLECTION.md](./FINANCIAL_RATIOS_COLLECTION.md) - 재무비율 수집 기본 가이드
- [CLAUDE.md](../CLAUDE.md) - 전체 프로젝트 가이드
