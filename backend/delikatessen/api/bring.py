"""Bring!: Konto, Liste, Übertragung der Einkaufsliste (F-32, F-33, Abschnitt 8)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..bring import BringClient, BringError
from ..config import Settings
from ..crypto import SecretError, decrypt, encrypt
from ..models import Setting
from ..shopping import transfer_to_bring
from .deps import get_db, get_settings, get_today, require_adult

router = APIRouter()

KEY = "bring"


class BringConfig(BaseModel):
    enabled: bool = False
    mail: str | None = None
    password: str | None = None  # verschlüsselt
    list_uuid: str | None = None
    list_name: str | None = None


class BringOut(BaseModel):
    enabled: bool
    configured: bool
    mail: str | None
    list_uuid: str | None
    list_name: str | None
    secret_key_missing: bool


class BringIn(BaseModel):
    enabled: bool
    list_uuid: str | None = None
    list_name: str | None = Field(None, max_length=200)


class BringAccountIn(BaseModel):
    mail: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class BringListOut(BaseModel):
    uuid: str
    name: str


class TransferOut(BaseModel):
    uebertragen: int
    entfernt: int
    liste: str | None


def load_config(db: Session) -> BringConfig:
    row = db.get(Setting, KEY)
    return BringConfig.model_validate(row.value) if row and isinstance(row.value, dict) else BringConfig()


def save_config(db: Session, cfg: BringConfig) -> None:
    row = db.get(Setting, KEY)
    data = cfg.model_dump()
    if row is None:
        db.add(Setting(key=KEY, value=data))
    else:
        row.value = data
    db.commit()


def out(cfg: BringConfig, settings: Settings) -> BringOut:
    return BringOut(
        enabled=cfg.enabled,
        configured=bool(cfg.mail and cfg.password),
        mail=cfg.mail,
        list_uuid=cfg.list_uuid,
        list_name=cfg.list_name,
        secret_key_missing=not settings.secret_key,
    )


def make_client(request: Request, mail: str, password: str) -> BringClient:
    return request.app.state.bring_factory(mail, password)


def client_from_config(request: Request, cfg: BringConfig, settings: Settings) -> BringClient:
    if not (cfg.mail and cfg.password):
        raise HTTPException(409, "Bring! ist noch nicht eingerichtet")
    try:
        password = decrypt(settings.secret_key, cfg.password)
    except SecretError as e:
        raise HTTPException(409, str(e)) from e
    return make_client(request, cfg.mail, password)


def status(db: Session, settings: Settings) -> dict:
    cfg = load_config(db)
    if not cfg.enabled:
        return {"aktiv": False, "hinweis": "abgeschaltet"}
    if not (cfg.mail and cfg.password and cfg.list_uuid):
        return {"aktiv": False, "hinweis": "nicht vollständig eingerichtet"}
    return {"aktiv": True, "hinweis": f"Liste „{cfg.list_name or cfg.list_uuid}“"}


@router.get("/bring", response_model=BringOut)
def get_bring(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return out(load_config(db), settings)


@router.put("/bring", response_model=BringOut, dependencies=[Depends(require_adult)])
def put_bring(data: BringIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    cfg = load_config(db)
    cfg.enabled = data.enabled
    if data.list_uuid is not None:
        cfg.list_uuid, cfg.list_name = data.list_uuid, data.list_name
    save_config(db, cfg)
    return out(cfg, settings)


@router.put("/bring/account", response_model=list[BringListOut], dependencies=[Depends(require_adult)])
def put_account(
    data: BringAccountIn,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Prüft die Zugangsdaten mit einer Anmeldung und speichert sie verschlüsselt. Liefert die Listen zur Auswahl."""
    if not settings.secret_key:
        raise HTTPException(409, "DELIKATESSEN_SECRET_KEY fehlt in /etc/delikatessen/env, siehe docs/betrieb.md")
    try:
        lists = make_client(request, data.mail, data.password).lists()
    except BringError as e:
        raise HTTPException(502, str(e)) from e
    cfg = load_config(db)
    cfg.mail, cfg.password = data.mail.strip(), encrypt(settings.secret_key, data.password)
    if cfg.list_uuid not in {x.uuid for x in lists}:
        cfg.list_uuid, cfg.list_name = (lists[0].uuid, lists[0].name) if lists else (None, None)
    cfg.enabled = True
    save_config(db, cfg)
    return [BringListOut(uuid=x.uuid, name=x.name) for x in lists]


@router.delete("/bring/account", response_model=BringOut, dependencies=[Depends(require_adult)])
def delete_account(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    cfg = BringConfig()
    save_config(db, cfg)
    return out(cfg, settings)


@router.get("/bring/lists", response_model=list[BringListOut], dependencies=[Depends(require_adult)])
def get_lists(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    client = client_from_config(request, load_config(db), settings)
    try:
        return [BringListOut(uuid=x.uuid, name=x.name) for x in client.lists()]
    except BringError as e:
        raise HTTPException(502, str(e)) from e


@router.post("/plans/{start}/shopping/bring", response_model=TransferOut)
def post_transfer(
    start: str,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    today: date = Depends(get_today),
):
    from .plans import load_week

    cfg = load_config(db)
    if not cfg.enabled:
        raise HTTPException(409, "Bring! ist in den Einstellungen abgeschaltet")
    if not cfg.list_uuid:
        raise HTTPException(409, "Bitte in den Einstellungen eine Bring!-Liste wählen")
    client = client_from_config(request, cfg, settings)
    week = load_week(db, start, today)
    try:
        result = transfer_to_bring(db, week, client, cfg.list_uuid)
    except BringError as e:
        db.rollback()
        raise HTTPException(502, str(e)) from e
    return TransferOut(**result, liste=cfg.list_name)
