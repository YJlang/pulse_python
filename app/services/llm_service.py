"""
LLM 기반 페르소나 및 요약 생성 서비스
"""
import os
import json
import re
from collections import Counter
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

    @staticmethod
    def _extract_fallback_keywords(reviews: List[Dict], limit: int = 8) -> List[str]:
        """
        토픽 모델이 실패했을 때 리뷰 본문에서 자주 등장한 단어를 간이 키워드로 사용합니다.
        """
        stopwords = {
            "스타벅스", "강남교보타워", "강남교보타워r점", "정말", "너무", "진짜",
            "그리고", "그냥", "항상", "이번", "다음", "방문", "매장", "가게",
            "주문", "메뉴", "음료", "커피", "디저트", "고객", "분위기"
        }
        counter = Counter()

        for review in reviews:
            text = review.get("text") or review.get("raw_text") or ""
            for token in re.findall(r"[가-힣A-Za-z]{2,}", text):
                normalized = token.lower()
                if normalized in stopwords:
                    continue
                counter[normalized] += 1

        return [token for token, _ in counter.most_common(limit)]

    def _build_fallback_persona_groups(self, reviews: List[Dict]) -> List[Dict[str, Any]]:
        """
        토픽 모델 결과가 부족할 때 리뷰 내용을 3개의 대표 그룹으로 재구성합니다.
        FE는 항상 top3 페르소나를 기대하므로, 그룹 수가 부족하면 분할/패딩합니다.
        """
        theme_specs = [
            {
                "seed": "hangover",
                "default_keywords": ["맛", "시그니처", "디저트"],
                "match_tokens": ["맛", "디저트", "케이크", "샌드위치", "커피", "라떼", "음료", "에스프레소"],
            },
            {
                "seed": "worker",
                "default_keywords": ["쿠폰", "가성비", "빠른 픽업"],
                "match_tokens": ["쿠폰", "픽업", "빠른", "가성비", "할인", "이벤트", "출근", "주문"],
            },
            {
                "seed": "couple",
                "default_keywords": ["좌석", "분위기", "친절"],
                "match_tokens": ["좌석", "자리", "매장", "친절", "분위기", "조용", "편안", "공간"],
            },
        ]

        grouped_reviews = [[] for _ in theme_specs]

        for index, review in enumerate(reviews):
            text = (review.get("text") or review.get("raw_text") or "").lower()
            scores = [
                sum(1 for token in spec["match_tokens"] if token in text)
                for spec in theme_specs
            ]

            if max(scores) == 0:
                target_index = index % len(theme_specs)
            else:
                target_index = scores.index(max(scores))

            grouped_reviews[target_index].append(review)

        # 비어 있는 그룹은 전체 리뷰를 순환 배분해 항상 3개를 채웁니다.
        for index, group in enumerate(grouped_reviews):
            if group:
                continue

            fallback_review = reviews[index % len(reviews)]
            group.append(fallback_review)

        groups = []
        for index, spec in enumerate(theme_specs):
            group_reviews = grouped_reviews[index]
            extracted_keywords = self._extract_fallback_keywords(group_reviews, limit=5)
            merged_keywords = []

            for keyword in spec["default_keywords"] + extracted_keywords:
                if keyword and keyword not in merged_keywords:
                    merged_keywords.append(keyword)

            groups.append({
                "topic_id": -(index + 1),
                "reviews": group_reviews,
                "keywords": merged_keywords[:8],
                "percentage": round((len(group_reviews) / max(len(reviews), 1)) * 100, 1),
                "seed": spec["seed"],
            })

        return groups

    @staticmethod
    def _build_persona_image(seed: str) -> str:
        """
        프론트 mock 데이터와 동일한 DiceBear Adventurer 스타일을 사용합니다.
        """
        return f"https://api.dicebear.com/7.x/adventurer/svg?seed={seed}"

    def _map_persona_response(
        self,
        persona_index: int,
        p_data: Dict[str, Any],
        fallback_keywords: List[str],
        seed: str,
        fallback_nickname: str,
    ) -> Dict[str, Any]:
        return {
            "id": persona_index,
            "nickname": p_data.get("nickname", fallback_nickname),
            "tags": p_data.get("tags") or fallback_keywords[:3],
            "img": self._build_persona_image(seed),
            "summary": p_data.get("summary", ""),
            "journey": p_data.get("journey", {}),
            "overall_comment": p_data.get("overall_comment"),
            "action_recommendation": p_data.get("action_recommendation")
        }

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
        
        sorted_topics = sorted(topics.keys())[:3] # 상위 3개만

        for t_id in sorted_topics:
            count = topic_counts[t_id]
            percentage = round((count / total_docs) * 100, 1)
            
            # 해당 토픽 리뷰 필터링
            topic_reviews = [r for r in reviews if r['topic'] == t_id]
            
            # LLM으로 페르소나 및 여정 지도 생성
            p_data = self._generate_single_persona(
                t_id, topics[t_id], topic_reviews, store_name, percentage
            )

            personas.append(
                self._map_persona_response(
                    len(personas) + 1,
                    p_data,
                    topics[t_id],
                    f"topic-{len(personas) + 1}",
                    f"대표 고객 그룹 {len(personas) + 1}",
                )
            )

        if len(personas) < 3 and reviews:
            fallback_groups = self._build_fallback_persona_groups(reviews)
            for group in fallback_groups:
                if len(personas) >= 3:
                    break

                p_data = self._generate_single_persona(
                    group["topic_id"],
                    group["keywords"],
                    group["reviews"],
                    store_name,
                    group["percentage"],
                )
                personas.append(
                    self._map_persona_response(
                        len(personas) + 1,
                        p_data,
                        group["keywords"],
                        group["seed"],
                        f"대표 고객 그룹 {len(personas) + 1}",
                    )
                )
            
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

    @staticmethod
    def _find_matching_exception_cases(review_text: str, exception_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        lowered = (review_text or "").lower()
        matches = []
        for exception_case in exception_cases or []:
            if not exception_case.get("enabled"):
                continue
            keywords = exception_case.get("keywords") or []
            if any((keyword or "").lower() in lowered for keyword in keywords):
                matches.append(exception_case)
        return matches

    def generate_review_reply(
        self,
        review_text: str,
        tone: str = "친근함",
        length: str = "보통",
        settings: Dict[str, Any] | None = None,
    ) -> str:
        """
        리뷰에 대한 답글을 생성합니다.
        """
        settings = settings or {}
        matched_cases = self._find_matching_exception_cases(
            review_text,
            settings.get("exceptionCases") or [],
        )

        exception_case_guide = "\n".join(
            [
                f"- 유형: {case.get('type')}\n  공감: {case.get('empathy')}\n  사과: {case.get('apology')}\n  해결: {case.get('solution')}"
                for case in matched_cases
            ]
        ) or "- 해당 없음"

        prompt = f"""
당신은 사장님을 대신해 고객 리뷰에 답글을 다는 AI 비서입니다.
다음 리뷰에 대해 **{tone}** 말투로, **{length}** 길이의 답글을 작성해주세요.

[고객 리뷰]
{review_text}

[답글 설정]
- 감사 인사 포함: {"예" if settings.get("includeThanks", True) else "아니오"}
- '좋은 하루 보내세요' 포함: {"예" if settings.get("includeGreatDay", True) else "아니오"}
- 이모지 사용: {"예" if settings.get("useEmojis", False) else "아니오"}
- 브랜드 프리셋: {settings.get("brandPreset") or "없음"}
- 추가 요청: {settings.get("optionalInstruction") or "없음"}

[예외 케이스 가이드]
{exception_case_guide}

[답글 작성 가이드]
1. 고객의 칭찬 포인트에 감사함을 표현하세요.
2. 불만 사항이 있다면 정중히 사과하고 개선을 약속하세요.
3. 재방문을 유도하는 따뜻한 멘트로 마무리하세요.
"""
        return self.chat_completion([{"role": "user", "content": prompt}])

    def generate_review_replies(self, shop_name: str, reviews: List[Dict[str, Any]], settings: Dict[str, Any]) -> List[Dict[str, Any]]:
        replies = []

        for index, review in enumerate(reviews):
            review_text = review.get("text") or review.get("raw_text") or ""
            if review.get("has_photo") and settings.get("photoThanks", True):
                review_text = f"{review_text}\n\n[참고] 이 리뷰는 사진이 포함된 리뷰입니다."

            content = self.generate_review_reply(
                review_text=review_text,
                tone=settings.get("tone", "친근함"),
                length=settings.get("length", "보통"),
                settings=settings,
            )

            replies.append({
                "id": f"reply-{review.get('id')}",
                "review_id": review.get("id"),
                "content": content,
                "is_recommended": index == 0,
            })

        return replies
