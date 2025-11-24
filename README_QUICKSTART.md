# 🚀 빠른 시작 가이드

네이버 리뷰 크롤링 → 토픽 분석 → 페르소나 생성을 간단하게 시작하세요!

---

## ⚡ 가장 빠른 방법

### 1단계: 가상환경 활성화

**PowerShell (권장):**
```powershell
.\.venv\Scripts\Activate.ps1
```

**CMD:**
```cmd
.venv\Scripts\activate.bat
```

**Git Bash:**
```bash
source .venv/Scripts/activate
```

### 2단계: 스크립트 실행

#### 옵션 A: 크롤링만 빠르게 테스트 (30초)
```bash
python test_crawl.py
```
- 입력: 가게 이름 (예: "바람난 얼큰 수제비 범계점")
- 출력: `output/crawl_test.json` (20개 리뷰)
- **장점**: 빠르고 간단, BERTopic 로딩 없음

#### 옵션 B: 전체 파이프라인 실행 (최적화 버전)
```bash
python run_pipeline_optimized.py
```
- 입력: 가게 이름
- 출력: 토픽 분석 + 페르소나 (GPT o1)
- **최초 실행**: 1-2분 (라이브러리 로딩)
- **이후 실행**: 30초~1분

#### 옵션 C: 기본 파이프라인
```bash
python run_pipeline.py
```
- 기능은 옵션 B와 동일
- 라이브러리를 먼저 로딩하므로 시작이 느릴 수 있음

---

## 🎯 예시 실행

### 크롤링 테스트
```bash
(.venv) PS C:\online_review\backend_fastapi> python test_crawl.py

============================================================
🔍 네이버 리뷰 크롤링 테스트
============================================================

검색할 가게 이름이나 주소를 입력하세요: 바람난 얼큰 수제비 범계점

============================================================
🔍 자동 검색 크롤링 시작
============================================================
🔍 네이버 지도에서 '바람난 얼큰 수제비 범계점' 검색 중...
📍 가게 페이지로 이동 중...
✅ 가게 찾기 완료: 바람난 얼큰 수제비 범계점
📍 리뷰 URL: https://m.place.naver.com/restaurant/31264425/review/visitor

📥 리뷰 크롤링 시작...
현재까지 12개 리뷰 수집 (시도 1회)...
현재까지 20개 리뷰 수집 (시도 2회)...
✅ 총 20개 리뷰 수집 완료

============================================================
✅ 크롤링 완료: 바람난 얼큰 수제비 범계점
📊 수집된 리뷰: 20개
============================================================
```

### 전체 파이프라인 실행
```bash
(.venv) PS C:\online_review\backend_fastapi> python run_pipeline_optimized.py

============================================================
🏪 온라인 리뷰 분석 파이프라인
============================================================

🔍 분석할 가게 이름이나 주소를 입력하세요: 스타벅스 강남역점

⏳ 분석 라이브러리 로딩 중... (최초 실행 시 1-2분 소요)
   Tip: 다음 실행부터는 훨씬 빠릅니다!
✅ 라이브러리 로딩 완료!

============================================================
📥 Step 1: 네이버 자동 검색 & 리뷰 크롤링
============================================================
[... 크롤링 진행 ...]

============================================================
🤖 Step 2: BERTopic 토픽 분석
============================================================
[... 토픽 분석 진행 ...]

============================================================
🧠 Step 3: 토픽별 페르소나 생성 (GPT o1)
============================================================
[... 페르소나 생성 진행 ...]
```

---

## 📁 생성되는 파일

### 크롤링 테스트 (`test_crawl.py`)
```
output/
  └── crawl_test.json     # 크롤링한 리뷰 데이터
```

### 전체 파이프라인 (`run_pipeline_optimized.py`)
```
output/
  ├── topic_summary.csv    # 토픽별 요약
  ├── topic_details.csv    # 리뷰별 토픽 할당 상세
  └── persona.json         # 토픽별 페르소나 (최종 결과)
```

---

## ⚙️ 설정 변경

### 리뷰 수집 개수 변경

**크롤링 테스트:**
```python
# test_crawl.py 파일 열기
# 13번 줄 수정
reviews, store_name = await crawl_by_search(query, max_reviews=50)  # 20 → 50
```

**전체 파이프라인:**
```python
# run_pipeline_optimized.py 파일 열기
# 30번 줄 수정
naver_reviews, store_name = await crawl_by_search(query, max_reviews=100)  # 50 → 100
```

### 토픽 개수 변경
```python
# run_pipeline_optimized.py 파일 열기
# 48번 줄 수정
result = run_topic_model(all_reviews, n_topics=7, output_dir="./output")  # 5 → 7
```

---

## 🐛 문제 해결

### 1. KeyboardInterrupt 또는 로딩이 멈춤

**증상:**
```
File "<frozen codecs>", line 312, in __init__
KeyboardInterrupt
```

**해결책:**
1. `run_pipeline_optimized.py` 사용 (라이브러리 로딩 전에 사용자 입력)
2. 또는 크롤링만 테스트: `python test_crawl.py`
3. 최초 실행 시 1-2분 기다리기 (transformers 라이브러리 초기화)

### 2. 가게를 찾을 수 없음

**증상:**
```
❌ 검색 결과를 찾을 수 없습니다.
```

**해결책:**
- 더 정확한 가게명 입력 (지점명 포함)
- 주소 추가 (예: "스타벅스 강남역점 서울")
- 네이버 지도에서 직접 검색해보고 정확한 이름 확인

### 3. OPENAI_API_KEY 오류

**증상:**
```
openai.OpenAIError: The api_key client option must be set
```

**해결책:**
`.env` 파일에 API 키 추가:
```bash
OPENAI_API_KEY=sk-your-api-key-here
```

### 4. Playwright 브라우저 오류

**증상:**
```
playwright._impl._errors.Error: Executable doesn't exist
```

**해결책:**
```bash
playwright install chromium
```

---

## 💡 팁

1. **처음 실행은 느립니다**: transformers 라이브러리가 모델 구조를 분석하는데 1-2분 소요
2. **두 번째 실행부터 빠름**: 캐싱되어 30초~1분이면 완료
3. **크롤링만 테스트**: `test_crawl.py`로 빠르게 확인
4. **리뷰 개수 조절**: 많을수록 정확하지만 시간 소요 (추천: 50개)
5. **체인점은 지점명 필수**: "스타벅스" → "스타벅스 강남역점"

---

## 📚 더 많은 정보

- **자동 검색 상세 가이드**: [README_AUTO_SEARCH.md](README_AUTO_SEARCH.md)
- **파이프라인 구조**: [run_pipeline.py](run_pipeline.py)
- **크롤러 코드**: [crawling/playwright_crawler.py](crawling/playwright_crawler.py)

---

**🎉 이제 준비 완료! 가게 이름만 입력하면 자동으로 페르소나가 생성됩니다!**
