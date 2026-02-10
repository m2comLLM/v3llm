#!/usr/bin/env bash
# =============================================================
#  v3llm 프로젝트 설치 스크립트
#  - Python 가상환경(venv) 생성 및 패키지 설치
#  - Ollama 설치 및 모델 다운로드
# =============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

echo "=========================================="
echo "  v3llm 프로젝트 환경 설치"
echo "=========================================="

# ----------------------------------------------------------
# 1. 시스템 패키지 (Debian/Ubuntu 계열)
# ----------------------------------------------------------
echo ""
echo "[1/4] 시스템 패키지 확인 중..."
if command -v apt-get &>/dev/null; then
    if command -v sudo &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq python3 python3-venv python3-pip curl zstd
    else
        apt-get update -qq
        apt-get install -y -qq python3 python3-venv python3-pip curl zstd
    fi
else
    echo "      apt-get 을 찾을 수 없습니다. Python3, pip, curl 이 설치되어 있는지 확인해주세요."
fi

# ----------------------------------------------------------
# 2. Python 가상환경 생성 및 패키지 설치
# ----------------------------------------------------------
echo ""
echo "[2/4] Python 가상환경 생성 중... ($VENV_DIR)"

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "      pip 업그레이드 중..."
pip install --upgrade pip -q

echo "      Python 패키지 설치 중..."
pip install -q \
    streamlit \
    pandas \
    pdfplumber \
    chromadb \
    requests \
    ollama

echo "      Python 패키지 설치 완료"

# ----------------------------------------------------------
# 3. Ollama 설치
# ----------------------------------------------------------
echo ""
echo "[3/4] Ollama 설치 확인 중..."

if command -v ollama &>/dev/null; then
    echo "      Ollama 가 이미 설치되어 있습니다: $(ollama --version)"
else
    echo "      Ollama 설치 중..."
    curl -fsSL https://ollama.com/install.sh | sh
    echo "      Ollama 설치 완료"
fi

# ----------------------------------------------------------
# 4. Ollama 모델 다운로드
# ----------------------------------------------------------
echo ""
echo "[4/4] Ollama 모델 다운로드 중..."

if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo "      Ollama 서버 시작 중..."
    ollama serve &>/dev/null &
    sleep 3
fi

echo "      임베딩 모델 다운로드: nomic-embed-text"
ollama pull nomic-embed-text

echo "      LLM 모델 다운로드: exaone3.5:7.8b"
ollama pull exaone3.5:7.8b

# ----------------------------------------------------------
# 완료
# ----------------------------------------------------------
echo ""
echo "=========================================="
echo "  설치 완료!"
echo "=========================================="
echo ""
echo "사용법:"
echo "  1. 가상환경 활성화:  source venv/bin/activate"
echo "  2. 인덱스 빌드:     python index_data.py"
echo "  3. 대시보드 실행:   streamlit run dashboard.py"
echo ""
