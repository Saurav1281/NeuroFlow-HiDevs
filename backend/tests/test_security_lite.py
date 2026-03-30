from fastapi import FastAPI, Security, Depends
from fastapi.security import SecurityScopes, OAuth2PasswordBearer
from fastapi.testclient import TestClient
import pytest

app = FastAPI()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(security_scopes: SecurityScopes, token: str = Depends(oauth2_scheme)):
    return {"token": token, "scopes": security_scopes.scopes}

@app.get("/test")
async def read_test(user = Security(get_current_user, scopes=["admin"])):
    return user

def test_security_scopes():
    client = TestClient(app)
    # This should return 401 because no token is provided
    response = client.get("/test")
    assert response.status_code == 401
