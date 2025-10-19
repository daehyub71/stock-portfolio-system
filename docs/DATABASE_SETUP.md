# PostgreSQL 데이터베이스 설정 가이드

## 📋 현재 설정 (이미 완료됨)

`.env` 파일의 데이터베이스 설정은 **이미 올바르게 설정**되어 있습니다:

```bash
DB_HOST=localhost        # ✅ 로컬 컴퓨터에서 실행
DB_PORT=5432             # ✅ PostgreSQL 기본 포트
DB_NAME=stock_portfolio  # ✅ 생성된 데이터베이스 이름
DB_USER=sunchulkim       # ✅ macOS 사용자명 (슈퍼유저)
DB_PASSWORD=             # ✅ 비워두기 (로컬 연결은 비밀번호 불필요)
```

## ❓ 왜 비밀번호가 비어있나요?

macOS에서 Homebrew로 PostgreSQL을 설치하면:

1. **자동 사용자 생성**: 현재 macOS 사용자(`sunchulkim`)가 PostgreSQL 슈퍼유저로 자동 생성됩니다
2. **Peer Authentication**: 로컬 연결에서는 운영체제 사용자명으로 인증
   - 같은 사용자명이면 비밀번호 없이 접속 가능
   - 보안상 안전 (외부에서 접속 불가능)

## 🔍 연결 테스트 방법

### 1. 환경 변수 확인
```bash
python -c "
from dotenv import load_dotenv
import os
load_dotenv()
print(f'DB_NAME: {os.getenv(\"DB_NAME\")}')
print(f'DB_USER: {os.getenv(\"DB_USER\")}')
"
```

### 2. DB 연결 테스트
```bash
python db/connection.py
```

성공 시 출력:
```
🔍 Testing database connection...
✅ PostgreSQL version: PostgreSQL 15.14 (Homebrew) ...
✅ Database connection test passed
```

### 3. psql로 직접 접속
```bash
psql stock_portfolio
```

접속 후:
```sql
-- 현재 사용자 확인
SELECT current_user;

-- 데이터베이스 목록 보기
\l

-- 테이블 목록 보기
\dt

-- 종료
\q
```

## 📌 유용한 PostgreSQL 명령어

### psql 명령어 (터미널에서)
```bash
# 데이터베이스 접속
psql stock_portfolio

# 특정 쿼리 실행
psql -d stock_portfolio -c "SELECT version();"

# 모든 데이터베이스 목록
psql -l
```

### SQL 명령어 (psql 접속 후)
```sql
-- 현재 데이터베이스 정보
SELECT current_database();

-- 사용자 목록
\du

-- 테이블 목록
\dt

-- 테이블 구조 확인
\d table_name

-- 테이블 크기 확인
SELECT pg_size_pretty(pg_total_relation_size('table_name'));
```

## 🔧 PostgreSQL 서비스 관리

```bash
# 서비스 시작
brew services start postgresql@15

# 서비스 중지
brew services stop postgresql@15

# 서비스 재시작
brew services restart postgresql@15

# 서비스 상태 확인
brew services list | grep postgresql
```

## 🚨 문제 해결

### 연결이 안 될 때

1. **PostgreSQL이 실행 중인지 확인**
   ```bash
   brew services list | grep postgresql@15
   ```

2. **재시작 시도**
   ```bash
   brew services restart postgresql@15
   ```

3. **포트 확인**
   ```bash
   lsof -i :5432
   ```

### 비밀번호 설정이 필요한 경우 (선택사항)

프로덕션 환경이나 외부 접속이 필요한 경우:

```sql
-- psql 접속 후
ALTER USER sunchulkim WITH PASSWORD 'your_password';
```

그 다음 `.env` 파일 업데이트:
```bash
DB_PASSWORD=your_password
```

## ⚙️ 고급 설정 (필요시)

### 외부 접속 허용 (주의!)

`/opt/homebrew/var/postgresql@15/postgresql.conf`:
```conf
listen_addresses = '*'  # 모든 IP에서 접속 허용
```

`/opt/homebrew/var/postgresql@15/pg_hba.conf`:
```conf
host    all    all    0.0.0.0/0    md5
```

**⚠️ 보안 위험**: 프로덕션에서는 특정 IP만 허용하세요!

## 📊 데이터베이스 백업

```bash
# 백업
pg_dump stock_portfolio > backup_$(date +%Y%m%d).sql

# 복구
psql stock_portfolio < backup_20251019.sql
```

## ✅ 현재 상태 요약

- ✅ PostgreSQL 15.14 설치 완료
- ✅ stock_portfolio 데이터베이스 생성 완료
- ✅ sunchulkim 슈퍼유저 권한 설정 완료
- ✅ DB 연결 테스트 성공
- ✅ `.env` 파일 설정 완료

**결론**: 현재 설정을 **그대로 사용**하시면 됩니다! 🎉
