"""
카카오맵 리뷰 크롤러 (별점 포함)
"""
import asyncio
from playwright.async_api import async_playwright
from typing import List, Dict
import re

async def crawl_kakao_reviews(url: str, max_reviews: int = 50) -> List[Dict]:
    """
    카카오맵 리뷰를 크롤링합니다 (별점 포함).
    
    Args:
        url: 카카오맵 Place URL (예: https://place.map.kakao.com/...)
        max_reviews: 수집할 최대 리뷰 개수
        
    Returns:
        리뷰 리스트 [{'text': cleaned, 'raw_text': original, 'rating': int, 'source': 'kakao', 'date': str}]
    """
    reviews = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
            viewport={"width": 375, "height": 812}
        )
        page = await context.new_page()
        
        try:
            print(f"📍 Navigating to Kakao Map: {url}")
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)
            
            scroll_attempts = 0
            max_scroll_attempts = 15
            prev_count = 0
            
            while len(reviews) < max_reviews and scroll_attempts < max_scroll_attempts:
                # 카카오맵 리뷰 요소 찾기 (ul.list_review > li)
                review_elements = await page.locator("ul.list_review > li").all()
                
                print(f"   Found {len(review_elements)} review elements...")
                
                temp_reviews = []
                for i, el in enumerate(review_elements):
                    try:
                        # 텍스트 추출
                        text_el = el.locator("p.desc_review").first
                        if await text_el.count() == 0:
                            continue
                            
                        # "더보기" 버튼이 있으면 클릭
                        more_btn = text_el.locator(".btn_more").first
                        if await more_btn.count() > 0 and await more_btn.is_visible():
                            try:
                                await more_btn.click(timeout=1000)
                                await page.wait_for_timeout(200)
                            except:
                                pass
                        
                        text = await text_el.inner_text()
                        text = text.replace("더보기", "").strip()
                        
                        if not text:
                            continue
                        
                        # 별점 추출
                        rating = None
                        try:
                            # <span class="starred_grade"><span class="screen_out">별점</span><span class="screen_out">5.0</span>...</span>
                            grade_spans = await el.locator(".starred_grade .screen_out").all()
                            for span in grade_spans:
                                span_text = await span.inner_text()
                                if span_text.replace('.', '').isdigit(): # "5.0" -> "50"
                                    rating = int(float(span_text))
                                    break
                        except:
                            pass
                        
                        # 날짜 추출
                        date = None
                        try:
                            date_el = el.locator(".txt_date").first
                            if await date_el.count() > 0:
                                date = await date_el.inner_text()
                        except:
                            pass
                        
                        review_data = {
                            'raw_text': text,
                            'text': text,
                            'rating': rating,
                            'date': date,
                            'source': 'kakao'
                        }
                        
                        temp_reviews.append(review_data)
                    
                    except Exception as e:
                        continue
                
                # 중복 제거 (텍스트 기준)
                unique_texts = set([r['raw_text'] for r in reviews])
                for r in temp_reviews:
                    if r['raw_text'] not in unique_texts:
                        reviews.append(r)
                        unique_texts.add(r['raw_text'])
                
                current_count = len(reviews)
                print(f"   📊 Collected {current_count} Kakao reviews (attempt {scroll_attempts + 1})...")
                
                if current_count == prev_count:
                    scroll_attempts += 1
                else:
                    scroll_attempts = 0
                    prev_count = current_count
                
                # 스크롤
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
                
                # 더보기 버튼 (페이지 하단) 처리 - 카카오맵은 스크롤만으로 로딩되는 경우가 많지만, "후기 더보기" 버튼이 있을 수도 있음
                try:
                    more_reviews_btn = await page.locator("a.link_more:has-text('후기 더보기')").first
                    if await more_reviews_btn.count() > 0 and await more_reviews_btn.is_visible():
                        await more_reviews_btn.click()
                        await page.wait_for_timeout(2000)
                except:
                    pass
            
            print(f"✅ Collected {len(reviews)} Kakao Map reviews")
        
        except Exception as e:
            print(f"❌ Error during Kakao crawling: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await browser.close()
    
    return reviews[:max_reviews]

if __name__ == "__main__":
    # 테스트
    test_url = "https://place.map.kakao.com/1799462452#review"  # 실제 URL로 교체
    result = asyncio.run(crawl_kakao_reviews(test_url, max_reviews=10))
    print(f"\n=== Kakao Reviews ===")
    for i, review in enumerate(result[:5], 1):
        print(f"\n[Review {i}]")
        print(f"Rating: {review.get('rating', 'N/A')}")
        print(f"Text: {review.get('text', 'N/A')[:80]}...")
        print(f"Date: {review.get('date', 'N/A')}")
