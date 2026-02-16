from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.dependencies import get_db
from app.models import Artifact, ArtifactLang, Run, RunStatus
from app.schemas import ExportResponse

router = APIRouter(tags=["export"])


def _render_mdx(frontmatter: dict[str, Any], body_mdx: str) -> str:
    fm_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{fm_text}\n---\n\n{body_mdx.rstrip()}\n"


def _validate_export_gates(run: Run, fr_artifact: Artifact | None, en_artifact: Artifact | None) -> list[str]:
    reasons: list[str] = []

    if run.status != RunStatus.SUCCEEDED:
        reasons.append(f"run.status must be 'succeeded' (current: '{run.status.value}')")

    if fr_artifact is None:
        reasons.append("missing artifact for lang='fr'")
    if en_artifact is None:
        reasons.append("missing artifact for lang='en'")

    if fr_artifact is not None and not fr_artifact.reviewed:
        reasons.append("artifact 'fr' must have reviewed=true")
    if en_artifact is not None and not en_artifact.reviewed:
        reasons.append("artifact 'en' must have reviewed=true")

    meta = run.meta if isinstance(run.meta, dict) else {}
    claims_to_verify = meta.get("claims_to_verify")
    if claims_to_verify:
        reasons.append("run.meta.claims_to_verify must be empty or missing")

    return reasons


@router.post("/runs/{id}/export", response_model=ExportResponse)
def export_run(id: UUID, db: Session = Depends(get_db)) -> ExportResponse:
    run = db.scalar(select(Run).options(selectinload(Run.topic)).where(Run.id == id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    artifacts = list(db.scalars(select(Artifact).where(Artifact.run_id == run.id)))
    fr_artifact = next((a for a in artifacts if a.lang == ArtifactLang.FR), None)
    en_artifact = next((a for a in artifacts if a.lang == ArtifactLang.EN), None)

    reasons = _validate_export_gates(run, fr_artifact, en_artifact)
    if reasons:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Export blocked by strict gates",
                "reasons": reasons,
            },
        )

    if not settings.blog_repo_path:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="BLOG_REPO_PATH is not configured")

    repo_root = Path(settings.blog_repo_path)
    fr_path = repo_root / "src" / "content" / "blog" / "fr" / f"{run.topic.slug}.mdx"
    en_path = repo_root / "src" / "content" / "blog" / "en" / f"{run.topic.slug}.mdx"

    fr_path.parent.mkdir(parents=True, exist_ok=True)
    en_path.parent.mkdir(parents=True, exist_ok=True)

    fr_path.write_text(_render_mdx(fr_artifact.frontmatter, fr_artifact.body_mdx), encoding="utf-8")
    en_path.write_text(_render_mdx(en_artifact.frontmatter, en_artifact.body_mdx), encoding="utf-8")

    return ExportResponse(
        run_id=run.id,
        slug=run.topic.slug,
        files={"fr": str(fr_path), "en": str(en_path)},
    )
