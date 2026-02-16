"""
네이버 및 카카오맵 리뷰 크롤링 서비스
"""
import asyncio
import re
import sys
import threading
from typing import List, Dict, Optional, Tuple
from playwright.async_api import async_playwright
from app.utils.logger import get_logger

logger = get_logger(__name__)

class CrawlerService:
    """
    네이버와 카카오맵에서 리뷰를 수집하는 서비스 클래스입니다.
    """

    @staticmethod
    def _clean_review_text(text: str) -> str:
        """
        리뷰 텍스트에서 불필요한 UI 요소(메타데이터)를 제거하고 정제합니다.
        """
        lines = text.split('\n')
        noise_patterns = [
            r'^리뷰\s+\d+', r'^사진\s+\d+', r'팔로워?\s+\d+', r'^\d+\s*팔로우',
            r'방문일\s+\d+\.\d+\.', r'\d{4}년\s+\d{1,2}월\s+\d{1,2}일',
            r'[일월화수목금토]요일', r'\d+번째\s+방문', r'인증\s+수단',
            r'영수증|결제내역', r'더\s*보기', r'펼쳐보기', r'반응\s+남기기',
            r'개의\s+리뷰가\s+더\s+있습니다', r'^\s*[+※]\d+\s*$',
            r'예약\s+없이\s+이용', r'대기\s+시간\s+바로\s+입장',
            r'[저점]심에?\s+방문', r'일상|친목|데이트|나들이',
            r'혼자|연인・배우자|친구|가족|아이', r'@\w+'
        ]
        
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if not line: continue
            
            is_noise = False
            for pattern in noise_patterns:
                if re.search(pattern, line):
                    is_noise = True
                    break
            
            # 짧은 UI 텍스트 필터링
            short_keywords = ['음식이 맛있어요', '매장이 청결해요', '친절해요', '가성비가 좋아요']
            if line.startswith('"') and any(k in line for k in short_keywords):
                continue
                
            if re.match(r'^\d+$', line): # 숫자만 있는 줄
                continue
                
            if not is_noise and len(line) > 3:
                cleaned_lines.append(line)
                
        review_text = ' '.join(cleaned_lines)
        review_text = re.sub(r'[+※~]{2,}', '', review_text)
        review_text = re.sub(r'\s+', ' ', review_text)
        return review_text.strip()

    async def crawl_naver(self, query: str, max_reviews: int = 50) -> List[Dict]:
        """
        네이버 플레이스에서 리뷰를 수집합니다.
        """
        logger.info(f"🚀 [Naver] Searching for: {query}")
        reviews = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                viewport={"width": 375, "height": 812}
            )
            page = await context.new_page()
            
            try:
                # 1. 검색 및 URL 획득
                search_url = f"https://m.map.naver.com/search2/search.naver?query={query}"
                await page.goto(search_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)
                
                place_id = None
                current_url = page.url
                
                # 상세 페이지로 바로 이동했는지 확인
                if "m.place.naver.com" in current_url and ("/restaurant/" in current_url or "/place/" in current_url):
                    match = re.search(r'/(?:restaurant|place)/(\d+)', current_url)
                    if match: place_id = match.group(1)
                else:
                    # 검색 결과 리스트에서 첫 번째 항목 선택
                    try:
                        first_link = page.locator('a[href*="/place/"], a[href*="/restaurant/"]').first
                        if await first_link.count() > 0:
                            href = await first_link.get_attribute('href')
                            match = re.search(r'/(?:restaurant|place)/(\d+)', href)
                            if match: place_id = match.group(1)
                    except:
                        pass

                if not place_id:
                    logger.warning("[Naver] Could not find place ID.")
                    return []

                # 2. 리뷰 페이지 이동
                review_url = f"https://m.place.naver.com/restaurant/{place_id}/review/visitor"
                logger.info(f"Go to Review Page: {review_url}")
                await page.goto(review_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(3000)

                # 3. 크롤링 루프
                scroll_attempts = 0
                max_scrolls = 20
                prev_count = 0
                
                while len(reviews) < max_reviews and scroll_attempts < max_scrolls:
                    elements = await page.locator("ul > li").all()
                    
                    temp_reviews = []
                    for el in elements:
                        try:
                            text = await el.inner_text()
                            if text and len(text) > 10:
                                cleaned = self._clean_review_text(text)
                                if len(cleaned) < 5: continue
                                
                                # 평점 추출
                                rating = None
                                match = re.search(r'([1-5])(점|개)', text)
                                if match: rating = int(match.group(1))

                                # 날짜 간단 추출 (첫 번째 발견되는 날짜 패턴)
                                date = None
                                date_match = re.search(r'(\d{4}\.\d{1,2}\.\d{1,2})', text)
                                if date_match: date = date_match.group(1)

                                temp_reviews.append({
                                    "raw_text": text.strip(),
                                    "text": cleaned,
                                    "rating": rating,
                                    "date": date,
                                    "source": "naver"
                                })
                        except: continue

                    # 중복 제거 및 추가
                    unique_texts = set(r['raw_text'] for r in reviews)
                    for r in temp_reviews:
                        if r['raw_text'] not in unique_texts:
                            reviews.append(r)
                            unique_texts.add(r['raw_text'])
                    
                    if len(reviews) == prev_count:
                        scroll_attempts += 1
                        # 더보기 버튼 클릭 시도
                        try:
                            btn = page.locator("button:has-text('더보기'), a:has-text('더보기')").first
                            if await btn.count() > 0:
                                await btn.click()
                                await page.wait_for_timeout(1000)
                                scroll_attempts = 0
                        except: pass
                    else:
                        scroll_attempts = 0
                        prev_count = len(reviews)

                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1500)

                logger.info(f"✅ [Naver] Collected {len(reviews)} reviews")
                
            except Exception as e:
                logger.error(f"❌ [Naver] Crawling error: {e}")
            finally:
                await browser.close()
                
        return reviews[:max_reviews]

    async def crawl_kakao(self, query: str, max_reviews: int = 50) -> List[Dict]:
        """
        카카오맵에서 리뷰를 수집합니다.
        """
        logger.info(f"🚀 [Kakao] Searching for: {query}")
        reviews = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                viewport={"width": 375, "height": 812}
            )
            page = await context.new_page()
            
            try:
                # 1. 검색
                search_url = f"https://m.map.kakao.com/actions/searchView?q={query}"
                await page.goto(search_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)
                
                # 첫 번째 결과 선택
                first_item = page.locator('li[data-id]').first
                if await first_item.count() == 0:
                    logger.warning("[Kakao] No search results found.")
                    return []
                    
                data_id = await first_item.get_attribute("data-id")
                review_url = f"https://place.map.kakao.com/{data_id}#review"
                
                # 2. 리뷰 페이지 이동
                await page.goto(review_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(3000)
                
                # 3. 크롤링 루프
                scroll_attempts = 0
                max_scrolls = 15
                prev_count = 0
                
                while len(reviews) < max_reviews and scroll_attempts < max_scrolls:
                    elements = await page.locator("ul.list_review > li").all()
                    
                    temp_reviews = []
                    for el in elements:
                        try:
                            text_el = el.locator("p.desc_review").first
                            if await text_el.count() == 0: continue
                            
                            # 더보기 클릭
                            more = text_el.locator(".btn_more").first
                            if await more.count() > 0 and await more.is_visible():
                                await more.click(timeout=1000)
                            
                            text = await text_el.inner_text()
                            text = text.replace("더보기", "").strip()
                            if not text: continue
                            
                            # 별점
                            rating = None
                            try:
                                spans = await el.locator(".starred_grade .screen_out").all()
                                for s in spans:
                                    st = await s.inner_text()
                                    if st.replace('.','').isdigit():
                                        rating = int(float(st))
                                        break
                            except: pass

                            # 날짜
                            date = None
                            try:
                                de = el.locator(".txt_date").first
                                if await de.count() > 0: date = await de.inner_text()
                            except: pass
                            
                            temp_reviews.append({
                                "raw_text": text,
                                "text": text, # 카카오는 비교적 깨끗함
                                "rating": rating,
                                "date": date,
                                "source": "kakao"
                            })
                        except: continue
                        
                    unique_texts = set(r['raw_text'] for r in reviews)
                    for r in temp_reviews:
                        if r['raw_text'] not in unique_texts:
                            reviews.append(r)
                            unique_texts.add(r['raw_text'])
                            
                    if len(reviews) == prev_count:
                        scroll_attempts += 1
                        # 더보기 버튼 (페이지 하단)
                        try:
                            more_link = page.locator("a.link_more:has-text('후기 더보기')").first
                            if await more_link.count() > 0 and await more_link.is_visible():
                                await more_link.click()
                                await page.wait_for_timeout(1000)
                                scroll_attempts = 0
                        except: pass
                    else:
                        scroll_attempts = 0
                        prev_count = len(reviews)
                        
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1500)
                    
                logger.info(f"✅ [Kakao] Collected {len(reviews)} reviews")
                
            except Exception as e:
                logger.error(f"❌ [Kakao] Crawling error: {e}")
            finally:
                await browser.close()
                
        return reviews[:max_reviews]
    
    async def collect_all_reviews(self, store_name: str, address: str) -> List[Dict]:
        """
        네이버와 카카오맵 리뷰를 동시에 수집합니다.
        가게 이름과 주소를 조합하여 검색 정확도를 높입니다.
        
        Windows에서는 Uvicorn의 SelectorEventLoop과 Playwright의 ProactorEventLoop
        충돌을 피하기 위해, 별도 스레드에서 새로운 ProactorEventLoop을 생성하여 실행합니다.
        """
        query = f"{address} {store_name}"
        logger.info(f"🔎 Starting concurrent crawling for: {query}")

        async def _crawl_all():
            naver_task = asyncio.create_task(self.crawl_naver(query))
            kakao_task = asyncio.create_task(self.crawl_kakao(query))
            return await asyncio.gather(naver_task, kakao_task)

        if sys.platform == 'win32':
            # Windows: Uvicorn uses SelectorEventLoop which can't spawn subprocesses.
            # Run Playwright in a dedicated thread with its own ProactorEventLoop.
            result_container = {}

            def _run_in_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # ProactorEventLoop is the default on Windows when creating a new loop
                    # but let's be explicit
                    if not isinstance(loop, asyncio.ProactorEventLoop):
                        loop.close()
                        loop = asyncio.ProactorEventLoop()
                        asyncio.set_event_loop(loop)
                    result_container['result'] = loop.run_until_complete(_crawl_all())
                except Exception as e:
                    result_container['error'] = e
                finally:
                    loop.close()

            thread = threading.Thread(target=_run_in_thread)
            thread.start()
            
            # await를 사용하여 메인 루프를 블로킹하지 않고 스레드 완료 대기
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, thread.join)

            if 'error' in result_container:
                raise result_container['error']
            results = result_container['result']
        else:
            # Linux/Mac: 이벤트 루프 충돌 없음, 직접 실행
            results = await _crawl_all()

        all_reviews = results[0] + results[1]
        logger.info(f"📊 Total reviews collected: {len(all_reviews)} (Naver: {len(results[0])}, Kakao: {len(results[1])})")

        return all_reviews
