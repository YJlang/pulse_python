# 🔍 자동 검색 크롤링 가이드

네이버 플레이스 URL을 몰라도 **가게 이름이나 주소만 입력**하면 자동으로 리뷰를 수집할 수 있습니다!

## ✨ 주요 기능

- **자동 검색**: 네이버 지도에서 가게를 자동으로 찾아줍니다
- **URL 불필요**: 복잡한 URL을 찾을 필요 없이 가게 이름만 입력
- **정확한 매칭**: 플레이스 ID를 자동으로 추출하여 정확한 리뷰 수집
- **가게명 자동 추출**: 정확한 가게명을 자동으로 가져옵니다

---

## 📋 사용 방법

### 1. 통합 파이프라인 실행 (권장)

가장 간단한 방법입니다. 가게 이름만 입력하면 크롤링 → 분석 → 페르소나 생성까지 자동으로 진행됩니다.

```bash
python run_pipeline.py
```

**실행 화면:**
```
============================================================
🏪 온라인 리뷰 분석 파이프라인
============================================================

🔍 분석할 가게 이름이나 주소를 입력하세요: 바람난 얼큰 수제비 범계점
```

입력 후 자동으로:
1. 네이버 지도에서 가게 검색
2. 리뷰 크롤링 (50개)
3. BERTopic 토픽 분석
4. GPT o1 페르소나 생성

---

### 2. 리뷰만 수집하기

페르소나 생성 없이 리뷰만 빠르게 수집하고 싶을 때:

```bash
cd crawling
python playwright_crawler.py
```

**대화형 입력:**
```
🔍 검색할 가게 이름이나 주소를 입력하세요: 스타벅스 강남역점
```

**명령줄 인자 방식:**
```bash
python playwright_crawler.py "스타벅스 강남역점"
```

---

### 3. Python 코드에서 사용하기

#### 방법 A: 자동 검색 (추천)

```python
import asyncio
from crawling.playwright_crawler import crawl_by_search

async def main():
    # 가게 이름으로 자동 검색 + 크롤링
    reviews, store_name = await crawl_by_search(
        query="바람난 얼큰 수제비 범계점",
        max_reviews=50
    )

    print(f"{store_name}의 리뷰 {len(reviews)}개 수집!")

    for review in reviews[:3]:
        print(f"⭐ {review['rating']}: {review['text'][:50]}...")

asyncio.run(main())
```

#### 방법 B: URL 직접 지정 (기존 방식)

```python
import asyncio
from crawling.playwright_crawler import crawl_naver_reviews

async def main():
    # URL을 알고 있을 때
    url = "https://m.place.naver.com/restaurant/31264425/review/visitor"
    reviews = await crawl_naver_reviews(url, max_reviews=50)

    print(f"{len(reviews)}개 리뷰 수집!")

asyncio.run(main())
```

---

## 🎯 검색어 입력 팁

### ✅ 추천 검색어 형식

1. **정확한 가게명**
   ```
   바람난 얼큰 수제비 범계점
   스타벅스 강남역점
   교촌치킨 홍대점
   ```

2. **가게명 + 지역**
   ```
   수제비 맛집 범계
   카페 강남역
   ```

3. **주소**
   ```
   서울 강남구 테헤란로 123
   부산 해운대구 센텀중앙로 48
   ```

### ⚠️ 주의사항

- 너무 일반적인 검색어는 다른 가게가 검색될 수 있습니다
  - ❌ "수제비" (너무 광범위)
  - ✅ "바람난 얼큰 수제비 범계점" (정확)

- 체인점은 지점명까지 입력하세요
  - ❌ "스타벅스" (전국에 수백 개)
  - ✅ "스타벅스 강남역점" (특정 지점)

---

## 📊 출력 데이터 구조

```python
# crawl_by_search() 반환값
reviews = [
    {
        "text": "매콤하고 맛있어요!",           # 정제된 리뷰 본문 (BERTopic 분석용)
        "raw_text": "리뷰 56\n사진 164\n매콤하고 맛있어요!", # 원본 텍스트 (LLM용)
        "rating": 5,                          # 평점 (1-5)
        "date": "2024.01.15",                 # 작성일
        "source": "naver"                     # 출처
    },
    # ... 더 많은 리뷰
]

store_name = "바람난 얼큰 수제비 범계점"  # 자동 추출된 가게명
```

---

## 🔧 고급 설정

### 수집 개수 조절

```python
# 10개만 수집
reviews, store_name = await crawl_by_search("가게명", max_reviews=10)

# 100개 수집 (시간 소요)
reviews, store_name = await crawl_by_search("가게명", max_reviews=100)
```

### 검색 결과 확인

```python
from crawling.playwright_crawler import search_place_and_get_url

# 검색만 먼저 해보기
result = await search_place_and_get_url("바람난 얼큰 수제비")

if result:
    url, name = result
    print(f"찾은 가게: {name}")
    print(f"URL: {url}")
else:
    print("검색 실패")
```

---

## 🆚 기존 방식과 비교

### 기존 방식 (URL 필요)
```python
# 1. 네이버 지도에서 수동으로 가게 검색
# 2. 브라우저에서 URL 복사: https://m.place.naver.com/restaurant/31264425/...
# 3. 코드에 URL 붙여넣기

url = "https://m.place.naver.com/restaurant/31264425/review/visitor"
reviews = await crawl_naver_reviews(url, max_reviews=50)
```

### 새로운 방식 (자동 검색) ⭐
```python
# 가게 이름만 입력하면 끝!
reviews, store_name = await crawl_by_search("바람난 얼큰 수제비", max_reviews=50)
```

---

## ❓ FAQ

**Q: 검색 결과가 여러 개일 때는?**
A: 첫 번째 검색 결과를 자동으로 선택합니다. 정확한 가게명을 입력하면 원하는 가게가 상위에 나옵니다.

**Q: 가게를 못 찾으면?**
A: 검색어를 더 구체적으로 입력하거나, 주소를 함께 입력해보세요.

**Q: 크롤링 속도가 느린가요?**
A: 자동 검색 단계(약 5-10초)가 추가되지만, 수동으로 URL을 찾는 시간보다 훨씬 빠릅니다.

**Q: 카카오맵도 지원하나요?**
A: 현재는 네이버 플레이스만 자동 검색을 지원합니다. 카카오맵은 수동 URL 방식으로 사용 가능합니다.

---

## 🎉 완성 예시

```bash
$ python run_pipeline.py

============================================================
🏪 온라인 리뷰 분석 파이프라인
============================================================

🔍 분석할 가게 이름이나 주소를 입력하세요: 바람난 얼큰 수제비 범계점

============================================================
📥 Step 1-1: 네이버 자동 검색 & 리뷰 크롤링
============================================================
🔍 네이버 지도에서 '바람난 얼큰 수제비 범계점' 검색 중...
📍 가게 페이지로 이동 중...
✅ 가게 찾기 완료: 바람난 얼큰 수제비 범계점
📍 리뷰 URL: https://m.place.naver.com/restaurant/31264425/review/visitor

📥 리뷰 크롤링 시작...
현재까지 12개 리뷰 수집 (시도 1회)...
현재까지 25개 리뷰 수집 (시도 2회)...
✅ 총 50개 리뷰 수집 완료

✅ {len(naver_reviews)}개 네이버 리뷰 수집 (바람난 얼큰 수제비 범계점)

[... 이후 토픽 분석 & 페르소나 생성 진행 ...]
```

---

**💡 Tip**: 처음 사용할 때는 `python playwright_crawler.py`로 검색이 잘 되는지 먼저 테스트해보세요!
