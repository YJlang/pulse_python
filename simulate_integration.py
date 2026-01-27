import threading
import time
import requests
import uvicorn
import sys
import json
from app.main import app

# =========================================================
# 🧪 통합 테스트 시뮬레이션 (Configurable)
# Spring Boot가 할 역할을 대신 수행하는 스크립트입니다.
# =========================================================

# 👇 테스트할 가게 정보를 여기서 수정하세요!
TEST_STORE_NAME = "태평순대 본점"
TEST_ADDRESS = "경기 안양시 만안구 문예로 36번길 11 101호(안양아트센터 앞)"

def run_server():
    """FastAPI 서버를 백그라운드 스레드에서 실행"""
    # 로그 레벨을 critical로 설정하여 서버 자체 로그는 최소화하고 시뮬레이션 로그에 집중
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="critical")

def simulate_client():
    """클라이언트(Spring Boot) 역할"""
    base_url = "http://127.0.0.1:8000/api"
    
    # 서버 부팅 대기
    print("⏳ Waiting for server to start...")
    time.sleep(10) # 모델 로딩 시간 대기
    
    # 1. 분석 요청
    print("\n" + "="*50)
    print(f"🚀 [Client] Requesting analysis for: {TEST_STORE_NAME}")
    print("="*50)
    
    payload = {
        "shopInfo_name": TEST_STORE_NAME,
        "shopInfo_address": TEST_ADDRESS
    }
    
    try:
        resp = requests.post(f"{base_url}/analysis/request", json=payload)
        resp.raise_for_status()
        data = resp.json()
        task_id = data['task_id']
        print(f"✅ Analysis Task Started! ID: {task_id}")
    except Exception as e:
        print(f"❌ Failed to create task: {e}")
        # 혹시 서버가 안 떴을 수도 있으니 확인 메시지
        print("   (서버가 아직 준비되지 않았을 수 있습니다. 잠시 후 다시 시도해보세요.)")
        return

    # 2. 상태 조회 (Polling)
    print("\n" + "="*50)
    print("🔄 [Client] Polling status...")
    print("="*50)
    
    start_time = time.time()
    
    while True:
        try:
            resp = requests.get(f"{base_url}/analysis/status/{task_id}")
            resp.raise_for_status()
            status_data = resp.json()
            
            status = status_data['status']
            progress = status_data['progress']
            message = status_data['message']
            
            # 진행상황 출력 (로딩 바)
            bar_length = 30
            filled_length = int(bar_length * progress // 100)
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            
            elapsed = int(time.time() - start_time)
            print(f"\r[{bar}] {progress}% ({elapsed}s) - {message}   ", end="", flush=True)
            
            if status in ['completed', 'failed']:
                print("\n") # 줄바꿈
                break
                
            time.sleep(1) # 1초 간격 polling
            
        except Exception as e:
            print(f"\n❌ Polling error: {e}")
            break

    # 3. 결과 조회
    if status == 'completed':
        print("\n" + "="*50)
        print("🎉 [Client] Analysis Completed! Fetching results...")
        print("="*50)
        
        try:
            resp = requests.get(f"{base_url}/analysis/result/{task_id}")
            resp.raise_for_status()
            result = resp.json()
            
            # 결과 요약 출력
            print(f"📍 가게: {result['store_name']}")
            print(f"⭐ 평점: {result['average_rating']}")
            print(f"📝 요약: {result['store_summary']}")
            print(f"\n🎭 생성된 페르소나 리포트 ({len(result['personas'])}개):")
            
            for p in result['personas']:
                print("-" * 30)
                print(f"[{p['topic_name']}] (비중: {p['percentage']}%)")
                print(f"   🔑 키워드: {', '.join(p['keywords'][:5])}")
                
                # 페르소나 상세 내용이 있을 경우에만 출력
                if p.get('persona'):
                    chars = p['persona'].get('characteristics', 'N/A')
                    print(f"   👤 특징: {chars[:60]}..." if len(chars) > 60 else f"   👤 특징: {chars}")
            
            print("\n✅ Simulation Passed Successfully!")
            
            # 4. 결과 파일 저장 (사용자 요청)
            output_file = "latest_simulation_result.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"💾 Full JSON response saved to: {output_file}")
            
        except Exception as e:
            print(f"❌ Failed to get result: {e}")
    else:
        print(f"\n❌ Task Failed: {message}")

if __name__ == "__main__":
    print("🎬 Starting Integration Simulation...")
    print(f"   Target: {TEST_STORE_NAME} ({TEST_ADDRESS})")
    
    # 서버 스레드 시작
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # 클라이언트 시뮬레이션 시작
    try:
        simulate_client()
    except KeyboardInterrupt:
        print("\n⚠️ Simulation interrupted by user.")
    
    print("👋 Shutting down.")
    sys.exit(0)
