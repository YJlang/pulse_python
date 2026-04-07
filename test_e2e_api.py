"""
Live FastAPI API smoke test.

Skipped by default. Run it explicitly by setting RUN_PULSE_E2E=1.
"""

from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = os.getenv("PULSE_FASTAPI_BASE", "http://127.0.0.1:8000/api")
HEALTHCHECK_URL = os.getenv("PULSE_FASTAPI_HEALTH", "http://127.0.0.1:8000/")
RUN_E2E = os.getenv("RUN_PULSE_E2E") == "1"

STORE_NAME = "바람난왕족발보쌈 범계점"
ADDRESS = "경기 안양시 동안구 평촌대로223번길 48 백운빌딩 301호 바람난왕족발보쌈"

pytestmark = pytest.mark.e2e


def _require_live_server() -> None:
    if not RUN_E2E:
        pytest.skip("Set RUN_PULSE_E2E=1 to run live FastAPI E2E tests.")

    try:
        response = requests.get(HEALTHCHECK_URL, timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:
        pytest.skip(f"FastAPI server unavailable: {exc}")


def test_e2e_api_smoke() -> None:
    _require_live_server()

    request_response = requests.post(
        f"{BASE_URL}/analysis/request",
        json={
            "shopInfo_name": STORE_NAME,
            "shopInfo_address": ADDRESS,
        },
        timeout=10,
    )
    assert request_response.status_code == 200, request_response.text

    task_id = request_response.json()["task_id"]

    while True:
        status_response = requests.get(
            f"{BASE_URL}/analysis/status/{task_id}",
            timeout=10,
        )
        assert status_response.status_code == 200, status_response.text

        status_data = status_response.json()
        if status_data["status"] == "completed":
            break
        if status_data["status"] == "failed":
            pytest.fail(f"Analysis failed: {status_data['message']}")

        time.sleep(2)

    result_response = requests.get(
        f"{BASE_URL}/analysis/result/{task_id}",
        timeout=10,
    )
    assert result_response.status_code == 200, result_response.text

    result = result_response.json()
    personas = result.get("personas", [])

    assert personas, "Expected personas in the final result"
    assert "journey" in personas[0], "Expected journey data in the first persona"


if __name__ == "__main__":
    os.environ.setdefault("RUN_PULSE_E2E", "1")
    raise SystemExit(pytest.main([__file__]))
