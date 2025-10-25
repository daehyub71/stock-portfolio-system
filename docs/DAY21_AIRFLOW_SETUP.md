## Day 21: Apache Airflow 설치 및 환경 설정

Workflow orchestration을 위한 Apache Airflow 설치 및 설정 가이드입니다.

---

## 📋 Overview

Apache Airflow는 복잡한 데이터 파이프라인을 프로그래밍 방식으로 작성, 스케줄링, 모니터링할 수 있는 플랫폼입니다.

### 구현 목표

✅ Airflow 설치 및 기본 설정
✅ PostgreSQL 메타 데이터베이스 연결
✅ Connections 설정 (PostgreSQL, DART API, KIS API)
✅ 테스트 DAG 작성 및 실행

---

## 🚀 Quick Start

### 1. Airflow 설치

```bash
# 가상환경 활성화
source venv/bin/activate

# Airflow 설치 스크립트 실행
./scripts/setup_airflow.sh
```

### 2. Airflow 설정

```bash
# SQLite 사용 (개발용, 기본값)
python scripts/configure_airflow.py

# PostgreSQL 사용 (프로덕션 권장)
python scripts/configure_airflow.py --postgres
```

### 3. Connections 설정

```bash
# .env 파일에 API 키가 설정되어 있어야 함
python scripts/setup_airflow_connections.py
```

### 4. Airflow 시작

```bash
# Webserver와 Scheduler 시작
./scripts/start_airflow.sh

# 상태 확인
./scripts/airflow_status.sh

# 종료
./scripts/stop_airflow.sh
```

### 5. 웹 UI 접속

```
URL: http://localhost:8080
Username: admin
Password: admin
```

---

## 📁 파일 구조

```
stock-portfolio-system/
├── airflow/                          # Airflow home directory
│   ├── airflow.cfg                   # Airflow 설정 파일
│   ├── dags/                         # DAG 파일들
│   │   └── test_dag.py               # 테스트 DAG
│   ├── logs/                         # Airflow 로그
│   ├── plugins/                      # 커스텀 플러그인
│   └── .airflow_env                  # 환경 변수
│
├── scripts/
│   ├── setup_airflow.sh              # Airflow 설치 스크립트
│   ├── configure_airflow.py          # Airflow 설정 스크립트
│   ├── setup_airflow_connections.py  # Connections 설정 스크립트
│   ├── start_airflow.sh              # Airflow 시작 스크립트
│   ├── stop_airflow.sh               # Airflow 종료 스크립트
│   └── airflow_status.sh             # Airflow 상태 확인 스크립트
│
└── airflow-requirements.txt          # Airflow 전용 requirements
```

---

## 🔧 상세 설치 가이드

### Step 1: Airflow 설치

#### 1-1. 설치 스크립트 실행

```bash
# 프로젝트 루트 디렉토리에서
cd /Users/sunchulkim/src/stock-portfolio-system

# 가상환경 활성화 확인
source venv/bin/activate

# 설치 스크립트 실행
./scripts/setup_airflow.sh
```

**설치되는 항목:**
- Apache Airflow 2.10.4 (Python 3.13 지원)
- Airflow Providers (postgres, http)
- 필요한 디렉토리 구조
- 시작/종료 스크립트
- 기본 관리자 계정 (admin/admin)

#### 1-2. 환경 변수 설정

설치 후 새 터미널을 열거나 다음 명령 실행:

```bash
source ~/.zshrc  # 또는 ~/.bashrc
```

`AIRFLOW_HOME` 환경 변수가 설정됩니다:

```bash
echo $AIRFLOW_HOME
# 출력: /Users/sunchulkim/src/stock-portfolio-system/airflow
```

---

### Step 2: Airflow 설정

#### 2-1. 데이터베이스 선택

**Option A: SQLite (개발용, 기본값)**

```bash
python scripts/configure_airflow.py
```

장점:
- 설정 간단
- 별도 DB 서버 불필요

단점:
- 병렬 처리 제한
- 프로덕션 부적합

**Option B: PostgreSQL (프로덕션 권장)**

```bash
# 먼저 PostgreSQL에 Airflow 전용 DB 생성
createdb airflow_db

# Airflow 설정 (자동으로 DB 생성 시도)
python scripts/configure_airflow.py --postgres
```

장점:
- 완전한 병렬 처리
- 프로덕션 환경 적합
- 고성능

#### 2-2. 설정 파일 확인

`airflow/airflow.cfg` 파일이 생성됩니다:

```ini
[core]
dags_folder = /Users/sunchulkim/src/stock-portfolio-system/airflow/dags
load_examples = False
executor = LocalExecutor
default_timezone = Asia/Seoul
parallelism = 32

[database]
sql_alchemy_conn = postgresql+psycopg2://...
# 또는
sql_alchemy_conn = sqlite:////path/to/airflow/airflow.db

[webserver]
base_url = http://localhost:8080
expose_config = True

[scheduler]
catchup_by_default = False
dag_run_timeout = 86400
```

주요 설정:
- `load_examples = False`: 예제 DAG 로드 안함
- `executor = LocalExecutor`: 로컬 실행자 (병렬 가능)
- `default_timezone = Asia/Seoul`: 한국 시간대
- `catchup_by_default = False`: 과거 실행 건너뛰기

---

### Step 3: Connections 설정

Airflow에서 외부 시스템에 접근하기 위한 연결 정보를 설정합니다.

#### 3-1. .env 파일 확인

먼저 `.env` 파일에 필요한 정보가 있는지 확인:

```bash
# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stock_portfolio
DB_USER=your_username
DB_PASSWORD=

# DART API
DART_API_KEY=your_dart_api_key

# KIS API
KIS_APP_KEY=your_kis_app_key
KIS_APP_SECRET=your_kis_app_secret
KIS_ACCOUNT_TYPE=VIRTUAL
```

#### 3-2. Connections 생성

```bash
python scripts/setup_airflow_connections.py
```

생성되는 Connections:

| Connection ID | Type | 설명 |
|--------------|------|------|
| `postgres_stock_portfolio` | postgres | Stock Portfolio DB |
| `dart_api` | http | DART OpenAPI |
| `kis_api` | http | Korea Investment Securities API |

#### 3-3. 웹 UI에서 확인

1. Airflow 시작: `./scripts/start_airflow.sh`
2. 웹 UI 접속: http://localhost:8080
3. Admin → Connections 메뉴
4. 생성된 Connection 확인

---

### Step 4: Airflow 시작

#### 4-1. 시작 스크립트 사용

```bash
./scripts/start_airflow.sh
```

출력:
```
Starting Airflow webserver and scheduler...
Airflow Home: /Users/sunchulkim/src/stock-portfolio-system/airflow

✅ Airflow가 시작되었습니다!
   웹 UI: http://localhost:8080
   Username: admin
   Password: admin

종료하려면: ./scripts/stop_airflow.sh
```

#### 4-2. 수동 시작 (디버깅용)

```bash
# 터미널 1: Webserver
airflow webserver --port 8080

# 터미널 2: Scheduler
airflow scheduler
```

#### 4-3. 상태 확인

```bash
./scripts/airflow_status.sh
```

출력:
```
=== Airflow 상태 ===

✅ Webserver: Running (http://localhost:8080)
✅ Scheduler: Running

프로세스 상세:
  PID: 12345 CMD: airflow webserver
  PID: 12346 CMD: airflow scheduler
```

#### 4-4. 로그 확인

```bash
# Webserver 로그
tail -f airflow/logs/scheduler/latest/scheduler.log

# Scheduler 로그
tail -f airflow/logs/dag_processor_manager/dag_processor_manager.log
```

---

### Step 5: 테스트 DAG 실행

#### 5-1. DAG 파일 확인

`airflow/dags/test_dag.py`가 생성되어 있습니다.

이 DAG는 다음을 테스트합니다:
- Python operator
- Bash operator
- PostgreSQL connection
- 프로젝트 모듈 import

#### 5-2. 웹 UI에서 실행

1. http://localhost:8080 접속
2. 로그인 (admin/admin)
3. DAGs 목록에서 `test_dag` 찾기
4. 왼쪽 토글 버튼을 ON으로 변경
5. "Trigger DAG" 버튼 (▶️) 클릭
6. Graph View 또는 Grid View에서 실행 상태 확인

#### 5-3. CLI에서 실행

```bash
# DAG 목록 확인
airflow dags list

# test_dag 실행
airflow dags test test_dag 2025-01-24

# 특정 task만 실행
airflow tasks test test_dag print_context 2025-01-24
```

#### 5-4. 실행 결과 확인

모든 Task가 초록색(성공)이면 Airflow 설정이 올바르게 완료된 것입니다.

**성공 화면:**
```
✅ print_context
✅ test_python_environment
✅ echo_test
✅ test_postgres_connection
✅ success
```

---

## 🎯 검증 항목

### ✅ 필수 검증

- [ ] Airflow 설치 완료 (`airflow version` 실행)
- [ ] 웹 UI 접속 가능 (http://localhost:8080)
- [ ] 관리자 계정 로그인 성공 (admin/admin)
- [ ] PostgreSQL connection 설정됨
- [ ] DART API connection 설정됨
- [ ] KIS API connection 설정됨
- [ ] test_dag 실행 성공
- [ ] 모든 task가 성공 (초록색)

### 🔍 추가 확인

```bash
# Airflow 버전
airflow version

# DAG 목록
airflow dags list

# Connection 목록
airflow connections list

# 사용자 목록
airflow users list
```

---

## 🛠️ 트러블슈팅

### 문제 1: "airflow: command not found"

**원인:** 가상환경이 활성화되지 않음 또는 PATH 문제

**해결:**
```bash
# 가상환경 활성화
source venv/bin/activate

# Airflow 설치 확인
which airflow
# 출력: /Users/sunchulkim/src/stock-portfolio-system/venv/bin/airflow
```

### 문제 2: "ImportError: No module named 'airflow'"

**원인:** Airflow가 설치되지 않음

**해결:**
```bash
# Airflow 재설치
./scripts/setup_airflow.sh
```

### 문제 3: "Database connection refused"

**원인:** PostgreSQL이 실행되지 않음

**해결:**
```bash
# PostgreSQL 상태 확인
brew services list | grep postgresql

# PostgreSQL 시작
brew services start postgresql@15
```

### 문제 4: "ModuleNotFoundError" in DAG

**원인:** DAG에서 프로젝트 모듈을 import할 수 없음

**해결:**

DAG 파일 상단에 추가:
```python
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
```

### 문제 5: "Port 8080 already in use"

**원인:** 다른 프로세스가 8080 포트 사용

**해결:**
```bash
# 포트 사용 프로세스 확인
lsof -i :8080

# 프로세스 종료
kill -9 <PID>

# 또는 다른 포트 사용
airflow webserver --port 8081
```

### 문제 6: DAG가 웹 UI에 나타나지 않음

**원인:**
- DAG 파일 구문 오류
- DAG 폴더 경로 잘못됨
- Scheduler가 실행되지 않음

**해결:**
```bash
# DAG 파일 구문 검증
python airflow/dags/test_dag.py

# DAG 폴더 확인
airflow config get-value core dags_folder

# Scheduler 상태 확인
./scripts/airflow_status.sh

# Scheduler 재시작
./scripts/stop_airflow.sh
./scripts/start_airflow.sh
```

---

## 📊 Airflow 아키텍처

```
┌─────────────────────────────────────────┐
│         Airflow Webserver               │
│     (http://localhost:8080)             │
│  - DAG 시각화                            │
│  - Task 실행 모니터링                    │
│  - Connection 관리                       │
└─────────────────────────────────────────┘
                  ↕
┌─────────────────────────────────────────┐
│         Airflow Scheduler               │
│  - DAG 파싱                              │
│  - Task 스케줄링                         │
│  - Task 실행                             │
└─────────────────────────────────────────┘
                  ↕
┌─────────────────────────────────────────┐
│         Metadata Database               │
│    (PostgreSQL 또는 SQLite)              │
│  - DAG 정의                              │
│  - Task 상태                             │
│  - 실행 히스토리                         │
└─────────────────────────────────────────┘
                  ↕
┌─────────────────────────────────────────┐
│            DAG Files                    │
│     (airflow/dags/*.py)                 │
│  - ETL 파이프라인 정의                   │
│  - Task 의존성                           │
│  - 스케줄 설정                           │
└─────────────────────────────────────────┘
```

### 주요 컴포넌트

**Webserver:**
- 사용자 인터페이스 제공
- DAG 시각화 및 모니터링
- Task 로그 조회

**Scheduler:**
- DAG 파일 파싱
- Task 스케줄링 및 실행
- 의존성 관리

**Metadata Database:**
- DAG 및 Task 정보 저장
- 실행 히스토리 기록
- Connection 정보 저장

**Executor:**
- LocalExecutor: 로컬 프로세스로 Task 실행 (병렬 가능)
- SequentialExecutor: 순차 실행 (SQLite 전용)
- CeleryExecutor: 분산 실행 (프로덕션)

---

## 📝 다음 단계

Airflow 설치 및 설정이 완료되었습니다!

### Day 22: 데이터 수집 DAG 작성

다음 Day에서는 실제 데이터 수집 파이프라인을 DAG로 구현합니다:

1. **일일 시세 수집 DAG**
   - 매일 오전 9시 실행
   - pykrx로 전일 데이터 수집
   - 실패 시 재시도

2. **분기 재무제표 수집 DAG**
   - 분기별 실행
   - DART API로 재무제표 수집
   - 재무비율 자동 계산

3. **데이터 품질 검증 DAG**
   - 데이터 수집 후 자동 실행
   - 이상치 탐지
   - 품질 리포트 생성

---

## 🔗 참고 자료

### 공식 문서
- Apache Airflow: https://airflow.apache.org/
- Airflow Tutorial: https://airflow.apache.org/docs/apache-airflow/stable/tutorial.html
- Airflow CLI: https://airflow.apache.org/docs/apache-airflow/stable/cli-and-env-variables-ref.html

### 유용한 링크
- DAG Best Practices: https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html
- Operators: https://airflow.apache.org/docs/apache-airflow/stable/_api/airflow/operators/index.html
- Hooks: https://airflow.apache.org/docs/apache-airflow/stable/_api/airflow/hooks/index.html

---

**Last Updated**: 2025-01-24
**Author**: Stock Portfolio System Development Team
