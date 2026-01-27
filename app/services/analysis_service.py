"""
BERTopic 기반 리뷰 분석 및 토픽 모델링 서비스
"""
from typing import List, Dict, Any
from collections import Counter
import torch
from kiwipiepy import Kiwi
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from app.utils.logger import get_logger

logger = get_logger(__name__)

class AnalysisService:
    """
    NLP 분석 및 토픽 모델링을 담당하는 서비스입니다.
    모델 로딩 시간을 줄이기 위해 싱글톤 패턴과 유사하게 인스턴스를 관리합니다.
    """
    
    _instance = None
    
    # 불용어 리스트
    STOPWORDS = {
        '리뷰', '사진', '팔로우', '팔로워', '방문', '예약', '이용', '대기', '시간',
        '입장', '반응', '인증', '수단', '영수증', '결제', '내역',
        '일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일',
        '년', '월', '일', '번째', '저녁', '점심', '아침', '오전', '오후',
        '일상', '친목', '데이트', '나들이', '혼자', '친구', '가족', '연인', '배우자', '아이', '동료',
        '개', '곳', '더', '있다', '있습니다', '없다', '하다', '합니다', '이다', '입니다',
        '것', '거', '수', '등', '때', '및', '위해', '통해', '하나', '가지',
        '인원', '선택', '키워드', '조회', '업체', '장소', '테마', '리스트'
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AnalysisService, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def initialize(self):
        """
        모델을 메모리에 미리 로드합니다. (App Startup 시 호출 권장)
        """
        if self.initialized:
            return

        logger.info("⏳ [AnalysisService] Loading NLP models... (This may take a while)")
        
        # 1. Kiwi 형태소 분석기 로드
        self.kiwi = Kiwi()
        logger.info("   ✅ Kiwi loaded")
        
        # 2. 임베딩 모델 로드 (GPU 확인)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"   Using device: {device}")
        self.embedding_model = SentenceTransformer("jhgan/ko-sbert-nli", device=device)
        logger.info("   ✅ Embedding model loaded")
        
        self.initialized = True
        logger.info("✅ [AnalysisService] Initialization complete")

    def _preprocess(self, text: str) -> List[str]:
        """
        텍스트에서 명사만 추출하고 불용어를 제거합니다.
        """
        tokens = self.kiwi.tokenize(text)
        results = []
        for token in tokens:
            if token.tag in ['NNG', 'NNP']:
                word = token.form
                if len(word) > 1 and word not in self.STOPWORDS:
                    results.append(word)
        return results

    def run_analysis(self, reviews: List[Dict], n_topics: int = None) -> Dict[str, Any]:
        """
        리뷰 리스트를 받아 토픽 모델링을 수행합니다.
        
        Returns:
            {
                'topics': {topic_id: [keyword1, keyword2...]},
                'topic_counts': {topic_id: count},
                'reviews_with_topics': [review_dict_with_topic_id],
                'docs_count': int
            }
        """
        if not reviews:
            return {"error": "리뷰 데이터가 없습니다."}

        if not self.initialized:
            self.initialize()

        logger.info(f"📊 Analyzing {len(reviews)} reviews...")

        # 1. 전처리
        processed_docs = []
        valid_reviews = []
        
        for r in reviews:
            text = r.get('text', r.get('raw_text', ''))
            tokens = self._preprocess(text)
            if tokens:
                processed_docs.append(' '.join(tokens))
                # 원본 리뷰에 토큰 정보 추가 (나중에 키워드 추출용)
                r['tokens'] = tokens
                valid_reviews.append(r)
        
        if not processed_docs:
            return {"error": "전처리 후 유효한 데이터가 없습니다."}

        # 2. 토픽 모델링 (BERTopic)
        # HDBSCAN 설치 여부 확인
        try:
            import hdbscan
            has_hdbscan = True
        except ImportError:
            has_hdbscan = False

        # 모델 설정
        if n_topics or not has_hdbscan:
            # 토픽 수 지정 또는 KMeans 사용 시
            n_clusters = n_topics if n_topics else max(3, min(len(processed_docs) // 10, 10))
            cluster_model = KMeans(n_clusters=n_clusters, random_state=42)
            topic_model = BERTopic(
                embedding_model=self.embedding_model,
                hdbscan_model=cluster_model,
                verbose=False,
                min_topic_size=3
            )
        else:
            # HDBSCAN 자동 클러스터링
            topic_model = BERTopic(
                embedding_model=self.embedding_model,
                verbose=False,
                min_topic_size=3
            )

        topics, _ = topic_model.fit_transform(processed_docs)
        
        # 3. 토픽 정보 매핑 및 키워드 추출
        topic_counts = Counter(topics)
        keywords_map = {}
        
        # 각 리뷰에 토픽 ID 할당
        for i, review in enumerate(valid_reviews):
            review['topic'] = int(topics[i])

        # 토픽별 키워드 추출 (단순 빈도 기반)
        # BERTopic 내장 함수 get_topic()을 써도 되지만, 커스텀 로직(명사만)이 더 정확할 수 있음
        unique_topics = set(topics)
        if -1 in unique_topics: unique_topics.remove(-1) # 아웃라이어 제외
        
        for t_id in unique_topics:
            # 해당 토픽의 모든 토큰 수집
            all_tokens = []
            for r in valid_reviews:
                if r['topic'] == t_id:
                    all_tokens.extend(r['tokens'])
            
            # 상위 5개 키워드
            top_5 = [word for word, count in Counter(all_tokens).most_common(5)]
            keywords_map[int(t_id)] = top_5

        logger.info(f"✅ Analysis done. Found {len(unique_topics)} topics.")
        
        return {
            "topics": keywords_map,
            "topic_counts": dict(topic_counts),
            "reviews_with_topics": valid_reviews,
            "docs_count": len(processed_docs)
        }
