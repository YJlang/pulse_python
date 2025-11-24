# 🛠️ PULSE Technical Architecture

> **Project:** PULSE (외식업 자영업자 마케팅 자동화 플랫폼)
> **Architecture Type:** Microservices-oriented Architecture (Frontend / Main Backend / AI Server)

---

## 1. System Overview (시스템 개요)

PULSE는 사용자 경험을 담당하는 **React Frontend**, 비즈니스 로직을 처리하는 **Spring Boot API**, 그리고 데이터 수집 및 생성형 AI 작업을 전담하는 **FastAPI AI Server**로 구성된 3-Tier 아키텍처를 따릅니다.

### 🏗️ High-Level Architecture
전체 시스템은 크게 두 가지 핵심 파이프라인으로 작동합니다.
1.  **Review Analysis Pipeline:** 리뷰 수집 → 분석 → 페르소나/인사이트 도출
2.  **Content Generation Pipeline:** 이미지 업로드 → 영상 렌더링 → 숏폼(Reels) 생성

---

## 2. Tech Stack (기술 스택)

### 💻 Frontend (User Interface)
사용자(사장님)와 상호작용하는 웹 애플리케이션입니다.
* **Framework:** **React**
* **Role:**
    * 회원가입 및 가게 정보 입력 UI
    * 대시보드 렌더링 (분석 결과 시각화)
    * 사진 업로드 및 릴스 생성 요청
    * 최종 결과물(영상) 미리보기 제공

### ☕ Main Backend (API Gateway & Business Logic)
프론트엔드와 AI 서버 간의 중계 및 데이터 관리를 담당합니다.
* **Framework:** **Spring Boot**
* **Role:**
    * RESTful API 제공
    * 사용자 인증 및 가게 정보 관리
    * AI 서버로 분석/생성 요청 위임 (Proxy)
    * 최종 결과 데이터(JSON/MP4 URL) 응답

### 🐍 AI & Data Server (Core Engine)
무거운 데이터 처리, 크롤링, AI 모델링, 영상 렌더링을 수행합니다.
* **Framework:** **FastAPI (Python)**
* **Data Collection:** **Playwright** (네이버/카카오맵 리뷰 크롤링)
* **NLP & Analysis:**
    * **Kiwi:** 한국어 형태소 분석
    * **BERTopic:** 리뷰 주제 군집화 (Clustering)
* **Generative AI:** **LLM API (Gemini / GPT)** (키워드 기반 페르소나 및 인사이트 생성)
* **Video Processing:** **MoviePy** (이미지 및 스크립트 기반 숏폼 렌더링)

### 💾 Database
데이터의 성격에 따라 관계형과 비관계형 데이터베이스를 혼용합니다.
* **MySQL:** 정형 데이터 저장 (사용자 정보, 가게 기본 정보, 영상 URL 등)
* **MongoDB:** 비정형 데이터 저장 (수집된 원본 리뷰 데이터, 분석 로그 등)

---

## 3. Data Flow & Pipelines (데이터 흐름)

### 🔄 A. 사용자 등록 및 초기 설정
1.  **회원가입 & 가게 URL 입력:** 사용자가 React 프론트엔드에서 정보를 입력합니다.
2.  **가게 정보 저장:** Spring Boot가 MySQL에 해당 정보를 저장하고 관리합니다.

### 📊 B. 리뷰 분석 파이프라인 (Review Analysis)
사장님이 '분석'을 요청하면 실행되는 프로세스입니다.

1.  **분석 요청:** React → Spring Boot (`POST /api/analysis`) → FastAPI로 전달.
2.  **데이터 수집 (Crawling):**
    * FastAPI의 **Playwright**가 네이버/카카오맵에서 리뷰 데이터를 수집합니다.
    * 수집된 **Raw Reviews**는 **MongoDB**에 저장됩니다.
3.  **전처리 및 분석 (NLP):**
    * **Kiwi**로 형태소를 분석하고 불용어를 제거합니다.
    * **BERTopic**을 통해 리뷰를 의미론적 그룹(Topic)으로 군집화합니다.
4.  **AI 인사이트 생성 (LLM):**
    * 추출된 키워드와 클러스터 정보를 **LLM(Gemini/GPT)**에 프롬프트로 주입합니다.
    * **결과:** 페르소나(Persona) 및 마케팅 인사이트가 담긴 **JSON** 데이터가 생성됩니다.
5.  **결과 반환:** FastAPI → Spring Boot → React (대시보드 렌더링).

### 🎬 C. 숏폼 영상 생성 파이프라인 (Content Generation)
사장님이 사진을 업로드하고 영상을 요청하면 실행되는 프로세스입니다.

1.  **생성 요청:** React → Spring Boot (사진 업로드) → FastAPI (`POST /api/video`).
2.  **영상 렌더링 (Rendering):**
    * FastAPI가 전송받은 이미지와 분석된 스크립트를 기반으로 **MoviePy**를 실행합니다.
    * 자동 편집, 자막 삽입, 효과 적용이 수행됩니다.
3.  **MP4 Output:** 최종 결과물인 `.mp4` 파일이 생성됩니다.
4.  **URL 반환:** 영상 파일의 경로(URL)가 Spring Boot를 통해 React로 전달됩니다.
5.  **미리보기:** 프론트엔드에서 생성된 영상을 즉시 재생합니다.

---

## 4. Database Schema Strategy (데이터 저장 전략)

* **MySQL (RDBMS):**
    * ACID 트랜잭션이 필요한 중요 정보 관리.
    * `User`, `Store`, `AnalysisResult(Summary)`, `VideoLog` 테이블 등.
* **MongoDB (NoSQL):**
    * 스키마가 유동적이고 대용량인 텍스트 데이터 관리.
    * `RawReviewData` (크롤링된 전체 텍스트), `AnalysisLog` (중간 분석 과정) 등.

---

## 5. API Interface (Summary)

| Direction | Method | Endpoint | Description |
| :--- | :--- | :--- | :--- |
| **FE ↔ BE** | `POST` | `/api/users/store` | 가게 정보 등록 |
| **FE ↔ BE** | `GET` | `/api/dashboard/{id}` | 분석 완료된 대시보드 데이터 조회 |
| **FE ↔ BE** | `POST` | `/api/analysis/request` | 리뷰 분석 시작 요청 |
| **FE ↔ BE** | `POST` | `/api/video/generate` | 릴스 생성 요청 (이미지 포함) |
| **BE ↔ AI** | `POST` | `/internal/crawl` | AI 서버에 크롤링 명령 |
| **BE ↔ AI** | `POST` | `/internal/render` | AI 서버에 영상 렌더링 명령 |