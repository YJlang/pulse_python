"""
통합 파이프라인: 멀티플랫폼 크롤링 (네이버 + 카카오) → BERTopic 분석 → LLM 페르소나 생성
"""
import asyncio
import json
from crawling.playwright_crawler import crawl_naver_reviews
from crawling.kakao_crawler import crawl_kakao_reviews
from analysis.topic_model import run_topic_model
from llm.persona_generator import generate_persona_with_ratings

async def main():
    naver_url = "https://m.place.naver.com/restaurant/31264425/review/visitor"
    kakao_url = "https://place.map.kakao.com/1799462452#review"  # 카카오맵 URL 설정
    
    # 1단계: 네이버 방문자 리뷰 크롤링
    print("=" * 60)
    print("📥 Step 1-1: 네이버 방문자 리뷰 크롤링")
    print("=" * 60)
    naver_reviews = await crawl_naver_reviews(naver_url, max_reviews=50)
    print(f"\n✅ {len(naver_reviews)}개 네이버 리뷰 수집\n")
    
    # 1단계-2: 카카오맵 리뷰 크롤링 (선택)
    kakao_reviews = []
    if kakao_url:
        print("=" * 60)
        print("📍 Step 1-2: 카카오맵 리뷰 크롤링")
        print("=" * 60)
        kakao_reviews = await crawl_kakao_reviews(kakao_url, max_reviews=50)
        print(f"\n✅ {len(kakao_reviews)}개 카카오 리뷰 수집\n")
    
    # 리뷰 통합
    all_reviews = naver_reviews + kakao_reviews
    print(f"📊 총 {len(all_reviews)}개 리뷰 (네이버: {len(naver_reviews)}, 카카오: {len(kakao_reviews)})\n")
    
    if not all_reviews:
        print("❌ 리뷰가 없습니다. 종료합니다.")
        return
    
    # 2단계: BERTopic 토픽 분석 (cleaned text 사용)
    print("=" * 60)
    print("🤖 Step 2: BERTopic 토픽 분석 (CUDA)")
    print("=" * 60)
    result = run_topic_model(all_reviews, n_topics=5, output_dir="./output")
    
    # 3단계: LLM 토픽별 페르소나 생성 (GPT o1 모델 사용)
    print("\n" + "=" * 60)
    print("🧠 Step 3: 토픽별 페르소나 생성 (GPT o1)")
    print("=" * 60)

    # 토픽 정보가 추가된 리뷰 사용
    reviews_with_topics = result.get('reviews_with_topics', all_reviews)

    persona_result = generate_persona_with_ratings(
        reviews=reviews_with_topics,
        topics=result['topics'],
        topic_counts=result['topic_counts'],
        total_docs=result['docs_count'],
        store_name="바람난 얼큰 수제비 범계점"
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
    
    # 4단계: 결과 출력
    print("\n" + "=" * 60)
    print("📊 Step 4: 분석 결과 요약")
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
