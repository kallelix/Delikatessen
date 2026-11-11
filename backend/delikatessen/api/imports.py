"""Import per Link oder Teilen-Menü (D-LINK, Abschnitt 7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import Settings
from ..images import ImageError, save_image
from ..importer import download_image
from ..models import ImportJob
from .deps import get_db, get_settings
from .recipes import create_recipe, detail
from .schemas import ImportAccept, ImportIn, ImportOut, RecipeOut

router = APIRouter()


def job_out(job: ImportJob) -> ImportOut:
    return ImportOut(
        id=job.id,
        kind=job.kind,
        source=job.source,
        status=job.status,
        result=job.result,
        error=job.error,
        recipe_id=job.recipe_id,
    )


@router.post("/imports", response_model=ImportOut, status_code=202)
def post_import(data: ImportIn, request: Request, db: Session = Depends(get_db)):
    job = ImportJob(kind=data.kind, source=str(data.url), status="wartet")
    db.add(job)
    db.commit()
    request.app.state.imports.submit(job.id)
    return job_out(job)


@router.get("/imports/{job_id}", response_model=ImportOut)
def get_import(job_id: int, db: Session = Depends(get_db)):
    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(404, "Import nicht gefunden")
    return job_out(job)


@router.post("/imports/{job_id}/accept", response_model=RecipeOut, status_code=201)
def accept_import(
    job_id: int, data: ImportAccept, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
):
    """Übernimmt die geprüfte Vorschau als Rezept. Ohne diese Bestätigung wird nichts gespeichert."""
    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(404, "Import nicht gefunden")
    if job.status not in ("fertig", "ohne_schema", "fehler"):
        raise HTTPException(409, "Der Import ist noch nicht fertig oder schon übernommen")
    recipe = create_recipe(db, data.recipe)
    if data.image_url:
        raw = download_image(data.image_url, settings)
        if raw:
            try:
                recipe.image = save_image(raw, settings.image_dir)
            except ImageError:
                pass
    job.status = "uebernommen"
    job.recipe_id = recipe.id
    db.commit()
    return detail(recipe, None)
