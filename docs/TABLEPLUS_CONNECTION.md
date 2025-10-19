# TablePlus에서 PostgreSQL 접속하기

## 📋 접속 정보

TablePlus에서 stock_portfolio 데이터베이스에 접속하려면 다음 정보를 사용하세요:

```
Name:           Stock Portfolio (원하는 이름)
Host:           localhost (또는 127.0.0.1)
Port:           5432
User:           sunchulkim
Password:       (비워두기)
Database:       stock_portfolio
```

## 🔧 TablePlus 접속 설정 (단계별)

### 1. TablePlus 실행

TablePlus를 실행하세요.

### 2. 새 연결 생성

- **방법 1**: 상단 메뉴 → `File` → `New Connection`
- **방법 2**: `⌘ + N` (Command + N) 단축키
- **방법 3**: 왼쪽 사이드바 하단의 `+` 버튼 클릭

### 3. PostgreSQL 선택

나타나는 데이터베이스 유형 목록에서 **PostgreSQL**을 선택하세요.

### 4. 연결 정보 입력

다음과 같이 입력하세요:

| 필드 | 값 | 설명 |
|------|-----|------|
| **Name** | `Stock Portfolio` | 연결 이름 (원하는 대로) |
| **Color** | 🟢 녹색 (선택사항) | 시각적 구분용 |
| **Host** | `localhost` | 또는 `127.0.0.1` |
| **Port** | `5432` | PostgreSQL 기본 포트 |
| **User** | `sunchulkim` | PostgreSQL 사용자명 |
| **Password** | **(비워두기)** | 로컬은 비밀번호 불필요 |
| **Database** | `stock_portfolio` | 데이터베이스 이름 |

### 5. 고급 설정 (선택사항)

**"Show advanced options"** 또는 **"Advanced"** 탭을 열면:

- **SSL Mode**: `Disable` (로컬 연결은 불필요)
- **Connection Timeout**: `30` (기본값)
- **Keep Alive**: 체크 (선택사항)

### 6. 연결 테스트

- **"Test"** 버튼 클릭
- 성공 시: ✅ "Connection is OK" 메시지 표시
- 실패 시: 아래 "문제 해결" 섹션 참고

### 7. 저장 및 연결

- **"Save"** 또는 **"Connect"** 버튼 클릭
- 연결이 저장되고 데이터베이스에 접속됩니다

## 📸 시각적 가이드

### 입력 예시 (실제 화면)

```
┌─────────────────────────────────────┐
│ Create a new connection             │
├─────────────────────────────────────┤
│ Name:      Stock Portfolio          │
│ Color:     🟢                        │
│ Host:      localhost                │
│ Port:      5432                     │
│ User:      sunchulkim               │
│ Password:  (empty)                  │
│ Database:  stock_portfolio          │
│                                     │
│ ☐ Use SSH                           │
│ ☐ Use SSL                           │
│                                     │
│ [Test]  [Cancel]  [Connect]        │
└─────────────────────────────────────┘
```

## 🚨 문제 해결

### 1. "Connection refused" 오류

**원인**: PostgreSQL 서비스가 실행되지 않음

**해결**:
```bash
# 터미널에서 실행
brew services start postgresql@15

# 상태 확인
brew services list | grep postgresql@15
```

### 2. "Role does not exist" 오류

**원인**: 사용자명이 잘못됨

**해결**:
```bash
# 터미널에서 PostgreSQL 사용자 확인
psql -d stock_portfolio -c "\du"
```

사용자명을 정확히 입력하세요 (대소문자 구분).

### 3. "Database does not exist" 오류

**원인**: 데이터베이스가 생성되지 않음

**해결**:
```bash
# 터미널에서 데이터베이스 생성
createdb stock_portfolio

# 또는
psql -c "CREATE DATABASE stock_portfolio;"
```

### 4. "Password authentication failed" 오류

**원인**: 비밀번호 필드에 값이 입력됨

**해결**: Password 필드를 **완전히 비워두세요**.

### 5. "Could not connect to server" 오류

**원인**: 포트 또는 호스트가 잘못됨

**해결**:
1. Host를 `localhost` 대신 `127.0.0.1`로 시도
2. Port가 `5432`인지 확인
3. 터미널에서 포트 확인:
   ```bash
   lsof -i :5432
   ```

## ✅ 접속 성공 후 할 일

### 1. 테이블 목록 확인

왼쪽 사이드바에서:
- `stock_portfolio` 데이터베이스
- `public` 스키마
- `Tables` 폴더

현재는 테이블이 없습니다 (Day 2에서 생성 예정).

### 2. SQL 쿼리 실행

상단 `SQL` 버튼 클릭 또는 `⌘ + T`:

```sql
-- 데이터베이스 정보 확인
SELECT current_database(), current_user, version();

-- 테이블 목록 (현재는 비어있음)
SELECT * FROM information_schema.tables
WHERE table_schema = 'public';
```

### 3. 스키마 확인

```sql
-- 모든 스키마 보기
SELECT * FROM information_schema.schemata;
```

## 💡 유용한 TablePlus 기능

### 단축키

- `⌘ + N`: 새 연결
- `⌘ + T`: 새 쿼리 탭
- `⌘ + R`: 쿼리 실행
- `⌘ + K`: 데이터 필터
- `⌘ + F`: 검색

### 데이터 관리

- **더블클릭**: 셀 편집
- **우클릭**: 컨텍스트 메뉴 (복사, 붙여넣기, 삭제 등)
- **+ 버튼**: 새 행 추가
- **- 버튼**: 행 삭제
- **Commit**: 변경사항 저장
- **Rollback**: 변경사항 취소

### 구조 관리

- **Structure 탭**: 테이블 구조 보기/편집
- **Content 탭**: 데이터 보기/편집
- **SQL 탭**: SQL 쿼리 실행

## 📚 다음 단계

Day 2 작업 후 다음 테이블들이 생성됩니다:

- `sectors` - 업종 정보
- `stocks` - 종목 정보
- `daily_prices` - 일일 시세
- `financial_statements` - 재무제표
- `financial_ratios` - 재무비율
- `corp_code_map` - 기업코드 매핑

TablePlus에서 이 테이블들을 시각적으로 확인하고 관리할 수 있습니다!

## 🔒 보안 팁

- **로컬 개발**: 현재 설정 (비밀번호 없음) 유지
- **프로덕션**: 반드시 강력한 비밀번호 설정
- **외부 접속**: SSH 터널링 사용 권장
- **백업**: 정기적으로 데이터 백업

---

**문서 버전**: 1.0
**작성일**: 2025-10-19
**관련 문서**: [DATABASE_SETUP.md](DATABASE_SETUP.md)
