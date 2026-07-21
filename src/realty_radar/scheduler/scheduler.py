import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from realty_radar.scheduler.schedules import schedule_regular_search_job


class TaskScheduler:
    """APScheduler 기반 자동 작업 예약 프로세스."""

    def __init__(self):
        self.scheduler = BackgroundScheduler()

    def start(self) -> None:
        """기본 크론 작업등록 및 스케줄러 실행 (예: 6시간마다 수집 작업 자동 생성)."""
        print("[Scheduler] Realty Radar 예약 실행 스케줄러를 시작합니다...")

        # 6시간마다 여의도동 정기 수집 작업 등록 (크론: 0 */6 * * *)
        self.scheduler.add_job(
            schedule_regular_search_job,
            trigger=CronTrigger.from_crontab("0 */6 * * *"),
            id="job_regular_search_site_a",
            name="SITE_A 정기 수집",
            replace_existing=True,
            kwargs={"source_code": "SITE_A", "region_name": "여의도동"},
        )

        self.scheduler.start()
        print("[Scheduler] 정기 예약 태스크 등록 완료 (Cron: '0 */6 * * *').")

    def stop(self) -> None:
        """스케줄러 종료."""
        print("[Scheduler] 스케줄러를 종료합니다.")
        self.scheduler.shutdown()


def start_scheduler():
    """스케줄러 단독 프로세스 실행 엔트리포인트."""
    task_scheduler = TaskScheduler()
    task_scheduler.start()

    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        task_scheduler.stop()
