import os
import sys
import time
import subprocess
import uvicorn


def main():
    """Realty Radar 다중 프로세스(Worker, Scheduler, Web Server) 오케스트레이터 및 자동 종료 매니저."""
    print("===================================================")
    print(" Realty Radar Multi-Process System Starting...")
    print("===================================================")

    # PYTHONPATH 설정
    sys.path.insert(0, os.path.abspath("src"))
    os.environ["PYTHONPATH"] = "src"

    # .env 파일 검증
    if not os.path.exists(".env"):
        print("[.env] File not found. Please check your .env configuration.")
        sys.exit(1)

    procs: list[subprocess.Popen] = []

    try:
        # 1. 백그라운드 Worker 프로세스 띄우기 (독립 CMD 콘솔)
        print("1. Starting Worker Process...")
        cmd_worker = [sys.executable, "-m", "realty_radar.worker"]
        if sys.platform == "win32":
            p_worker = subprocess.Popen(
                cmd_worker,
                env=dict(os.environ, PYTHONPATH="src"),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            p_worker = subprocess.Popen(cmd_worker, env=dict(os.environ, PYTHONPATH="src"))
        procs.append(p_worker)

        # 2. 백그라운드 Scheduler 프로세스 띄우기 (독립 CMD 콘솔)
        print("2. Starting Scheduler Process...")
        cmd_scheduler = [sys.executable, "-m", "realty_radar.scheduler"]
        if sys.platform == "win32":
            p_scheduler = subprocess.Popen(
                cmd_scheduler,
                env=dict(os.environ, PYTHONPATH="src"),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            p_scheduler = subprocess.Popen(cmd_scheduler, env=dict(os.environ, PYTHONPATH="src"))
        procs.append(p_scheduler)

        # 3. FastAPI Web Server 실행 (환경 변수 또는 기본값 적용)
        host = os.getenv("HOST") or os.getenv("APP_HOST") or "127.0.0.1"
        port = int(os.getenv("PORT") or os.getenv("APP_PORT") or "8000")
        is_reload = os.getenv("APP_ENV", "local").lower() == "local"

        print(f"3. Starting FastAPI Web Server (http://{host}:{port})...")
        uvicorn.run(
            "realty_radar.web.main:app",
            host=host,
            port=port,
            reload=is_reload,
        )

    except (KeyboardInterrupt, SystemExit):
        print("\n[System] Shutdown signal received...")
    finally:
        print("===================================================")
        print(" Server stopped: Cleaning up background processes...")
        print("===================================================")

        # 띄웠던 Worker 및 Scheduler 자식 프로세스와 CMD 창 100% 강제 종료
        for p in procs:
            try:
                p.terminate()
                p.wait(timeout=1.0)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass

        # Windows 환경의 남은 자식 CMD 창 일괄 강제 정리
        if sys.platform == "win32":
            try:
                subprocess.run(
                    'taskkill /FI "IMAGENAME eq python.exe" /F /T >nul 2>&1',
                    shell=True,
                )
            except Exception:
                pass

        print("[System] All processes and CMD windows cleaned up.")


if __name__ == "__main__":
    main()
