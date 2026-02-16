from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.admin.auth import require_admin_access

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin_access)])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("")
def admin_index() -> RedirectResponse:
    return RedirectResponse(url="/admin/topics", status_code=302)


@router.get("/topics")
def admin_topics(request: Request):
    return templates.TemplateResponse("admin/topics.html", {"request": request})


@router.get("/batches")
def admin_batches(request: Request):
    return templates.TemplateResponse(
        "admin/topics.html",
        {"request": request, "message": "Batch admin page will be available in a later step."},
    )
