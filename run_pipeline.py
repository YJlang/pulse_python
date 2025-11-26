"""
통합 파이프라인: 멀티플랫폼 크롤링 (네이버 + 카카오) → BERTopic 분석 → LLM 페르소나 생성

사용자가 가게 이름이나 주소만 입력하면 자동으로 검색하여 리뷰를 수집합니다.
네이버와 카카오맵 모두 검색 결과가 여러 개일 경우 인터랙티브하게 선택할 수 있습니다.
"""
import asyncio
import json
import sys

# 사용자 입력을 먼저 받기 (라이브러리 로딩 전)
print("=" * 60)
print("🏪 온라인 리뷰 분석 파이프라인 (네이버 + 카카오)")
print("=" * 60)

query = input("\n🔍 분석할 가게 이름이나 주소를 입력하세요: ").strip()

if not query:
    print("❌ 검색어를 입력하지 않았습니다.")
    sys.exit(1)

# 사용자 입력 받은 후에 라이브러리 로딩 시작
print("\n⏳ 분석 라이브러리 로딩 중... (최초 실행 시 1-2분 소요)")
print("   Tip: 다음 실행부터는 훨씬 빠릅니다!")

from crawling.playwright_crawler import crawl_by_search, crawl_naver_reviews, search_place_and_get_url as search_naver
from crawling.kakao_crawler import crawl_kakao_reviews, search_place_and_get_url as search_kakao
from analysis.topic_model import run_topic_model
from llm.persona_generator import generate_persona_with_ratings

print("✅ 라이브러리 로딩 완료!\n")


async def main():
    # 1단계: 네이버 검색 및 크롤링
    print("=" * 60)
    print("📥 Step 1: 네이버(Naver) 검색 및 크롤링")
    print("=" * 60)
    
    naver_url = None
    store_name = query # 기본값
    
    # 네이버 검색 (인터랙티브 선택 포함)
    search_result = await search_naver(query)
    if search_result:
        naver_url, found_name = search_result
        store_name = found_name # 네이버에서 찾은 이름으로 업데이트
        
        # 네이버 리뷰 크롤링
        print(f"\n🚀 네이버 리뷰 수집 시작: {store_name}")
        naver_reviews = await crawl_naver_reviews(naver_url, max_reviews=50)
        print(f"✅ {len(naver_reviews)}개 네이버 리뷰 수집 완료")
    else:
        print("⚠️ 네이버에서 가게를 찾지 못했습니다.")
        naver_reviews = []

    # 2단계: 카카오맵 검색 및 크롤링
    print("\n" + "=" * 60)
    print("📥 Step 2: 카카오맵(Kakao) 검색 및 크롤링")
    print("=" * 60)
    
    kakao_url = await search_kakao(query)
    
    if kakao_url:
        # 카카오 리뷰 크롤링
        print(f"\n🚀 카카오맵 리뷰 수집 시작")
        kakao_reviews = await crawl_kakao_reviews(kakao_url, max_reviews=50)
        print(f"✅ {len(kakao_reviews)}개 카카오 리뷰 수집 완료")
    else:
        print("⚠️ 카카오맵에서 가게를 찾지 못했습니다.")
        kakao_reviews = []

    # 리뷰 통합
    all_reviews = naver_reviews + kakao_reviews
    print(f"\n📊 총 {len(all_reviews)}개 리뷰 (네이버: {len(naver_reviews)}, 카카오: {len(kakao_reviews)})\n")
    
    if not all_reviews:
        print("❌ 수집된 리뷰가 없습니다. 프로그램을 종료합니다.")
        return

    # 3단계: BERTopic 토픽 분석
    print("=" * 60)
    print("🤖 Step 3: BERTopic 토픽 분석")
    print("=" * 60)
    result = run_topic_model(all_reviews, n_topics=5, output_dir="./output")

    # 4단계: LLM 토픽별 페르소나 생성
    print("\n" + "=" * 60)
    print("🧠 Step 4: 토픽별 페르소나 생성 (Solar Pro2)")
    print("=" * 60)

    reviews_with_topics = result.get('reviews_with_topics', all_reviews)

    persona_result = generate_persona_with_ratings(
        reviews=reviews_with_topics,
        topics=result['topics'],
        topic_counts=result['topic_counts'],
        total_docs=result['docs_count'],
        store_name=store_name
    )

    # 페르소나 저장
    with open("./output/persona.json", "w", encoding="utf-8") as f:
        json.dump(persona_result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 페르소나 생성 완료!")
    print(f"📍 가게: {persona_result['store_name']}")
    print(f"⭐ 평균 평점: {persona_result['average_rating']}/5.0")
    print(f"💬 총 리뷰: {persona_result['total_reviews']}개")
    print(f"🏪 가게 이미지: {persona_result['store_summary']}")
    print(f"\n🎭 생성된 페르소나: {len(persona_result['personas'])}개")

    for p in persona_result['personas']:
        print(f"\n   [{p['topic_id']}] {p['topic_name']}")
        print(f"       📊 비중: {p['percentage']}% ({p['review_count']}개)")
        print(f"       ⭐ 평점: {p['avg_rating']}/5.0")
        print(f"       🔑 키워드: {', '.join(p['keywords'][:3])}")
        print(f"       👤 특성: {p['persona']['characteristics'][:50]}...")

        # CJM 정보 출력
        if 'customer_journey_map' in p and p['customer_journey_map']:
            cjm = p['customer_journey_map']
            print(f"       🗺️  고객여정지도:")
            if cjm.get('awareness'):
                print(f"          - 인지: {cjm['awareness'][:50]}...")
            if cjm.get('consideration'):
                print(f"          - 고려: {cjm['consideration'][:50]}...")
            if cjm.get('visit'):
                print(f"          - 방문: {cjm['visit'][:50]}...")
            if cjm.get('post_visit'):
                print(f"          - 방문 후: {cjm['post_visit'][:50]}...")

    # 5단계: 결과 출력
    print("\n" + "=" * 60)
    print("📊 Step 5: 분석 결과 요약")
    print("=" * 60)

    if "error" not in result:
        print(f"\n📈 전체 문서 수: {result['docs_count']}")
        print(f"📈 아웃라이어: {result['outliers_count']}")
        print(f"📑 토픽 수: {len(result['topics'])}\n")

        print("🔑 토픽별 키워드:")
        print("-" * 60)
        for topic_id in sorted(result['topics'].keys()):
            keywords = result['topics'][topic_id]
            count = result['topic_counts'][topic_id]
            pct = count / result['docs_count'] * 100
            print(f"  🏷️  Topic {topic_id} ({count}개, {pct:.1f}%): {', '.join(keywords)}")

    print("\n📁 생성된 파일:")
    print("-" * 60)
    print(f"  ✅ {result['files'].get('summary', 'N/A')}")
    print(f"  ✅ {result['files'].get('details', 'N/A')}")
    print(f"  ✅ ./output/persona.json")

    print("\n" + "=" * 60)
    print("✅ 전체 파이프라인 완료!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
