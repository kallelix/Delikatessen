"""Rezepte, Katalog und Bilder (F-01 bis F-04, F-13, D-TAG, N-13)."""

from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import history, search
from ..catalog import learn_alias, normalize
from ..config import Settings
from ..images import ImageError, delete_image, save_image, valid_name
from ..models import Ingredient, IngredientAlias, IngredientGroup, Recipe, RecipeIngredient, Tag
from ..units import format_quantity
from .deps import get_db, get_settings, get_today
from .schemas import (
    GroupOut,
    IngredientIn,
    IngredientOut,
    RecipeIn,
    RecipeIngredientOut,
    RecipeOut,
    RecipePatch,
    RecipeSummary,
    TagIn,
    TagOut,
)

router = APIRouter()


def image_url(name: str | None) -> str | None:
    return f"/api/v1/images/{name}" if name else None


def summary(r: Recipe) -> RecipeSummary:
    return RecipeSummary(
        id=r.id,
        title=r.title,
        size=r.size,
        duration_min=r.duration_min,
        image_url=image_url(r.image),
        favorite=r.favorite,
        excluded=r.excluded,
        plannable=r.plannable,
        tags=[TagOut.model_validate(t) for t in r.tags],
    )


def detail(r: Recipe, st: history.RecipeStats | None) -> RecipeOut:
    return RecipeOut(
        **summary(r).model_dump(),
        servings=r.servings,
        steps=r.steps or [],
        ingredients=[
            RecipeIngredientOut(
                amount=ri.amount,
                unit=ri.unit,
                name=ri.name,
                note=ri.note,
                ingredient_id=ri.ingredient_id,
                ingredient_name=ri.ingredient.name if ri.ingredient else None,
            )
            for ri in r.ingredients
        ],
        source_url=r.source_url,
        favorite_score=round(history.favorite_score(st, r.favorite), 3),
        cooked_count=len(st.cooked) if st else 0,
        last_cooked=st.last_cooked if st else None,
        cooked_dates=sorted(st.cooked, reverse=True) if st else [],
    )


def ingredient_out(i: Ingredient) -> IngredientOut:
    return IngredientOut(
        id=i.id,
        name=i.name,
        group_id=i.group_id,
        group=i.group.name if i.group else None,
        default_unit=i.default_unit,
        aliases=sorted(a.alias for a in i.aliases),
    )


def apply_recipe(db: Session, recipe: Recipe, data: RecipeIn) -> None:
    recipe.title = " ".join(data.title.split())
    recipe.servings = data.servings
    recipe.size = data.size
    recipe.duration_min = data.duration_min
    recipe.steps = data.steps
    recipe.source_url = data.source_url
    recipe.favorite = data.favorite
    recipe.excluded = data.excluded
    tags = db.scalars(select(Tag).where(Tag.id.in_(data.tag_ids))).all() if data.tag_ids else []
    if len(tags) != len(set(data.tag_ids)):
        raise HTTPException(422, "Unbekannter Tag")
    recipe.tags = list(tags)
    ingredient_ids = {i.ingredient_id for i in data.ingredients if i.ingredient_id}
    known = {i.id: i for i in db.scalars(select(Ingredient).where(Ingredient.id.in_(ingredient_ids)))}
    if len(known) != len(ingredient_ids):
        raise HTTPException(422, "Unbekannte Zutat im Katalog")
    recipe.ingredients = [
        RecipeIngredient(
            position=pos,
            amount=i.amount,
            unit=i.unit,
            name=" ".join(i.name.split()),
            note=i.note,
            ingredient_id=i.ingredient_id,
            ingredient=known.get(i.ingredient_id) if i.ingredient_id else None,
        )
        for pos, i in enumerate(data.ingredients)
    ]
    # jede Zuordnung erweitert die Aliasse (Abschnitt 13, Risiko Zuordnung)
    for i in data.ingredients:
        if i.ingredient_id:
            learn_alias(db, known[i.ingredient_id], i.name)


def create_recipe(db: Session, data: RecipeIn) -> Recipe:
    recipe = Recipe()
    apply_recipe(db, recipe, data)
    db.add(recipe)
    db.flush()
    search.index_recipe(db, recipe)
    db.commit()
    return recipe


def _get(db: Session, recipe_id: int) -> Recipe:
    recipe = db.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(404, "Rezept nicht gefunden")
    return recipe


@router.get("/recipes", response_model=list[RecipeSummary])
def list_recipes(
    q: str | None = None,
    tag: list[int] = Query(default=[]),
    size: str | None = None,
    max_duration: int | None = None,
    favorite: bool | None = None,
    plannable: bool | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Recipe)
    order = None
    if q and q.strip():
        ids = search.search_ids(db, q)
        if not ids:
            return []
        stmt = stmt.where(Recipe.id.in_(ids))
        order = {rid: i for i, rid in enumerate(ids)}
    if size:
        stmt = stmt.where(Recipe.size == size)
    if max_duration:
        stmt = stmt.where(Recipe.duration_min.is_not(None), Recipe.duration_min <= max_duration)
    if favorite is not None:
        stmt = stmt.where(Recipe.favorite.is_(favorite))
    for tag_id in tag:
        stmt = stmt.where(Recipe.tags.any(Tag.id == tag_id))
    recipes = db.scalars(stmt.order_by(func.lower(Recipe.title))).all()
    if plannable is not None:
        recipes = [r for r in recipes if r.plannable == plannable]
    if order is not None:
        recipes = sorted(recipes, key=lambda r: order[r.id])
    return [summary(r) for r in recipes]


@router.post("/recipes", response_model=RecipeOut, status_code=201)
def post_recipe(data: RecipeIn, db: Session = Depends(get_db)):
    return detail(create_recipe(db, data), None)


@router.get("/recipes/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int, db: Session = Depends(get_db), today: date = Depends(get_today)):
    recipe = _get(db, recipe_id)
    return detail(recipe, history.collect(db, today).get(recipe.id))


@router.put("/recipes/{recipe_id}", response_model=RecipeOut)
def put_recipe(recipe_id: int, data: RecipeIn, db: Session = Depends(get_db), today: date = Depends(get_today)):
    recipe = _get(db, recipe_id)
    apply_recipe(db, recipe, data)
    db.flush()
    search.index_recipe(db, recipe)
    db.commit()
    return detail(recipe, history.collect(db, today).get(recipe.id))


@router.patch("/recipes/{recipe_id}", response_model=RecipeSummary)
def patch_recipe(recipe_id: int, data: RecipePatch, db: Session = Depends(get_db)):
    """Favorit setzen oder von der Planung ausschließen, jederzeit umkehrbar (F-13)."""
    recipe = _get(db, recipe_id)
    if data.favorite is not None:
        recipe.favorite = data.favorite
    if data.excluded is not None:
        recipe.excluded = data.excluded
    db.commit()
    return summary(recipe)


@router.delete("/recipes/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    recipe = _get(db, recipe_id)
    image = recipe.image
    search.remove_recipe(db, recipe.id)
    db.delete(recipe)
    db.commit()
    delete_image(image, settings.image_dir)
    return Response(status_code=204)


@router.post("/recipes/{recipe_id}/image", response_model=RecipeSummary)
async def upload_image(
    recipe_id: int, file: UploadFile, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
):
    recipe = _get(db, recipe_id)
    data = await file.read()
    try:
        name = save_image(data, settings.image_dir)
    except ImageError as e:
        raise HTTPException(422, str(e)) from e
    old = recipe.image
    recipe.image = name
    db.commit()
    delete_image(old, settings.image_dir)
    return summary(recipe)


@router.delete("/recipes/{recipe_id}/image", response_model=RecipeSummary)
def remove_image(recipe_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    recipe = _get(db, recipe_id)
    old = recipe.image
    recipe.image = None
    db.commit()
    delete_image(old, settings.image_dir)
    return summary(recipe)


@router.get("/images/{name}")
def get_image(name: str, settings: Settings = Depends(get_settings)):
    path = settings.image_dir / name
    if not valid_name(name) or not path.is_file():
        raise HTTPException(404, "Bild nicht gefunden")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "public, max-age=31536000, immutable"})


# --- Katalog ---------------------------------------------------------------------------


@router.get("/ingredients", response_model=list[IngredientOut])
def list_ingredients(q: str | None = None, limit: int = 500, db: Session = Depends(get_db)):
    """Autovervollständigung über Name und Aliasse."""
    stmt = select(Ingredient)
    if q and q.strip():
        n = f"%{normalize(q)}%"
        stmt = stmt.where(func.lower(Ingredient.name).like(n) | Ingredient.aliases.any(IngredientAlias.alias.like(n)))
    items = db.scalars(stmt.order_by(func.lower(Ingredient.name)).limit(min(limit, 2000))).unique().all()
    if q and q.strip():
        nq = normalize(q)
        items.sort(key=lambda i: (not normalize(i.name).startswith(nq), normalize(i.name)))
    return [ingredient_out(i) for i in items]


@router.post("/ingredients", response_model=IngredientOut, status_code=201)
def post_ingredient(data: IngredientIn, db: Session = Depends(get_db)):
    existing = db.scalar(select(Ingredient).where(func.lower(Ingredient.name) == data.name.lower()))
    if existing is not None:
        return ingredient_out(existing)
    if data.group_id is not None and db.get(IngredientGroup, data.group_id) is None:
        raise HTTPException(422, "Unbekannte Gruppe")
    alias = db.scalar(select(IngredientAlias).where(IngredientAlias.alias == normalize(data.name)))
    if alias is not None:
        return ingredient_out(alias.ingredient)
    ing = Ingredient(name=data.name, group_id=data.group_id, default_unit=data.default_unit)
    db.add(ing)
    db.commit()
    db.refresh(ing)
    return ingredient_out(ing)


@router.get("/ingredient-groups", response_model=list[GroupOut])
def list_groups(db: Session = Depends(get_db)):
    return db.scalars(select(IngredientGroup).order_by(IngredientGroup.name)).all()


@router.get("/tags", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db)):
    return db.scalars(select(Tag).order_by(func.lower(Tag.name))).all()


@router.post("/tags", response_model=TagOut, status_code=201)
def post_tag(data: TagIn, db: Session = Depends(get_db)):
    name = " ".join(data.name.split())
    existing = db.scalar(select(Tag).where(func.lower(Tag.name) == name.lower()))
    if existing is not None:
        return existing
    tag = Tag(name=name)
    db.add(tag)
    db.commit()
    return tag


# --- Export (N-13) ---------------------------------------------------------------------


@router.get("/export/recipes")
def export_recipes(db: Session = Depends(get_db)):
    """Alle Rezepte als JSON nach Schema.org Recipe."""
    out = []
    for r in db.scalars(select(Recipe).order_by(Recipe.id)):
        out.append(
            {
                "@context": "https://schema.org",
                "@type": "Recipe",
                "name": r.title,
                "recipeYield": str(r.servings),
                "totalTime": f"PT{r.duration_min}M" if r.duration_min else None,
                "recipeCategory": "Hauptgericht" if r.size == "haupt" else "Kleine Mahlzeit",
                "keywords": ", ".join(t.name for t in r.tags),
                "recipeIngredient": [
                    " ".join(
                        p
                        for p in (format_quantity(ri.amount, ri.unit), ri.name, f"({ri.note})" if ri.note else "")
                        if p
                    )
                    for ri in r.ingredients
                ],
                "recipeInstructions": [{"@type": "HowToStep", "text": s} for s in (r.steps or [])],
                "isBasedOn": r.source_url,
                "image": image_url(r.image),
            }
        )
    return Response(
        content=json.dumps(out, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="delikatessen-rezepte.json"'},
    )
