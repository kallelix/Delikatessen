"""Familie, Profil, Einstellungen und Status (F-40, F-41, N-09)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import __version__, appsettings, ki, push
from ..config import Settings
from ..models import Ingredient, IngredientGroup, Person, PersonNoGo
from .deps import current_person, get_db, get_settings, require_adult
from .schemas import NoGoOut, PersonIn, PersonOut

router = APIRouter()

DEFAULT_FACTOR = {"erwachsen": 1.0, "kind": 0.5}


def person_out(db: Session, p: Person) -> PersonOut:
    nogos = []
    for n in p.nogos:
        if n.ingredient_id:
            ing = db.get(Ingredient, n.ingredient_id)
            nogos.append(NoGoOut(ingredient_id=n.ingredient_id, name=ing.name if ing else "?"))
        else:
            grp = db.get(IngredientGroup, n.group_id)
            nogos.append(NoGoOut(group_id=n.group_id, name=f"{grp.name if grp else '?'} (Gruppe)"))
    return PersonOut(
        id=p.id,
        name=p.name,
        kind=p.kind,
        portion_factor=p.portion_factor,
        active=p.active,
        netbird_ip=p.netbird_ip,
        nogos=sorted(nogos, key=lambda n: n.name.lower()),
    )


def apply_person(db: Session, p: Person, data: PersonIn) -> None:
    p.name = " ".join(data.name.split())
    p.kind = data.kind
    p.portion_factor = data.portion_factor or DEFAULT_FACTOR[data.kind]
    p.active = data.active
    p.netbird_ip = data.netbird_ip
    nogos = []
    seen = set()
    for n in data.nogos:
        if (n.ingredient_id is None) == (n.group_id is None):
            raise HTTPException(422, "Ein No-go ist entweder eine Zutat oder eine Gruppe")
        if n.ingredient_id and db.get(Ingredient, n.ingredient_id) is None:
            raise HTTPException(422, "Unbekannte Zutat")
        if n.group_id and db.get(IngredientGroup, n.group_id) is None:
            raise HTTPException(422, "Unbekannte Gruppe")
        key = (n.ingredient_id, n.group_id)
        if key not in seen:
            seen.add(key)
            nogos.append(PersonNoGo(ingredient_id=n.ingredient_id, group_id=n.group_id))
    p.nogos = nogos


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, "Diese NetBird-IP ist schon einer anderen Person zugeordnet") from e


@router.get("/persons", response_model=list[PersonOut])
def list_persons(db: Session = Depends(get_db)):
    return [person_out(db, p) for p in db.scalars(select(Person).order_by(Person.kind, Person.name))]


@router.post("/persons", response_model=PersonOut, status_code=201, dependencies=[Depends(require_adult)])
def post_person(data: PersonIn, db: Session = Depends(get_db)):
    p = Person()
    apply_person(db, p, data)
    db.add(p)
    _commit(db)
    return person_out(db, p)


@router.put("/persons/{person_id}", response_model=PersonOut, dependencies=[Depends(require_adult)])
def put_person(person_id: int, data: PersonIn, db: Session = Depends(get_db)):
    p = db.get(Person, person_id)
    if p is None:
        raise HTTPException(404, "Person nicht gefunden")
    apply_person(db, p, data)
    _commit(db)
    return person_out(db, p)


@router.delete("/persons/{person_id}", status_code=204, dependencies=[Depends(require_adult)])
def delete_person(person_id: int, db: Session = Depends(get_db)):
    p = db.get(Person, person_id)
    if p is None:
        raise HTTPException(404, "Person nicht gefunden")
    db.delete(p)
    db.commit()
    return Response(status_code=204)


@router.get("/me", response_model=PersonOut | None)
def me(person: Person | None = Depends(current_person), db: Session = Depends(get_db)):
    """Profil aus dem Header der App oder über die NetBird-IP des Geräts."""
    return person_out(db, person) if person else None


@router.get("/settings", response_model=appsettings.AppSettings)
def get_app_settings(db: Session = Depends(get_db)):
    return appsettings.load(db)


@router.put("/settings", response_model=appsettings.AppSettings, dependencies=[Depends(require_adult)])
def put_app_settings(data: appsettings.AppSettings, request: Request, db: Session = Depends(get_db)):
    saved = appsettings.save(db, data)
    # neue Uhrzeit gilt sofort für den Donnerstagslauf (F-24)
    request.app.state.scheduler.reschedule(saved.plan_time)
    return saved


@router.get("/status")
def status(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    from . import bring

    db.execute(select(1))
    return {
        "version": __version__,
        "datenbank": "ok",
        "dienste": {
            "bring": bring.status(db, settings),
            "ki": ki.status(settings),
            "push": push.status(db),
        },
    }
