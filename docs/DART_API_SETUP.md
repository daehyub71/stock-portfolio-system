# DART API 설정 가이드

DART (전자공시시스템) API를 사용하여 기업의 재무제표 데이터를 수집하는 방법을 안내합니다.

## DART API란?

DART는 금융감독원 전자공시시스템으로, 상장기업의 공시 정보를 제공합니다.
- 재무제표 (사업보고서, 분기보고서)
- 공시 정보
- 기업 개황
- **무료 사용 가능**

## API 키 발급 방법

### 1. DART 홈페이지 접속
https://opendart.fss.or.kr/

### 2. 인증키 신청
1. 상단 메뉴에서 `오픈API` 클릭
2. `인증키 신청/관리` 클릭
3. 로그인 또는 회원가입
4. `인증키 신청` 버튼 클릭
5. 필요 정보 입력 (이메일, 사용 목적 등)
6. 신청 완료 후 **즉시 발급** (이메일로도 전송)

### 3. .env 파일에 API 키 설정

발급받은 API 키를 `.env` 파일에 추가하세요:

```bash
# DART API (전자공시)
DART_API_KEY=your_api_key_here
```

예시:
```bash
DART_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## API 사용 제한

- **무료**로 사용 가능
- 일일 요청 제한: **10,000건**
- 초당 요청 제한: 없음 (권장: 초당 5건 이하)

## 주요 API 엔드포인트

### 1. 고유번호 (corp_code)
- 엔드포인트: `https://opendart.fss.or.kr/api/corpCode.xml`
- 용도: 기업의 고유번호 조회 (종목코드 ↔ corp_code 매핑)

### 2. 재무제표
- 엔드포인트: `https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json`
- 용도: 재무상태표, 손익계산서, 현금흐름표 등

### 3. 공시정보
- 엔드포인트: `https://opendart.fss.or.kr/api/list.json`
- 용도: 최근 공시 목록 조회

## 테스트

API 키 발급 후 테스트:

```bash
source venv/bin/activate
python scripts/test_dart_api.py
```

## 문제 해결

### "인증키가 유효하지 않습니다"
- .env 파일의 DART_API_KEY 확인
- 공백이나 줄바꿈 없는지 확인
- 키가 정확히 복사되었는지 확인

### "일일 한도 초과"
- 10,000건 제한 초과
- 다음날까지 대기 또는 새로운 키 발급

### "데이터가 조회되지 않음"
- corp_code가 올바른지 확인
- 해당 기업의 재무제표가 공시되었는지 확인
- 조회 기간 (reprt_code) 확인

## 참고 문서

- DART API 가이드: https://opendart.fss.or.kr/guide/main.do
- API 명세: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001
- 개발자 가이드: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003

## 다음 단계

1. DART API 키 발급 완료
2. `.env` 파일에 키 설정
3. `python scripts/test_dart_api.py` 실행
4. `python scripts/collect_financial_statements.py` 실행하여 재무제표 수집
