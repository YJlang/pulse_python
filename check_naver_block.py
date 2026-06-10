"""
네이버 플레이스 IP 차단 해제 여부를 '요청 1번'으로만 확인하는 단발 점검 스크립트.
크롤링 루프를 돌지 않으므로 차단 IP를 추가로 자극하지 않는다.
사용: python check_naver_block.py
"""

import asyncio
import re
import sys
from urllib.parse import quote

import urllib.request

from playwright.async_api import async_playwright

QUERY = "부산가야밀면 안양"


def current_public_ip() -> str:
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=10) as resp:
            return resp.read().decode().strip()
    except Exception as exc:  # noqa: BLE001
        return f"(IP 조회 실패: {exc})"


async def _check() -> None:
    print(f"현재 공인 IP: {current_public_ip()}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                "Mobile/15E148 Safari/604.1"
            ),
            viewport={"width": 375, "height": 812},
        )
        page = await context.new_page()
        try:
            url = f"https://m.place.naver.com/restaurant/list?query={quote(QUERY)}"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            body = await page.locator("body").inner_text(timeout=5000)
            blocked = ("서비스 이용이 제한" in body) or ("과도한 접근 요청" in body)
            if blocked:
                print("❌ 아직 차단 상태입니다.")
                print("   " + re.sub(r"\s+", " ", body).strip()[:200])
            else:
                print("✅ 차단 해제! 네이버 검색 결과가 정상 응답합니다.")
                print("   본문 미리보기: " + re.sub(r"\s+", " ", body).strip()[:120])
        except Exception as exc:  # noqa: BLE001
            print(f"점검 중 오류: {exc}")
        finally:
            await browser.close()


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(_check())


if __name__ == "__main__":
    main()
