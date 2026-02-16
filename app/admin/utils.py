from typing import Any

from app.models import Artifact, Run, RunStatus


def compute_export_gate(run: Run, fr_artifact: Artifact | None, en_artifact: Artifact | None) -> dict[str, Any]:
    checks = {
        "run_succeeded": run.status == RunStatus.SUCCEEDED,
        "artifact_fr_exists": fr_artifact is not None,
        "artifact_en_exists": en_artifact is not None,
        "artifact_fr_reviewed": bool(fr_artifact and fr_artifact.reviewed),
        "artifact_en_reviewed": bool(en_artifact and en_artifact.reviewed),
        "claims_to_verify_empty": True,
    }

    meta = run.meta if isinstance(run.meta, dict) else {}
    claims_to_verify = meta.get("claims_to_verify")
    if claims_to_verify:
        checks["claims_to_verify_empty"] = False

    reasons: list[str] = []
    if not checks["run_succeeded"]:
        reasons.append(f"run.status must be 'succeeded' (current: '{run.status.value}')")
    if not checks["artifact_fr_exists"]:
        reasons.append("missing artifact for lang='fr'")
    if not checks["artifact_en_exists"]:
        reasons.append("missing artifact for lang='en'")
    if not checks["artifact_fr_reviewed"]:
        reasons.append("artifact 'fr' must have reviewed=true")
    if not checks["artifact_en_reviewed"]:
        reasons.append("artifact 'en' must have reviewed=true")
    if not checks["claims_to_verify_empty"]:
        reasons.append("run.meta.claims_to_verify must be empty or missing")

    return {"ready": all(checks.values()), "reasons": reasons, "checks": checks}
