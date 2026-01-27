"""
LLM 기반 페르소나 및 요약 생성 서비스
"""
import os
import json
from typing import List, Dict, Any
from dotenv import load_dotenv
from openai import OpenAI
from app.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

class LLMService:
    """
    LLM (Large Language Model)을 사용하여 분석 결과로부터
    의미 있는 텍스트(페르소나, 요약 등)를 생성하는 서비스입니다.
    """

    def __init__(self):
        # Upstage API 키 확인
        api_key = os.getenv("UPSTAGE_API_KEY")
        if not api_key:
            logger.warning("⚠️ [LLMService] UPSTAGE_API_KEY is missing. LLM features may fail.")
        
        # OpenAI 클라이언트 초기화 (Upstage Endpoint 사용)
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.upstage.ai/v1"
        )
        self.model = "solar-pro2" # 모델명 고정

    def _calculate_avg_rating(self, reviews: List[Dict]) -> float:
        ratings = [r.get('rating') for r in reviews if r.get('rating') is not None]
        if not ratings: return 0.0
        return round(sum(ratings) / len(ratings), 1)

    def generate_store_summary(self, reviews: List[Dict], topics: Dict[int, List[str]], store_name: str) -> str:
        """
        가게 전체를 아우르는 한 줄 요약을 생성합니다.
        """
        avg_rating = self._calculate_avg_rating(reviews)
        
        # 모든 키워드 합치기
        all_keywords = []
        for kws in topics.values():
            all_keywords.extend(kws[:3])
        keywords_str = ", ".join(all_keywords[:10])

        # 리뷰 샘플링
        sample_texts = []
        for r in reviews[:10]:
            t = r.get('text', r.get('raw_text', ''))[:100]
            if t: sample_texts.append(f"- {t}")
        reviews_context = "\n".join(sample_texts)

        prompt = f"""
당신은 음식점 리뷰 분석 전문가입니다. 다음은 "{store_name}"의 분석 결과입니다.

[기본 정보]
- 평균 평점: {avg_rating}/5.0
- 주요 키워드: {keywords_str}

[실제 고객 리뷰]
{reviews_context}

위 정보를 바탕으로 이 가게의 핵심 이미지를 **한 문장**으로 매력적으로 요약하세요.
(예: "매콤한 수제비가 인기인 가성비 좋은 맛집")
JSON 없이 텍스트만 출력하세요.
"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"❌ Error generating summary: {e}")
            return f"{store_name} (평점 {avg_rating})"

    def _generate_single_persona(self, topic_id: int, keywords: List[str], reviews: List[Dict], store_name: str, percentage: float) -> Dict[str, Any]:
        """
        특정 토픽(고객군)에 대한 상세 페르소나를 생성합니다.
        """
        # 리뷰 샘플링
        samples = []
        for r in reviews[:20]:
            rating = r.get('rating', 'N/A')
            text = r.get('text', r.get('raw_text', ''))[:200]
            if text: samples.append(f"★{rating}: {text}")
        reviews_str = "\n".join(samples)
        
        keywords_str = ", ".join(keywords[:10])
        avg_rating = self._calculate_avg_rating(reviews)

        prompt = f"""
당신은 고객 분석 전문가입니다. "{store_name}"의 특정 고객 그룹(토픽 {topic_id})을 분석해주세요.

## 분석 데이터
- 키워드: {keywords_str}
- 비중: {percentage}%
- 평균 평점: {avg_rating}
- 리뷰 샘플:
{reviews_str}

## 요청사항 (JSON 포맷 준수)
다음 정보를 포함하는 JSON을 생성하세요:
1. topic_name: 그룹을 대표하는 이름 (예: 매운맛 매니아)
2. persona: {{ characteristics, preferences, goals, pain_points }} (각 2문장 내외)
3. customer_journey_map: {{ awareness, consideration, visit, post_visit }} (각 단계 행동)

**반드시 JSON만 출력하세요.**
"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful data analyst. Output only JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            result_text = response.choices[0].message.content.strip()
            
            # 마크다운 코드 블록 제거
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            
            return json.loads(result_text.strip())
            
        except Exception as e:
            logger.error(f"❌ Error generating persona for topic {topic_id}: {e}")
            return {
                "topic_name": f"그룹 {topic_id}",
                "persona": {},
                "customer_journey_map": {}
            }

    def generate_full_report(self, store_name: str, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        분석 결과를 종합하여 최종 페르소나 리포트를 생성합니다.
        """
        reviews = analysis_result['reviews_with_topics']
        topics = analysis_result['topics']
        topic_counts = analysis_result['topic_counts']
        total_docs = analysis_result['docs_count']
        
        # 1. 가게 요약
        store_summary = self.generate_store_summary(reviews, topics, store_name)
        
        # 2. 토픽별 페르소나
        personas = []
        for t_id in sorted(topics.keys()):
            count = topic_counts[t_id]
            percentage = round((count / total_docs) * 100, 1)
            
            # 해당 토픽 리뷰 필터링
            topic_reviews = [r for r in reviews if r['topic'] == t_id]
            topic_avg = self._calculate_avg_rating(topic_reviews)
            
            p_data = self._generate_single_persona(
                t_id, topics[t_id], topic_reviews, store_name, percentage
            )
            
            personas.append({
                "topic_id": t_id,
                "topic_name": p_data.get("topic_name", f"Topic {t_id}"),
                "keywords": topics[t_id],
                "percentage": percentage,
                "review_count": count,
                "avg_rating": topic_avg,
                "persona": p_data.get("persona", {}),
                "customer_journey_map": p_data.get("customer_journey_map", {})
            })
            
        return {
            "store_name": store_name,
            "average_rating": self._calculate_avg_rating(reviews),
            "total_reviews": total_docs,
            "store_summary": store_summary,
            "personas": personas
        }
