"""
LLM 기반 토픽별 페르소나 생성 (Upstage Solar-Pro2 모델 사용)
각 토픽마다 고유한 페르소나를 생성하여 다양한 고객 세그먼트를 파악합니다.
"""
import os
from dotenv import load_dotenv
from openai import OpenAI
import json
from typing import List, Dict, Any
import pandas as pd

load_dotenv()

# Upstage API 클라이언트 초기화
client = OpenAI(
    api_key=os.getenv("UPSTAGE_API_KEY"),
    base_url="https://api.upstage.ai/v1"
)

def calculate_avg_rating(reviews: List[Dict]) -> float:
    """
    리뷰의 평균 평점 계산
    
    Args:
        reviews: 리뷰 리스트 (rating 필드 포함)
        
    Returns:
        평균 평점 (1.0 ~ 5.0)
    """
    ratings = [r.get('rating') for r in reviews if r.get('rating') is not None]
    if not ratings:
        return 0.0
    return round(sum(ratings) / len(ratings), 1)


def generate_personas_by_topic(
    reviews: List[Dict],
    topics: Dict[int, List[str]],
    topic_counts: Dict[int, int],
    total_docs: int,
    store_name: str = "이 가게"
) -> Dict[str, Any]:
    """
    토픽별로 LLM을 통해 페르소나를 생성합니다 (GPT o1 모델 사용).
    각 토픽은 고유한 고객 세그먼트를 대표합니다.

    Args:
        reviews: 리뷰 리스트 (raw_text, rating, topic 포함)
        topics: BERTopic 결과 {topic_id: [keywords]}
        topic_counts: 토픽별 문서 수 {topic_id: count}
        total_docs: 전체 문서 수
        store_name: 가게 이름

    Returns:
        {
            'store_name': str,
            'average_rating': float,
            'total_reviews': int,
            'store_summary': str,  # 가게 전체 이미지
            'personas': [
                {
                    'topic_id': int,
                    'topic_name': str,  # 토픽 이름 (자동 생성)
                    'keywords': [str],
                    'percentage': float,
                    'review_count': int,
                    'avg_rating': float,
                    'persona': {
                        'characteristics': str,
                        'preferences': str,
                        'goals': str,
                        'pain_points': str
                    },
                    'customer_journey_map': {
                        'awareness': str,
                        'consideration': str,
                        'visit': str,
                        'post_visit': str
                    }
                }
            ]
        }
    """
    # 전체 평균 평점 계산
    avg_rating = calculate_avg_rating(reviews)
    total_reviews = len(reviews)

    # 1단계: 가게 전체 요약 생성 (모든 토픽 통합)
    print("📝 Generating store summary...")
    store_summary = _generate_store_summary(reviews, topics, store_name, avg_rating)

    # 2단계: 토픽별 페르소나 생성
    personas = []
    for topic_id in sorted(topics.keys()):
        print(f"\n🎭 Generating persona for Topic {topic_id}...")

        keywords = topics[topic_id]
        count = topic_counts[topic_id]
        percentage = round((count / total_docs) * 100, 1)

        # 해당 토픽의 리뷰만 필터링
        topic_reviews = [r for r in reviews if r.get('topic') == topic_id]
        topic_avg_rating = calculate_avg_rating(topic_reviews)

        # 토픽별 페르소나 생성
        persona_data = _generate_single_persona(
            topic_id=topic_id,
            keywords=keywords,
            reviews=topic_reviews,
            store_name=store_name,
            percentage=percentage
        )

        personas.append({
            'topic_id': topic_id,
            'topic_name': persona_data['topic_name'],
            'keywords': keywords,
            'percentage': percentage,
            'review_count': count,
            'avg_rating': topic_avg_rating,
            'persona': persona_data['persona'],
            'customer_journey_map': persona_data.get('customer_journey_map', {})
        })

        print(f"   ✅ Topic {topic_id}: {persona_data['topic_name']} ({percentage}%)")

    # 최종 결과 구성
    result = {
        'store_name': store_name,
        'average_rating': avg_rating,
        'total_reviews': total_reviews,
        'store_summary': store_summary,
        'personas': personas
    }

    return result


def _generate_store_summary(reviews: List[Dict], topics: Dict[int, List[str]], store_name: str, avg_rating: float) -> str:
    """
    가게 전체 요약 생성 (모든 토픽을 통합하여 한 문장 요약)

    Returns:
        가게 이미지 문장 (예: "매콤한 수제비가 인기인 가성비 좋은 맛집")
    """
    # 모든 키워드 수집
    all_keywords = []
    for keywords in topics.values():
        all_keywords.extend(keywords[:3])  # 상위 3개씩

    keywords_str = ", ".join(all_keywords[:10])  # 최대 10개

    # 상위 리뷰 샘플 추가 (더 풍부한 컨텍스트 제공)
    sample_reviews = []
    for r in reviews[:10]:
        text = r.get('raw_text', r.get('text', ''))[:100]
        if text:
            sample_reviews.append(f"- {text}")
    reviews_context = "\n".join(sample_reviews) if sample_reviews else "리뷰 없음"

    prompt = f"""
당신은 음식점 리뷰 분석 전문가입니다. 다음은 "{store_name}"의 분석 결과입니다.

[기본 정보]
- 평균 평점: {avg_rating}/5.0
- 주요 키워드: {keywords_str}

[실제 고객 리뷰 샘플]
{reviews_context}

위 정보를 바탕으로 이 가게의 핵심 이미지를 **한 문장**으로 요약하세요.
- 고객들이 실제로 경험한 내용을 반영하세요
- 가게의 독특한 강점이나 특징을 포함하세요
- 간결하고 매력적인 표현을 사용하세요

예시:
- "매콤한 수제비가 인기인 가성비 좋은 맛집"
- "분위기 좋은 프리미엄 수제비 전문점"
- "친절한 서비스와 푸짐한 양이 자랑인 동네 맛집"

**출력**: 한 문장만 출력하세요 (마침표 포함, JSON 없이 텍스트만).
"""

    try:
        response = client.chat.completions.create(
            model="solar-pro2",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        summary = response.choices[0].message.content.strip()
        return summary

    except Exception as e:
        print(f"   ⚠️ Error generating store summary: {e}")
        return f"{store_name} (평점 {avg_rating}/5.0)"


def _generate_single_persona(
    topic_id: int,
    keywords: List[str],
    reviews: List[Dict],
    store_name: str,
    percentage: float
) -> Dict[str, Any]:
    """
    단일 토픽에 대한 페르소나 생성

    Returns:
        {
            'topic_name': str,  # 토픽 이름
            'persona': {...},
            'customer_journey_map': {...}
        }
    """
    # 리뷰 샘플 (최대 20개로 증가, 더 풍부한 컨텍스트)
    sample_reviews = []
    for r in reviews[:20]:
        rating = r.get('rating', 'N/A')
        text = r.get('raw_text', r.get('text', ''))[:200]  # 더 긴 텍스트
        if text:
            sample_reviews.append(f"★{rating}: {text}")

    reviews_str = "\n".join(sample_reviews)
    keywords_str = ", ".join(keywords[:10])  # 키워드도 더 많이

    # 평점 분포 계산 (추가 인사이트)
    ratings = [r.get('rating') for r in reviews if r.get('rating') is not None]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0
    positive_ratio = round(len([r for r in ratings if r >= 4]) / len(ratings) * 100, 1) if ratings else 0

    prompt = f"""
당신은 음식점 고객 세그먼트 분석 전문가입니다. "{store_name}"의 특정 고객 그룹을 분석하여 상세한 페르소나를 생성해주세요.

## 📊 토픽 정보
- 토픽 ID: {topic_id}
- 핵심 키워드: {keywords_str}
- 비중: {percentage}% (전체 리뷰 중 {len(reviews)}개)
- 평균 평점: {avg_rating}/5.0
- 긍정 리뷰 비율: {positive_ratio}%

## 📝 실제 고객 리뷰 샘플
{reviews_str}

## 🎯 요청사항
위 리뷰들을 심층 분석하여 다음을 생성하세요:

1. **topic_name**: 이 고객 그룹을 대표하는 간결하고 매력적인 이름
   - 4-10글자 내외
   - 고객의 핵심 특성이 드러나도록
   - 예시: "매운맛 애호가", "가성비 헌터", "SNS 인플루언서", "단골 로컬", "특별한 날 방문객"

2. **persona**: 이 고객 그룹의 상세한 페르소나 (각 항목당 2-3문장으로 구체적으로)

   a) **characteristics** (인구통계 및 특성):
      - 추정 나이대, 직업군, 라이프스타일
      - 음식에 대한 관심도와 소비 패턴
      - 실제 리뷰 내용에서 드러나는 구체적인 특징

   b) **preferences** (선호사항):
      - 선호하는 메뉴, 맛의 특징 (짜다, 달다, 맵다 등)
      - 선호하는 분위기, 서비스 스타일
      - 중요하게 생각하는 요소 (가격, 양, 품질, 분위기 등)

   c) **goals** (방문 목적 및 기대):
      - 이 가게를 방문하는 주된 목적
      - 방문을 통해 얻고자 하는 경험
      - 재방문 의도와 추천 의향

   d) **pain_points** (불만 및 개선 필요사항):
      - 실제 리뷰에서 언급된 구체적인 불만사항
      - 개선이 필요한 부분
      - 잠재적 이탈 위험 요소

3. **customer_journey_map**: 이 페르소나의 고객 여정 지도 (각 단계별로 구체적인 행동과 감정 서술)
   - **Awareness** (인지): 가게를 알게 된 경로 (SNS, 지인 추천, 검색 등)
   - **Consideration** (고려): 방문을 결심하게 된 결정적 요인 (메뉴 사진, 리뷰, 위치 등)
   - **Visit** (방문/경험): 실제 매장에서의 경험 (대기, 주문, 식사, 분위기 등)
   - **Post-Visit** (방문 후): 방문 후 행동 (재방문 의사, 리뷰 작성, 지인 추천 등)

**중요**: 실제 리뷰 내용을 바탕으로 구체적이고 실용적인 인사이트를 제공하세요. 일반적인 내용보다는 이 가게와 고객 그룹만의 특징이 드러나야 합니다.

**출력 형식** (반드시 JSON만 출력):
{{
  "topic_name": "...",
  "persona": {{
    "characteristics": "...",
    "preferences": "...",
    "goals": "...",
    "pain_points": "..."
  }},
  "customer_journey_map": {{
    "awareness": "...",
    "consideration": "...",
    "visit": "...",
    "post_visit": "..."
  }}
}}
"""

    try:
        response = client.chat.completions.create(
            model="solar-pro2",
            messages=[
                {
                    "role": "system",
                    "content": "당신은 음식점 고객 데이터 분석 전문가입니다. 실제 리뷰 데이터를 바탕으로 정확하고 실용적인 페르소나를 생성합니다."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7
        )

        result_text = response.choices[0].message.content.strip()

        # JSON 파싱 (마크다운 코드 블록 제거)
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        persona_data = json.loads(result_text)
        return persona_data

    except Exception as e:
        print(f"   ⚠️ Error generating persona for Topic {topic_id}: {e}")
        import traceback
        traceback.print_exc()

        # Fallback
        return {
            "topic_name": f"토픽 {topic_id}",
            "persona": {
                "characteristics": "분석 실패",
                "preferences": "분석 실패",
                "goals": "분석 실패",
                "pain_points": "분석 실패"
            },
            "customer_journey_map": {
                "awareness": "분석 실패",
                "consideration": "분석 실패",
                "visit": "분석 실패",
                "post_visit": "분석 실패"
            }
        }


# 하위 호환성을 위한 Alias (기존 함수명 유지)
def generate_persona_with_ratings(
    reviews: List[Dict],
    topics: Dict[int, List[str]],
    store_name: str = "이 가게",
    topic_counts: Dict[int, int] = None,
    total_docs: int = None
) -> Dict[str, Any]:
    """
    [DEPRECATED] 하위 호환성을 위한 래퍼 함수.
    generate_personas_by_topic()를 사용하세요.
    """
    # topic_counts와 total_docs가 없으면 직접 계산
    if topic_counts is None:
        topic_counts = {}
        for r in reviews:
            topic = r.get('topic')
            if topic is not None and topic != -1:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

    if total_docs is None:
        total_docs = len([r for r in reviews if r.get('topic', -1) != -1])

    return generate_personas_by_topic(reviews, topics, topic_counts, total_docs, store_name)
