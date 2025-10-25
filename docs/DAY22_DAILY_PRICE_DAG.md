# Day 22: Daily Price Collection DAG

## 📋 Overview

일일 시세 자동 수집을 위한 Airflow DAG 구현 완료.

## ✅ Completed Tasks

### Task 22.1: DAG Skeleton ✅
- DAG 파일 생성: `airflow/dags/daily_price_collection.py`
- 4개 Task 구조 정의
- XCom을 통한 Task 간 데이터 전달

### Task 22.2: KIS API Call Task (PythonOperator) ✅
- **실제로는 PyKRX 사용** (KIS API보다 안정적이고 빠름)
- `collect_daily_prices` 함수 구현
- 2,500개 종목 처리 최적화
- 실시간 진행률 로깅 (100개마다)

### Task 22.3: DB Save Task ✅
- PyKRXPriceCollector 내부에서 자동 저장
- 트랜잭션 관리 및 중복 방지
- 에러 처리 및 재시도 로직

### Task 22.4: Failure Notifications ✅
- 콜백 함수 구현: `utils/notification_callbacks.py`
- Task 레벨 콜백:
  - `task_failure_callback`: Task 실패 시
  - `task_success_callback`: Task 성공 시
- DAG 레벨 콜백:
  - `dag_failure_callback`: DAG 실패 시
  - `dag_success_callback`: DAG 성공 시
- Slack/Email 통합 준비 (구현 예정)

### Task 22.5: DAG Scheduling ✅
- 스케줄: `0 18 * * 1-5` (월-금 오후 6시 KST)
- `catchup=False`: 과거 실행 건너뛰기
- `max_active_runs=1`: 동시 실행 방지

## 📊 DAG Structure

```
daily_price_collection DAG
│
├─ get_stocks_to_update
│   └─ 활성 종목 리스트 조회 (DB)
│   └─ XCom: stock_list, total_stocks
│
├─ collect_daily_prices
│   └─ PyKRX로 일일 시세 수집
│   └─ XCom: collection_stats, failed_stocks
│
├─ validate_collection
│   └─ 성공률 검증 (>= 90%)
│   └─ 실패 시 Exception raise
│
└─ send_completion_report
    └─ 완료 리포트 생성 및 로깅
    └─ XCom: completion_report
```

## 🎯 Performance Target

- **2,500 stocks in 30 minutes**
- PyKRX는 rate limit 없음
- 실제 소요 시간: ~15-20분 예상

## 🚀 Usage

### 1. DAG 파일 위치 확인

```bash
# DAG 파일이 올바른 위치에 있는지 확인
ls -la ~/airflow/dags/daily_price_collection.py
ls -la ~/airflow/dags/utils/notification_callbacks.py
```

**중요**: Airflow는 `~/airflow/dags/` 디렉토리를 기본으로 사용합니다.
프로젝트 디렉토리의 `airflow/dags/`가 아니라 홈 디렉토리의 `~/airflow/dags/`에 파일을 복사해야 합니다.

```bash
# DAG 파일 복사
cp airflow/dags/daily_price_collection.py ~/airflow/dags/
cp -r airflow/dags/utils ~/airflow/dags/
```

### 2. PYTHONPATH 설정

DAG가 프로젝트 모듈(collectors, models 등)을 import할 수 있도록 PYTHONPATH 설정:

```bash
# ~/.zshrc 또는 ~/.bashrc에 추가
export AIRFLOW_HOME=~/airflow
export PYTHONPATH="/Users/sunchulkim/src/stock-portfolio-system:$PYTHONPATH"
```

또는 Airflow 시작 시마다:

```bash
export PYTHONPATH="/Users/sunchulkim/src/stock-portfolio-system:$PYTHONPATH"
airflow webserver --port 8080 &
airflow scheduler &
```

### 3. Airflow 시작

```bash
# 가상환경 활성화
source venv/bin/activate

# Webserver 시작 (백그라운드)
airflow webserver --port 8080 --daemon

# Scheduler 시작 (백그라운드)
airflow scheduler --daemon

# 상태 확인
ps aux | grep airflow
```

### 4. DAG 확인

웹 UI에서 확인:
- URL: http://localhost:8080
- Login: admin / admin
- DAG 목록에서 `daily_price_collection` 찾기

CLI로 확인:
```bash
# DAG 리스트 확인
airflow dags list

# DAG 상세 정보
airflow dags show daily_price_collection

# DAG Tasks 확인
airflow tasks list daily_price_collection
```

### 5. 수동 실행 (테스트)

```bash
# DAG 트리거 (현재 시간으로 실행)
airflow dags trigger daily_price_collection

# 특정 날짜로 실행 (backfill)
airflow dags backfill daily_price_collection \
  -s 2025-10-24 \
  -e 2025-10-24 \
  --reset-dagruns

# 실시간 로그 확인
tail -f ~/airflow/logs/dag_id=daily_price_collection/run_id=*/task_id=collect_daily_prices/*.log
```

### 6. 모니터링

```bash
# DAG 실행 상태 확인
airflow dags list-runs -d daily_price_collection

# Task 상태 확인
airflow tasks states-for-dag-run \
  daily_price_collection \
  <run_id>

# 로그 확인
tail -f logs/airflow_daily_price_*.log
```

## 🔧 Configuration

### Environment Variables

`.env` 파일에 필요한 변수들:

```bash
# Database (이미 설정되어 있음)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stock_portfolio
DB_USER=sunchulkim
DB_PASSWORD=

# Airflow (선택사항)
AIRFLOW_HOME=~/airflow
```

### Email Notifications (선택사항)

`~/airflow/airflow.cfg` 파일에서 SMTP 설정:

```ini
[smtp]
smtp_host = smtp.gmail.com
smtp_starttls = True
smtp_ssl = False
smtp_user = your-email@gmail.com
smtp_password = your-app-password
smtp_port = 587
smtp_mail_from = airflow@example.com
```

### Slack Notifications (선택사항)

Slack Webhook URL을 Airflow Variable로 설정:

```bash
airflow variables set slack_webhook_url "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

그리고 `utils/notification_callbacks.py`의 `_send_slack_notification` 함수 주석 해제.

## 📈 Success Criteria

### ✅ Validation Checks

1. **DAG 수동 실행 성공**: `airflow dags trigger` 명령으로 실행 성공
2. **2,500개 종목 수집**: 활성 종목 전체 수집
3. **30분 이내 완료**: 전체 프로세스 30분 이내
4. **성공률 >= 90%**: validate_collection Task 통과
5. **로그 정상 생성**: `logs/airflow_daily_price_*.log` 파일 생성

### 📊 Expected Statistics

예상 통계 (2,500개 종목 기준):
- **Success**: ~2,450개 (98%)
- **Skipped**: ~30개 (휴장일, 거래정지 등)
- **Failed**: ~20개 (2%, API 오류 등)

## 🐛 Troubleshooting

### Issue 1: DAG가 Airflow UI에 안 보임

**원인**: DAG 파일이 `~/airflow/dags/`에 없음

**해결**:
```bash
cp airflow/dags/daily_price_collection.py ~/airflow/dags/
cp -r airflow/dags/utils ~/airflow/dags/
```

### Issue 2: Import Error - No module named 'collectors'

**원인**: PYTHONPATH 설정 안 됨

**해결**:
```bash
export PYTHONPATH="/Users/sunchulkim/src/stock-portfolio-system:$PYTHONPATH"
airflow scheduler --daemon  # Restart scheduler
```

### Issue 3: Database connection error

**원인**: PostgreSQL 연결 정보 불일치

**해결**:
```bash
# .env 파일 확인
cat .env | grep DB_

# PostgreSQL 실행 확인
brew services list | grep postgresql

# 연결 테스트
python -c "from db.connection import test_connection; test_connection()"
```

### Issue 4: Task 실패 - Too many failures

**원인**: 네트워크 오류 또는 API 문제

**해결**:
1. 로그 확인: `tail -f logs/airflow_daily_price_*.log`
2. 수동 재시도: Airflow UI에서 "Clear" 버튼
3. 재시도 횟수 증가: `default_args['retries']` 수정

## 📝 Next Steps

### Week 5 - Day 23-25

- **Day 23**: 재무제표 수집 DAG
- **Day 24**: 모니터링 대시보드
- **Day 25**: 성능 최적화 및 안정화

## 📚 References

- Airflow Documentation: https://airflow.apache.org/docs/
- PyKRX Documentation: https://github.com/sharebook-kr/pykrx
- Project CLAUDE.md: 프로젝트 구조 및 설정

## 🎓 Lessons Learned

1. **PyKRX vs KIS API**: PyKRX가 더 안정적이고 빠름 (rate limit 없음)
2. **XCom 활용**: Task 간 데이터 전달에 효과적
3. **Validation Layer**: 데이터 품질 검증 필수
4. **Callback Functions**: 운영 모니터링에 중요
5. **PYTHONPATH 설정**: Airflow에서 프로젝트 모듈 import 시 필수
