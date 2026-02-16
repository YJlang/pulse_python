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
        # OpenAI API 키 확인
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("⚠️ [LLMService] OPENAI_API_KEY is missing. LLM features may fail.")
        
        # OpenAI 클라이언트 초기화
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4o" # 모델명 변경: solar-pro2 -> gpt-4o

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
        특정 토픽(고객군)에 대한 상세 페르소나 및 고객 여정 지도를 생성합니다.
        FE의 UnifiedInsightPage.jsx 구조와 일치해야 합니다.
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
당신은 고객 경험(CX) 분석 전문가입니다. "{store_name}"의 특정 고객 그룹(토픽 {topic_id})을 심층 분석하여 페르소나와 고객 여정 지도를 작성해주세요.

## 분석 데이터
- 키워드: {keywords_str}
- 그룹 비중: {percentage}%
- 평균 평점: {avg_rating}
- 리뷰 샘플:
{reviews_str}

## 요청사항 (JSON 포맷 준수)
다음 구조를 가진 JSON을 생성하세요. (Markdown code block 없이 순수 JSON만 출력)

{{
    "nickname": "그룹을 대표하는 매력적인 별명 (예: 시원 국물파, 가성비 직장인)",
    "tags": ["특징1", "특징2", "특징3"],
    "summary": "이 그룹의 행동 패턴과 니즈를 한 문장으로 요약",
    "journey": {{
        "explore": {{
            "label": "탐색",
            "action": "가게를 찾게 된 구체적 행동 (예: 네이버 검색, 지인 추천)",
            "thought": "방문 전 속마음",
            "type": "탐색 단계의 감정 (good, neutral, pain 중 택1)",
            "touchpoint": "접점 (예: 네이버 플레이스, 인스타그램)",
            "painPoint": "불편했던 점 (없으면 null)",
            "opportunity": "이 단계에서 우리 가게가 어필할 수 있는 기회"
        }},
        "visit": {{
            "label": "방문",
            "action": "가게 도착 및 웨이팅/입장 행동",
            "thought": "입장 시 속마음",
            "type": "방문 단계의 감정 (good, neutral, pain 중 택1)",
            "touchpoint": "매장 입구/대기석",
            "painPoint": "불편했던 점 (없으면 null)",
            "opportunity": "첫인상을 개선할 아이디어"
        }},
        "eat": {{
            "label": "식사",
            "action": "메뉴 주문 및 식사 중 행동",
            "thought": "음식을 먹으며 든 생각",
            "type": "식사 단계의 감정 (good, neutral, pain 중 택1)",
            "touchpoint": "테이블/음식",
            "painPoint": "불편했던 점 (없으면 null)",
            "opportunity": "맛/서비스 경험을 극대화할 아이디어"
        }},
        "share": {{
            "label": "공유",
            "action": "결제 및 퇴장, 후기 작성 행동",
            "thought": "나기면서 든 생각",
            "type": "공유 단계의 감정 (good, neutral, pain 중 택1)",
            "touchpoint": "카운터/SNS",
            "painPoint": "불편했던 점 (없으면 null)",
            "opportunity": "단골 유치 및 리뷰 작성을 유도할 아이디어"
        }}
    }},
    "overall_comment": "이 페르소나의 전체 여정을 분석한 총평. 긍정적인 부분과 개선이 필요한 부분을 구체적으로 언급하며, 숫자나 수치를 활용해 설득력 있게 작성 (2~3문장)",
    "action_recommendation": "가장 시급하게 개선해야 할 구체적인 액션 아이템. 현실적이고 즉시 실행 가능한 제안 (1~2문장)"
}}
"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful CX analyst. Output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            result_text = response.choices[0].message.content.strip()
            return json.loads(result_text)
            
        except Exception as e:
            logger.error(f"❌ Error generating persona for topic {topic_id}: {e}")
            # Fallback 데이터 반환
            return {
                "nickname": f"고객 그룹 {topic_id}",
                "tags": ["분석 실패"],
                "summary": "데이터를 분석하는 중 오류가 발생했습니다.",
                "journey": {
                    "explore": {"label": "탐색", "action": "-", "thought": "-", "type": "neutral", "touchpoint": "-", "opportunity": "-"},
                    "visit": {"label": "방문", "action": "-", "thought": "-", "type": "neutral", "touchpoint": "-", "opportunity": "-"},
                    "eat": {"label": "식사", "action": "-", "thought": "-", "type": "neutral", "touchpoint": "-", "opportunity": "-"},
                    "share": {"label": "공유", "action": "-", "thought": "-", "type": "neutral", "touchpoint": "-", "opportunity": "-"}
                },
                "overall_comment": "데이터 분석 중 오류가 발생하여 총평을 생성할 수 없습니다.",
                "action_recommendation": "다시 분석을 시도해주세요."
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
        
        # 2. 토픽별 페르소나 (최대 3개까지만 생성 - FE 레이아웃 고려)
        personas = []
        
        # DiceBear 시드 목록 (랜덤성 부여)
        seeds = ["happy-woman-1", "happy-man-2", "happy-woman-2", "happy-man-1", "happy-woman-3"]
        bg_colors = ["fef3c7", "d1fae5", "fce7f3", "e0f2fe", "fef9c3"]
        
        sorted_topics = sorted(topics.keys())[:3] # 상위 3개만
        
        for idx, t_id in enumerate(sorted_topics):
            count = topic_counts[t_id]
            percentage = round((count / total_docs) * 100, 1)
            
            # 해당 토픽 리뷰 필터링
            topic_reviews = [r for r in reviews if r['topic'] == t_id]
            
            # LLM으로 페르소나 및 여정 지도 생성
            p_data = self._generate_single_persona(
                t_id, topics[t_id], topic_reviews, store_name, percentage
            )
            
            # 이미지 생성 (DiceBear API)
            seed = seeds[idx % len(seeds)]
            bg = bg_colors[idx % len(bg_colors)]
            img_url = f"https://api.dicebear.com/7.x/notionists/svg?seed={seed}&backgroundColor={bg}"
            
            # 결과 매핑
            personas.append({
                "id": idx + 1, # FE에서는 1부터 시작하는 ID 사용
                "nickname": p_data.get("nickname", f"그룹 {t_id}"),
                "tags": p_data.get("tags", []),
                "img": img_url,
                "summary": p_data.get("summary", ""),
                "journey": p_data.get("journey", {})
            })
            
        return {
            "store_name": store_name,
            "average_rating": self._calculate_avg_rating(reviews),
            "total_reviews": total_docs,
            "store_summary": store_summary,
            "personas": personas
        }

    def chat_completion(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        """
        일반적인 대화형 응답을 생성합니다. (챗봇 기능 등)
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"❌ Error during chat completion: {e}")
            return "죄송합니다. 오류가 발생하여 응답을 생성할 수 없습니다."

    def generate_review_reply(self, review_text: str, tone: str = "친근함", length: str = "보통") -> str:
        """
        리뷰에 대한 답글을 생성합니다.
        """
        prompt = f"""
당신은 사장님을 대신해 고객 리뷰에 답글을 다는 AI 비서입니다.
다음 리뷰에 대해 **{tone}** 말투로, **{length}** 길이의 답글을 작성해주세요.

[고객 리뷰]
{review_text}

[답글 작성 가이드]
1. 고객의 칭찬 포인트에 감사함을 표현하세요.
2. 불만 사항이 있다면 정중히 사과하고 개선을 약속하세요.
3. 재방문을 유도하는 따뜻한 멘트로 마무리하세요.
"""
        return self.chat_completion([{"role": "user", "content": prompt}])
