"""Tests for the template definition data (minerva_bot.cogs.template)."""

from __future__ import annotations

from minerva_bot.cogs.template import _CATEGORIES, _ROLES


def test_role_names_unique() -> None:
    names = [r.name for r in _ROLES]
    assert len(names) == len(set(names))


def test_role_order_requirements() -> None:
    # admin first (highest), participant last (lowest), per the spec.
    assert _ROLES[0].name == "admin"
    assert _ROLES[-1].name == "participant"
    assert _ROLES[0].permissions.administrator is True


def test_allowed_roles_exist() -> None:
    role_names = {r.name for r in _ROLES}
    for cat in _CATEGORIES:
        if cat.allow is None:
            continue
        assert set(cat.allow) <= role_names, cat.name


def test_channel_names_unique_within_category() -> None:
    for cat in _CATEGORIES:
        names = [c.name for c in cat.channels]
        assert len(names) == len(set(names)), cat.name


def test_private_categories_are_hidden_from_everyone() -> None:
    seen_private = False
    for cat in _CATEGORIES:
        if cat.allow is not None:
            seen_private = True
            assert "participant" in cat.allow or "lead" in cat.allow
    # The template must contain at least one private category.
    assert seen_private


def test_organizers_are_lead_and_above_only() -> None:
    org = next(c for c in _CATEGORIES if c.name == "organizers")
    assert org.allow == ("lead", "admin")
    names = {c.name for c in org.channels}
    assert names == {
        "general",
        "workshops",
        "mentors",
        "judges",
        "verification",
        "logs",
    }
