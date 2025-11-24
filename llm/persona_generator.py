"""
LLM 기반 토픽별 페르소나 생성 (GPT o1 모델 사용)
각 토픽마다 고유한 페르소나를 생성하여 다양한 고객 세그먼트를 파악합니다.
"""
import os
from dotenv import load_dotenv
import openai
import json
from typing import List, Dict, Any
import pandas as pd

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

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
            'persona': persona_data['persona']
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

    prompt = f"""
다음은 "{store_name}"의 분석 결과입니다.

- 평균 평점: {avg_rating}/5.0
- 주요 키워드: {keywords_str}

위 정보를 바탕으로 이 가게의 핵심 이미지를 **한 문장**으로 요약하세요.
- 예시: "매콤한 수제비가 인기인 가성비 좋은 맛집"
- 예시: "분위기 좋은 프리미엄 수제비 전문점"

**출력**: 한 문장만 출력하세요 (마침표 포함, JSON 없이 텍스트만).
"""

    try:
        response = openai.chat.completions.create(
            model="o1",  # GPT o1 모델
            messages=[
                {"role": "user", "content": prompt}
            ]
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
            'persona': {...}
        }
    """
    # 리뷰 샘플 (최대 15개)
    sample_reviews = []
    for r in reviews[:15]:
        rating = r.get('rating', 'N/A')
        text = r.get('raw_text', r.get('text', ''))[:150]
        sample_reviews.append(f"★{rating}: {text}")

    reviews_str = "\n".join(sample_reviews)
    keywords_str = ", ".join(keywords)

    prompt = f"""
당신은 고객 세그먼트 분석 전문가입니다. 다음 토픽에 속한 리뷰들을 분석하여 페르소나를 생성하세요.

### 토픽 정보
- 토픽 ID: {topic_id}
- 키워드: {keywords_str}
- 비중: {percentage}% (전체 리뷰 중)

### 리뷰 샘플
{reviews_str}

### 요청사항
1. **topic_name**: 이 토픽을 대표하는 간결한 이름 (4-8글자, 예: "매운맛 애호가", "가성비 중시형")
2. **persona**: Market-Compass 논문 Table 5 형식으로 페르소나 생성
   - characteristics: 나이대, 직업, 생활 패턴 등
   - preferences: 이 토픽 고객이 선호하는 메뉴, 맛, 분위기
   - goals: 방문 목적, 기대하는 경험
   - pain_points: 불만 사항, 개선 필요 사항

**출력 형식** (JSON만):
{{
  "topic_name": "...",
  "persona": {{
    "characteristics": "...",
    "preferences": "...",
    "goals": "...",
    "pain_points": "..."
  }}
}}
"""

    try:
        response = openai.chat.completions.create(
            model="o1",  # GPT o1 모델
            messages=[
                {"role": "user", "content": prompt}
            ]
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
