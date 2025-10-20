# Stock Portfolio System - Streamlit Dashboard

Week 1-3 (Day 11-12) 완료 체크 및 데이터 품질 점검 대시보드

## 📋 개요

이 Streamlit 대시보드는 Stock Portfolio System의 개발 진행 상황을 확인하고, 수집된 데이터의 품질을 점검하기 위한 웹 애플리케이션입니다.

## 🚀 실행 방법

### 1. 가상환경 활성화

```bash
cd /Users/sunchulkim/src/stock-portfolio-system
source venv/bin/activate
```

### 2. 필수 패키지 설치

Streamlit과 시각화 라이브러리가 필요합니다:

```bash
pip install streamlit plotly
```

### 3. Streamlit 앱 실행

```bash
streamlit run streamlit_app/main.py
```

브라우저가 자동으로 열리며 `http://localhost:8501`에서 대시보드에 접근할 수 있습니다.

## 📊 대시보드 구성

### 메인 페이지 (main.py)
- 프로젝트 전체 개요
- Week 1-2 진행 상황 요약
- 데이터베이스 연결 테스트

### 1️⃣ Week 1 체크
**Day 1-5: 환경 구축 및 API 연동 테스트**

- ✅ Day 1: 프로젝트 초기화 및 PostgreSQL 설정
- ✅ Day 2: 데이터베이스 스키마 생성
- ✅ Day 3: KRX API 연동 및 종목 리스트 수집
- ✅ Day 4: KIS API 연동 및 시세 데이터 수집
- ✅ Day 5: DART API 연동 및 재무제표 수집

**검증 항목:**
- 프로젝트 디렉토리 구조
- Python 가상환경 및 패키지
- 환경 변수 설정
- SQLAlchemy 모델 파일
- 데이터베이스 테이블 생성
- API 연동 테스트

### 2️⃣ Week 2 체크
**Day 6-10: 전체 종목 시세 데이터 수집**

- ✅ 2,500개 종목 10년치 시세 수집
- ✅ 배치 수집 시스템 (500개씩 5그룹)
- ✅ 체크포인트 및 재시도 메커니즘
- ✅ 데이터 품질 검증

**검증 항목:**
- 전체 데이터 통계 (종목 수, 레코드 수, 커버리지)
- 그룹별 수집 현황
- 날짜별 커버리지 분석
- 시장별 데이터 분포
- 샘플 데이터 조회
- 체크포인트 파일 확인

### 3️⃣ Week 3 (Day 11-12) 체크
**재무제표 수집 시작**

- ✅ Day 11: 첫 500개 종목 재무제표 수집 (10,000건)
- ✅ Day 12: 추가 1,000개 종목 수집 (누적 30,000건)

**검증 항목:**
- 재무제표 데이터 통계
- 유형별 분포 (annual/quarterly)
- 회계연도별/분기별 분포
- JSONB 데이터 구조 검증
- 필수 계정과목 존재율 분석
- 샘플 재무제표 조회

### 4️⃣ 데이터 품질 점검
**수집된 데이터의 품질 및 완전성 검증**

#### 종목 데이터
- 필수 필드 NULL 체크
- 중복 데이터 검사
- 상장/상폐 상태 분석

#### 시세 데이터
- 종목별 커버리지
- OHLCV 필드 NULL 체크
- 논리 오류 검사 (High < Low, Close > High 등)
- 날짜 연속성 검사

#### 재무제표
- 종목별 커버리지
- JSONB 필드 NULL 체크
- 핵심 계정과목 존재율
- 연도별 데이터 분포

#### 전체 요약
- 종합 품질 점수 계산
- 개선 권장사항
- 품질 점수 시각화

### 5️⃣ 데이터베이스 개요
**PostgreSQL 데이터베이스 상세 정보**

- 데이터베이스 연결 정보
- PostgreSQL 버전 정보
- 테이블 목록 및 레코드 수
- 테이블 상세 정보 (스키마, 인덱스, 외래키)
- 데이터베이스 저장 공간 분석
- 스키마 다이어그램
- 샘플 데이터 미리보기

## 🎯 주요 기능

### 실시간 데이터 조회
- PostgreSQL 데이터베이스에서 실시간으로 데이터 조회
- 버튼 클릭으로 최신 정보 업데이트

### 데이터 품질 검증
- NULL 값 체크
- 논리 오류 탐지
- 데이터 완전성 검사
- 종합 품질 점수 계산

### 시각화
- Streamlit 차트
- Plotly 인터랙티브 차트
- 테이블 및 메트릭

### 샘플 데이터 조회
- 종목 코드 입력으로 특정 종목 데이터 확인
- 최근 데이터 미리보기

## 📁 파일 구조

```
streamlit_app/
├── main.py                          # 메인 대시보드
├── pages/
│   ├── 1_✅_Week_1_체크.py          # Week 1 완료 체크
│   ├── 2_✅_Week_2_체크.py          # Week 2 완료 체크
│   ├── 3_✅_Week_3_Day_11-12.py     # Week 3 (Day 11-12) 체크
│   ├── 4_🔍_데이터_품질_점검.py      # 데이터 품질 점검
│   └── 5_💾_데이터베이스_개요.py     # 데이터베이스 개요
└── README.md                        # 이 파일
```

## 🔧 필수 요구사항

### Python 패키지
- streamlit >= 1.28.0
- plotly >= 5.17.0
- pandas >= 2.2.0
- sqlalchemy >= 2.0.25
- psycopg2-binary >= 2.9.10

### 환경 설정
- `.env` 파일에 데이터베이스 연결 정보 필요:
  ```
  DB_HOST=localhost
  DB_PORT=5432
  DB_NAME=stock_portfolio
  DB_USER=your_username
  DB_PASSWORD=
  ```

### PostgreSQL
- PostgreSQL 15가 실행 중이어야 함
- `stock_portfolio` 데이터베이스가 생성되어 있어야 함

## 💡 사용 팁

1. **데이터베이스 연결 확인**
   - 메인 페이지에서 "연결 테스트 실행" 버튼으로 PostgreSQL 연결 확인

2. **단계별 검증**
   - Week 1 → Week 2 → Week 3 순서로 각 단계의 완료 항목 확인

3. **데이터 품질 점검**
   - 각 탭에서 버튼을 클릭하여 해당 영역의 품질 검사 실행
   - 전체 요약 탭에서 종합 품질 점수 확인

4. **성능 고려**
   - 대용량 데이터 조회 시 시간이 걸릴 수 있음
   - 샘플 데이터는 최대 100-1000건으로 제한됨

## 🐛 문제 해결

### 데이터베이스 연결 실패
```bash
# PostgreSQL이 실행 중인지 확인
brew services list | grep postgresql

# PostgreSQL 시작
brew services start postgresql@15
```

### 모듈 import 오류
```bash
# 가상환경이 활성화되었는지 확인
which python  # venv 경로가 나와야 함

# 패키지 재설치
pip install -r requirements.txt
pip install streamlit plotly
```

### 페이지가 로드되지 않음
- 브라우저 캐시 삭제
- Streamlit 서버 재시작 (Ctrl+C 후 다시 실행)

## 📝 향후 개선 사항

- [ ] 자동 새로고침 기능
- [ ] 데이터 내보내기 (CSV, Excel)
- [ ] 고급 필터링 및 검색
- [ ] 차트 커스터마이징
- [ ] 알림 및 경고 시스템
- [ ] 성능 모니터링 대시보드

## 📞 지원

문제가 발생하면 프로젝트 README.md 또는 개발계획서를 참고하세요.

---

**Stock Portfolio System v1.0**
Developed by Sunchul Kim | 2025
