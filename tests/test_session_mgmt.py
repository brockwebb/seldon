"""
Session management tests. Pure Python — no Neo4j required.
"""
import json
import uuid
from pathlib import Path

import pytest

from seldon.config import start_session, get_current_session, get_current_session_data, end_session


def test_start_session_returns_valid_uuid(tmp_path):
    session_id = start_session(tmp_path)
    uuid.UUID(session_id)  # must be valid UUID


def test_start_session_creates_session_file(tmp_path):
    start_session(tmp_path)
    assert (tmp_path / ".seldon" / "current_session.json").exists()


def test_start_session_creates_seldon_dir(tmp_path):
    start_session(tmp_path)
    assert (tmp_path / ".seldon").is_dir()


def test_get_current_session_returns_session_id(tmp_path):
    session_id = start_session(tmp_path)
    assert get_current_session(tmp_path) == session_id


def test_get_current_session_none_when_no_session(tmp_path):
    assert get_current_session(tmp_path) is None


def test_get_current_session_data_has_started_at(tmp_path):
    start_session(tmp_path)
    data = get_current_session_data(tmp_path)
    assert "started_at" in data
    assert "session_id" in data


def test_end_session_clears_file(tmp_path):
    start_session(tmp_path)
    end_session(tmp_path)
    assert get_current_session(tmp_path) is None


def test_end_session_noop_when_no_session(tmp_path):
    end_session(tmp_path)  # must not raise


def test_start_session_overwrites_existing(tmp_path):
    id1 = start_session(tmp_path)
    id2 = start_session(tmp_path)
    assert id1 != id2
    assert get_current_session(tmp_path) == id2
