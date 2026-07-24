"""Realty Radar 웹서버 전용 실행 스크립트 (크롤러 제외).

Ubuntu 클라우드 서버에서 웹서버만 실행합니다.
크롤러(Worker/Scheduler)는 로컬 Windows PC에서 별도 실행합니다.
"""
import os
import sys
import uvicorn


def main():
    """웹서버만 실행 (Worker/Scheduler 제외)."""
    print("===================================================")
    print(" Realty Radar - 웹서버 전용 모드")
    print(" (크롤러는 로컬 PC에서 별도 실행)")
    print("===================================================")

    sys.path.insert(0, os.path.abspath("src"))
    os.environ["PYTHONPATH"] = "src"

    if not os.path.exists(".env"):
        print("[.env] File not found.")
        sys.exit(1)

    host = os.getenv("HOST") or os.getenv("APP_HOST") or "127.0.0.1"
    port = int(os.getenv("PORT") or os.getenv("APP_PORT") or "8000")
    is_reload = os.getenv("APP_ENV", "local").lower() == "local"

    print(f"웹서버 시작: http://{host}:{port}")
    uvicorn.run(
        "realty_radar.web.main:app",
        host=host,
        port=port,
        reload=is_reload,
    )


if __name__ == "__main__":
    main()
