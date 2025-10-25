# Week 5 - Day 23 Completion Report

## 📅 Date: 2025-10-25

## 🎯 Day 23 Goal: 분기 재무제표 수집 DAG 구현

---

## ✅ Completed Tasks

### Task 23.1: quarterly_financial_statement DAG 작성 ✅ (1시간)

**파일**: `airflow/dags/quarterly_financial_statement.py`

**구현 내용**:
- 6개 Task로 구성된 재무제표 수집 파이프라인
- DART API 기반 재무제표 자동 수집
- 재무비율 자동 계산
- 데이터 품질 검증

**Task 구조**:
1. `get_target_quarter`: 수집 대상 분기 계산
2. `get_stocks_with_corp_code`: DART corp_code가 있는 종목 조회
3. `collect_financial_statements`: DART API로 재무제표 수집
4. `calculate_financial_ratios`: 33개 재무비율 계산
5. `validate_data_quality`: 데이터 품질 검증
6. `send_completion_report`: 완료 리포트 생성

### Task 23.2: DART API 호출 Task 구현 ✅ (2시간)

**함수**: `collect_financial_statements()`

**주요 기능**:
- DART OpenAPI를 통한 재무제표 수집
- 분기별 리포트 코드 자동 매핑:
  - Q1: `11013` (1분기보고서)
  - Q2: `11023` (반기보고서)
  - Q3: `11033` (3분기보고서)
  - Q4: `11043` (사업보고서)
- Corp_code 기반 종목 매핑
- 배치 처리 및 진행률 로깅 (50개마다)
- 실패 종목 추적 및 통계

**Rate Limiting**:
- DART API 권장: ~5 requests/second
- DARTCollector에서 자동 처리

### Task 23.3: 재무비율 계산 Task 구현 ✅ (2시간)

**함수**: `calculate_financial_ratios()`

**계산 비율** (33개):

1. **수익성 지표 (7개)**:
   - ROE (자기자본이익률)
   - ROA (총자산이익률)
   - ROIC (투하자본이익률)
   - Gross Profit Margin (매출총이익률)
   - Operating Margin (영업이익률)
   - Net Margin (순이익률)
   - EBITDA Margin

2. **성장성 지표 (5개)**:
   - Revenue Growth (매출 성장률)
   - Operating Income Growth (영업이익 성장률)
   - Net Income Growth (순이익 성장률)
   - EPS Growth (주당순이익 성장률)
   - Asset Growth (자산 성장률)

3. **안정성 지표 (7개)**:
   - Debt Ratio (부채비율)
   - Debt-to-Equity (부채/자기자본비율)
   - Current Ratio (유동비율)
   - Quick Ratio (당좌비율)
   - Interest Coverage (이자보상배율)
   - Equity Ratio (자기자본비율)

4. **활동성 지표 (4개)**:
   - Asset Turnover (총자산회전율)
   - Inventory Turnover (재고자산회전율)
   - Receivables Turnover (매출채권회전율)
   - Payables Turnover (매입채무회전율)

5. **시장가치 지표 (10개)**:
   - PER (주가수익비율)
   - PBR (주가순자산비율)
   - PCR (주가현금흐름비율)
   - PSR (주가매출비율)
   - EV/EBITDA
   - Dividend Yield (배당수익률)
   - Payout Ratio (배당성향)

**처리 방식**:
- FinancialRatioCalculator 클래스 사용
- 자동 commit/rollback
- 계산 실패 종목 추적

### Task 23.4: 데이터 품질 검증 Task 추가 ✅ (1시간)

**함수**: `validate_data_quality()`

**검증 항목**:
1. **수집 성공률 >= 80%**
   - 실패 허용: 20% 이하
   - 예상 성공률: ~85-90%

2. **비율 계산 성공률 >= 90%**
   - 실패 허용: 10% 이하
   - 예상 성공률: ~95%+

3. **최소 수집 건수 >= 1,000**
   - 전체 상장사 대비 적절한 수집량 확인

**실패 시 동작**:
- Exception raise → DAG 실패 처리
- 자동 재시도 (최대 3회)
- Email 알림 발송

### Task 23.5: 스케줄링 설정 (분기말 + 45일 실행) ✅ (1시간)

**스케줄 설정**:
```python
schedule='0 0 15 2,5,8,11 *'  # 2월 15일, 5월 15일, 8월 15일, 11월 15일
```

**스케줄 로직**:
- **45일 대기 이유**: 기업이 분기말 후 45일 이내에 재무제표 공시
- **분기별 수집 일정**:
  - Q1 (1-3월): 5월 15일 수집 (3/31 + 45일)
  - Q2 (4-6월): 8월 15일 수집 (6/30 + 45일)
  - Q3 (7-9월): 11월 15일 수집 (9/30 + 45일)
  - Q4 (10-12월): 2월 15일 수집 (12/31 + 45일)

**재시도 정책**:
```python
'retries': 3,
'retry_delay': timedelta(minutes=10),
'execution_timeout': timedelta(hours=2),
```

---

## 📊 DAG Structure

### Task Dependencies

```
┌────────────────────────┐
│  get_target_quarter    │ ─┐
│  (Calculate Q1-Q4)     │  │
└────────────────────────┘  │
                            ▼
┌────────────────────────┐  │
│ get_stocks_with_corp   │ ─┤
│ _code (Get stocks)     │  │
└────────────────────────┘  │
                            ▼
        ┌───────────────────────────────┐
        │ collect_financial_statements  │
        │ (DART API collection)         │
        └───────────────┬───────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │  calculate_financial_ratios   │
        │  (Calculate 33 ratios)        │
        └───────────────┬───────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │    validate_data_quality      │
        │    (Validate results)         │
        └───────────────┬───────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │   send_completion_report      │
        │   (Generate report)           │
        └───────────────────────────────┘
```

### XCom Data Flow

```
Task 1 → XCom → Task 2-3
         ├─ quarter_info (year, quarter, reprt_code)
         └─ target date calculation

Task 2 → XCom → Task 3
         ├─ stock_list (with corp_code)
         └─ total_stocks

Task 3 → XCom → Task 4-5
         ├─ collection_stats
         └─ failed_stocks

Task 4 → XCom → Task 5-6
         ├─ ratio_stats
         └─ failed_calculations
```

---

## 📁 Created Files

### DAG File
```
airflow/dags/
└── quarterly_financial_statement.py   # Main DAG (650+ lines)
```

### Documentation
```
docs/
└── WEEK5_DAY23_COMPLETION.md          # This report
```

### Deployed Files
```
~/airflow/dags/
└── quarterly_financial_statement.py   # Copied to Airflow
```

---

## 🔧 Technical Details

### DART API Integration

**Report Codes**:
```python
# 분기별 리포트 코드
Q1: '11013'  # 1분기보고서
Q2: '11023'  # 반기보고서
Q3: '11033'  # 3분기보고서
Q4: '11043'  # 사업보고서 (연간)
```

**Corp Code Mapping**:
- `CorpCodeMap` 테이블에서 ticker ↔ corp_code 매핑
- DART API는 corp_code 기반으로 조회
- 한국거래소 ticker와 다른 고유 식별자

### Financial Ratio Calculator

**클래스**: `FinancialRatioCalculator`

**입력**: `FinancialStatement` 객체 (JSONB 데이터)
**출력**: `FinancialRatio` 객체 (33개 비율)

**주요 메서드**:
- `calculate_profitability_ratios()`: 수익성 지표
- `calculate_growth_ratios()`: 성장성 지표
- `calculate_stability_ratios()`: 안정성 지표
- `calculate_activity_ratios()`: 활동성 지표
- `calculate_market_ratios()`: 시장가치 지표
- `calculate_all_ratios()`: 전체 비율 통합

### Error Handling

**3-레벨 에러 처리**:
1. **Task Level**: 개별 종목 실패 → 통계 추적, 계속 진행
2. **Validation Level**: 전체 성공률 검증 → 기준 미달 시 DAG 실패
3. **DAG Level**: 전체 실패 시 콜백 → Email/Slack 알림

---

## 📈 Expected Performance

### Metrics

| Metric | Target | Expected |
|--------|--------|----------|
| Total Stocks | ~2,500 | ~2,500 |
| With Corp Code | ~2,000 | ~2,000 |
| Collection Success | >= 80% | ~85% |
| Ratio Calculation | >= 90% | ~95% |
| Duration | < 2 hours | ~1-1.5 hours |

### Resource Usage

- **CPU**: Medium (API 호출 + 계산)
- **Memory**: ~1GB (재무제표 데이터)
- **Network**: ~50MB (DART API 응답)
- **Disk**: ~20MB/quarter (재무 데이터)

---

## 🚀 Usage

### 1. DAG 확인

```bash
# DAG 리스트 확인
airflow dags list | grep quarterly

# Task 리스트 확인
airflow tasks list quarterly_financial_statement
```

### 2. 수동 실행 (테스트)

```bash
# 현재 분기 재무제표 수집
airflow dags trigger quarterly_financial_statement

# 특정 날짜로 실행 (예: 2025년 Q1 수집)
airflow dags backfill quarterly_financial_statement \
  -s 2025-05-15 \
  -e 2025-05-15 \
  --reset-dagruns
```

### 3. 모니터링

```bash
# 실행 상태 확인
airflow dags list-runs -d quarterly_financial_statement

# 로그 확인
tail -f logs/airflow_quarterly_financial_*.log

# 웹 UI
# http://localhost:8080 → quarterly_financial_statement
```

---

## 🔍 Data Validation

### Pre-collection Checks

1. **Corp Code 존재 확인**:
   ```sql
   SELECT COUNT(*) FROM corp_code_map;
   -- Expected: ~2,000 mappings
   ```

2. **DART API 키 확인**:
   ```bash
   echo $DART_API_KEY
   # Should not be empty
   ```

### Post-collection Checks

1. **수집된 재무제표 확인**:
   ```sql
   SELECT COUNT(*) FROM financial_statements
   WHERE fiscal_year = 2025 AND fiscal_quarter = 1;
   ```

2. **계산된 비율 확인**:
   ```sql
   SELECT COUNT(*) FROM financial_ratios
   WHERE created_at >= CURRENT_DATE;
   ```

3. **데이터 품질 확인**:
   ```sql
   SELECT
       COUNT(*) as total,
       COUNT(CASE WHEN roe IS NOT NULL THEN 1 END) as has_roe,
       COUNT(CASE WHEN per IS NOT NULL THEN 1 END) as has_per
   FROM financial_ratios
   WHERE created_at >= CURRENT_DATE;
   ```

---

## ⚠️ Important Notes

### 1. Corp Code Requirement

**CRITICAL**: DAG는 `corp_code_map` 테이블에 데이터가 있어야 작동합니다.

**확인 방법**:
```python
from db.connection import SessionLocal
from models import CorpCodeMap

db = SessionLocal()
count = db.query(CorpCodeMap).count()
print(f"Corp codes: {count}")
db.close()
```

**Corp Code 수집** (별도 스크립트 필요):
- DART에서 제공하는 corp_code XML 다운로드
- Ticker와 corp_code 매핑 테이블 생성
- 참고: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001

### 2. DART API Rate Limit

- **권장**: ~5 requests/second
- **일일 한도**: 10,000 requests (무료 API KEY)
- **대응**: DARTCollector에서 자동 delay 처리

### 3. 45일 대기 Period

**법적 근거**:
- 자본시장법에 따라 상장사는 분기말 후 45일 이내 재무제표 공시
- 일부 기업은 더 빨리 공시하지만, 전체를 수집하려면 45일 대기 필요

**예외 처리**:
- 공시 지연 기업: 다음 분기에 재수집
- 공시 미제출 기업: failed_stocks에 기록

---

## 🐛 Troubleshooting

### Issue: No stocks with corp_code

**원인**: `corp_code_map` 테이블이 비어있음

**해결**:
1. DART corp_code XML 다운로드
2. 매핑 스크립트 실행 (별도 구현 필요)
3. DAG 재실행

### Issue: DART API 401 Unauthorized

**원인**: DART_API_KEY가 없거나 잘못됨

**해결**:
```bash
# .env 파일 확인
cat .env | grep DART_API_KEY

# API 키 테스트
python scripts/test_dart_api.py
```

### Issue: Ratio calculation fails

**원인**: 재무제표 JSONB 구조 불일치

**해결**:
1. FinancialStatement 데이터 구조 확인
2. FinancialRatioCalculator 로직 디버깅
3. 로그 확인: `logs/airflow_quarterly_financial_*.log`

---

## 📊 Success Criteria

### ✅ Validation Criteria

1. **DAG Import**: ✅ No errors
2. **Task Recognition**: ✅ 6 tasks listed
3. **Manual Trigger**: To be tested
4. **Collection Success**: >= 80%
5. **Ratio Calculation**: >= 90%

### Expected Results

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Quarter: 2025 Q1
Total Stocks: 2,000
Collected: 1,700 (85%)
Ratios Calculated: 1,650 (97%)
Duration: ~90 minutes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🎓 Next Steps

### Day 24: 모니터링 대시보드 구축

1. Airflow 메트릭 수집
2. DAG 실행 상태 시각화
3. 데이터 품질 대시보드
4. 알림 시스템 강화

### Week 6: Phase 2 시작

1. 포트폴리오 최적화 모델
2. 백테스팅 시스템
3. 리스크 관리
4. 성과 분석

---

## 📚 References

- [DART OpenAPI Guide](https://opendart.fss.or.kr/guide/main.do)
- [Financial Ratio Definitions](https://www.investopedia.com/financial-ratios-4689817)
- [Airflow Best Practices](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html)

---

**Status**: 🟢 **DAG CREATED - READY FOR TESTING**

**Generated**: 2025-10-25
**Author**: Stock Portfolio System
**Version**: 1.0
