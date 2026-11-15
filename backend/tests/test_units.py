import pytest

from delikatessen.units import format_quantity, parse_ingredient_line, round_amount, scale


@pytest.mark.parametrize(
    ("line", "amount", "unit", "name", "note"),
    [
        ("200 g Mehl", 200, "g", "Mehl", None),
        ("200g Mehl (Type 405), gesiebt", 200, "g", "Mehl", "Type 405, gesiebt"),
        ("1 1/2 TL Salz", 1.5, "TL", "Salz", None),
        ("½ Bund Petersilie", 0.5, "Bund", "Petersilie", None),
        ("1,5 kg Kartoffeln", 1.5, "kg", "Kartoffeln", None),
        ("2-3 Zwiebeln", 3, None, "Zwiebeln", "2–3"),
        ("3 Esslöffel Olivenöl", 3, "EL", "Olivenöl", None),
        ("Salz und Pfeffer", None, None, "Salz und Pfeffer", None),
        ("etwas Butter", None, None, "Butter", "etwas"),
        ("ca. 400 ml Milch", 400, "ml", "Milch", None),
        ("2 Zehen Knoblauch, gehackt", 2, "Zehe", "Knoblauch", "gehackt"),
        ("1 Hand voll Rucola", 1, "Handvoll", "Rucola", None),
        # Schreibweisen aus der Praxis (Feedback 15.11.2026)
        ("Mehl 200 g", 200, "g", "Mehl", None),
        ("Butter: 100g", 100, "g", "Butter", None),
        ("Zucker, 50 g", 50, "g", "Zucker", None),
        ("Sahne (200 ml)", 200, "ml", "Sahne", None),
        ("Mehl Type 405", None, None, "Mehl Type 405", None),
        ("1 Dose (400 g) Tomaten", 1, "Dose", "Tomaten", "400 g"),
        ("2 Zwiebel(n)", 2, None, "Zwiebel", None),
        ("3 Zehe/n Knoblauch", 3, "Zehe", "Knoblauch", None),
        ("eine Zwiebel", 1, None, "Zwiebel", None),
        ("Eine halbe Zitrone", 0.5, None, "Zitrone", None),
        ("zwei Eier", 2, None, "Eier", None),
        ("Ein Schuss Sahne", 1, "Schuss", "Sahne", None),
        ("ein paar Blätter Basilikum", None, None, "Blätter Basilikum", "ein paar"),
        ("Eier", None, None, "Eier", None),
        ("Salz nach Belieben", None, None, "Salz", "nach Belieben"),
        ("1 EL Butter für die Form", 1, "EL", "Butter", "für die Form"),
        ("Puderzucker zum Bestäuben", None, None, "Puderzucker", "zum Bestäuben"),
        ("250 g. Quark", 250, "g", "Quark", None),
        ("1 Rolle Blätterteig", 1, "Rolle", "Blätterteig", None),
    ],
)
def test_parse_line(line, amount, unit, name, note):
    p = parse_ingredient_line(line)
    assert (p.amount, p.unit, p.name, p.note) == (amount, unit, name, note)


def test_rounding_rules():
    # Gramm und Milliliter auf 5, Stück auf 0,5 (F-02)
    assert round_amount(123, "g") == 125
    assert round_amount(333.3, "ml") == 335
    assert round_amount(2.4, "g") == 2  # kleine Mengen werden nicht zu 0
    assert round_amount(1.3, "Stück") == 1.5
    assert round_amount(0.1, "Stück") == 0.5
    assert scale(None, "g", 2) is None
    assert scale(200, "g", 6 / 4) == 300
    assert scale(3, None, 1 / 4) == 1


def test_format():
    assert format_quantity(1.5, "kg") == "1,5 kg"
    assert format_quantity(2, None) == "2"
    assert format_quantity(None, "g") == ""
