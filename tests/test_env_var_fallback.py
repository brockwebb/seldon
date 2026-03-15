"""Tests for env var fallback in get_neo4j_driver."""
import os
from unittest.mock import patch, MagicMock


def test_neo4j_username_password_used_when_set(monkeypatch):
    """Primary env vars (NEO4J_USERNAME/NEO4J_PASSWORD) are used when set."""
    monkeypatch.setenv("NEO4J_USERNAME", "primary_user")
    monkeypatch.setenv("NEO4J_PASSWORD", "primary_pass")
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.delenv("NEO4J_PASS", raising=False)

    config = {"neo4j": {"uri": "bolt://localhost:7687"}}
    with patch("neo4j.GraphDatabase.driver") as mock_driver:
        from seldon.config import get_neo4j_driver
        get_neo4j_driver(config)
        mock_driver.assert_called_once_with(
            "bolt://localhost:7687", auth=("primary_user", "primary_pass")
        )


def test_neo4j_user_pass_fallback_when_primary_not_set(monkeypatch):
    """Fallback env vars (NEO4J_USER/NEO4J_PASS) are used when primary not set."""
    monkeypatch.delenv("NEO4J_USERNAME", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.setenv("NEO4J_USER", "fallback_user")
    monkeypatch.setenv("NEO4J_PASS", "fallback_pass")

    config = {"neo4j": {"uri": "bolt://localhost:7687"}}
    with patch("neo4j.GraphDatabase.driver") as mock_driver:
        from seldon.config import get_neo4j_driver
        get_neo4j_driver(config)
        mock_driver.assert_called_once_with(
            "bolt://localhost:7687", auth=("fallback_user", "fallback_pass")
        )


def test_defaults_when_no_env_vars_set(monkeypatch):
    """Default credentials used when neither env var set is present."""
    monkeypatch.delenv("NEO4J_USERNAME", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.delenv("NEO4J_PASS", raising=False)

    config = {"neo4j": {"uri": "bolt://localhost:7687"}}
    with patch("neo4j.GraphDatabase.driver") as mock_driver:
        from seldon.config import get_neo4j_driver
        get_neo4j_driver(config)
        mock_driver.assert_called_once_with(
            "bolt://localhost:7687", auth=("neo4j", "password")
        )


def test_primary_takes_priority_over_fallback(monkeypatch):
    """NEO4J_USERNAME takes priority over NEO4J_USER when both set."""
    monkeypatch.setenv("NEO4J_USERNAME", "primary_user")
    monkeypatch.setenv("NEO4J_PASSWORD", "primary_pass")
    monkeypatch.setenv("NEO4J_USER", "fallback_user")
    monkeypatch.setenv("NEO4J_PASS", "fallback_pass")

    config = {"neo4j": {"uri": "bolt://localhost:7687"}}
    with patch("neo4j.GraphDatabase.driver") as mock_driver:
        from seldon.config import get_neo4j_driver
        get_neo4j_driver(config)
        mock_driver.assert_called_once_with(
            "bolt://localhost:7687", auth=("primary_user", "primary_pass")
        )
