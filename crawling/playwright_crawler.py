"""
네이버 리뷰 크롤러 (Playwright 사용)
네이버 플레이스/지도에서 리뷰를 자동으로 수집하는 프로그램입니다.
"""
import asyncio
from playwright.async_api import async_playwright
from typing import List, Dict
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


# 이 파일을 직접 실행할 때만 작동하는 테스트 코드
if __name__ == "__main__":
    # 테스트용 URL 설정 (실제 네이버 플레이스 리뷰 페이지)
    test_url = "https://m.place.naver.com/restaurant/31264425/review/visitor"

    # 크롤링 실행 (최대 20개)
    result = asyncio.run(crawl_naver_reviews(test_url, max_reviews=20))

    # 결과 출력 (처음 5개만 미리보기)
    print(f"\n=== 수집 결과 ===")
    for i, review in enumerate(result[:5], 1):
        print(f"\n[리뷰 {i}]")
        print(f"내용: {review.get('text', 'N/A')[:100]}...")
        print(f"평점: {review.get('rating', 'N/A')}")
        print(f"작성일: {review.get('date', 'N/A')}")
