"""Filter für Alembic-Vergleiche."""


def include_name(name, type_, _parent_names) -> bool:
    """Die Volltexttabelle recipe_fts und ihre Schattentabellen pflegt die Migration von Hand."""
    return not (type_ == "table" and name.startswith("recipe_fts"))
