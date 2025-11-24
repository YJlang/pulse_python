"""
간단한 크롤링 테스트 스크립트

BERTopic이나 LLM 없이 크롤링만 빠르게 테스트할 수 있습니다.
"""
import asyncio
import json
from crawling.playwright_crawler import crawl_by_search

async def main():
    print("=" * 60)
    print("🔍 네이버 리뷰 크롤링 테스트")
    print("=" * 60)

    query = input("\n검색할 가게 이름이나 주소를 입력하세요: ").strip()

    if not query:
        print("❌ 검색어를 입력하지 않았습니다.")
        return

    # 자동 검색 + 크롤링
    reviews, store_name = await crawl_by_search(query, max_reviews=20)

    if not store_name:
        print("❌ 가게를 찾을 수 없습니다.")
        return

    # 결과 저장
    result = {
        "store_name": store_name,
        "total_reviews": len(reviews),
        "reviews": reviews
    }

    with open("./output/crawl_test.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 미리보기 출력
    print(f"\n{'=' * 60}")
    print(f"✅ 크롤링 완료: {store_name}")
    print(f"📊 수집된 리뷰: {len(reviews)}개")
    print(f"{'=' * 60}")

    print("\n📝 리뷰 미리보기 (처음 5개):")
    print("-" * 60)
    for i, review in enumerate(reviews[:5], 1):
        print(f"\n[리뷰 {i}]")
        print(f"⭐ 평점: {review.get('rating', 'N/A')}/5")
        print(f"📅 작성일: {review.get('date', 'N/A')}")
        print(f"💬 내용: {review.get('text', 'N/A')[:100]}...")

    print(f"\n📁 저장된 파일: ./output/crawl_test.json")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
