"""Authentication and authorization utilities.

Placeholder for future auth implementation.
Could integrate with:
- OAuth2/OIDC
- API keys
- JWT tokens
- USC Shibboleth
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException


async def verify_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
) -> str | None:
    """
    Verify API key from header.
    
    Currently a no-op placeholder. Enable by setting REQUIRE_AUTH=true.
    
    In production, validate against:
    - Database of valid keys
    - External auth service
    - Environment variable whitelist
    """
    # Placeholder: accept any request
    # To enable: check x_api_key against valid keys
    return x_api_key


async def get_current_user(
    api_key: Annotated[str | None, Depends(verify_api_key)],
) -> dict:
    """
    Get current user context.
    
    Returns user info that can be used for:
    - Audit logging
    - Rate limiting
    - Access control
    """
    # Placeholder: return anonymous user
    return {
        "user_id": "anonymous",
        "groups": ["ADV-ALL"],  # Default group for access control
    }


class AuthError(HTTPException):
    """Authentication/authorization error."""
    
    def __init__(self, detail: str = "Authentication required"):
        super().__init__(status_code=401, detail=detail)


class ForbiddenError(HTTPException):
    """Access forbidden error."""
    
    def __init__(self, detail: str = "Access denied"):
        super().__init__(status_code=403, detail=detail)

