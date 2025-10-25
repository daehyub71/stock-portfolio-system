# Cron Job 자동화 가이드

Stock Portfolio System의 데이터 수집 및 백업 작업을 cron으로 자동화하는 가이드입니다.

## 📋 Overview

자동화가 필요한 작업:
1. **일일 시세 업데이트** - 매일 실행
2. **분기 재무제표 업데이트** - 분기별 실행
3. **데이터베이스 백업** - 매일 실행
4. **테이블 스냅샷** - 주간 실행
5. **백업 정리** - 주간 실행

---

## 🔧 Cron 설정

### 1. Crontab 편집

```bash
crontab -e
```

### 2. 환경 변수 설정

crontab 파일 상단에 환경 변수 추가:

```bash
# Path to Python virtual environment
VENV_PATH=/Users/your_username/src/stock-portfolio-system/venv
PROJECT_PATH=/Users/your_username/src/stock-portfolio-system

# PostgreSQL settings (if needed)
PGPASSWORD=your_password

# Email for notifications (optional)
MAILTO=your_email@example.com
```

### 3. Cron Jobs

```bash
# ============================================
# Stock Portfolio System - Automated Tasks
# ============================================

# 1. Daily Price Update (매일 오전 9시)
# 장 시작 전에 전일 데이터 업데이트
0 9 * * * cd $PROJECT_PATH && $VENV_PATH/bin/python scripts/update_daily_prices.py >> logs/cron_daily_prices.log 2>&1

# 2. Database Backup (매일 오전 1시)
# 새벽 시간대에 전체 DB 백업
0 1 * * * cd $PROJECT_PATH && $VENV_PATH/bin/python scripts/backup_database.py >> logs/cron_backup.log 2>&1

# 3. Table Snapshots (매주 일요일 오전 2시)
# 주간 스냅샷 생성
0 2 * * 0 cd $PROJECT_PATH && $VENV_PATH/bin/python scripts/snapshot_tables.py create >> logs/cron_snapshot.log 2>&1

# 4. Cleanup Old Backups (매주 일요일 오전 3시)
# 30일 이상 된 백업 삭제
0 3 * * 0 cd $PROJECT_PATH && $VENV_PATH/bin/python scripts/backup_database.py --cleanup-only --retention-days 30 >> logs/cron_cleanup.log 2>&1

# 5. Cleanup Old Snapshots (매주 일요일 오전 3시 30분)
# 7일 이상 된 스냅샷 삭제
30 3 * * 0 cd $PROJECT_PATH && $VENV_PATH/bin/python scripts/snapshot_tables.py cleanup --days 7 >> logs/cron_cleanup.log 2>&1

# ============================================
# Quarterly Financial Updates (수동 실행 권장)
# ============================================
# 분기 발표일 이후 수동으로 실행:
# python scripts/update_quarterly_financials.py
```

---

## 📅 실행 스케줄 설명

### 일일 작업

| 시간 | 작업 | 설명 |
|------|------|------|
| 01:00 | 데이터베이스 백업 | 전체 DB를 pg_dump로 백업 |
| 09:00 | 일일 시세 업데이트 | 전일(T-1) 주가 데이터 수집 |

### 주간 작업 (일요일)

| 시간 | 작업 | 설명 |
|------|------|------|
| 02:00 | 테이블 스냅샷 | 주요 테이블 스냅샷 생성 |
| 03:00 | 백업 정리 | 30일 이상 백업 삭제 |
| 03:30 | 스냅샷 정리 | 7일 이상 스냅샷 삭제 |

### 분기별 작업 (수동 권장)

분기보고서 발표일 이후 수동 실행:
- Q1 (1-3월): 5월 중순
- Q2 (4-6월): 8월 중순
- Q3 (7-9월): 11월 중순
- Q4 (10-12월): 다음 해 3월 중순

```bash
python scripts/update_quarterly_financials.py
```

---

## 🔔 알림 설정

### 1. 이메일 알림

crontab에서 `MAILTO` 설정:

```bash
MAILTO=your_email@example.com
```

오류 발생 시 자동으로 이메일 전송됩니다.

### 2. 슬랙 알림 (선택사항)

슬랙 웹훅을 사용한 알림 스크립트:

```bash
#!/bin/bash
# scripts/notify_slack.sh

WEBHOOK_URL="your_slack_webhook_url"
MESSAGE="$1"

curl -X POST -H 'Content-type: application/json' \
--data "{\"text\":\"${MESSAGE}\"}" \
${WEBHOOK_URL}
```

cron job에 추가:

```bash
0 9 * * * cd $PROJECT_PATH && $VENV_PATH/bin/python scripts/update_daily_prices.py && ./scripts/notify_slack.sh "Daily price update completed" >> logs/cron_daily_prices.log 2>&1
```

---

## 📝 로그 관리

### 로그 파일 위치

```
logs/
├── cron_daily_prices.log      # 일일 시세 업데이트
├── cron_backup.log             # 데이터베이스 백업
├── cron_snapshot.log           # 테이블 스냅샷
├── cron_cleanup.log            # 백업/스냅샷 정리
├── backup_YYYY-MM-DD.log       # 백업 상세 로그
├── snapshot_YYYY-MM-DD.log     # 스냅샷 상세 로그
└── update_daily_prices_YYYY-MM-DD.log  # 시세 업데이트 상세 로그
```

### 로그 로테이션

loguru가 자동으로 로그 로테이션을 처리합니다:
- 파일 크기: 100 MB
- 보존 기간: 30일

수동 정리 (필요시):

```bash
# 30일 이상 로그 삭제
find logs/ -name "*.log" -mtime +30 -delete
```

---

## 🔍 모니터링

### 1. Cron 실행 확인

최근 실행 로그 확인:

```bash
# 시세 업데이트
tail -f logs/cron_daily_prices.log

# 백업
tail -f logs/cron_backup.log

# 스냅샷
tail -f logs/cron_snapshot.log
```

### 2. 데이터 업데이트 확인

```bash
# 최근 시세 데이터 확인
psql -d stock_portfolio -c "
SELECT date, COUNT(*) as stocks
FROM daily_prices
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY date
ORDER BY date DESC;"

# 최근 백업 확인
ls -lth backups/db_full/ | head -5
```

### 3. 스크립트 성능 확인

```bash
# 평균 실행 시간 분석
grep "소요 시간" logs/cron_daily_prices.log | tail -10

# 성공률 확인
grep "성공률" logs/cron_daily_prices.log | tail -10
```

---

## ⚠️ 주의사항

### 1. 시장 휴장일

- 일일 시세 업데이트는 휴장일에도 실행되지만 데이터가 없을 수 있습니다
- 스크립트는 자동으로 "No data" 처리하므로 문제없습니다
- 로그에서 휴장일 여부 확인 가능

### 2. 백업 디스크 공간

백업 파일이 누적되면 디스크 공간 부족 가능:

```bash
# 백업 디렉토리 크기 확인
du -sh backups/

# 디스크 여유 공간 확인
df -h
```

권장 설정:
- 일일 백업: 30일 보존
- 테이블 스냅샷: 7일 보존
- 최소 여유 공간: 10 GB

### 3. 데이터베이스 잠금

백업 중에는 데이터베이스 쓰기가 차단될 수 있습니다.
- 백업은 새벽 시간(01:00)에 실행
- 평균 소요 시간: 5-10분

### 4. 분기 재무제표 업데이트

자동화하지 않는 이유:
- 분기 발표일이 정확하지 않음 (기업마다 다름)
- 수동 실행 후 재무비율 재계산 확인 필요
- DART API 부하 방지

---

## 🛠️ 트러블슈팅

### 문제 1: Cron job이 실행되지 않음

**확인 사항:**

```bash
# cron 서비스 실행 확인
service cron status

# cron 로그 확인 (macOS)
log show --predicate 'process == "cron"' --last 1h

# cron 로그 확인 (Linux)
grep CRON /var/log/syslog
```

**해결:**

```bash
# cron 서비스 재시작 (Linux)
sudo service cron restart

# 수동 테스트
cd /path/to/project && venv/bin/python scripts/update_daily_prices.py
```

### 문제 2: 권한 오류

**증상:**
```
Permission denied: scripts/update_daily_prices.py
```

**해결:**

```bash
# 실행 권한 부여
chmod +x scripts/*.py

# 로그 디렉토리 권한 확인
chmod 755 logs/
```

### 문제 3: 가상환경 활성화 실패

**증상:**
```
ModuleNotFoundError: No module named 'loguru'
```

**해결:**

crontab에서 정확한 Python 경로 사용:

```bash
# 잘못된 예
python scripts/update_daily_prices.py

# 올바른 예
/full/path/to/venv/bin/python scripts/update_daily_prices.py
```

### 문제 4: 백업 실패 (디스크 공간 부족)

**증상:**
```
No space left on device
```

**해결:**

```bash
# 이전 백업 수동 삭제
python scripts/backup_database.py --cleanup-only --retention-days 7

# 또는 직접 삭제
rm backups/db_full/*_20240[1-6]*.sql.gz
```

---

## 📊 성능 최적화

### 1. 병렬 실행 (선택사항)

여러 시장을 병렬로 업데이트:

```bash
# KOSPI와 KOSDAQ 병렬 실행
0 9 * * * cd $PROJECT_PATH && $VENV_PATH/bin/python scripts/update_daily_prices.py --market KOSPI >> logs/cron_kospi.log 2>&1 &
1 9 * * * cd $PROJECT_PATH && $VENV_PATH/bin/python scripts/update_daily_prices.py --market KOSDAQ >> logs/cron_kosdaq.log 2>&1
```

### 2. 백업 압축 레벨 조정

압축 시간 vs 파일 크기 트레이드오프:

```python
# scripts/backup_database.py 수정
# 기본: compresslevel=6
# 빠른 백업: compresslevel=1
# 최대 압축: compresslevel=9
```

### 3. 증분 백업 (고급)

매일 전체 백업 대신 증분 백업 사용 (구현 필요):
- 일요일: 전체 백업
- 월-토: 변경된 데이터만 백업

---

## 📈 모니터링 대시보드 (선택사항)

Grafana 또는 커스텀 대시보드로 모니터링:

**수집할 메트릭:**
- 일일 업데이트 성공률
- 백업 파일 크기 추이
- 스크립트 실행 시간
- 디스크 사용량

**구현 예시:**

```python
# scripts/metrics_collector.py
import json
from datetime import datetime

metrics = {
    'timestamp': datetime.now().isoformat(),
    'daily_price_update': {
        'success_rate': 98.5,
        'elapsed_minutes': 25.3,
        'stocks_updated': 2650
    },
    'backup': {
        'size_mb': 1250.5,
        'elapsed_minutes': 8.2
    }
}

with open('logs/metrics.json', 'a') as f:
    json.dump(metrics, f)
    f.write('\n')
```

---

## ✅ Validation Checklist

백업 자동화 검증:

- [ ] crontab 설정 완료
- [ ] 일일 시세 업데이트 실행 확인 (로그)
- [ ] 데이터베이스 백업 실행 확인 (파일 생성)
- [ ] 테이블 스냅샷 실행 확인
- [ ] 백업 정리 동작 확인
- [ ] 디스크 공간 충분 (최소 10 GB)
- [ ] 로그 파일 로테이션 동작 확인
- [ ] 이메일 알림 수신 확인 (MAILTO 설정 시)

---

## 📚 References

- **Cron 문법**: `man 5 crontab`
- **PostgreSQL pg_dump**: https://www.postgresql.org/docs/current/app-pgdump.html
- **Loguru**: https://loguru.readthedocs.io/
- **백업 스크립트**: [scripts/backup_database.py](../scripts/backup_database.py)

---

**Last Updated**: 2025-10-24
**Author**: Stock Portfolio System Development Team
