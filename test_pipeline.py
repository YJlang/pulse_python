"""
Live FastAPI pipeline E2E test.

This test is skipped by default because it requires a running local FastAPI
server plus external crawling and LLM dependencies.
"""

from __future__ import annotations

import json
import os
import time

import pytest
import requests

FASTAPI_BASE = os.getenv("PULSE_FASTAPI_BASE", "http://127.0.0.1:8000/api")
FASTAPI_HEALTH = os.getenv("PULSE_FASTAPI_HEALTH", "http://127.0.0.1:8000/")
RUN_E2E = os.getenv("RUN_PULSE_E2E") == "1"

TEST_STORE = {
    "shopInfo_name": "바람난왕족발보쌈 범계점",
    "shopInfo_address": "경기 안양시 동안구 평촌대로223번길 48",
}

pytestmark = pytest.mark.e2e


def _require_live_server() -> None:
    if not RUN_E2E:
        pytest.skip("Set RUN_PULSE_E2E=1 to run live FastAPI E2E tests.")

    try:
        response = requests.get(FASTAPI_HEALTH, timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:
        pytest.skip(f"FastAPI server unavailable: {exc}")


def test_pipeline() -> None:
    _require_live_server()

    request_response = requests.post(
        f"{FASTAPI_BASE}/analysis/request",
        json=TEST_STORE,
        timeout=10,
    )
    assert request_response.status_code == 200, request_response.text

    task_id = request_response.json()["task_id"]
    max_wait_seconds = 300
    started_at = time.time()

    while time.time() - started_at < max_wait_seconds:
        status_response = requests.get(
            f"{FASTAPI_BASE}/analysis/status/{task_id}",
            timeout=10,
        )
        assert status_response.status_code == 200, status_response.text

        status = status_response.json()
        if status["status"] == "completed":
            break
        if status["status"] == "failed":
            pytest.fail(f"Analysis failed: {status['message']}")

        time.sleep(5)
    else:
        pytest.fail(f"Analysis timed out after {max_wait_seconds}s")

    result_response = requests.get(
        f"{FASTAPI_BASE}/analysis/result/{task_id}",
        timeout=10,
    )
    assert result_response.status_code == 200, result_response.text

    result = result_response.json()

    for field in [
        "store_name",
        "average_rating",
        "total_reviews",
        "store_summary",
        "personas",
    ]:
        assert field in result, f"Missing top-level field: {field}"

    personas = result.get("personas", [])
    assert personas, "Expected at least one persona in the analysis result"

    first_persona = personas[0]
    for field in ["id", "nickname", "tags", "img", "summary", "journey"]:
        assert field in first_persona, f"Missing persona field: {field}"

    journey = first_persona["journey"]
    for step_name in ["explore", "visit", "eat", "share"]:
        assert step_name in journey, f"Missing journey step: {step_name}"

    with open("test_result.json", "w", encoding="utf-8") as result_file:
        json.dump(result, result_file, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    os.environ.setdefault("RUN_PULSE_E2E", "1")
    raise SystemExit(pytest.main([__file__]))
