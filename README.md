# 📅 Project PULSE Development Journal

## 2026-01-27 (화) - FastAPI 리팩토링 및 구조 잡기 🏗️

### 1. 프로젝트 구조 개편 (Refactoring)
기존의 `run_pipeline.py` 하나로 돌아가던 거대한 스크립트를 유지보수하기 좋게 **Layered Architecture**로 뜯어고쳤다. Spring Boot랑 비슷하게 구조를 잡으니 마음이 편하다.

- **`app/api/`**: 엔드포인트(Controller). 요청을 받고 백그라운드 작업을 넘기는 역할.
- **`app/services/`**: 핵심 로직(Service).
    - `crawler_service.py`: 네이버/카카오맵 리뷰 수집 (Playwright 사용)
    - `analysis_service.py`: BERTopic 토픽 모델링 & Singleton 패턴으로 모델 로딩 최적화
    - `llm_service.py`: Upstage Solar API 연동하여 페르소나/요약 생성
- **`app/schemas/`**: DTO 정의 (Pydantic). 프론트엔드쪽 필드명(`shopInfo_name` 등)이랑 맞춤.

### 2. 비동기 처리 도입 (Async)
분석 작업이 오래 걸리기 때문에(크롤링 + AI 연산), 사용자가 무한정 기다리지 않게 **Polling 방식**을 도입했다.
1. `POST /request` → 즉시 **Task ID** 발급
2. 백그라운드에서 크롤링 & 분석 뺑뺑이 🏃
3. `GET /status/{task_id}` → 진행률(Progress Bar) 확인 가능
4. `GET /result/{task_id}` → 최종 결과 수령

### 3. 검증 및 시뮬레이션 (Simulation)
Spring Boot 서버가 아직 없어도 테스트 가능하게 `simulate_integration.py`를 만들어서 돌려봤다.
- **테스트 케이스 1:** "바람난 얼큰 수제비" → 성공 ✅
- **테스트 케이스 2:** "태평순대 본점" (복잡한 주소) → 성공 ✅
- **결과:** 네이버 리뷰 35개 수집되고, 3가지 페르소나 그룹(단골/단체/혼밥러)으로 예쁘게 분석됨.

### � Next Step
- 이제 Spring Boot에서 이 API 서버(`http://localhost:8000`)를 찔러서 데이터 받아가기만 하면 된다.
- LLM API 키는 `.env`에 잘 숨겨둠.
