#!/usr/bin/env bash

# Realty Radar Ubuntu/Linux 실행 스크립트
echo "==================================================="
echo " Realty Radar Ubuntu/Linux System Starting..."
echo "==================================================="

# 가상환경 파이썬 확인
PYTHON_CMD="python3"
if [ -f ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
elif [ -f "venv/bin/python" ]; then
    PYTHON_CMD="venv/bin/python"
fi

# PYTHONPATH 설정 및 파이썬 오케스트레이터 실행
export PYTHONPATH="src"
$PYTHON_CMD scripts/run.py
