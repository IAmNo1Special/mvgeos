from __future__ import annotations

from mvgeos_tome.index import Index
from mvgeos_tome.types import TomeEntry, TomeEntryType


def _entry(
    eid: str, parent_id: str | None = None, etype: TomeEntryType | None = None
) -> TomeEntry:
    return TomeEntry(
        id=eid,
        parent_id=parent_id,
        type=etype or TomeEntryType.MESSAGE,
        timestamp=0.0,
        payload={},
    )


class TestIndexAddAndGet:
    def test_add_and_get_entry(self) -> None:
        idx = Index()
        e = _entry("e1")
        idx.add(e)
        assert idx.get("e1") is e

    def test_get_returns_none_for_unknown_id(self) -> None:
        idx = Index()
        assert idx.get("nope") is None


class TestIndexChildren:
    def test_children_returns_entries_with_matching_parent(self) -> None:
        idx = Index()
        parent = _entry("p1")
        child_a = _entry("c1", parent_id="p1")
        child_b = _entry("c2", parent_id="p1")
        orphan = _entry("c3", parent_id="other")
        idx.add(parent)
        idx.add(child_a)
        idx.add(child_b)
        idx.add(orphan)

        results = list(idx.children("p1"))
        assert {e.id for e in results} == {"c1", "c2"}

    def test_children_of_none_parent(self) -> None:
        idx = Index()
        root = _entry("r1", parent_id=None)
        idx.add(root)

        results = list(idx.children(None))
        assert len(results) == 1
        assert results[0].id == "r1"

    def test_children_returns_empty_for_unknown_parent(self) -> None:
        idx = Index()
        assert list(idx.children("unknown")) == []


class TestIndexLeaves:
    def test_leaves_yields_only_leaf_entries(self) -> None:
        idx = Index()
        regular = _entry("m1")
        leaf = _entry("l1", etype=TomeEntryType.LEAF)
        idx.add(regular)
        idx.add(leaf)

        results = list(idx.leaves())
        assert len(results) == 1
        assert results[0].id == "l1"

    def test_leaves_empty_when_no_leaf_entries(self) -> None:
        idx = Index()
        assert list(idx.leaves()) == []


class TestIndexAll:
    def test_all_yields_every_added_entry(self) -> None:
        idx = Index()
        e1 = _entry("1")
        e2 = _entry("2")
        idx.add(e1)
        idx.add(e2)

        results = list(idx.all())
        assert {e.id for e in results} == {"1", "2"}

    def test_all_empty_when_nothing_added(self) -> None:
        idx = Index()
        assert list(idx.all()) == []
