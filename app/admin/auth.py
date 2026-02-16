import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings

security = HTTPBasic(auto_error=False)


def require_admin_access(
    request: Request, credentials: HTTPBasicCredentials | None = Depends(security)
) -> None:
    if settings.admin_user and settings.admin_pass:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Basic"},
            )

        valid_user = secrets.compare_digest(credentials.username, settings.admin_user)
        valid_pass = secrets.compare_digest(credentials.password, settings.admin_pass)
        if not (valid_user and valid_pass):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        return

    client_host = (request.client.host if request.client else "") or ""
    allowed_hosts = {"127.0.0.1", "::1", "localhost"}
    if client_host not in allowed_hosts:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access allowed from localhost only")
