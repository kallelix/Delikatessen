"""Einheiten, Zutatenzeilen und Rundung (F-02, Abschnitt 8)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# Einheit -> (Einheitenart, Faktor zur Basiseinheit der Art)
UNITS: dict[str, tuple[str, float]] = {
    "g": ("masse", 1),
    "kg": ("masse", 1000),
    "ml": ("volumen", 1),
    "cl": ("volumen", 10),
    "dl": ("volumen", 100),
    "l": ("volumen", 1000),
}
COUNT_UNITS = [
    "EL",
    "TL",
    "Stück",
    "Prise",
    "Bund",
    "Dose",
    "Packung",
    "Zehe",
    "Scheibe",
    "Becher",
    "Tasse",
    "Msp.",
    "Glas",
    "Zweig",
    "Handvoll",
    "Stange",
    "Blatt",
    "Knolle",
    "Kopf",
    "Würfel",
    "Tüte",
    "Schuss",
    "Spritzer",
    "Stiel",
    "Rolle",
    "Kugel",
]
ALL_UNITS = list(UNITS) + COUNT_UNITS

_UNIT_VARIANTS = {
    "g": ["g", "g.", "gr", "gr.", "gramm"],
    "kg": ["kg", "kg.", "kilo", "kilogramm"],
    "ml": ["ml", "ml.", "milliliter"],
    "cl": ["cl"],
    "dl": ["dl"],
    "l": ["l", "liter", "ltr", "ltr."],
    "EL": ["el", "el.", "esslöffel", "eßlöffel", "essl.", "elöffel", "tbsp", "tbsp."],
    "TL": ["tl", "tl.", "teelöffel", "tsp", "tsp."],
    "Stück": ["stück", "stk", "stk.", "st.", "st", "pcs", "pcs.", "pc", "pc.", "piece", "pieces"],
    "Prise": ["prise", "prisen", "pr."],
    "Bund": ["bund", "bd.", "bunde"],
    "Dose": ["dose", "dosen"],
    "Packung": ["packung", "packungen", "pck.", "pck", "pkg.", "päckchen", "pk.", "pack"],
    "Zehe": ["zehe", "zehen"],
    "Scheibe": ["scheibe", "scheiben"],
    "Becher": ["becher"],
    "Tasse": ["tasse", "tassen"],
    "Msp.": ["msp.", "msp", "messerspitze", "messerspitzen"],
    "Glas": ["glas", "gläser"],
    "Zweig": ["zweig", "zweige", "zweiglein"],
    "Handvoll": ["handvoll", "hand voll"],
    "Stange": ["stange", "stangen"],
    "Blatt": ["blatt", "blätter"],
    "Knolle": ["knolle", "knollen"],
    "Kopf": ["kopf", "köpfe"],
    "Würfel": ["würfel"],
    "Tüte": ["tüte", "tüten"],
    "Schuss": ["schuss", "schüsse", "schluck"],
    "Spritzer": ["spritzer"],
    "Stiel": ["stiel", "stiele", "stängel", "stängel."],
    "Rolle": ["rolle", "rollen"],
    "Kugel": ["kugel", "kugeln"],
}
UNIT_LOOKUP = {v: canon for canon, vs in _UNIT_VARIANTS.items() for v in vs}

_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3, "⅛": 0.125}
_NUM = r"(?:\d+\s+\d+/\d+|\d+\s*[½¼¾⅓⅔⅛]|\d+/\d+|\d+(?:[.,]\d+)?|[½¼¾⅓⅔⅛])"
_QTY_RE = re.compile(
    rf"^\s*(?:ca\.?\s*|etwa\s+|circa\s+)?(?P<a>{_NUM})(?:\s*(?:-|–|bis)\s*(?P<b>{_NUM}))?\s*",
    re.IGNORECASE,
)
_OPTIONAL_PREFIX = re.compile(
    r"^(etwas|evtl\.?|eventuell|optional|ein\s+paar|ein\s+wenig|ein\s+bisschen|ein\s+bißchen|einige)\s+", re.IGNORECASE
)

# Zahlwörter am Zeilenanfang: "eine Zwiebel", "eine halbe Zitrone", "zwei Eier"
_WORD_NUMBERS = {
    "eineinhalb": 1.5,
    "anderthalb": 1.5,
    "ein": 1,
    "eine": 1,
    "einen": 1,
    "einem": 1,
    "einer": 1,
    "zwei": 2,
    "drei": 3,
    "vier": 4,
    "fünf": 5,
    "sechs": 6,
    "sieben": 7,
    "acht": 8,
    "neun": 9,
    "zehn": 10,
    "zwölf": 12,
    "halbe": 0.5,
    "halber": 0.5,
    "halbes": 0.5,
    "halben": 0.5,
}
_WORD_NUM_RE = re.compile(
    r"^(?!ein\s+(?:paar|wenig|bisschen|bißchen)\b)(?P<w>"
    + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True))
    + r")(?:\s+(?P<h>halbe[rsn]?))?\s+(?=\S)",
    re.IGNORECASE,
)
# Endungen in Klammern oder mit Schrägstrich: "Zwiebel(n)", "Zehe/n", "Ei(er)"
_PLURAL_MARK_RE = re.compile(r"(?<=[^\W\d_])(?:\((?:n|en|e|er|s|nen)\)|/(?:n|en|e|er|s)\b)", re.IGNORECASE)
# Verwendungszweck am Ende wird zum Zusatz: "Salz nach Belieben", "Butter für die Form", "Mehl zum Bestäuben"
_PURPOSE_RE = re.compile(
    r"\s+(?P<p>nach\s+(?:belieben|geschmack|bedarf)|n\.\s?b\.|zum\s+\w+|für\s+(?:die|den|das)\s+\w+|zum\s+servieren)\s*$",
    re.IGNORECASE,
)


def _unit_at(text: str) -> tuple[str | None, str]:
    """Einheit am Anfang des Textes: zwei Wörter zuerst ("hand voll"), dann eins. Gibt (Einheit, Rest) zurück."""
    words = text.split(" ", 2)
    if len(words) >= 2 and f"{words[0]} {words[1]}".lower() in UNIT_LOOKUP:
        return UNIT_LOOKUP[f"{words[0]} {words[1]}".lower()], (words[2] if len(words) > 2 else "")
    if words and words[0].lower() in UNIT_LOOKUP:
        return UNIT_LOOKUP[words[0].lower()], " ".join(words[1:])
    return None, text


# Menge mit Einheit als ganzer Text, etwa in Klammern "(200 g)" oder am Ende "Mehl 200 g"
_QTY_UNIT_RE = re.compile(rf"^(?:ca\.?\s*|etwa\s+)?(?P<a>{_NUM})\s*(?P<u>[^\W\d_][\w.]*(?:\s[\w.]+)?)$", re.IGNORECASE)
_TRAILING_QTY_RE = re.compile(
    rf"[\s,:]+(?:ca\.?\s*|etwa\s+)?(?P<a>{_NUM})\s*(?P<u>[^\W\d_][\w.]*(?:\s[\w.]+)?)$", re.IGNORECASE
)


def _qty_with_unit(m: re.Match | None) -> tuple[float, str] | None:
    if not m:
        return None
    unit = UNIT_LOOKUP.get(m.group("u").lower())
    if unit is None:
        return None
    try:
        return parse_number(m.group("a")), unit
    except (ValueError, ZeroDivisionError):
        return None


def normalize_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    u = unit.strip()
    if u in UNITS or u in COUNT_UNITS:
        return u
    return UNIT_LOOKUP.get(u.lower(), u)


def unit_kind(unit: str | None) -> str | None:
    """Art der Einheit: masse, volumen, sonst die Einheit selbst (nicht umrechenbar)."""
    if unit is None:
        return None
    if unit in UNITS:
        return UNITS[unit][0]
    return unit


def to_base(amount: float, unit: str) -> float:
    return amount * UNITS[unit][1] if unit in UNITS else amount


def parse_number(text: str) -> float:
    text = text.strip().replace(",", ".")
    m = re.fullmatch(r"(\d+)\s*([½¼¾⅓⅔⅛])", text)
    if m:
        return int(m.group(1)) + _FRACTIONS[m.group(2)]
    if text in _FRACTIONS:
        return _FRACTIONS[text]
    m = re.fullmatch(r"(\d+)\s+(\d+)/(\d+)", text)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    m = re.fullmatch(r"(\d+)/(\d+)", text)
    if m:
        return int(m.group(1)) / int(m.group(2))
    return float(text)


@dataclass
class ParsedLine:
    line: str
    amount: float | None
    unit: str | None
    name: str
    note: str | None
    # Text nach Menge und Einheit samt Kommateil ("Salz, Pfeffer") und die Zusätze ohne Kommateil,
    # damit der Import Sammelzeilen in einzelne Zutaten zerlegen kann
    body: str = ""
    base_notes: tuple[str, ...] = ()


def parse_ingredient_line(line: str) -> ParsedLine:
    """Zerlegt eine Zeile wie "200 g Mehl (Type 405), gesiebt" in Menge, Einheit, Name und Zusatz."""
    original = " ".join(line.split())
    rest = _PLURAL_MARK_RE.sub("", original)
    notes: list[str] = []

    # Klammern sind Zusätze
    for m in re.findall(r"\(([^)]*)\)", rest):
        if m.strip():
            notes.append(m.strip())
    rest = " ".join(re.sub(r"\([^)]*\)", " ", rest).split())

    amount = None
    m = _QTY_RE.match(rest)
    if m:
        try:
            a = parse_number(m.group("a"))
            b = parse_number(m.group("b")) if m.group("b") else None
            amount = b if b is not None else a  # bei Spannen die obere Grenze, damit es reicht
            if b is not None:
                notes.append(f"{m.group('a').strip()}–{m.group('b').strip()}")
            rest = rest[m.end() :]
        except (ValueError, ZeroDivisionError):
            amount = None
    if amount is None:
        m = _WORD_NUM_RE.match(rest)
        if m:
            amount = _WORD_NUMBERS[m.group("w").lower()] * (0.5 if m.group("h") else 1)
            rest = rest[m.end() :]

    unit = None
    if amount is not None:
        unit, rest = _unit_at(rest)
    else:
        # Menge hinten oder in Klammern: "Mehl 200 g", "Butter: 100g", "Sahne (200 ml)"
        trailing = _TRAILING_QTY_RE.search(rest)
        found = _qty_with_unit(trailing)
        if found:
            amount, unit = found
            rest = rest[: trailing.start()]
        else:
            for i, n in enumerate(notes):
                found = _qty_with_unit(_QTY_UNIT_RE.match(n))
                if found:
                    amount, unit = found
                    del notes[i]
                    break

    rest = rest.strip()
    m = _OPTIONAL_PREFIX.match(rest)
    if m:
        notes.insert(0, m.group(1))
        rest = rest[m.end() :]
    m = _PURPOSE_RE.search(rest)
    if m and m.start() > 0:
        notes.append(m.group("p"))
        # "Salz oder nach Geschmack": das verwaiste "oder" gehört nicht zum Namen
        rest = re.sub(r"\s+(?:oder|und)$", "", rest[: m.start()], flags=re.IGNORECASE)
    body = rest.strip(" -–;.")
    base_notes = tuple(notes)

    # Zusatz nach Komma
    if "," in rest:
        rest, after = rest.split(",", 1)
        if after.strip():
            notes.append(after.strip())

    name = rest.strip(" -–:;.") or original
    return ParsedLine(
        line=original,
        amount=amount,
        unit=unit,
        name=name,
        note=", ".join(notes) or None,
        body=body,
        base_notes=base_notes,
    )


def round_amount(amount: float, unit: str | None) -> float:
    """Sinnvolle Rundung nach dem Umrechnen (F-02).

    Gramm und Milliliter auf 5, kleine Mengen unter 20 auf 1, damit etwa 2 g Hefe nicht zu 0 werden.
    Stück auf 0,5, Kilogramm und Liter auf 0,05, alle übrigen Einheiten auf 0,25.
    """
    if amount <= 0:
        return 0
    if unit in ("g", "ml"):
        step = 5 if amount >= 20 else 1
    elif unit in ("kg", "l"):
        step = 0.05
    elif unit == "Stück" or unit is None:
        step = 0.5
    else:
        step = 0.25
    rounded = round(amount / step) * step
    if rounded == 0:
        rounded = step
    return round(rounded, 4)


def scale(amount: float | None, unit: str | None, factor: float) -> float | None:
    if amount is None:
        return None
    return round_amount(amount * factor, unit)


def format_number(x: float) -> str:
    if math.isclose(x, round(x)):
        return str(int(round(x)))
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def format_quantity(amount: float | None, unit: str | None) -> str:
    if amount is None:
        return ""
    return f"{format_number(amount)} {unit}".strip() if unit else format_number(amount)


def humanize_base(amount: float, kind: str) -> tuple[float, str]:
    """Basismenge (g oder ml) in lesbare Einheit, ab 1000 in kg oder l."""
    if kind == "masse":
        return (round_amount(amount / 1000, "kg"), "kg") if amount >= 1000 else (round_amount(amount, "g"), "g")
    if kind == "volumen":
        return (round_amount(amount / 1000, "l"), "l") if amount >= 1000 else (round_amount(amount, "ml"), "ml")
    raise ValueError(kind)
