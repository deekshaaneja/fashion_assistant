from __future__ import annotations

from src.agent.session_store import SessionStore
from src.domain.models.session import DesignSession, FabricRef


def test_save_and_load_round_trips(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    store = SessionStore(db_path)
    session = DesignSession()
    session.fabric_refs.append(FabricRef(fabric_id="f1", fabric_name="organza", source="text_declared"))
    store.save(session)

    loaded = store.load(session.session_id)
    assert loaded is not None
    assert loaded.fabric_refs[0].fabric_name == "organza"


def test_load_survives_a_fresh_store_instance_pointed_at_the_same_file(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    session = DesignSession()
    SessionStore(db_path).save(session)

    # A brand new SessionStore instance (simulating a process restart)
    # against the same file must still see the session.
    reopened = SessionStore(db_path)
    loaded = reopened.load(session.session_id)
    assert loaded is not None
    assert loaded.session_id == session.session_id


def test_save_overwrites_rather_than_duplicating(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    store = SessionStore(db_path)
    session = DesignSession()
    store.save(session)
    session.selected_design_family_id = "D1"
    store.save(session)

    assert store.list_ids().count(session.session_id) == 1
    loaded = store.load(session.session_id)
    assert loaded.selected_design_family_id == "D1"


def test_unknown_session_id_returns_none(tmp_path):
    store = SessionStore(str(tmp_path / "sessions.db"))
    assert store.load("does-not-exist") is None