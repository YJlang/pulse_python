
import requests
import time
import json
import sys

# Constants
BASE_URL = "http://127.0.0.1:8000/api"
STORE_NAME = "바람난 얼큰 수제비 범계점"
ADDRESS = "경기 안양시 동안구 평촌대로223번길 48 백운빌딩 301호 바람난 얼큰 수제비"

def main():
    print(f"🚀 Starting E2E API Test for: {STORE_NAME}")

    # 1. Request Analysis
    print("\n1️⃣ Requesting Analysis...")
    payload = {
        "shopInfo_name": STORE_NAME,
        "shopInfo_address": ADDRESS
    }
    try:
        resp = requests.post(f"{BASE_URL}/analysis/request", json=payload)
        resp.raise_for_status()
        data = resp.json()
        task_id = data["task_id"]
        print(f"✅ Request Accepted! Task ID: {task_id}")
    except Exception as e:
        print(f"❌ Analysis Request Failed: {e}")
        try: print(resp.text)
        except: pass
        sys.exit(1)

    # 2. Poll Status
    print("\n2️⃣ Polling Status...")
    while True:
        try:
            resp = requests.get(f"{BASE_URL}/analysis/status/{task_id}")
            resp.raise_for_status()
            status_data = resp.json()
            status = status_data["status"]
            progress = status_data["progress"]
            message = status_data["message"]
            
            print(f"   Now: [{status.upper()}] {progress}% - {message}")
            
            if status == "completed":
                print("✅ Analysis Completed!")
                break
            elif status == "failed":
                print(f"❌ Analysis Failed: {message}")
                sys.exit(1)
            
            time.sleep(2)
        except Exception as e:
            print(f"❌ Polling Failed: {e}")
            sys.exit(1)

    # 3. Get Result
    print("\n3️⃣ Retrieving Final Result...")
    try:
        resp = requests.get(f"{BASE_URL}/analysis/result/{task_id}")
        resp.raise_for_status()
        result = resp.json()
        
        # Validate Result
        personas = result.get("personas", [])
        if not personas:
            print("⚠️ Warning: No personas returned.")
        else:
            print(f"✅ Received {len(personas)} personas.")
            p1 = personas[0]
            print(f"   Persona 1: {p1['nickname']} ({p1['summary']})")
            if 'journey' in p1:
                eat_step = p1['journey'].get('eat', {})
                print(f"   Journey Step (Eat): {eat_step.get('label')} -> {eat_step.get('opportunity')}")
            else:
                print("   ⚠️ Journey data missing logic error")

        print("\n🎉 E2E Test Passed Successfully!")
        
    except Exception as e:
        print(f"❌ Result Retrieval Failed: {e}")
        try: print(resp.text)
        except: pass
        sys.exit(1)

if __name__ == "__main__":
    main()
