"""Tests for .env auto-loading in load_project_config."""
import os


def test_load_project_config_loads_dotenv(tmp_path):
    """load_project_config loads .env from project directory."""
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: test\n  slug: test\n  domain: research\n"
        "neo4j:\n  uri: bolt://localhost:7687\n  database: test\n"
        "event_store:\n  path: events.jsonl\n"
    )
    (tmp_path / ".env").write_text("SELDON_TEST_VAR=loaded_from_dotenv\n")

    os.environ.pop("SELDON_TEST_VAR", None)

    from seldon.config import load_project_config
    load_project_config(tmp_path)

    assert os.getenv("SELDON_TEST_VAR") == "loaded_from_dotenv"

    os.environ.pop("SELDON_TEST_VAR", None)


def test_load_project_config_no_dotenv_override(tmp_path):
    """Shell env vars take precedence over .env file (override=False)."""
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: test\n  slug: test\n  domain: research\n"
        "neo4j:\n  uri: bolt://localhost:7687\n  database: test\n"
        "event_store:\n  path: events.jsonl\n"
    )
    (tmp_path / ".env").write_text("SELDON_TEST_VAR=from_dotenv\n")
    os.environ["SELDON_TEST_VAR"] = "from_shell"

    from seldon.config import load_project_config
    load_project_config(tmp_path)

    assert os.getenv("SELDON_TEST_VAR") == "from_shell"

    os.environ.pop("SELDON_TEST_VAR", None)


def test_load_project_config_no_env_file_is_noop(tmp_path):
    """load_project_config succeeds silently when no .env file present."""
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: test\n  slug: test\n  domain: research\n"
        "neo4j:\n  uri: bolt://localhost:7687\n  database: test\n"
        "event_store:\n  path: events.jsonl\n"
    )
    # No .env file created — should not raise
    from seldon.config import load_project_config
    config = load_project_config(tmp_path)
    assert config["project"]["name"] == "test"
