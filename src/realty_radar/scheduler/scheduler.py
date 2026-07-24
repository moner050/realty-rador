import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from realty_radar.scheduler.schedules import schedule_regular_search_job


class TaskScheduler:
    """APScheduler 기반 자동 작업 예약 프로세스."""

    def __init__(self):
        self.scheduler = BackgroundScheduler()

    def start(self) -> None:
        """매일 오전 06:00 정각 전체 지역(서울/경기/인천) 정기 크롤링 작업 자동 등록."""
        print("[Scheduler] Realty Radar 매일 06시 전체 스크래핑 예약 스케줄러를 시작합니다...")

        # 매일 오전 06시 정각 전체 지역 수집 작업 등록 (크론: 0 6 * * *)
        self.scheduler.add_job(
            schedule_regular_search_job,
            trigger=CronTrigger.from_crontab("0 6 * * *"),
            id="job_regular_search_site_a",
            name="네이버부동산 매일 06시 전체 지역 정기 수집",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
            kwargs={"source_code": "SITE_A", "region_name": "ALL_METRO"},
        )

        self.scheduler.start()
        print("[Scheduler] 정기 예약 태스크 등록 완료 (Cron: '0 6 * * *' - 매일 06시 서울/경기/인천 전체 수집).")

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
