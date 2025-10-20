"""Stock Portfolio System - Main Dashboard

Week 1-2 완료 체크 및 데이터 품질 점검 대시보드
"""

import streamlit as st
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Page configuration
st.set_page_config(
    page_title="Stock Portfolio System Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border-left: 4px solid #28a745;
        padding: 1rem;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 1rem;
        margin: 1rem 0;
    }
    .info-box {
        background-color: #d1ecf1;
        border-left: 4px solid #17a2b8;
        padding: 1rem;
        margin: 1rem 0;
    }
    </style>
""", unsafe_allow_html=True)

# Main header
st.markdown('<div class="main-header">📈 Stock Portfolio System</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">한국 주식 투자 포트폴리오 시스템 개발 대시보드</div>', unsafe_allow_html=True)

# Sidebar
st.sidebar.title("📋 Navigation")
st.sidebar.markdown("---")

# Project info
st.sidebar.markdown("### 📊 Project Info")
st.sidebar.info("""
**프로젝트:** Stock Portfolio System
**기간:** 7주 (35일)
**현재 진행:** Week 2 완료
**개발자:** Sunchul Kim
""")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔗 Quick Links")
st.sidebar.markdown("""
- 📄 [README.md](../README.md)
- 📝 [개발계획서](../개발계획서_Phase1_Phase2.md)
- ✅ [Task 분할서](../Task_분할서_Phase1_Phase2.md)
""")

# Main content
st.markdown("---")

# Overview section
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="📅 Week 1",
        value="완료",
        delta="5/5 days",
        help="프로젝트 초기화 및 데이터베이스 설정"
    )

with col2:
    st.metric(
        label="📅 Week 2",
        value="완료",
        delta="5/5 days",
        help="전체 종목 데이터 수집"
    )

with col3:
    st.metric(
        label="📦 총 종목 수",
        value="2,500+",
        help="KOSPI + KOSDAQ 상장 종목"
    )

with col4:
    st.metric(
        label="💾 데이터 기간",
        value="10년",
        help="2015-01-01 ~ 2025-01-01"
    )

st.markdown("---")

# Feature cards
st.subheader("🎯 대시보드 기능")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    <div class="info-box">
        <h4>✅ Week 1 완료 체크</h4>
        <p>프로젝트 초기화, PostgreSQL 설정, 데이터베이스 스키마 생성, API 연동 테스트 항목 검증</p>
        <ul>
            <li>Day 1: 프로젝트 초기화 및 PostgreSQL 설정</li>
            <li>Day 2: 데이터베이스 스키마 생성</li>
            <li>Day 3: KRX API 연동 및 종목 리스트 수집</li>
            <li>Day 4: KIS API 연동 및 시세 데이터 수집</li>
            <li>Day 5: DART API 연동 및 재무제표 수집</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="info-box">
        <h4>✅ Week 2 완료 체크</h4>
        <p>전체 종목 시세 데이터 수집 및 검증 항목 확인</p>
        <ul>
            <li>Day 6-10: 전체 2,500개 종목 10년치 시세 수집</li>
            <li>배치 수집 시스템 (500개씩 5개 그룹)</li>
            <li>체크포인트 및 재시도 메커니즘</li>
            <li>데이터 품질 검증</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    <div class="info-box">
        <h4>📊 데이터베이스 개요</h4>
        <p>PostgreSQL 데이터베이스 테이블 및 데이터 현황 확인</p>
        <ul>
            <li>테이블 목록 및 레코드 수</li>
            <li>시장별 종목 분포</li>
            <li>데이터 수집 기간 분포</li>
            <li>스토리지 사용량</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="info-box">
        <h4>🔍 데이터 품질 점검</h4>
        <p>수집된 데이터의 품질 및 완전성 검증</p>
        <ul>
            <li>결측치 분석 (NULL 값 체크)</li>
            <li>이상치 탐지 (OHLCV 논리 오류)</li>
            <li>날짜 연속성 검증</li>
            <li>데이터 커버리지 분석</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# Instructions
st.subheader("📖 사용 방법")

st.markdown("""
1. **왼쪽 사이드바**에서 원하는 페이지를 선택하세요
2. **Week 1 체크**: Day 1-5까지 완료 항목 검증
3. **Week 2 체크**: Day 6-10까지 데이터 수집 현황 확인
4. **데이터베이스 개요**: 전체 데이터베이스 상태 확인
5. **데이터 품질 점검**: 수집된 데이터의 품질 분석
""")

# Database connection test
st.markdown("---")
st.subheader("🔌 데이터베이스 연결 테스트")

try:
    from db.connection import test_connection, engine
    from sqlalchemy import text

    if st.button("연결 테스트 실행", type="primary"):
        with st.spinner("PostgreSQL 연결 테스트 중..."):
            if test_connection():
                st.success("✅ PostgreSQL 연결 성공!")

                # Get PostgreSQL version
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT version();"))
                    version = result.fetchone()[0]
                    st.code(version, language="text")
            else:
                st.error("❌ 데이터베이스 연결 실패. .env 파일 및 PostgreSQL 서비스 상태를 확인하세요.")
except Exception as e:
    st.error(f"❌ 오류 발생: {e}")
    st.info("💡 데이터베이스가 실행 중인지 확인하세요: `brew services list | grep postgresql`")

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 2rem 0;">
    <p>Stock Portfolio System Dashboard v1.0</p>
    <p>Developed by Sunchul Kim | 2025</p>
</div>
""", unsafe_allow_html=True)
