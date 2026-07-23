#!/usr/bin/env bash

# Realty Radar Ubuntu/Linux 전용 자동 실행 스크립트
echo "==================================================="
echo " Realty Radar Ubuntu/Linux System Starting..."
echo "==================================================="

# virtualenv 활성화 체크 (있는 경우)
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Python 프로세스 오케스트레이터 호출
python3 scripts/run.py
