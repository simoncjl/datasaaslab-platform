import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.admin.auth import require_admin_access
from app.admin.utils import compute_export_gate
from app.config import settings
from app.dependencies import get_db
from app.models import Artifact, ArtifactLang, Run, RunStatus, Topic
from app.tasks import generate_run

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin_access)])
templates = Jinja2Templates(directory="app/templates")


def _tags_from_input(tags_input: str) -> dict:
    tags = [t.strip() for t in tags_input.split(",") if t.strip()]
    return {"items": tags}


def _tags_to_text(tags: dict | None) -> str:
    if not isinstance(tags, dict):
        return ""
    values = tags.get("items", [])
    if isinstance(values, list):
        return ", ".join(str(v) for v in values)
    return ""


def _bullets_to_text(blob: dict | None) -> str:
    if not isinstance(blob, dict):
        return ""
    values = blob.get("bullets", [])
    if isinstance(values, list):
        return "\n".join(str(v) for v in values)
    return ""


def _build_topic_payload(
    slug: str,
    tags_text: str,
    fr_title: str,
    fr_description: str,
    en_title: str,
    en_description: str,
    context_bullets: str,
    constraints_bullets: str,
    author_inputs_text: str,
) -> tuple[dict, str | None]:
    slug = slug.strip()
    if not slug:
        return {}, "Slug is required"

    try:
        author_inputs = json.loads(author_inputs_text.strip() or "{}")
        if not isinstance(author_inputs, dict):
            return {}, "author_inputs JSON must be an object"
    except json.JSONDecodeError as exc:
        return {}, f"Invalid author_inputs JSON: {exc.msg}"

    payload = {
        "slug": slug,
        "tags": _tags_from_input(tags_text),
        "fr_content": {"title": fr_title.strip(), "description": fr_description.strip()},
        "en_content": {"title": en_title.strip(), "description": en_description.strip()},
        "context": {"bullets": [line.strip() for line in context_bullets.splitlines() if line.strip()]},
        "constraints_json": {"bullets": [line.strip() for line in constraints_bullets.splitlines() if line.strip()]},
        "author_inputs": author_inputs,
    }
    return payload, None


def _topic_form_context(topic: Topic | None = None) -> dict:
    if topic is None:
        return {
            "id": None,
            "slug": "",
            "tags": "",
            "fr_title": "",
            "fr_description": "",
            "en_title": "",
            "en_description": "",
            "context_bullets": "",
            "constraints_bullets": "",
            "author_inputs": "{}",
        }

    return {
        "id": topic.id,
        "slug": topic.slug,
        "tags": _tags_to_text(topic.tags),
        "fr_title": topic.fr_content.get("title", "") if isinstance(topic.fr_content, dict) else "",
        "fr_description": topic.fr_content.get("description", "") if isinstance(topic.fr_content, dict) else "",
        "en_title": topic.en_content.get("title", "") if isinstance(topic.en_content, dict) else "",
        "en_description": topic.en_content.get("description", "") if isinstance(topic.en_content, dict) else "",
        "context_bullets": _bullets_to_text(topic.context),
        "constraints_bullets": _bullets_to_text(topic.constraints_json),
        "author_inputs": json.dumps(topic.author_inputs or {}, indent=2),
    }


def _run_context(run: Run, export_message: str | None = None, export_files: dict[str, str] | None = None) -> dict:
    artifacts_by_lang = {artifact.lang: artifact for artifact in run.artifacts}
    fr_artifact = artifacts_by_lang.get(ArtifactLang.FR)
    en_artifact = artifacts_by_lang.get(ArtifactLang.EN)
    export_gate = compute_export_gate(run, fr_artifact, en_artifact)

    meta = run.meta if isinstance(run.meta, dict) else {}
    return {
        "run": run,
        "topic": run.topic,
        "fr_artifact": fr_artifact,
        "en_artifact": en_artifact,
        "export_gate": export_gate,
        "claims_to_verify": meta.get("claims_to_verify", []),
        "questions_for_author": meta.get("questions_for_author", []),
        "diagram_suggestions": meta.get("diagram_suggestions", []),
        "tables_to_include": meta.get("tables_to_include", []),
        "export_message": export_message,
        "export_files": export_files or {},
    }


def _render_mdx(frontmatter: dict[str, Any], body_mdx: str) -> str:
    fm_text = yaml.safe_dump(frontmatter or {}, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{fm_text}\n---\n\n{(body_mdx or '').rstrip()}\n"


@router.get("")
def admin_index() -> RedirectResponse:
    return RedirectResponse(url="/admin/topics", status_code=302)


@router.get("/topics")
def admin_topics(request: Request, db: Session = Depends(get_db)):
    topics = list(db.scalars(select(Topic).order_by(Topic.created_at.desc())))
    return templates.TemplateResponse("admin/topics.html", {"request": request, "topics": topics})


@router.get("/topics/new")
def admin_topic_new(request: Request):
    return templates.TemplateResponse(
        "admin/topic_detail.html",
        {"request": request, "topic": None, "form": _topic_form_context(None), "message": None, "level": "info"},
    )


@router.get("/topics/{id}")
def admin_topic_edit(id: UUID, request: Request, db: Session = Depends(get_db)):
    topic = db.get(Topic, id)
    if topic is None:
        return RedirectResponse(url="/admin/topics", status_code=302)
    return templates.TemplateResponse(
        "admin/topic_detail.html",
        {"request": request, "topic": topic, "form": _topic_form_context(topic), "message": None, "level": "info"},
    )


@router.post("/topics")
def admin_topic_create(
    request: Request,
    db: Session = Depends(get_db),
    slug: str = Form(""),
    tags: str = Form(""),
    fr_title: str = Form(""),
    fr_description: str = Form(""),
    en_title: str = Form(""),
    en_description: str = Form(""),
    context_bullets: str = Form(""),
    constraints_bullets: str = Form(""),
    author_inputs: str = Form("{}"),
):
    payload, error = _build_topic_payload(
        slug,
        tags,
        fr_title,
        fr_description,
        en_title,
        en_description,
        context_bullets,
        constraints_bullets,
        author_inputs,
    )
    if error:
        return templates.TemplateResponse(
            "admin/topic_detail.html",
            {
                "request": request,
                "topic": None,
                "form": {
                    "id": None,
                    "slug": slug,
                    "tags": tags,
                    "fr_title": fr_title,
                    "fr_description": fr_description,
                    "en_title": en_title,
                    "en_description": en_description,
                    "context_bullets": context_bullets,
                    "constraints_bullets": constraints_bullets,
                    "author_inputs": author_inputs,
                },
                "message": error,
                "level": "error",
            },
            status_code=400,
        )

    topic = Topic(**payload)
    db.add(topic)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            "admin/topic_detail.html",
            {
                "request": request,
                "topic": None,
                "form": {
                    "id": None,
                    "slug": slug,
                    "tags": tags,
                    "fr_title": fr_title,
                    "fr_description": fr_description,
                    "en_title": en_title,
                    "en_description": en_description,
                    "context_bullets": context_bullets,
                    "constraints_bullets": constraints_bullets,
                    "author_inputs": author_inputs,
                },
                "message": "Slug already exists.",
                "level": "error",
            },
            status_code=409,
        )
    return RedirectResponse(url=f"/admin/topics/{topic.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/topics/{id}")
def admin_topic_update(
    id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    slug: str = Form(""),
    tags: str = Form(""),
    fr_title: str = Form(""),
    fr_description: str = Form(""),
    en_title: str = Form(""),
    en_description: str = Form(""),
    context_bullets: str = Form(""),
    constraints_bullets: str = Form(""),
    author_inputs: str = Form("{}"),
):
    topic = db.get(Topic, id)
    if topic is None:
        return RedirectResponse(url="/admin/topics", status_code=302)

    payload, error = _build_topic_payload(
        slug,
        tags,
        fr_title,
        fr_description,
        en_title,
        en_description,
        context_bullets,
        constraints_bullets,
        author_inputs,
    )
    if error:
        return templates.TemplateResponse(
            "admin/topic_detail.html",
            {
                "request": request,
                "topic": topic,
                "form": {
                    "id": topic.id,
                    "slug": slug,
                    "tags": tags,
                    "fr_title": fr_title,
                    "fr_description": fr_description,
                    "en_title": en_title,
                    "en_description": en_description,
                    "context_bullets": context_bullets,
                    "constraints_bullets": constraints_bullets,
                    "author_inputs": author_inputs,
                },
                "message": error,
                "level": "error",
            },
            status_code=400,
        )

    topic.slug = payload["slug"]
    topic.tags = payload["tags"]
    topic.fr_content = payload["fr_content"]
    topic.en_content = payload["en_content"]
    topic.context = payload["context"]
    topic.constraints_json = payload["constraints_json"]
    topic.author_inputs = payload["author_inputs"]

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            "admin/topic_detail.html",
            {
                "request": request,
                "topic": topic,
                "form": {
                    "id": topic.id,
                    "slug": slug,
                    "tags": tags,
                    "fr_title": fr_title,
                    "fr_description": fr_description,
                    "en_title": en_title,
                    "en_description": en_description,
                    "context_bullets": context_bullets,
                    "constraints_bullets": constraints_bullets,
                    "author_inputs": author_inputs,
                },
                "message": "Slug already exists.",
                "level": "error",
            },
            status_code=409,
        )
    return RedirectResponse(url=f"/admin/topics/{topic.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/topics/{id}/generate")
def admin_generate_topic(id: UUID, request: Request, db: Session = Depends(get_db)):
    topic = db.get(Topic, id)
    if topic is None:
        return RedirectResponse(url="/admin/topics", status_code=302)

    run = Run(topic_id=topic.id, status=RunStatus.QUEUED, model=None, meta={})
    db.add(run)
    db.commit()
    db.refresh(run)

    generate_run.delay(str(run.id))
    target_url = f"/admin/runs/{run.id}"
    if request.headers.get("HX-Request") == "true":
        response = Response(status_code=status.HTTP_200_OK)
        response.headers["HX-Redirect"] = target_url
        return response
    return RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/runs/{run_id}")
def admin_run_detail(run_id: UUID, request: Request, db: Session = Depends(get_db)):
    run = db.scalar(select(Run).options(selectinload(Run.topic), selectinload(Run.artifacts)).where(Run.id == run_id))
    if run is None:
        return RedirectResponse(url="/admin/topics", status_code=302)
    context = {"request": request, **_run_context(run)}
    return templates.TemplateResponse("admin/run_detail.html", context)


@router.get("/runs/{run_id}/status")
def admin_run_status(run_id: UUID, request: Request, db: Session = Depends(get_db)):
    run = db.scalar(select(Run).options(selectinload(Run.topic)).where(Run.id == run_id))
    if run is None:
        return Response("Run not found", status_code=404)
    return templates.TemplateResponse("admin/partials/run_status.html", {"request": request, "run": run, "topic": run.topic})


@router.patch("/artifacts/{artifact_id}")
def admin_patch_artifact(
    artifact_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    body_mdx: str = Form(""),
    reviewed: str | None = Form(None),
    review_notes: str = Form(""),
):
    artifact = db.get(Artifact, artifact_id)
    if artifact is None:
        response = Response(status_code=404)
        response.body = b"Artifact not found"
        return response

    artifact.body_mdx = body_mdx
    artifact.reviewed = reviewed is not None
    artifact.review_notes = review_notes.strip() or None
    db.commit()

    run = db.scalar(select(Run).options(selectinload(Run.topic), selectinload(Run.artifacts)).where(Run.id == artifact.run_id))
    context = _run_context(run)

    return templates.TemplateResponse(
        "admin/partials/artifact_save_status.html",
        {
            "request": request,
            "artifact": artifact,
            "saved_at": datetime.now(timezone.utc),
            **context,
        },
    )


@router.post("/runs/{run_id}/export")
def admin_export_run(run_id: UUID, request: Request, db: Session = Depends(get_db)):
    run = db.scalar(select(Run).options(selectinload(Run.topic), selectinload(Run.artifacts)).where(Run.id == run_id))
    if run is None:
        return Response("Run not found", status_code=404)

    context = _run_context(run)
    if not context["export_gate"]["ready"]:
        return templates.TemplateResponse(
            "admin/partials/export_panel.html",
            {"request": request, **context},
            status_code=409,
        )

    if not settings.blog_repo_path:
        context["export_gate"]["ready"] = False
        context["export_gate"]["reasons"].append("BLOG_REPO_PATH is not configured")
        return templates.TemplateResponse(
            "admin/partials/export_panel.html",
            {"request": request, **context},
            status_code=500,
        )

    repo_root = Path(settings.blog_repo_path)
    fr_path = repo_root / "src" / "content" / "blog" / "fr" / f"{run.topic.slug}.mdx"
    en_path = repo_root / "src" / "content" / "blog" / "en" / f"{run.topic.slug}.mdx"

    fr_path.parent.mkdir(parents=True, exist_ok=True)
    en_path.parent.mkdir(parents=True, exist_ok=True)

    fr_artifact = context["fr_artifact"]
    en_artifact = context["en_artifact"]
    fr_path.write_text(_render_mdx(fr_artifact.frontmatter, fr_artifact.body_mdx), encoding="utf-8")
    en_path.write_text(_render_mdx(en_artifact.frontmatter, en_artifact.body_mdx), encoding="utf-8")

    context = _run_context(
        run,
        export_message="Export completed. Both FR+EN files were written.",
        export_files={"fr": str(fr_path), "en": str(en_path)},
    )
    return templates.TemplateResponse("admin/partials/export_panel.html", {"request": request, **context})


@router.get("/batches")
def admin_batches(request: Request):
    return templates.TemplateResponse(
        "admin/topics.html",
        {"request": request, "topics": [], "message": "Batch admin page will be available in a later step."},
    )
