#!/bin/bash
# Apache Airflow 설치 및 설정 스크립트

set -e  # Exit on error

echo "==========================================="
echo "Apache Airflow 설치 시작"
echo "==========================================="

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${GREEN}프로젝트 디렉토리: ${PROJECT_ROOT}${NC}"

# Check Python version
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}Python 버전: ${PYTHON_VERSION}${NC}"

# Set Airflow home directory
export AIRFLOW_HOME="${PROJECT_ROOT}/airflow"
echo -e "${GREEN}Airflow Home: ${AIRFLOW_HOME}${NC}"

# Create Airflow directories
echo ""
echo "1. Airflow 디렉토리 생성..."
mkdir -p "${AIRFLOW_HOME}/dags"
mkdir -p "${AIRFLOW_HOME}/logs"
mkdir -p "${AIRFLOW_HOME}/plugins"
mkdir -p "${AIRFLOW_HOME}/config"

# Check if virtual environment is activated
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo -e "${YELLOW}Warning: 가상환경이 활성화되지 않았습니다.${NC}"
    echo -e "${YELLOW}다음 명령어로 활성화하세요: source venv/bin/activate${NC}"
    exit 1
fi

# Install Airflow with constraints
echo ""
echo "2. Apache Airflow 설치..."

# Airflow version
AIRFLOW_VERSION=2.10.4
PYTHON_VERSION="3.12"  # Use 3.12 constraints for 3.13 (closest compatible)

# Constraint URL
CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

echo -e "${GREEN}Constraint URL: ${CONSTRAINT_URL}${NC}"

# Install Airflow
pip install "apache-airflow==${AIRFLOW_VERSION}" --constraint "${CONSTRAINT_URL}"

# Install Airflow providers
echo ""
echo "3. Airflow Providers 설치..."
pip install apache-airflow-providers-postgres
pip install apache-airflow-providers-http

# Initialize Airflow database (SQLite for development, can be changed to PostgreSQL later)
echo ""
echo "4. Airflow 데이터베이스 초기화..."
airflow db init

# Create admin user
echo ""
echo "5. Airflow 관리자 계정 생성..."
echo -e "${YELLOW}기본 계정 정보:${NC}"
echo -e "  Username: admin"
echo -e "  Password: admin"
echo -e "  Email: admin@example.com"

airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com \
    --password admin || echo -e "${YELLOW}사용자가 이미 존재합니다.${NC}"

# Create environment file for Airflow
echo ""
echo "6. Airflow 환경 변수 설정..."

cat > "${AIRFLOW_HOME}/.airflow_env" << EOF
# Airflow Environment Variables
export AIRFLOW_HOME=${AIRFLOW_HOME}
export AIRFLOW__CORE__DAGS_FOLDER=${AIRFLOW_HOME}/dags
export AIRFLOW__CORE__PLUGINS_FOLDER=${AIRFLOW_HOME}/plugins
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export AIRFLOW__WEBSERVER__EXPOSE_CONFIG=True
export AIRFLOW__CORE__EXECUTOR=LocalExecutor
EOF

echo -e "${GREEN}환경 변수 파일 생성: ${AIRFLOW_HOME}/.airflow_env${NC}"

# Update .bashrc or .zshrc
SHELL_RC="${HOME}/.zshrc"
if [ ! -f "$SHELL_RC" ]; then
    SHELL_RC="${HOME}/.bashrc"
fi

if ! grep -q "AIRFLOW_HOME" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# Apache Airflow" >> "$SHELL_RC"
    echo "export AIRFLOW_HOME=${AIRFLOW_HOME}" >> "$SHELL_RC"
    echo -e "${GREEN}AIRFLOW_HOME이 ${SHELL_RC}에 추가되었습니다.${NC}"
fi

# Create start/stop scripts
echo ""
echo "7. 시작/종료 스크립트 생성..."

# Start script
cat > "${PROJECT_ROOT}/scripts/start_airflow.sh" << 'EOF'
#!/bin/bash
# Airflow 시작 스크립트

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export AIRFLOW_HOME="${PROJECT_ROOT}/airflow"

echo "Starting Airflow webserver and scheduler..."
echo "Airflow Home: ${AIRFLOW_HOME}"

# Start webserver in background
airflow webserver --port 8080 --daemon

# Start scheduler in background
airflow scheduler --daemon

echo ""
echo "✅ Airflow가 시작되었습니다!"
echo "   웹 UI: http://localhost:8080"
echo "   Username: admin"
echo "   Password: admin"
echo ""
echo "종료하려면: ./scripts/stop_airflow.sh"
EOF

chmod +x "${PROJECT_ROOT}/scripts/start_airflow.sh"

# Stop script
cat > "${PROJECT_ROOT}/scripts/stop_airflow.sh" << 'EOF'
#!/bin/bash
# Airflow 종료 스크립트

echo "Stopping Airflow..."

# Kill webserver
pkill -f "airflow webserver"

# Kill scheduler
pkill -f "airflow scheduler"

echo "✅ Airflow가 종료되었습니다."
EOF

chmod +x "${PROJECT_ROOT}/scripts/stop_airflow.sh"

# Create status script
cat > "${PROJECT_ROOT}/scripts/airflow_status.sh" << 'EOF'
#!/bin/bash
# Airflow 상태 확인 스크립트

echo "=== Airflow 상태 ==="
echo ""

# Check webserver
if pgrep -f "airflow webserver" > /dev/null; then
    echo "✅ Webserver: Running (http://localhost:8080)"
else
    echo "❌ Webserver: Not running"
fi

# Check scheduler
if pgrep -f "airflow scheduler" > /dev/null; then
    echo "✅ Scheduler: Running"
else
    echo "❌ Scheduler: Not running"
fi

echo ""
echo "프로세스 상세:"
ps aux | grep airflow | grep -v grep | awk '{print "  PID:", $2, "CMD:", $11, $12, $13}'
EOF

chmod +x "${PROJECT_ROOT}/scripts/airflow_status.sh"

echo ""
echo "==========================================="
echo -e "${GREEN}✅ Apache Airflow 설치 완료!${NC}"
echo "==========================================="
echo ""
echo "다음 단계:"
echo "  1. 새 터미널을 열거나 다음 명령 실행:"
echo "     source ~/.zshrc  (또는 ~/.bashrc)"
echo ""
echo "  2. Airflow 시작:"
echo "     ./scripts/start_airflow.sh"
echo ""
echo "  3. 웹 UI 접속:"
echo "     http://localhost:8080"
echo "     Username: admin"
echo "     Password: admin"
echo ""
echo "  4. Airflow 상태 확인:"
echo "     ./scripts/airflow_status.sh"
echo ""
echo "  5. Airflow 종료:"
echo "     ./scripts/stop_airflow.sh"
echo ""
