"""
FastAPI 파이프라인 E2E 테스트
크롤링 → BERTopic → LLM → MongoDB 저장까지 전체 파이프라인을 검증합니다.
"""
import requests
import time
import json
import sys

FASTAPI_BASE = "http://127.0.0.1:8000/api"

# 실제 가게 데이터
TEST_STORE = {
    "shopInfo_name": "바람난 얼큰 수제비 범계점",
    "shopInfo_address": "경기 안양시 동안구 평촌대로223번길 48"
}

def test_pipeline():
    print("=" * 60)
    print("🧪 PULSE FastAPI E2E Pipeline Test")
    print("=" * 60)
    
    # 1. 헬스체크
    print("\n[1/4] 🏥 Healthcheck...")
    try:
        r = requests.get("http://127.0.0.1:8000/")
        print(f"  ✅ Server OK: {r.json()}")
    except Exception as e:
        print(f"  ❌ Server not reachable: {e}")
        print("  💡 먼저 서버를 실행하세요: python run_server.py")
        sys.exit(1)
    
    # 2. 분석 요청
    print(f"\n[2/4] 📤 Analysis Request: {TEST_STORE['shopInfo_name']}")
    r = requests.post(f"{FASTAPI_BASE}/analysis/request", json=TEST_STORE)
    print(f"  Status: {r.status_code}")
    
    if r.status_code != 200:
        print(f"  ❌ Request failed: {r.text}")
        sys.exit(1)
    
    task_data = r.json()
    task_id = task_data["task_id"]
    print(f"  ✅ Task ID: {task_id}")
    
    # 3. 상태 폴링
    print(f"\n[3/4] ⏳ Polling status (max 5분)...")
    start = time.time()
    max_wait = 300  # 5분
    
    while time.time() - start < max_wait:
        r = requests.get(f"{FASTAPI_BASE}/analysis/status/{task_id}")
        status = r.json()
        
        elapsed = int(time.time() - start)
        print(f"  [{elapsed:3d}s] {status['status']:12s} | {status['progress']:3d}% | {status['message']}")
        
        if status["status"] == "completed":
            print(f"\n  🎉 Analysis completed in {elapsed}s!")
            break
        elif status["status"] == "failed":
            print(f"\n  ❌ Analysis FAILED: {status['message']}")
            sys.exit(1)
        
        time.sleep(5)
    else:
        print(f"\n  ⏰ Timeout after {max_wait}s")
        sys.exit(1)
    
    # 4. 결과 조회
    print(f"\n[4/4] 📊 Fetching result...")
    r = requests.get(f"{FASTAPI_BASE}/analysis/result/{task_id}")
    
    if r.status_code != 200:
        print(f"  ❌ Result fetch failed: {r.text}")
        sys.exit(1)
    
    result = r.json()
    
    print(f"\n{'=' * 60}")
    print(f"📋 FINAL REPORT")
    print(f"{'=' * 60}")
    print(f"  🏪 가게명: {result.get('store_name', 'N/A')}")
    print(f"  ⭐ 평균 평점: {result.get('average_rating', 'N/A')}")
    print(f"  📝 총 리뷰 수: {result.get('total_reviews', 'N/A')}")
    print(f"  📄 가게 요약: {result.get('store_summary', 'N/A')[:100]}...")
    
    personas = result.get("personas", [])
    print(f"\n  👥 페르소나 수: {len(personas)}")
    
    for p in personas:
        print(f"\n  ─── 페르소나 #{p.get('id', '?')} ───")
        print(f"  별명: {p.get('nickname', 'N/A')}")
        print(f"  태그: {p.get('tags', [])}")
        print(f"  요약: {p.get('summary', 'N/A')[:80]}...")
        print(f"  이미지: {p.get('img', 'N/A')}")
        
        journey = p.get("journey", {})
        if journey:
            for step_key in ["explore", "visit", "eat", "share"]:
                step = journey.get(step_key, {})
                print(f"    [{step.get('label', step_key)}] {step.get('action', '-')} | 감정: {step.get('type', '-')}")
    
    # 5. PersonaResponse 스키마 검증
    print(f"\n{'=' * 60}")
    print(f"🔍 Schema Validation")
    print(f"{'=' * 60}")
    
    errors = []
    required_top = ["store_name", "average_rating", "total_reviews", "store_summary", "personas"]
    for field in required_top:
        if field not in result:
            errors.append(f"Missing top-level field: {field}")
    
    if personas:
        p0 = personas[0]
        required_persona = ["id", "nickname", "tags", "img", "summary", "journey"]
        for field in required_persona:
            if field not in p0:
                errors.append(f"Missing persona field: {field}")
        
        journey = p0.get("journey", {})
        required_steps = ["explore", "visit", "eat", "share"]
        for step in required_steps:
            if step not in journey:
                errors.append(f"Missing journey step: {step}")
            else:
                step_data = journey[step]
                required_step_fields = ["label", "action", "thought", "type", "touchpoint", "opportunity"]
                for sf in required_step_fields:
                    if sf not in step_data:
                        errors.append(f"Missing journey.{step}.{sf}")
    
    if errors:
        print("  ❌ Schema errors found:")
        for e in errors:
            print(f"    - {e}")
    else:
        print("  ✅ All fields match PersonaResponse schema!")
    
    # 6. MongoDB 저장 확인
    print(f"\n{'=' * 60}")
    print(f"💾 MongoDB Check")
    print(f"{'=' * 60}")
    
    try:
        from pymongo import MongoClient
        client = MongoClient("mongodb://localhost:27017/")
        db = client["pulse_db"]
        
        # Check raw reviews
        raw_count = db["raw_reviews"].count_documents({"task_id": task_id})
        print(f"  raw_reviews collection: {'✅' if raw_count > 0 else '❌'} ({raw_count} docs for this task)")
        
        # Check analysis results
        result_count = db["analysis_results"].count_documents({"task_id": task_id})
        print(f"  analysis_results collection: {'✅' if result_count > 0 else '❌'} ({result_count} docs for this task)")
        
        if result_count > 0:
            doc = db["analysis_results"].find_one({"task_id": task_id})
            print(f"  Stored personas count: {len(doc.get('personas', []))}")
        
        client.close()
    except Exception as e:
        print(f"  ⚠️ Could not check MongoDB: {e}")
    
    print(f"\n{'=' * 60}")
    print(f"🏁 Test Complete!")
    print(f"{'=' * 60}")
    
    # Output full JSON for debugging
    with open("test_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  📁 Full result saved to test_result.json")

if __name__ == "__main__":
    test_pipeline()
