from typing import List, Dict, Any
import pandas as pd
from kiwipiepy import Kiwi
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from collections import Counter
import os
import torch

# Kiwi 형태소 분석기 초기화 (한국어 자연어 처리용)
kiwi = Kiwi()

# 불용어 리스트: 네이버 리뷰 UI 메타데이터 및 일반적인 불용어
STOPWORDS = {
    # UI 메타데이터
    '리뷰', '사진', '팔로우', '팔로워', '방문', '예약', '이용', '대기', '시간',
    '입장', '반응', '인증', '수단', '영수증', '결제', '내역',
    # 요일 및 날짜
    '일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일',
    '년', '월', '일', '번째',
    # 방문 관련
    '저녁', '점심', '아침', '오전', '오후',
    # 동반자/목적 태그
    '일상', '친목', '데이트', '나들이', '혼자', '친구', '가족', '연인', '배우자', '아이', '동료',
    # 일반 불용어
    '개', '곳', '더', '있다', '있습니다', '없다', '하다', '합니다', '이다', '입니다',
    '것', '거', '수', '등', '때', '및', '위해', '통해', '하나', '가지',
    # 수치 및 기타
    '인원', '선택', '키워드', '조회', '업체', '장소', '테마', '리스트',
}

def preprocess_text(text: str) -> List[str]:
    """
    Kiwi를 사용하여 텍스트에서 명사만 추출합니다.

    Args:
        text: 분석할 텍스트

    Returns:
        추출된 명사 리스트 (2글자 이상, 불용어 제외)
    """
    results = []
    # 텍스트를 토큰(단어)으로 분리
    tokens = kiwi.tokenize(text)
    for token in tokens:
        # NNG(일반 명사)와 NNP(고유 명사)만 추출
        if token.tag in ['NNG', 'NNP']:
            word = token.form
            # 한 글자 단어는 제외 (의미 없는 단어 필터링)
            # 불용어 제외
            if len(word) > 1 and word not in STOPWORDS:
                results.append(word)
    return results


def run_topic_model(reviews: List[Dict], n_topics: int = None, output_dir: str = "./output") -> Dict[str, Any]:
    """
    리뷰 데이터에 대해 BERTopic 토픽 모델링을 수행하고 키워드를 추출합니다.
    Market-Compass 구현 방식을 기반으로 합니다.

    Args:
        reviews: 'text' 또는 'raw_text' 키를 가진 딕셔너리 리스트
        n_topics: 추출할 토픽 개수 (None이면 자동으로 결정)
        output_dir: 결과를 저장할 디렉토리 경로

    Returns:
        토픽, 키워드, 파일 경로 정보를 담은 딕셔너리
    """
    if not reviews:
        return {"error": "No reviews provided"}

    # 결과 저장 디렉토리 생성 (이미 존재하면 무시)
    os.makedirs(output_dir, exist_ok=True)

    print(f"📊 Processing {len(reviews)} reviews...")

    # 1단계: 전처리 - 명사 추출
    print("🔍 Step 1: Preprocessing with Kiwi...")
    processed_data = []
    for r in reviews:
        # 리뷰 텍스트 추출 ('text' 또는 'raw_text' 키 사용)
        text = r.get('text', r.get('raw_text', ''))
        # Kiwi로 명사만 추출
        tokens = preprocess_text(text)
        if tokens:
            processed_data.append({
                'original_text': text,          # 원본 텍스트
                'tokens': tokens,               # 추출된 명사 리스트
                'document': ' '.join(tokens)    # BERTopic 입력용 문자열
            })

    if not processed_data:
        return {"error": "No valid text found after preprocessing"}

    print(f"✅ Preprocessed {len(processed_data)} documents")
    
    # 2단계: BERTopic 모델링 (GPU 사용 가능 시 GPU 활용)
    print("\n🤖 Step 2: BERTopic modeling...")
    # CUDA(GPU) 사용 가능 여부 확인
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"   Using device: {device.upper()}")

    # 한국어 문장 임베딩 모델 초기화 (GPU/CPU 설정 포함)
    embedding_model = SentenceTransformer("jhgan/ko-sbert-nli", device=device)

    # BERTopic에 입력할 문서 리스트 준비
    documents = [d['document'] for d in processed_data]

    # HDBSCAN 클러스터링 라이브러리 사용 가능 여부 확인
    # HDBSCAN이 없으면 KMeans로 대체
    try:
        import hdbscan
        has_hdbscan = True
    except ImportError:
        has_hdbscan = False
        print("   ⚠️ HDBSCAN not available, using KMeans")

    # BERTopic 모델 초기화
    # n_topics가 지정되었거나 HDBSCAN이 없으면 KMeans 사용
    if n_topics or not has_hdbscan:
        # 클러스터 개수 결정: 지정된 값 또는 문서 수의 1/10 (최소 3, 최대 10)
        n_clusters = n_topics if n_topics else max(3, min(len(documents) // 10, 10))
        cluster_model = KMeans(n_clusters=n_clusters, random_state=42)
        topic_model = BERTopic(
            embedding_model=embedding_model,     # 한국어 임베딩 모델
            hdbscan_model=cluster_model,         # KMeans 클러스터링 사용
            verbose=True,                        # 진행 상황 출력
            min_topic_size=3                     # 토픽당 최소 문서 수
        )
    else:
        # HDBSCAN 사용 가능 시 자동 클러스터링
        topic_model = BERTopic(
            embedding_model=embedding_model,
            verbose=True,
            min_topic_size=3
        )

    # 모델 학습 및 토픽 예측
    # topics: 각 문서의 토픽 번호, probs: 각 토픽에 속할 확률
    topics, probs = topic_model.fit_transform(documents)

    # 결과를 DataFrame으로 정리
    df = pd.DataFrame(processed_data)
    df['topic'] = topics  # 각 문서에 토픽 번호 추가

    # -1은 아웃라이어(분류되지 않은 문서)이므로 제외하고 카운트
    print(f"✅ Topic modeling complete - Found {len(set(topics)) - (1 if -1 in topics else 0)} topics")
    
    # 3단계: 커스텀 키워드 추출 (Market-Compass 방식)
    # 각 토픽에서 가장 많이 등장하는 단어 5개를 키워드로 선정
    print("\n📌 Step 3: Extracting custom keywords...")
    topic_keywords = {}   # 토픽별 키워드 저장
    topic_counts = {}     # 토픽별 문서 수 저장

    for topic_num in df['topic'].unique():
        if topic_num == -1:
            continue  # 아웃라이어(분류되지 않은 문서)는 건너뛰기

        # 해당 토픽에 속한 모든 문서 가져오기
        topic_docs = df[df['topic'] == topic_num]
        all_tokens = []
        # 해당 토픽의 모든 단어 수집
        for tokens in topic_docs['tokens']:
            all_tokens.extend(tokens)

        # 단어 빈도수 계산하고 상위 5개 추출
        word_counts = Counter(all_tokens)
        top_keywords = [word for word, count in word_counts.most_common(5)]
        topic_keywords[topic_num] = top_keywords       # 키워드 저장
        topic_counts[topic_num] = len(topic_docs)      # 문서 수 저장

    print(f"✅ Extracted keywords for {len(topic_keywords)} topics")
    
    # 4단계: 결과 저장
    print("\n💾 Step 4: Saving results...")

    # 토픽이 할당된 리뷰 데이터를 CSV로 저장
    output_csv = os.path.join(output_dir, "reviews_with_topics.csv")
    df.to_csv(output_csv, index=False, encoding='utf-8-sig')  # 한글 깨짐 방지: utf-8-sig
    print(f"   ✅ Saved: {output_csv}")

    # 토픽별 요약 정보 생성
    topic_summary = []
    for topic_num in sorted(topic_keywords.keys()):
        topic_summary.append({
            'Topic': f"Topic {topic_num}",                         # 토픽 번호
            'Count': topic_counts[topic_num],                      # 문서 수
            'Keywords': ', '.join(topic_keywords[topic_num]),      # 주요 키워드
            'Percentage': f"{topic_counts[topic_num] / len(df) * 100:.1f}%"  # 비율
        })

    # 토픽 요약을 CSV로 저장
    summary_df = pd.DataFrame(topic_summary)
    summary_csv = os.path.join(output_dir, "topic_summary.csv")
    summary_df.to_csv(summary_csv, index=False, encoding='utf-8-sig')
    print(f"   ✅ Saved: {summary_csv}")

    # 5단계: 원본 리뷰 데이터에 토픽 정보 추가 (페르소나 생성용)
    print("\n🔗 Step 5: Adding topic info to original reviews...")

    # 원본 리뷰와 processed_data를 매칭하여 토픽 정보 추가
    # processed_data의 original_text를 키로 사용
    text_to_topic = {}
    for idx, row in df.iterrows():
        text_to_topic[row['original_text']] = row['topic']

    # 원본 리뷰 리스트에 토픽 정보 추가
    for review in reviews:
        original_text = review.get('text', review.get('raw_text', ''))
        topic = text_to_topic.get(original_text, -1)  # 매칭 안되면 -1 (아웃라이어)
        review['topic'] = int(topic)

    print(f"   ✅ Added topic info to {len(reviews)} reviews")

    # 최종 결과 딕셔너리 생성 및 반환
    results = {
        "topics": {int(k): v for k, v in topic_keywords.items()},       # 토픽별 키워드
        "topic_counts": {int(k): v for k, v in topic_counts.items()},   # 토픽별 문서 수
        "docs_count": len(documents),                                    # 전체 문서 수
        "outliers_count": len(df[df['topic'] == -1]),                   # 아웃라이어 수
        "files": {
            "reviews_csv": output_csv,      # 리뷰 파일 경로
            "summary_csv": summary_csv      # 요약 파일 경로
        },
        "summary_table": summary_df.to_dict(orient='records'),  # 요약 테이블 (딕셔너리 형태)
        "reviews_with_topics": reviews  # 토픽 정보가 추가된 원본 리뷰 (페르소나 생성용)
    }

    return results

if __name__ == "__main__":
    # 테스트용 샘플 코드
    # 카페 리뷰 5개로 2개의 토픽을 추출하는 예제
    sample_reviews = [
        {"raw_text": "커피가 정말 맛있어요. 분위기도 좋고 직원들이 친절합니다."},
        {"raw_text": "가격이 좀 비싸지만 맛은 훌륭해요. 케이크도 맛있습니다."},
        {"raw_text": "매장이 넓고 쾌적해서 공부하기 좋아요. 콘센트도 많아요."},
        {"raw_text": "주차가 불편해요. 하지만 커피 맛 때문에 다시 올 것 같아요."},
        {"raw_text": "직원분들이 너무 친절하셔서 기분이 좋았습니다. 라떼 아트도 예뻐요."}
    ]
    print(run_topic_model(sample_reviews, n_topics=2))
