from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import BaseModel, model_validator


class RelationshipConfig(BaseModel):
    from_types: List[str]
    to_types: List[str]


class DomainConfig(BaseModel):
    domain: str
    version: str
    artifact_types: List[str]
    relationship_types: Dict[str, RelationshipConfig]
    state_machines: Dict[str, Dict[str, List[str]]]

    @model_validator(mode="after")
    def validate_state_machines_reference_known_types(self) -> "DomainConfig":
        for artifact_type in self.state_machines:
            if artifact_type not in self.artifact_types:
                raise ValueError(
                    f"State machine defined for unknown artifact type: {artifact_type}"
                )
        return self

    def get_initial_state(self, artifact_type: str) -> str:
        """Return the first key in the state machine (always 'proposed')."""
        sm = self.state_machines.get(artifact_type)
        if sm is None:
            return "proposed"
        return next(iter(sm))


def load_domain_config(config_path: Path) -> DomainConfig:
    """Parse domain YAML file and return validated DomainConfig."""
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)
    return DomainConfig(**raw)


def validate_artifact_type(domain_config: DomainConfig, artifact_type: str) -> None:
    """Raise ValueError if artifact_type is not in the domain config."""
    if artifact_type not in domain_config.artifact_types:
        raise ValueError(
            f"Unknown artifact type: '{artifact_type}'. "
            f"Valid types: {sorted(domain_config.artifact_types)}"
        )


def validate_relationship(
    domain_config: DomainConfig,
    rel_type: str,
    from_type: str,
    to_type: str,
) -> None:
    """Raise ValueError if the relationship is not valid per domain config."""
    if rel_type not in domain_config.relationship_types:
        raise ValueError(
            f"Unknown relationship type: '{rel_type}'. "
            f"Valid types: {sorted(domain_config.relationship_types.keys())}"
        )
    rel_config = domain_config.relationship_types[rel_type]
    if from_type not in rel_config.from_types:
        raise ValueError(
            f"'{from_type}' cannot originate a '{rel_type}' relationship. "
            f"Valid from_types: {rel_config.from_types}"
        )
    if to_type not in rel_config.to_types:
        raise ValueError(
            f"'{to_type}' cannot target a '{rel_type}' relationship. "
            f"Valid to_types: {rel_config.to_types}"
        )
