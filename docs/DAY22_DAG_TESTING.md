# Day 22: DAG Testing Guide

## ✅ DAG Import 성공!

**Status**: DAG가 Airflow에 성공적으로 로드되었습니다.

```bash
$ airflow dags list | grep daily_price
daily_price_collection    /Users/sunchulkim/airflow/dags/daily_price_collection.py    stock-portfolio
```

## 🔧 해결한 문제

### Issue 1: `ModuleNotFoundError: No module named 'pkg_resources'`

**원인**: pykrx가 `pkg_resources`를 사용하는데 `setuptools`가 설치되지 않음

**해결**:
```bash
pip install setuptools
```

### Issue 2: Deprecation warnings

**원인**: Airflow 2.x에서 deprecated된 파라미터 사용
- `schedule_interval` → `schedule`
- `provide_context` → 제거 (기본값)

**해결**: DAG 코드 업데이트 완료

## 📋 DAG 확인

### 1. DAG 리스트 확인

```bash
export PYTHONPATH="/Users/sunchulkim/src/stock-portfolio-system:$PYTHONPATH"
airflow dags list | grep daily_price
```

### 2. Task 리스트 확인

```bash
airflow tasks list daily_price_collection
```

**Output**:
```
collect_daily_prices
get_stocks_to_update
send_completion_report
validate_collection
```

### 3. DAG 구조 확인

```bash
airflow dags show daily_price_collection
```

### 4. DAG 상세 정보

```bash
airflow dags details daily_price_collection
```

## 🚀 DAG 실행 방법

### 방법 1: Airflow UI에서 실행

1. 웹 브라우저에서 http://localhost:8080 접속
2. Login: `admin` / `admin`
3. DAG 목록에서 `daily_price_collection` 찾기
4. 오른쪽의 "Play" 버튼 클릭 → "Trigger DAG" 선택

### 방법 2: CLI에서 수동 실행

```bash
# PYTHONPATH 설정
export PYTHONPATH="/Users/sunchulkim/src/stock-portfolio-system:$PYTHONPATH"

# DAG 트리거 (현재 시간으로 실행)
airflow dags trigger daily_price_collection

# 실행 상태 확인
airflow dags list-runs -d daily_price_collection --state running

# 특정 Task 로그 확인
airflow tasks logs daily_price_collection collect_daily_prices <run_id> 1
```

### 방법 3: 특정 날짜로 Backfill

```bash
# 2025-10-24 데이터 수집
airflow dags backfill daily_price_collection \
  -s 2025-10-24 \
  -e 2025-10-24 \
  --reset-dagruns
```

## 📊 모니터링

### 실시간 로그 확인

```bash
# Airflow 로그
tail -f ~/airflow/logs/dag_id=daily_price_collection/*/task_id=collect_daily_prices/*/attempt=*.log

# 프로젝트 로그
tail -f /Users/sunchulkim/src/stock-portfolio-system/logs/airflow_daily_price_*.log
```

### DAG Run 상태 확인

```bash
# 최근 실행 내역
airflow dags list-runs -d daily_price_collection

# 특정 Run의 Task 상태
airflow tasks states-for-dag-run daily_price_collection <run_id>
```

### 웹 UI에서 모니터링

1. **Graph View**: Task 의존성 및 실행 상태 시각화
2. **Tree View**: 시간별 실행 내역
3. **Gantt Chart**: Task 실행 시간 분석
4. **Task Logs**: 각 Task의 상세 로그

## ⚠️ 실행 전 체크리스트

### 1. Database 연결 확인

```bash
python -c "from db.connection import test_connection; test_connection()"
```

**Expected Output**:
```
Testing PostgreSQL connection...
✅ Connection successful!
PostgreSQL version: PostgreSQL 15.x
```

### 2. 활성 종목 수 확인

```bash
python -c "
from db.connection import SessionLocal
from models import Stock
from sqlalchemy import and_
from datetime import datetime

db = SessionLocal()
count = db.query(Stock).filter(
    and_(
        Stock.is_active == True,
        (Stock.delisting_date.is_(None) | (Stock.delisting_date >= datetime.now().date()))
    )
).count()
print(f'Active stocks: {count}')
db.close()
"
```

**Expected**: ~2,500 stocks

### 3. PYTHONPATH 설정 확인

```bash
echo $PYTHONPATH
# Should include: /Users/sunchulkim/src/stock-portfolio-system
```

### 4. Airflow 서비스 확인

```bash
ps aux | grep airflow | grep -v grep
```

**Expected**:
- `airflow webserver`
- `airflow scheduler`

## 🎯 예상 실행 결과

### Task 1: get_stocks_to_update

- **Duration**: ~5초
- **Output**: ~2,500 stocks pushed to XCom

### Task 2: collect_daily_prices

- **Duration**: ~15-20분 (2,500 stocks)
- **Success Rate**: ~98%
- **Output**: Collection statistics

### Task 3: validate_collection

- **Duration**: ~1초
- **Validation**: Success rate >= 90%

### Task 4: send_completion_report

- **Duration**: ~1초
- **Output**: Completion report logged

### Total Duration

**Target**: < 30분
**Expected**: ~20-25분

## 🐛 Troubleshooting

### Issue: Task가 "queued" 상태로 멈춤

**원인**: Executor가 SequentialExecutor (기본값)

**확인**:
```bash
airflow config get-value core executor
```

**해결**: LocalExecutor 사용 권장 (PostgreSQL 메타 DB 필요)

### Issue: Import Error in Task

**원인**: PYTHONPATH가 scheduler에 전달되지 않음

**해결**:
```bash
# Scheduler 재시작 시 PYTHONPATH 설정
export PYTHONPATH="/Users/sunchulkim/src/stock-portfolio-system:$PYTHONPATH"
pkill -f "airflow scheduler"
airflow scheduler --daemon
```

### Issue: Database connection failed

**원인**: PostgreSQL이 실행 중이지 않음

**해결**:
```bash
# PostgreSQL 시작
brew services start postgresql@15

# 연결 테스트
psql -U sunchulkim -d stock_portfolio -c "SELECT 1"
```

### Issue: Task timeout

**원인**: 2,500 종목 수집이 45분을 초과

**해결**: `default_args`의 `execution_timeout` 증가
```python
'execution_timeout': timedelta(minutes=60),  # 45 → 60분
```

## 📈 성공 기준

### ✅ Validation Criteria

1. **DAG Import**: ✅ No errors in Airflow UI
2. **Task Recognition**: ✅ 4 tasks listed
3. **Manual Trigger**: Successful execution
4. **Duration**: < 30 minutes
5. **Success Rate**: >= 90%
6. **Data Quality**: Prices saved to database

### 📊 Expected Statistics

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Stocks:    2,500
Success:         2,450 (98%)
Skipped:         30 (1.2%)
Failed:          20 (0.8%)
Success Rate:    98.00%
Duration:        ~20 minutes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 🎓 Next Steps

### 1. 첫 실행 (Test Run)

```bash
# PYTHONPATH 설정
export PYTHONPATH="/Users/sunchulkim/src/stock-portfolio-system:$PYTHONPATH"

# DAG 트리거
airflow dags trigger daily_price_collection

# 웹 UI에서 모니터링
# http://localhost:8080
```

### 2. 결과 검증

```bash
# 수집된 데이터 확인
python -c "
from db.connection import SessionLocal
from models import DailyPrice
from datetime import datetime

db = SessionLocal()
today = datetime.now().date()
count = db.query(DailyPrice).filter(DailyPrice.date == today).count()
print(f'Prices collected today: {count}')
db.close()
"
```

### 3. 스케줄 활성화

DAG가 정상 작동 확인 후:
1. Airflow UI에서 DAG 토글을 ON으로 설정
2. 매일 오후 6시에 자동 실행됨

### 4. Day 23으로 진행

재무제표 수집 DAG 구현 준비

---

**Status**: 🟢 **READY TO RUN**

**Last Updated**: 2025-10-25
