import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from pydantic import BaseModel, Field

from backend.config import settings

logger = logging.getLogger(__name__)

# Prefix is removed here so it can be controlled in main.py or set to /auth
router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


class TokenRequest(BaseModel):
    client_id: str = Field(..., description="The ID of the issuing client.", example="admin-client")
    client_secret: str = Field(
        ..., description="The secret associated with the client_id.", example="admin-secret"
    )

    model_config = {
        "json_schema_extra": {
            "example": {"client_id": "admin-client", "client_secret": "admin-secret"}
        }
    }


class TokenResponse(BaseModel):
    access_token: str = Field(
        ..., description="The generated JWT access token.", example="eyJhbGciOiJIUzI1NiIsInR..."
    )
    token_type: str = Field("bearer", description="The type of token (Bearer).", example="bearer")
    expires_in: int = Field(3600, description="Expiration time in seconds.", example=3600)

    model_config = {
        "json_schema_extra": {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIi...v",
                "token_type": "bearer",
                "expires_in": 3600,
            }
        }
    }


def create_access_token(
    data: dict[str, str | list[str]], expires_delta: timedelta | None = None
) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Get access token",
    description="Authenticate with client_id and client_secret to receive a JWT access token for API access.",
    response_description="A Bearer token granting access to authorized endpoint scopes.",
)
async def login_for_access_token(request: TokenRequest) -> dict[str, str | int]:
    logger.info(f"Token request for {request.client_id}")
    # In a real app, check against database. Here we use mock settings.
    if request.client_id == settings.CLIENT_ID and request.client_secret == settings.CLIENT_SECRET:
        scopes = ["query", "ingest", "admin"]
    elif request.client_id == "admin-client" and request.client_secret == "admin-secret":
        scopes = ["query", "ingest", "admin"]
    elif request.client_id == "query-user" and request.client_secret == "query-secret":
        scopes = ["query"]
    elif request.client_id == "ingest-user" and request.client_secret == "ingest-secret":
        scopes = ["query", "ingest"]
    else:
        logger.warning(f"Auth failed for {request.client_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect client_id or client_secret",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": request.client_id, "scopes": scopes}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "expires_in": 3600}
