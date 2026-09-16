"""Probe for `tests/test_neo4j_fixture_gate.py`. Not collected by default (no `test_` prefix
on the file); that module runs it explicitly in a subprocess under a controlled environment."""


def test_probe_requests_the_neo4j_gate(neo4j_available):
    assert neo4j_available is True
