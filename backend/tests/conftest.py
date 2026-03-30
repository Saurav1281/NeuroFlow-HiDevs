import pytest
import os

# Set environment variables for testing BEFORE importing the app or settings
os.environ["POSTGRES_PASSWORD"] = "testpassword"
os.environ["REDIS_PASSWORD"] = "testpassword"
os.environ["JWT_SECRET_KEY"] = "super-secret-key-for-testing"
os.environ["CLIENT_ID"] = "neuroflow-client"
os.environ["CLIENT_SECRET"] = "neuroflow-secret"

from backend.config import settings

@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "super-secret-key-for-testing")
    monkeypatch.setattr(settings, "CLIENT_ID", "neuroflow-client")
    monkeypatch.setattr(settings, "CLIENT_SECRET", "neuroflow-secret")
