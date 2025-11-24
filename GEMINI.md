# Project PULSE: Backend Development Context

## 1. 프로젝트 개요
**PULSE**는 외식업 소상공인을 위한 **지능형 마케팅 자동화 SaaS 플랫폼**입니다.
[cite_start]사장님이 마케팅 지식이나 편집 기술 없이도 "손님 분석 → 릴스 자동 제작 → 성과 기반 행동 제안"의 루프를 통해 자동으로 가게를 홍보할 수 있게 돕습니다[cite: 394, 402].

## 2. 핵심 기술 스택 (Tech Stack)
### A. Main Backend (Spring Boot)
- **Language:** Java 17+
- **Framework:** Spring Boot 3.x
- **Role:** API Gateway, 사용자 인증/인가, 데이터 관리, 프론트엔드(React)와의 통신 담당
- **Database:** MySQL (JPA/Hibernate 사용) - 사용자, 가게 정보, 완성된 콘텐츠 메타데이터 저장

### B. AI & Data Backend (FastAPI)
- **Language:** Python 3.10+
- **Framework:** FastAPI
- **Role:** 고연산 작업 처리 (크롤링, NLP 분석, 영상 렌더링)
- **Database:** MongoDB (Motor/Pymongo 사용) - 대용량 원본 리뷰 데이터, 크롤링 로그 저장
# Project PULSE: Backend Development Context

## 1. 프로젝트 개요
**PULSE**는 외식업 소상공인을 위한 **지능형 마케팅 자동화 SaaS 플랫폼**입니다.
[cite_start]사장님이 마케팅 지식이나 편집 기술 없이도 "손님 분석 → 릴스 자동 제작 → 성과 기반 행동 제안"의 루프를 통해 자동으로 가게를 홍보할 수 있게 돕습니다[cite: 394, 402].

## 2. 핵심 기술 스택 (Tech Stack)
### A. Main Backend (Spring Boot)
- **Language:** Java 17+
- **Framework:** Spring Boot 3.x
- **Role:** API Gateway, 사용자 인증/인가, 데이터 관리, 프론트엔드(React)와의 통신 담당
- **Database:** MySQL (JPA/Hibernate 사용) - 사용자, 가게 정보, 완성된 콘텐츠 메타데이터 저장

### B. AI & Data Backend (FastAPI)
- **Language:** Python 3.10+
- **Framework:** FastAPI
- **Role:** 고연산 작업 처리 (크롤링, NLP 분석, 영상 렌더링)
- **Database:** MongoDB (Motor/Pymongo 사용) - 대용량 원본 리뷰 데이터, 크롤링 로그 저장
- **Key Libs:**
    - **Crawling:** Playwright / Selenium
    - [cite_start]**NLP:** Kiwi (형태소 분석), BERTopic (토픽 모델링), Sentence-Transformers (임베딩) [cite: 11, 96, 100]
    - **Video:** MoviePy (이미지 합성 및 mp4 렌더링)
    - [cite_start]**LLM:** OpenAI API / Gemini API (페르소나 및 문구 생성) [cite: 108]

## 3. 시스템 아키텍처 및 데이터 흐름
**MSA 구조를 지향하며, Spring Boot가 컨트롤 타워 역할을 수행합니다.**

### 흐름 1: 분석 요청 (Analysis Pipeline)
1. **Spring Boot:** 사용자로부터 가게 URL 수신 -> FastAPI로 분석 요청 (`POST /api/analysis`)
2. **FastAPI:**
    - [cite_start]**Dual-Platform Crawling:** Playwright로 네이버 방문자 리뷰 + 카카오맵 리뷰(별점 포함) 동시 수집 [cite: 162]
    - [cite_start]**Data Separation Strategy:**
        - `text`: BERTopic용 (불용어 제거, 정제된 텍스트)
        - `raw_text`: LLM용 (평점 포함, 원본 텍스트 보존)
    - [cite_start]BERTopic 기반 군집화 수행 -> 주요 토픽(맛, 가성비, 분위기 등) 도출 [cite: 171]
    - [cite_start]LLM을 호출하여 '페르소나(Persona)' 및 '가게 이미지' 생성 (평균 평점 활용) [cite: 482, 568]
3. **Return:** 분석 결과를 JSON 형태로 Spring Boot에 반환

### 흐름 2: 릴스 생성 (Video Pipeline)
1. **Spring Boot:** 사용자 업로드 이미지(S3 등) URL + 선택된 인사이트 정보 -> FastAPI로 전송 (`POST /api/video`)
2. **FastAPI:**
    - [cite_start]LLM을 통해 인사이트 기반의 소구점(Hook) 문구 및 자막 스크립트 생성 [cite: 671]
    - [cite_start]MoviePy를 사용하여 이미지 + 자막 + 트랜지션 효과 합성 -> `.mp4` 렌더링 [cite: 695]
3. **Return:** 생성된 영상 파일 URL 반환

## 4. 데이터베이스 전략 (Database Strategy)
- **MySQL (Relational):**
    - `User`: 사장님 계정 정보
    - `Store`: 가게 기본 정보 (이름, 위치, 업종)
    - `Insight`: 생성된 분석 결과 요약 (JSON 타입 활용 고려)
    - `Video`: 생성된 릴스 메타데이터 및 성과 지표
- **MongoDB (Document):**
    - `RawReviews`: 크롤링한 리뷰 원본 (Schema-less, 대량 데이터)
    - `CrawlingLogs`: 크롤링 성공/실패 로그

## 5. 코딩 컨벤션 (Vibe Coding Rules)

### Spring Boot (Java)
- **Architecture:** Controller -> Service -> Repository 계층 구조 엄수.
- **DTO:** Entity를 직접 반환하지 말고, 반드시 `RequestDTO`, `ResponseDTO`를 사용.
- **Error Handling:** `@RestControllerAdvice`를 통한 전역 예외 처리.
- **Communication:** FastAPI와의 통신은 `WebClient` 또는 `OpenFeign` 사용 권장.

### FastAPI (Python)
- **Type Hinting:** 모든 함수 인자와 반환값에 Type Hint (`Thinking: str`, `List[int]` 등) 명시.
- **Async:** I/O 바운드 작업(크롤링, DB조회)은 반드시 `async/await` 사용.
- **Dependency Injection:** DB 세션 및 외부 서비스는 `Depends`로 주입.
- **Clean Code:** 비즈니스 로직은 `services/` 폴더로 분리, 라우터는 요청/응답 처리만 담당.

## 6. 구현 시 주의사항 (Business Logic)
1. [cite_start]**Dual Insight Model:** 리뷰가 적은 가게는 '상권 데이터' 기반, 많은 가게는 'BERTopic' 기반으로 분기 처리 로직 필수[cite: 460].
2. **성능 최적화:** 영상 렌더링과 크롤링은 시간이 오래 걸리므로, Spring Boot에서 **비동기 처리(Polling 또는 WebSocket)** 설계를 고려해야 함.
3. [cite_start]**LLM 프롬프트:** 페르소나 생성 시 논문의 'Table 5' 구조(특성, 선호도, 목표, 불편점)를 따르는 JSON 출력을 유도할 것[cite: 243].
4. **API Key 관리:** OpenAI/Gemini API 키는 환경 변수(`.env`)로 관리하며, 코드에 노출하지 않음.