import argparse
import asyncio
from playwright.async_api import async_playwright

from realty_radar.config import settings


async def run_manual_login(source_code: str, login_url: str) -> None:
    """수동 로그인 화면을 브라우저로 띄우고 쿠키 세션을 저장."""
    auth_dir = settings.auth_directory
    auth_dir.mkdir(parents=True, exist_ok=True)
    save_path = auth_dir / f"{source_code}.json"

    print(f"[{source_code}] 로그인 브라우저를 엽니다: {login_url}")
    print("로그인을 완료한 후 엔터(Enter) 키를 누르면 세션이 저장됩니다.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(login_url)

        # 사용자 로그인 대기
        input(">> 로그인을 완료했으면 엔터 키를 누르세요...")

        # 세션 쿠키 저장
        await context.storage_state(path=str(save_path))
        print(f"[{source_code}] 로그인 세션이 저장되었습니다 -> {save_path}")

        await context.close()
        await browser.close()


def main():
    parser = argparse.ArgumentParser(description="부동산 사이트 수동 로그인 CLI")
    parser.add_argument("--source", type=str, default="SITE_A", help="사이트 소스 코드 (예: SITE_A)")
    parser.add_argument("--url", type=str, default="https://site-a.com/login", help="로그인 페이지 URL")

    args = parser.parse_args()
    asyncio.run(run_manual_login(args.source, args.url))


if __name__ == "__main__":
    main()
