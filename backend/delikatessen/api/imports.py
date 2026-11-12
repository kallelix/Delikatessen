"""Import per Link oder Teilen-Menü (D-LINK, Abschnitt 7)."""

from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import ki
from ..config import Settings
from ..images import MAX_UPLOAD, ROTATIONS, ImageError, prepare_for_ki, save_image
from ..importer import dish_image, download_image, photo_dir
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


MAX_PHOTOS = 4


def require_ki(settings: Settings) -> None:
    """Text und Fotos gehen nur mit KI. Ein erschöpftes Budget meldet die App sofort (AK-25)."""
    s = ki.status(settings)
    if not settings.ki_configured:
        raise HTTPException(409, "Import aus Text und Fotos braucht den KI-Dienst, der ist nicht eingerichtet")
    if not s["aktiv"]:
        raise HTTPException(409, ki.MSG_BUDGET)


@router.post("/imports", response_model=ImportOut, status_code=202)
def post_import(
    data: ImportIn, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
):
    if data.kind == "text":
        require_ki(settings)
        job = ImportJob(kind="text", source=data.text.strip(), status="wartet")
    else:
        job = ImportJob(kind="link", source=str(data.url), status="wartet")
    db.add(job)
    db.commit()
    request.app.state.imports.submit(job.id)
    return job_out(job)


@router.post("/imports/foto", response_model=ImportOut, status_code=202)
async def post_photo_import(
    request: Request,
    bilder: list[UploadFile] = File(...),
    drehung: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Bis zu vier Fotos eines Rezepts (D-FOTO). Sie liegen nur bis zur Auswertung auf dem Server.

    drehung: je Foto die in der App gewählte Drehung im Uhrzeigersinn (0, 90, 180, 270), optional.
    """
    require_ki(settings)
    if not 1 <= len(bilder) <= MAX_PHOTOS:
        raise HTTPException(422, f"Bitte ein bis {MAX_PHOTOS} Fotos")
    if drehung and (len(drehung) != len(bilder) or any(d not in ROTATIONS for d in drehung)):
        raise HTTPException(422, "Ungültige Drehung der Fotos")
    prepared = []
    for i, f in enumerate(bilder):
        raw = await f.read(MAX_UPLOAD + 1)
        try:
            prepared.append(await run_in_threadpool(prepare_for_ki, raw, drehung[i] if drehung else 0))
        except ImageError as e:
            raise HTTPException(422, str(e)) from e
    job = ImportJob(kind="foto", source=f"{len(prepared)} Foto{'s' if len(prepared) > 1 else ''}", status="wartet")
    db.add(job)
    db.commit()
    folder = photo_dir(settings, job.id)
    folder.mkdir(parents=True, exist_ok=True)
    for i, data in enumerate(prepared):
        (folder / f"{i}.jpg").write_bytes(data)
    request.app.state.imports.submit(job.id)
    return job_out(job)


@router.get("/imports/{job_id}", response_model=ImportOut)
def get_import(job_id: int, db: Session = Depends(get_db)):
    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(404, "Import nicht gefunden")
    return job_out(job)


@router.get("/imports/{job_id}/bild")
def get_dish_image(job_id: int, settings: Settings = Depends(get_settings)):
    """Aus den Fotos ausgeschnittenes Gerichtsbild für die Vorschau."""
    path = dish_image(settings, job_id)
    if path is None:
        raise HTTPException(404, "Bild nicht gefunden")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "no-store"})


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
    local = dish_image(settings, job_id)
    if data.image_url and local is not None and data.image_url == (job.result or {}).get("image_url"):
        # Gerichtsbild aus den Fotos: liegt schon fertig verkleinert als WebP vor
        settings.image_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(local, settings.image_dir / local.name)
        recipe.image = local.name
    elif data.image_url:
        raw = download_image(data.image_url, settings)
        if raw:
            try:
                recipe.image = save_image(raw, settings.image_dir)
            except ImageError:
                pass
    job.status = "uebernommen"
    job.recipe_id = recipe.id
    db.commit()
    if job.kind == "foto":
        shutil.rmtree(photo_dir(settings, job_id), ignore_errors=True)
    return detail(recipe, None)
