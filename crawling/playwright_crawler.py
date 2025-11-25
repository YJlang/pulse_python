"""
네이버 리뷰 크롤러 (Playwright 사용)
네이버 플레이스/지도에서 리뷰를 자동으로 수집하는 프로그램입니다.

사용자가 가게 이름이나 주소만 입력하면 자동으로 네이버 플레이스를 찾아서 크롤링합니다.
"""
import asyncio
from playwright.async_api import async_playwright
from typing import List, Dict, Tuple, Optional
import re

def clean_review_text(text: str) -> str:
    """
    네이버 리뷰 텍스트 정제 함수

    웹페이지에서 가져온 리뷰에는 "리뷰 56", "사진 164", "팔로워 3" 같은
    UI 메타데이터가 섞여 있습니다. 이 함수는 실제 리뷰 내용만 추출합니다.

    Args:
        text: 크롤링한 원본 리뷰 텍스트 (UI 요소와 섞여있음)

    Returns:
        정제된 순수 리뷰 본문

    Example:
        입력: "리뷰 56\\n사진 164\\n맛있어요\\n팔로워 3"
        출력: "맛있어요"
    """
    # 줄바꿈 기준으로 텍스트를 여러 줄로 분리
    lines = text.split('\n')

    # 제거할 UI 요소 패턴들 (정규표현식 사용)
    # r'패턴'은 정규표현식(regex)을 의미하며, 특정 형태의 텍스트를 찾습니다
    noise_patterns = [
        r'^리뷰\s+\d+',                          # "리뷰 56" 형태 제거
        r'^사진\s+\d+',                          # "사진 164" 형태 제거
        r'팔로워?\s+\d+',                        # "팔로워 3", "팔로우 3" 제거
        r'^\d+\s*팔로우',                        # "3 팔로우" 제거
        r'방문일\s+\d+\.\d+\.',                  # "방문일 9.14." 제거
        r'\d{4}년\s+\d{1,2}월\s+\d{1,2}일',     # "2025년 9월 14일" 제거
        r'[일월화수목금토]요일',                 # 요일 정보 제거
        r'\d+번째\s+방문',                       # "1번째 방문" 제거
        r'인증\s+수단',                          # "인증 수단" 제거
        r'영수증|결제내역',                      # "영수증", "결제내역" 제거
        r'더\s*보기',                            # "더보기" 버튼 텍스트 제거
        r'펼쳐보기',                             # "펼쳐보기" 버튼 텍스트 제거
        r'반응\s+남기기',                        # "반응 남기기" 제거
        r'개의\s+리뷰가\s+더\s+있습니다',        # 리뷰 개수 안내 문구 제거
        r'^\s*[+※]\d+\s*$',                     # "+4", "※3" 같은 심볼 제거
        r'예약\s+없이\s+이용',                   # 예약 정보 제거
        r'대기\s+시간\s+바로\s+입장',            # 대기시간 정보 제거
        r'[저점]심에?\s+방문',                   # "저녁에 방문", "점심에 방문" 제거
        r'일상|친목|데이트|나들이',              # 방문 목적 태그 제거
        r'혼자|연인・배우자|친구|가족|아이',     # 동반자 태그 제거
        r'@\w+',                                 # 인스타그램 태그(@username) 제거
    ]

    cleaned_lines = []  # 정제된 텍스트 라인들을 저장할 리스트

    # 각 줄을 하나씩 검사
    for line in lines:
        line = line.strip()  # 앞뒤 공백 제거
        if not line:  # 빈 줄은 건너뛰기
            continue

        # 이 줄이 노이즈(불필요한 UI 요소)인지 체크
        is_noise = False
        for pattern in noise_patterns:
            if re.search(pattern, line):  # 패턴이 발견되면
                is_noise = True
                break
        
        # 짧은 UI 텍스트 필터링 (특정 키워드 제외)
        short_keywords = ['음식이 맛있어요', '매장이 청결해요', '친절해요', '가성비가 좋아요', 
                         '양이 많아요', '매장이 넓어요', '혼밥하기 좋아요', '특별한 메뉴가 있어요',
                         '재료가 신선해요', '인테리어가 멋져요', '단체모임 하기 좋아요',
                         '뷰가 좋아요', '특별한 날 가기 좋아요', '화장실이 깨끗해요',
                         '차분한 분위기예요', '대화하기 좋아요', '아늑해요', '아이와 가기 좋아요',
                         '메뉴 구성이 알차요']
        
        # 네이버 자동 키워드는 건너뛰기 (따옴표로 시작하는 경우)
        if line.startswith('"') and any(keyword in line for keyword in short_keywords):
            continue
        
        # 숫자로만 구성된 라인 제거 (평점, 방문 횟수 등)
        if re.match(r'^\d+$', line):
            continue
        
        if not is_noise and len(line) > 3:  # 최소 4글자 이상
            cleaned_lines.append(line)
    
    # 리뷰 본문 재구성
    review_text = ' '.join(cleaned_lines)
    
    # 추가 정제: 특수문자 과다 제거
    review_text = re.sub(r'[+※~]{2,}', '', review_text)  # +++, ~~~~ 같은 반복 제거
    review_text = re.sub(r'\s+', ' ', review_text)  # 다중 공백 제거
    
    return review_text.strip()


async def search_place_and_get_url(query: str) -> Optional[Tuple[str, str]]:
    """
    네이버 지도에서 가게를 검색하여 자동으로 플레이스 URL과 가게명을 찾습니다.

    사용자가 "바람난 얼큰 수제비 범계점" 또는 "서울 강남구 테헤란로 123" 같은
    가게 이름이나 주소를 입력하면, 네이버 지도 검색을 통해 자동으로
    해당 가게의 리뷰 페이지 URL을 찾아줍니다.

    Args:
        query: 검색할 가게 이름 또는 주소 (예: "바람난 얼큰 수제비 범계점")

    Returns:
        (리뷰 URL, 가게명) 튜플, 실패 시 None
        예: ("https://m.place.naver.com/restaurant/31264425/review/visitor", "바람난 얼큰 수제비 범계점")
    """
    async with async_playwright() as p:
        # 브라우저 실행 (headless=True는 화면 없이 백그라운드 실행)
        browser = await p.chromium.launch(headless=True)

        # 모바일 환경으로 설정 (모바일 페이지가 더 안정적)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 375, "height": 812}
        )

        page = await context.new_page()

        try:
            # 네이버 지도 모바일 검색 페이지로 이동
            search_url = f"https://m.map.naver.com/search2/search.naver?query={query}"
            print(f"🔍 네이버 지도에서 '{query}' 검색 중...")

            await page.goto(search_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)  # 검색 결과 로딩 대기

            # 1. 이미 플레이스 상세 페이지로 리다이렉트된 경우 체크
            current_url = page.url
            if "m.place.naver.com" in current_url and ("/restaurant/" in current_url or "/place/" in current_url):
                print("✅ 검색 결과가 바로 상세 페이지로 연결되었습니다.")
                place_href = current_url
                store_name = query 
            else:
                # 2. 검색 결과 리스트에서 장소들 찾기 (중복 제거 로직 추가)
                # 검색 결과 아이템 컨테이너를 먼저 찾음
                # 보통 li 태그 안에 _item_common_... 클래스 등을 가짐
                # 하지만 모바일 웹 구조가 복잡하므로, a 태그를 찾되 부모를 확인하여 중복 제거
                
                raw_links = await page.locator('a[href*="/place/"], a[href*="/restaurant/"]').all()
                
                unique_places = []
                seen_ids = set()
                
                for link in raw_links:
                    href = await link.get_attribute('href')
                    # ID 추출
                    id_match = re.search(r'/(?:restaurant|place)/(\d+)', href)
                    if not id_match:
                        continue
                        
                    place_id = id_match.group(1)
                    if place_id in seen_ids:
                        continue
                        
                    # 새로운 장소 발견
                    seen_ids.add(place_id)
                    
                    # 텍스트 추출 (부모 요소에서)
                    try:
                        # 링크의 텍스트가 비어있을 수 있음 (이미지 링크 등)
                        # 따라서 부모 요소의 텍스트를 가져오거나, 링크 자체의 텍스트를 확인
                        text = await link.inner_text()
                        if not text.strip():
                            # 텍스트가 없으면 부모나 형제 요소에서 찾기 시도
                            # 여기서는 간단히 부모 텍스트 사용
                            parent = link.locator("..")
                            text = await parent.inner_text()
                        
                        text = text.replace("\n", " ").strip()
                        # 너무 짧거나 이상한 텍스트 필터링 (예: "주소보기", "공유" 등)
                        if len(text) < 2 or text in ["주소보기", "공유", "지도보기"]:
                            # 상위 부모에서 다시 시도
                            grandparent = link.locator("../..")
                            text = await grandparent.inner_text()
                            text = text.replace("\n", " ").strip()
                            
                        unique_places.append((link, text, href))
                    except:
                        continue
                        
                    if len(unique_places) >= 10: # 최대 10개까지만 수집
                        break

                if not unique_places:
                    print("❌ 검색 결과를 찾을 수 없습니다.")
                    await browser.close()
                    return None

                # 검색 결과 필터링 (정확도 향상)
                filtered_places = []
                exact_matches = []
                
                # 쿼리 정규화 (공백 제거)
                normalized_query = query.replace(" ", "")
                
                for link, text, href in unique_places:
                    # 텍스트에서 가게 이름만 추출 시도 (첫 번째 줄 or 공백 전까지)
                    # 예: "이모네정육식당 정육식당..." -> "이모네정육식당"
                    # 예: "이모네 한식..." -> "이모네"
                    
                    # 1. 줄바꿈으로 분리하여 첫 줄 확인
                    first_line = text.split('\n')[0].strip()
                    
                    # 2. 이름 정규화
                    normalized_name = first_line.replace(" ", "")
                    
                    # 정확히 일치하는 경우 (이모네 == 이모네)
                    if normalized_name == normalized_query:
                        exact_matches.append((link, text, href))
                        continue
                        
                    # 쿼리가 이름에 포함되는 경우 (이모네김밥, 이모네식당)
                    if normalized_query in normalized_name:
                        filtered_places.append((link, text, href))
                
                # 정확히 일치하는 결과가 있으면 그것만 보여줌 (사용자 요청 반영)
                if exact_matches:
                    print(f"✨ '{query}'와 정확히 일치하는 가게를 우선 표시합니다.")
                    final_places = exact_matches
                else:
                    final_places = filtered_places

                if not final_places:
                    # 필터링 결과가 없으면 원본 사용 (혹시 모를 오류 방지)
                    final_places = unique_places

                # 검색 결과가 여러 개인 경우 사용자에게 선택 요청
                if len(final_places) > 1:
                    print(f"\n🤔 '{query}'에 대한 검색 결과가 {len(final_places)}개 발견되었습니다.")
                    print("-" * 50)
                    
                    for i, (link, text, href) in enumerate(final_places):
                        # 텍스트 정리 (너무 길면 자르기)
                        display_text = text
                        if len(display_text) > 60:
                            display_text = display_text[:57] + "..."
                        print(f"[{i+1}] {display_text}")
                    
                    print("-" * 50)
                    
                    # 사용자 입력 대기
                    try:
                        selection = input("👉 분석할 가게 번호를 선택하세요 (기본값 1): ").strip()
                        if not selection:
                            selected_idx = 0
                        else:
                            selected_idx = int(selection) - 1
                            if selected_idx < 0 or selected_idx >= len(final_places):
                                print("⚠️ 잘못된 번호입니다. 1번을 선택합니다.")
                                selected_idx = 0
                    except Exception:
                        selected_idx = 0
                    
                    print(f"✅ {selected_idx + 1}번 가게를 선택했습니다.")
                    place_href = final_places[selected_idx][2]
                else:
                    # 결과가 1개인 경우
                    place_href = final_places[0][2]
                
                # 장소 상세 페이지로 이동
                if place_href.startswith('/'):
                    place_href = f"https://m.map.naver.com{place_href}"

                print(f"📍 가게 페이지로 이동 중...")
                await page.goto(place_href, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)

            # 현재 URL에서 place ID 추출
            current_url = page.url
            place_id_match = re.search(r'/(?:restaurant|place)/(\d+)', current_url)

            if not place_id_match:
                print(f"❌ 플레이스 ID를 찾을 수 없습니다. URL: {current_url}")
                await browser.close()
                return None

            place_id = place_id_match.group(1)

            # 가게 이름 추출
            try:
                store_name_el = await page.locator('h1, .place_name, [class*="tit"]').first
                if await store_name_el.count() > 0:
                    store_name = await store_name_el.inner_text()
                    store_name = store_name.strip()
                elif 'store_name' not in locals():
                    store_name = query
            except:
                if 'store_name' not in locals():
                    store_name = query

            # 리뷰 페이지 URL 생성
            review_url = f"https://m.place.naver.com/restaurant/{place_id}/review/visitor"

            print(f"✅ 가게 찾기 완료: {store_name}")
            print(f"📍 리뷰 URL: {review_url}")

            await browser.close()
            return (review_url, store_name)

        except Exception as e:
            print(f"❌ 검색 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            await browser.close()
            return None


async def crawl_naver_reviews(url: str, max_reviews: int = 50) -> List[Dict]:
    """
    네이버 플레이스/지도 리뷰 크롤링 함수 (Playwright 사용)

    데스크톱(map.naver.com)과 모바일(m.place.naver.com) URL 모두 지원합니다.
    Playwright는 실제 브라우저를 자동으로 조작하여 데이터를 수집하는 라이브러리입니다.

    Args:
        url: 네이버 지도/플레이스 URL (예: https://m.place.naver.com/restaurant/31264425/review/visitor)
        max_reviews: 수집할 최대 리뷰 개수 (기본값: 50개)

    Returns:
        리뷰 정보를 담은 딕셔너리 리스트
        각 딕셔너리 형식:
        {
            'text': '정제된 리뷰 본문',
            'raw_text': '원본 리뷰 텍스트',
            'rating': 평점(1-5),
            'date': '작성일자',
            'source': 'naver'
        }
    """
    reviews = []  # 수집한 리뷰를 저장할 리스트

    # Playwright 비동기 컨텍스트 시작 (async with로 자동으로 종료됨)
    async with async_playwright() as p:
        # URL에 'm.place'가 있으면 모바일 페이지로 판단
        is_mobile = 'm.place.naver.com' in url

        # 크롬 브라우저 실행 (headless=True는 화면 없이 백그라운드 실행)
        browser = await p.chromium.launch(headless=True)

        # 브라우저 컨텍스트 생성 (User-Agent와 화면 크기 설정)
        # User-Agent: 웹사이트가 크롤러를 차단하지 않도록 실제 브라우저인 것처럼 위장
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1" if is_mobile else
                      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 375, "height": 812} if is_mobile else {"width": 1920, "height": 1080}
        )

        # 새 페이지(탭) 생성
        page = await context.new_page()

        try:
            print(f"페이지 이동 중: {url}")

            # 페이지 로딩 (wait_until="networkidle"는 네트워크 요청이 끝날 때까지 대기)
            # timeout=30000은 30초 (밀리초 단위)
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # 동적 컨텐츠(JavaScript로 생성되는 내용)가 로딩될 때까지 3초 대기
            await page.wait_for_timeout(3000)

            print("리뷰 추출 중...")

            # 스크롤 관련 변수 초기화
            scroll_attempts = 0        # 현재까지 시도한 스크롤 횟수
            max_scroll_attempts = 20   # 최대 스크롤 시도 횟수 (리뷰가 더 안나오면 중단)
            prev_count = 0             # 이전 단계에서 수집한 리뷰 개수
            
            # 메인 크롤링 루프: 목표 리뷰 개수에 도달하거나 스크롤이 끝날 때까지 반복
            while len(reviews) < max_reviews and scroll_attempts < max_scroll_attempts:
                # 페이지의 모든 <ul> > <li> 요소 찾기 (네이버는 리뷰를 리스트 아이템으로 표시)
                review_elements = await page.locator("ul > li").all()

                temp_reviews = []  # 이번 루프에서 찾은 리뷰들을 임시 저장

                # 각 리스트 아이템을 검사하여 리뷰인지 확인
                for el in review_elements:
                    try:
                        # 요소의 텍스트 내용 가져오기
                        text = await el.inner_text()

                        # 텍스트가 있고 최소 길이를 만족하는지 확인 (너무 짧으면 리뷰가 아님)
                        if text and len(text) > 10:
                            # UI 메타데이터를 제거하고 순수 리뷰 본문만 추출
                            cleaned_text = clean_review_text(text)

                            # 정제 후에도 최소 길이를 만족하는지 확인
                            if not cleaned_text or len(cleaned_text) < 5:
                                continue

                            # 리뷰 데이터 구조 생성
                            # - raw_text: 원본 (LLM 분석용, 평점/날짜 등 메타데이터 포함)
                            # - text: 정제본 (BERTopic 토픽 분석용, 순수 리뷰 본문만)
                            review_data = {
                                "raw_text": text.strip(),      # 원본 텍스트 (공백 제거)
                                "text": cleaned_text,          # 정제된 텍스트
                                "source": "naver"              # 출처 표시
                            }

                            # 평점 추출 시도 (정규표현식 사용)
                            # 예: "5점", "4개" 같은 패턴에서 숫자 추출
                            rating_match = re.search(r'([1-5])(점|개)', text)
                            if rating_match:
                                review_data['rating'] = int(rating_match.group(1))  # 숫자 부분만 추출
                            else:
                                review_data['rating'] = None  # 평점 정보 없음

                            # 작성일자 추출 시도 (여러 형식 지원)
                            date_patterns = [
                                r'(\d{4}\.\d{1,2}\.\d{1,2})',  # "2024.01.15" 형식
                                r'(\d{1,2}개월 전)',            # "3개월 전" 형식
                                r'(\d{1,2}주 전)',              # "2주 전" 형식
                                r'(\d{1,2}일 전)',              # "5일 전" 형식
                            ]
                            for pattern in date_patterns:
                                date_match = re.search(pattern, text)
                                if date_match:
                                    review_data['date'] = date_match.group(1)
                                    break  # 첫 번째로 매칭된 형식 사용

                            temp_reviews.append(review_data)

                    except Exception as e:
                        # 오류 발생 시 해당 요소 건너뛰고 계속 진행
                        continue
                
                # 중복 제거하면서 리뷰 리스트 업데이트
                # 이미 수집한 리뷰의 텍스트를 Set에 저장하여 빠른 중복 검사
                unique_texts = set([r['raw_text'] for r in reviews])
                for r in temp_reviews:
                    if r['raw_text'] not in unique_texts:  # 중복이 아니면
                        reviews.append(r)                   # 리스트에 추가
                        unique_texts.add(r['raw_text'])     # Set에도 추가

                current_count = len(reviews)
                print(f"현재까지 {current_count}개 리뷰 수집 (시도 {scroll_attempts + 1}회)...")

                # 새로운 리뷰가 없으면 스크롤 시도 횟수 증가
                if current_count == prev_count:
                    scroll_attempts += 1  # 리뷰가 안늘어나면 카운트 증가
                else:
                    scroll_attempts = 0    # 새 리뷰가 있으면 카운트 리셋
                    prev_count = current_count

                # 페이지 맨 아래로 스크롤 (새로운 리뷰 로딩 유도)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)  # 2초 대기 (새 콘텐츠 로딩 시간)

                # "더보기" 버튼이 있으면 클릭 시도
                try:
                    more_buttons = await page.locator("button:has-text('더보기'), a:has-text('더보기')").all()
                    if more_buttons:
                        await more_buttons[0].click()  # 첫 번째 더보기 버튼 클릭
                        await page.wait_for_timeout(1500)  # 1.5초 대기
                        scroll_attempts = 0  # 버튼 클릭 성공 시 스크롤 카운트 리셋
                except:
                    pass  # 더보기 버튼이 없거나 클릭 실패해도 계속 진행

            print(f"✅ 총 {len(reviews)}개 리뷰 수집 완료")

        except Exception as e:
            # 크롤링 중 오류 발생 시 에러 메시지 출력
            print(f"❌ 크롤링 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()  # 상세 오류 내역 출력 (디버깅용)
        finally:
            # 성공/실패 여부와 관계없이 브라우저 종료 (메모리 누수 방지)
            await browser.close()

    # 최대 개수만큼 리뷰 반환 (초과 수집한 경우 잘라냄)
    return reviews[:max_reviews]


async def crawl_by_search(query: str, max_reviews: int = 50) -> Tuple[List[Dict], Optional[str]]:
    """
    가게 이름/주소로 검색하여 자동으로 리뷰를 크롤링하는 올인원 함수

    사용자 입장에서 가장 편리한 함수입니다. URL을 몰라도 가게 이름만 입력하면
    자동으로 네이버 지도에서 검색하고 리뷰를 수집합니다.

    Args:
        query: 가게 이름 또는 주소 (예: "바람난 얼큰 수제비 범계점", "서울 강남구 테헤란로 123")
        max_reviews: 수집할 최대 리뷰 개수 (기본값: 50개)

    Returns:
        (리뷰 리스트, 가게명) 튜플
        - 리뷰 리스트: [{'text': ..., 'rating': ..., 'date': ..., 'source': 'naver'}, ...]
        - 가게명: 자동으로 추출된 정확한 가게 이름

    Example:
        >>> reviews, store_name = await crawl_by_search("바람난 얼큰 수제비 범계점", max_reviews=30)
        >>> print(f"{store_name}의 리뷰 {len(reviews)}개 수집 완료!")
    """
    print("=" * 60)
    print("🔍 자동 검색 크롤링 시작")
    print("=" * 60)

    # 1단계: 네이버 지도에서 가게 검색
    search_result = await search_place_and_get_url(query)

    if not search_result:
        print("❌ 가게를 찾을 수 없습니다. 검색어를 다시 확인해주세요.")
        return ([], None)

    review_url, store_name = search_result

    # 2단계: 리뷰 크롤링
    print(f"\n📥 리뷰 크롤링 시작...")
    reviews = await crawl_naver_reviews(review_url, max_reviews=max_reviews)

    print("=" * 60)
    print(f"✅ 크롤링 완료: {store_name}")
    print(f"📊 수집된 리뷰: {len(reviews)}개")
    print("=" * 60)

    return (reviews, store_name)


# 이 파일을 직접 실행할 때만 작동하는 테스트 코드
if __name__ == "__main__":
    import sys

    # 사용자 입력 받기
    if len(sys.argv) > 1:
        # 명령줄 인자로 검색어 받기: python playwright_crawler.py "바람난 얼큰 수제비"
        query = " ".join(sys.argv[1:])
    else:
        # 대화형으로 검색어 입력받기
        query = input("\n🔍 검색할 가게 이름이나 주소를 입력하세요: ").strip()

    if not query:
        print("❌ 검색어를 입력하지 않았습니다.")
        sys.exit(1)

    # 자동 검색 크롤링 실행
    reviews, store_name = asyncio.run(crawl_by_search(query, max_reviews=20))

    if not reviews:
        print("❌ 리뷰 수집에 실패했습니다.")
        sys.exit(1)

    # 결과 출력 (처음 5개만 미리보기)
    print(f"\n=== 수집 결과 ({store_name}) ===")
    for i, review in enumerate(reviews[:5], 1):
        print(f"\n[리뷰 {i}]")
        print(f"내용: {review.get('text', 'N/A')[:100]}...")
        print(f"평점: {review.get('rating', 'N/A')}")
        print(f"작성일: {review.get('date', 'N/A')}")
