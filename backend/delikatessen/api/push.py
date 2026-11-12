"""Benachrichtigungen: Geräte an- und abmelden, Testnachricht, Donnerstagslauf von Hand (F-24)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import push
from ..config import Settings
from ..models import Person, PushSubscription
from .deps import current_person, get_db, get_settings, get_today, require_adult

router = APIRouter()


class Keys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=4, max_length=100)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000, pattern=r"^https://")
    keys: Keys


class EndpointIn(BaseModel):
    endpoint: str = Field(max_length=1000)


@router.get("/push/key")
def get_key(settings: Settings = Depends(get_settings)):
    """Öffentlicher VAPID-Schlüssel für pushManager.subscribe()."""
    return {"public_key": push.public_key(settings)}


@router.post("/push/subscriptions", status_code=201)
def subscribe(data: SubscriptionIn, db: Session = Depends(get_db), person: Person | None = Depends(current_person)):
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == data.endpoint))
    if sub is None:
        sub = PushSubscription(endpoint=data.endpoint)
        db.add(sub)
    sub.p256dh, sub.auth = data.keys.p256dh, data.keys.auth
    sub.person_id = person.id if person else None
    db.commit()
    return {"id": sub.id}


@router.delete("/push/subscriptions", status_code=204)
def unsubscribe(data: EndpointIn, db: Session = Depends(get_db)):
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == data.endpoint))
    if sub is not None:
        db.delete(sub)
        db.commit()
    return Response(status_code=204)


@router.post("/push/test")
def test_message(data: EndpointIn, request: Request, db: Session = Depends(get_db), settings=Depends(get_settings)):
    """Testnachricht an genau dieses Gerät."""
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == data.endpoint))
    if sub is None:
        raise HTTPException(404, "Dieses Gerät ist nicht angemeldet")
    sender = request.app.state.push_sender_factory(settings)
    return push.send_all(db, sender, "Delikatessen", "So sieht eine Benachrichtigung aus.", "/mehr", only=[sub])


@router.post("/push/donnerstagslauf", dependencies=[Depends(require_adult)])
def run_now(request: Request, today=Depends(get_today), settings=Depends(get_settings)):
    """Den Donnerstagslauf sofort ausführen, etwa zum Ausprobieren (AK-26)."""
    from ..scheduler import thursday_run

    sender = request.app.state.push_sender_factory(settings)
    return thursday_run(request.app.state.db.sessionmaker, today, sender)
