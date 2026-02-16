
import sys
import os
import json
from dotenv import load_dotenv

# Add app to path
sys.path.append(os.getcwd())

from app.services.llm_service import LLMService
from app.schemas.dtos import PersonaResponse

# Load env (specifically for OPENAI_API_KEY)
load_dotenv()

def main():
    print("🚀 Starting LLM Service Verification...")

    # 1. Initialize Service
    try:
        service = LLMService()
        print("✅ LLMService Initialized")
    except Exception as e:
        print(f"❌ Failed to init service: {e}")
        return

    # 2. Mock Data
    mock_reviews = [
        {"text": "국물이 진짜 시원하고 맛있어요. 해장으로 딱입니다.", "rating": 5, "topic": 0},
        {"text": "직원분들이 친절하고 매장이 깔끔해요.", "rating": 5, "topic": 0},
        {"text": "가격이 좀 비싼 감이 있지만 맛은 보장합니다.", "rating": 4, "topic": 1},
        {"text": "웨이팅이 너무 길어서 힘들었어요.", "rating": 3, "topic": 1},
    ]
    
    mock_topics = {
        0: ["국물", "해장", "친절"],
        1: ["가격", "웨이팅", "맛집"]
    }
    
    mock_analysis_result = {
        "reviews_with_topics": mock_reviews,
        "topics": mock_topics,
        "topic_counts": {0: 2, 1: 2},
        "docs_count": 4
    }

    # 3. Call Service
    print("\n🔍 Generating Report (Calling OpenAI GPT-4o)...")
    try:
        result = service.generate_full_report("테스트 해장국", mock_analysis_result)
        print("✅ Report Generated!")
    except Exception as e:
        print(f"❌ Verification Failed: {e}")
        return

    # 4. Print Result Pretty
    print("\n📊 Result JSON:")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 5. Validate against Pydantic
    print("\n🧐 Validating against PersonaResponse Schema...")
    try:
        dto = PersonaResponse(**result)
        print("✅ Validation PASSED! The output strictly matches the DTO.")
    except Exception as e:
        print(f"❌ Validation FAILED: {e}")



    # 6. Test Chatbot / Reply Generation
    print("\n💬 Testing Review Reply Generation...")
    try:
        reply = service.generate_review_reply("음식이 너무 늦게 나왔지만 맛은 있었어요.", tone="친근함", length="짧게")
        print(f"✅ Reply Generated: {reply}")
        if not reply: raise Exception("Empty reply returned")
    except Exception as e:
        print(f"❌ Reply Generation Failed: {e}")

if __name__ == "__main__":
    main()
