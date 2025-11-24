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

async def search_place_and_get_url(query: str) -> str:
    """
    카카오맵에서 가게를 검색하고 URL을 반환합니다.
    여러 결과가 있을 경우 사용자에게 선택을 요청합니다.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) # 검색 과정은 보여줌
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 375, "height": 812}
        )
        page = await context.new_page()
        
        try:
            # 카카오맵 모바일 검색
            search_url = f"https://m.map.kakao.com/actions/searchView?q={query}"
            print(f"🔍 카카오맵에서 '{query}' 검색 중...")
            
            await page.goto(search_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            
            # 검색 결과 찾기 (li[data-id])
            result_items = await page.locator('li[data-id]').all()
            
            if not result_items:
                # 결과가 없는 경우
                print("❌ 카카오맵 검색 결과를 찾을 수 없습니다.")
                return None
            
            selected_id = None
            
            if len(result_items) > 1:
                print(f"\n🤔 카카오맵: '{query}'에 대한 검색 결과가 {len(result_items)}개 발견되었습니다.")
                print("-" * 50)
                
                candidates = []
                for i, item in enumerate(result_items[:5]):
                    try:
                        data_id = await item.get_attribute("data-id")
                        text = await item.inner_text()
                        text = text.replace("\n", " ").strip()
                        if len(text) > 60:
                            text = text[:57] + "..."
                        
                        candidates.append((data_id, text))
                        print(f"[{i+1}] {text}")
                    except:
                        print(f"[{i+1}] (정보를 가져올 수 없음)")
                        candidates.append((None, "정보 없음"))
                
                print("-" * 50)
                
                # 사용자 입력 대기
                try:
                    selection = input("👉 카카오맵 분석할 가게 번호를 선택하세요 (기본값 1): ").strip()
                    if not selection:
                        selected_idx = 0
                    else:
                        selected_idx = int(selection) - 1
                        if selected_idx < 0 or selected_idx >= len(candidates):
                            print("⚠️ 잘못된 번호입니다. 1번을 선택합니다.")
                            selected_idx = 0
                except:
                    selected_idx = 0
                
                print(f"✅ {selected_idx + 1}번 가게를 선택했습니다.")
                selected_id = candidates[selected_idx][0]
            else:
                # 결과가 1개인 경우
                selected_id = await result_items[0].get_attribute("data-id")
            
            if selected_id:
                # URL 생성 (리뷰 탭으로 바로 이동)
                # https://place.map.kakao.com/{id}#review
                final_url = f"https://place.map.kakao.com/{selected_id}#review"
                print(f"✅ 카카오맵 가게 찾기 완료: ID {selected_id}")
                print(f"📍 URL: {final_url}")
                return final_url
            else:
                return None
                
        except Exception as e:
            print(f"❌ 카카오맵 검색 중 오류 발생: {e}")
            return None
        finally:
            await browser.close()

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
