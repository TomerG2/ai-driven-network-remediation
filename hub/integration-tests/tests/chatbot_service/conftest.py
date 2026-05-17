import os

import httpx
import pytest


@pytest.fixture(scope="session")
def chatbot_client():
    base_url = os.environ.get("CHATBOT_SERVICE_URL", "http://localhost:8080")
    with httpx.Client(base_url=base_url) as client:
        yield client
