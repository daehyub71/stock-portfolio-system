#!/bin/bash
# Streamlit Dashboard 실행 스크립트

echo "================================================"
echo "Stock Portfolio System - Streamlit Dashboard"
echo "================================================"
echo ""

# 가상환경 활성화
echo "✓ 가상환경 활성화 중..."
source venv/bin/activate

# PostgreSQL 상태 확인
echo "✓ PostgreSQL 상태 확인..."
if brew services list | grep postgresql@15 | grep started > /dev/null; then
    echo "  ✓ PostgreSQL 실행 중"
else
    echo "  ⚠️  PostgreSQL이 실행되지 않았습니다"
    echo "  실행: brew services start postgresql@15"
    exit 1
fi

# 데이터베이스 연결 테스트
echo "✓ 데이터베이스 연결 테스트..."
python -c "from db.connection import test_connection; test_connection()" 2>&1 | grep -q "PostgreSQL version"
if [ $? -eq 0 ]; then
    echo "  ✓ 데이터베이스 연결 성공"
else
    echo "  ⚠️  데이터베이스 연결 실패"
    echo "  .env 파일을 확인하세요"
    exit 1
fi

echo ""
echo "================================================"
echo "Streamlit 대시보드 시작 중..."
echo "================================================"
echo ""
echo "브라우저가 자동으로 열립니다"
echo "URL: http://localhost:8501"
echo ""
echo "종료하려면 Ctrl+C를 누르세요"
echo ""

# Streamlit 실행
streamlit run streamlit_app/main.py
