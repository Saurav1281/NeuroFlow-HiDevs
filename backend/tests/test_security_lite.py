from typing import Any

from fastapi import Depends, FastAPI, Security
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from fastapi.testclient import TestClient

app = FastAPI()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_current_user(
    security_scopes: SecurityScopes, token: str = Depends(oauth2_scheme)
) -> dict[str, Any]:
    return {"token": token, "scopes": security_scopes.scopes}


@app.get("/test")
async def read_test(
    user: dict[str, Any] = Security(get_current_user, scopes=["admin"]),
) -> dict[str, Any]:
    return user


def test_security_scopes() -> None:
    client = TestClient(app)
    # This should return 401 because no token is provided
    response = client.get("/test")
    assert response.status_code == 401
