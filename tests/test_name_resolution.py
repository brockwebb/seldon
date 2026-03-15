"""Tests for name-based artifact resolution (graph.py + result.py + link.py)."""
import pytest
from unittest.mock import MagicMock, patch

from seldon.core.graph import find_artifact_by_property, find_any_artifact_by_name


class TestFindArtifactByProperty:
    def _make_session(self, records):
        session = MagicMock()
        session.run.return_value.data.return_value = records
        return session

    def test_returns_artifact_when_found(self):
        session = MagicMock()
        session.run.return_value.data.return_value = [{"a": {"artifact_id": "abc-123", "name": "test_script"}}]

        result = find_artifact_by_property(session, "Script", "name", "test_script")
        assert result == {"artifact_id": "abc-123", "name": "test_script"}

    def test_returns_none_when_not_found(self):
        session = MagicMock()
        session.run.return_value.data.return_value = []

        result = find_artifact_by_property(session, "Script", "name", "nonexistent")
        assert result is None

    def test_raises_on_multiple_matches(self):
        session = MagicMock()
        session.run.return_value.data.return_value = [
            {"a": {"artifact_id": "id-1", "name": "dup"}},
            {"a": {"artifact_id": "id-2", "name": "dup"}},
        ]

        with pytest.raises(ValueError, match="Multiple Script artifacts"):
            find_artifact_by_property(session, "Script", "name", "dup")

    def test_raises_on_disallowed_property(self):
        session = MagicMock()
        with pytest.raises(ValueError, match="Cannot search by property"):
            find_artifact_by_property(session, "Script", "artifact_id", "some-id")

    def test_allowed_properties_work(self):
        session = MagicMock()
        session.run.return_value.data.return_value = []
        # Should not raise
        find_artifact_by_property(session, "Script", "name", "x")
        find_artifact_by_property(session, "Script", "path", "x")
        find_artifact_by_property(session, "Script", "description", "x")


class TestFindAnyArtifactByName:
    def test_returns_artifact_when_found(self):
        session = MagicMock()
        session.run.return_value.data.return_value = [{"a": {"artifact_id": "id-1", "name": "foo"}}]

        result = find_any_artifact_by_name(session, "foo")
        assert result == {"artifact_id": "id-1", "name": "foo"}

    def test_returns_none_when_not_found(self):
        session = MagicMock()
        session.run.return_value.data.return_value = []

        assert find_any_artifact_by_name(session, "nope") is None

    def test_raises_on_multiple_matches(self):
        session = MagicMock()
        session.run.return_value.data.return_value = [
            {"a": {"artifact_id": "id-1"}},
            {"a": {"artifact_id": "id-2"}},
        ]

        with pytest.raises(ValueError, match="Multiple artifacts"):
            find_any_artifact_by_name(session, "ambiguous")
