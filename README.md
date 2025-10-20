# 📈 Stock Portfolio System

한국 주식시장(KOSPI/KOSDAQ)을 위한 포트폴리오 관리 및 분석 시스템

## 🎯 프로젝트 개요

이 프로젝트는 한국투자증권 API와 DART(전자공시시스템) API를 활용하여 주식 데이터를 수집하고, 재무비율을 분석하며, 포트폴리오를 관리하는 시스템입니다.

### 주요 기능

- **실시간 주가 데이터 수집**: 한국투자증권 API를 통한 OHLCV 데이터 수집
- **재무 데이터 분석**: DART API를 통한 재무제표 및 33개 재무비율 계산
- **포트폴리오 관리**: 보유 종목 관리 및 수익률 추적
- **백테스팅**: 투자 전략 시뮬레이션 및 성과 분석
- **데이터베이스**: PostgreSQL 기반 효율적인 데이터 저장 및 조회

## 🏗️ 시스템 아키텍처

### 데이터베이스 스키마

```
├── sectors              # 업종 분류 (계층 구조)
├── stocks               # 종목 기본 정보
├── daily_prices         # 일별 주가 데이터 (OHLCV)
├── financial_statements # 재무제표 (JSONB)
├── financial_ratios     # 33개 재무비율
└── corp_code_map        # ticker ↔ DART corp_code 매핑
```

### 기술 스택

**Backend:**
- Python 3.13
- SQLAlchemy 2.0 (ORM)
- PostgreSQL 15
- httpx (비동기 HTTP 클라이언트)

**Data Sources:**
- 한국투자증권 (KIS) API - 실시간 주가 데이터
- DART (전자공시) API - 재무제표 및 공시 정보
- KRX (한국거래소) API - 상장 종목 리스트

**Analysis:**
- pandas - 데이터 분석
- numpy - 수치 계산

## 🚀 시작하기

### 1. 사전 요구사항

- Python 3.13
- PostgreSQL 15
- 한국투자증권 API 키 (APP_KEY, APP_SECRET)
- DART API 키

### 2. 설치

```bash
# 저장소 클론
git clone https://github.com/daehyub71/stock-portfolio-system.git
cd stock-portfolio-system

# 가상환경 생성 및 활성화
python3.13 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows

# 패키지 설치
pip install -r requirements.txt

# PostgreSQL 설치 (macOS - Homebrew)
brew install postgresql@15
brew services start postgresql@15

# 데이터베이스 생성
createdb stock_portfolio
```

### 3. 환경 설정

`.env` 파일을 생성하고 아래 정보를 입력하세요:

```bash
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stock_portfolio
DB_USER=your_username
DB_PASSWORD=

# KIS API (한국투자증권)
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_ACCOUNT_TYPE=REAL  # or VIRTUAL

# DART API (전자공시)
DART_API_KEY=your_dart_api_key

# Logging
LOG_LEVEL=INFO
LOG_FILE_PATH=./logs/

# Development
ENVIRONMENT=development
```

**API 키 발급 방법:**
- **한국투자증권 API**: [KIS Developers](https://apiportal.koreainvestment.com/)
- **DART API**: [DART 오픈API](https://opendart.fss.or.kr/)

### 4. 데이터베이스 초기화

```bash
# 가상환경 활성화 후
source venv/bin/activate

# 테이블 생성
python scripts/init_db.py
```

성공하면 다음과 같은 메시지가 표시됩니다:
```
✅ Database initialization completed successfully!
```

## 📊 주요 재무비율 (33개)

### 수익성 지표
- ROE (자기자본이익률), ROA (총자산이익률), ROIC (투하자본이익률)
- 매출총이익률, 영업이익률, 순이익률, EBITDA 마진

### 성장성 지표
- 매출액 증가율, 영업이익 증가율, 순이익 증가율
- EPS 증가율, 총자산 증가율

### 안정성 지표
- 부채비율, 부채자본비율, 유동비율, 당좌비율
- 이자보상배율, 자기자본비율

### 활동성 지표
- 총자산회전율, 재고자산회전율
- 매출채권회전율, 매입채무회전율

### 시장가치 지표
- PER (주가수익비율), PBR (주가순자산비율)
- PCR (주가현금흐름비율), PSR (주가매출액비율)
- EV/EBITDA, 배당수익률, 배당성향

## 📁 프로젝트 구조

```
stock-portfolio-system/
├── calculators/         # 재무비율 계산 모듈
├── collectors/          # 데이터 수집 모듈 (KIS, DART, KRX)
├── config/              # 설정 파일
├── db/                  # 데이터베이스 연결 및 관리
│   └── connection.py
├── models/              # SQLAlchemy 모델
│   ├── base.py         # Base 및 TimestampMixin
│   ├── sector.py       # 업종 모델
│   ├── stock.py        # 종목 모델
│   ├── daily_price.py  # 주가 모델
│   ├── financial_statement.py
│   ├── financial_ratio.py
│   └── corp_code_map.py
├── pipelines/           # 데이터 처리 파이프라인
├── scripts/             # 유틸리티 스크립트
│   └── init_db.py      # DB 초기화
├── tests/               # 테스트 코드
├── docs/                # 문서
│   ├── DATABASE_SETUP.md
│   └── TABLEPLUS_CONNECTION.md
├── .env                 # 환경 변수 (git ignored)
├── .env.example         # 환경 변수 예제
├── requirements.txt     # Python 패키지
└── README.md
```

## 🗓️ 개발 로드맵

### Phase 1: 데이터 수집 및 저장 (Week 1-3)
- ✅ Week 1 (Day 1-5): 프로젝트 초기화 및 DB 설계
  - ✅ Day 1: 프로젝트 초기화 및 PostgreSQL 설정
  - ✅ Day 2: 데이터베이스 모델 설계 및 테이블 생성
  - Day 3: KIS API 연동 (토큰 발급, 종목 리스트 수집)
  - Day 4: KIS API 일별 주가 데이터 수집
  - Day 5: DART API 연동 및 corp_code 매핑 테이블 구축

- Week 2 (Day 6-10): 재무 데이터 수집
- Week 3 (Day 11-15): 데이터 파이프라인 구축

### Phase 2: 분석 및 포트폴리오 관리 (Week 4-5)
- Week 4 (Day 16-20): 재무비율 계산 및 분석
- Week 5 (Day 21-25): 포트폴리오 관리 기능

### Phase 3: 백테스팅 및 최적화 (Week 6-7)
- Week 6 (Day 26-30): 백테스팅 엔진
- Week 7 (Day 31-35): 성능 최적화 및 배포

## 🔧 개발 가이드

### 가상환경 활성화
```bash
source venv/bin/activate  # 항상 먼저 실행!
```

### 데이터베이스 연결 테스트
```bash
python -c "from db.connection import test_connection; test_connection()"
```

### 테이블 확인
```bash
python -c "
from db.connection import engine
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text('SELECT tablename FROM pg_tables WHERE schemaname = \'public\' ORDER BY tablename'))
    for row in result:
        print(f'  ✓ {row[0]}')
"
```

### GUI 도구 (TablePlus)
데이터베이스를 시각적으로 확인하려면 [TablePlus](https://tableplus.com/)를 사용하세요.

연결 정보:
- Host: `localhost`
- Port: `5432`
- Database: `stock_portfolio`
- User: `<your_username>`
- Password: (비워두기 - peer authentication)

## 📚 문서

- [데이터베이스 설정 가이드](docs/DATABASE_SETUP.md)
- [TablePlus 연결 가이드](docs/TABLEPLUS_CONNECTION.md)
- [개발계획서](개발계획서_Phase1_Phase2.md)
- [Task 분할서](Task_분할서_Phase1_Phase2.md)

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 라이선스

This project is licensed under the MIT License.

## 👤 개발자

**Sunchul Kim (daehyub71)**
- GitHub: [@daehyub71](https://github.com/daehyub71)
- Email: your.email@example.com

## 🙏 감사의 말

- 한국투자증권 - API 제공
- 금융감독원 DART - 전자공시 API 제공
- 한국거래소 (KRX) - 시장 데이터 제공

---

**⚠️ 면책 조항**: 이 소프트웨어는 교육 및 연구 목적으로 제공됩니다. 실제 투자 결정에 사용하기 전에 반드시 전문가의 조언을 구하시기 바랍니다. 투자에는 위험이 따르며, 과거 성과가 미래 수익을 보장하지 않습니다.

## 📊 Streamlit 대시보드

Week 1-3 (Day 11-12) 완료 체크 및 데이터 품질 점검을 위한 웹 대시보드를 제공합니다.

### 실행 방법

```bash
# 방법 1: 실행 스크립트 사용 (권장)
./run_dashboard.sh

# 방법 2: 직접 실행
source venv/bin/activate
streamlit run streamlit_app/main.py
```

브라우저에서 `http://localhost:8501` 접속

### 대시보드 기능

- **Week 1 체크**: 프로젝트 초기화 및 API 연동 검증 (Day 1-5)
- **Week 2 체크**: 전체 종목 시세 데이터 수집 현황 (Day 6-10)
- **Week 3 체크**: 재무제표 수집 현황 (Day 11-12)
- **데이터 품질 점검**: NULL 체크, 논리 오류 검사, 종합 품질 점수
- **데이터베이스 개요**: 테이블 정보, 스키마, 저장 공간 분석

자세한 내용은 [streamlit_app/README.md](streamlit_app/README.md)를 참고하세요.

