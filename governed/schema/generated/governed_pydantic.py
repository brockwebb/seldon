from __future__ import annotations

import re
import sys
from datetime import (
    date,
    datetime,
    time
)
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    ClassVar,
    Literal,
    Optional,
    Union
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer
)


metamodel_version = "1.11.0"
version = "0.1.0"


class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(
        serialize_by_alias = True,
        validate_by_name = True,
        validate_assignment = True,
        validate_default = True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        use_enum_values = True,
        strict = False,
    )





class LinkMLMeta(RootModel):
    root: dict[str, Any] = {}
    model_config = ConfigDict(frozen=True)

    def __getattr__(self, key:str):
        return getattr(self.root, key)

    def __getitem__(self, key:str):
        return self.root[key]

    def __setitem__(self, key:str, value):
        self.root[key] = value

    def __contains__(self, key:str) -> bool:
        return key in self.root


linkml_meta = LinkMLMeta({'default_prefix': 'governed',
     'default_range': 'string',
     'description': "Seldon's own engineering record as graph content (AD-030). A "
                    'governed markdown file under docs/design/, '
                    'docs/requirements/, cc_tasks/ or handoffs/ is the '
                    'serialization of a Document node; parsing it is the single '
                    'write path (AD-030-R1). Node classes are the five AD-030 '
                    'section 4 names — Document, Section, Ruling, Citation, '
                    'Passage — and the edge classes are the closed set that '
                    'section declares, plus CiTO-typed citation edges '
                    '(AD-030-R7).\n'
                    "IDENTITY. A Document's key is its repo-relative path slugged, "
                    'and its content_hash is the sha256 of the file (AD-030-R4: '
                    'identity is the hash, the path is the edit surface). A '
                    "Section's key is `<doc>#<slug of its section path>`, which is "
                    'stable across every edit that does not rename the heading — '
                    'that stability is what lets a task cite a ruling and still be '
                    'citing it a month later.\n'
                    'WHAT THIS SCHEMA DOES NOT DO. It declares no rules engine '
                    '(AD-030-R5). The only gates are the hash mismatch, the '
                    'admission invariant, and the design-note reference on task '
                    'registration.',
     'id': 'https://github.com/brockwebb/seldon/governed/schema',
     'imports': ['linkml:types', 'kit/core'],
     'license': 'MIT',
     'name': 'governed',
     'prefixes': {'cito': {'prefix_prefix': 'cito',
                           'prefix_reference': 'http://purl.org/spar/cito/'},
                  'doco': {'prefix_prefix': 'doco',
                           'prefix_reference': 'http://purl.org/spar/doco/'},
                  'fabio': {'prefix_prefix': 'fabio',
                            'prefix_reference': 'http://purl.org/spar/fabio/'},
                  'governed': {'prefix_prefix': 'governed',
                               'prefix_reference': 'https://github.com/brockwebb/seldon/governed/'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'},
                  'prov': {'prefix_prefix': 'prov',
                           'prefix_reference': 'http://www.w3.org/ns/prov#'},
                  'squiddy': {'prefix_prefix': 'squiddy',
                              'prefix_reference': 'https://github.com/brockwebb/squiddy/schema/core/'}},
     'source_file': '/Users/brock/GitHub/seldon/governed/schema/governed.yaml',
     'title': 'the governed-documents graph'} )

class AssertionStatus(str, Enum):
    """
    The authority model on an assertion, from fss-policy-kg's overlay discipline.
    """
    proposed = "proposed"
    accepted = "accepted"
    retracted = "retracted"


class ManifestStage(str, Enum):
    """
    Axis 1, pipeline position, profiling UNECE GSBPM v5.1 (icsp_notebook/corpus/manifest_schema.md). `admitting` is `in_graph` in the middle of becoming true (v7.11, DI-078).
    """
    cataloged = "cataloged"
    acquired = "acquired"
    admitting = "admitting"
    in_graph = "in_graph"
    assess_queue = "assess_queue"


class ManifestDisposition(str, Enum):
    """
    Axis 2, intent or role, profiling DDI-Lifecycle 3.3 with local reason codes. A graph's config restricts this to the values it uses; a value not in the config is a gate failure.
    """
    active = "active"
    reference = "reference"
    metadata_only = "metadata_only"
    excludedCOLONdeferred = "excluded:deferred"
    excludedCOLONrestricted = "excluded:restricted"
    excludedCOLONout_of_scope = "excluded:out_of_scope"


class EventKind(str, Enum):
    node = "node"
    edge = "edge"
    retract = "retract"
    manifest = "manifest"
    catalog = "catalog"


class DocKind(str, Enum):
    """
    Which governed directory the document came from. The directory is the document's genre and decides how hard its citation gate is (AD-030-R6: a design note ships with `proposed` citations, a paper does not).
    """
    design = "design"
    """
    docs/design/ — architectural decisions and design notes.
    """
    requirements = "requirements"
    """
    docs/requirements/ — specifications.
    """
    cc_task = "cc_task"
    """
    cc_tasks/ — Claude Code task specifications and their RESULT files.
    """
    handoff = "handoff"
    """
    handoffs/ — session handoff records.
    """


class ManifestState(str, Enum):
    """
    AD-030-R5. Every document ever considered is a node from the moment it is cataloged. A `declined` node carries its reason and never receives a content edge; reopening one requires a new decision with a `supersedes` edge.
    """
    cataloged = "cataloged"
    held = "held"
    admitted = "admitted"
    declined = "declined"


class DeonticForce(str, Enum):
    """
    What makes a Section a Ruling. Profiled from the deontic axis fss-policy-kg uses over obligations; the vocabulary here is the one Seldon's own documents actually write.
    """
    binding = "binding"
    """
    The text says BINDING, or carries a numbered ruling identifier.
    """
    obligation = "obligation"
    """
    MUST, SHALL, or "is required to".
    """
    prohibition = "prohibition"
    """
    NEVER, MUST NOT, "is forbidden".
    """
    recommendation = "recommendation"
    """
    SHOULD, "prefer", "by default".
    """


class CitationState(str, Enum):
    """
    AD-030-R6. Capture is free; verification is a separate, recorded transition.
    """
    proposed = "proposed"
    verified = "verified"


class CitoType(str, Enum):
    """
    CiTO (Shotton 2010), the subset AD-030-R7 names. `disagrees_with` and `refutes` carry a `reason` naming the constraint that no longer holds: rejected science stays in the graph as a rejected prescription rather than vanishing from it.
    """
    cites_as_evidence = "cites_as_evidence"
    uses_method_in = "uses_method_in"
    cites_for_information = "cites_for_information"
    extends = "extends"
    disagrees_with = "disagrees_with"
    refutes = "refutes"



class Node(ConfiguredBaseModel):
    """
    A property-graph node keyed by `id`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True,
         'from_schema': 'https://github.com/brockwebb/squiddy/schema/core'})

    id: str = Field(default=..., description="""The readable, source-scoped key the graph minted at admission. It never changes and is never reused; a name is a property (DI-060, DI-062, OD-4 §3.1).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'ManifestEntry']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Edge(ConfiguredBaseModel):
    """
    A property-graph edge from `subject` to `object`; the class is the predicate.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True,
         'from_schema': 'https://github.com/brockwebb/squiddy/schema/core'})

    subject: str = Field(default=..., description="""The id of the source node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    object: str = Field(default=..., description="""The id of the target node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class ManifestEntry(ConfiguredBaseModel):
    """
    One entry per document ever considered (DI-070). The two status axes are required.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/schema/core',
         'slot_usage': {'disposition': {'name': 'disposition', 'required': True},
                        'stage': {'name': 'stage', 'required': True}}})

    id: str = Field(default=..., description="""The readable, source-scoped key the graph minted at admission. It never changes and is never reused; a name is a property (DI-060, DI-062, OD-4 §3.1).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'ManifestEntry']} })
    kind: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry']} })
    stage: ManifestStage = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry']} })
    disposition: ManifestDisposition = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Document']} })
    title: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Document', 'Citation']} })
    source_url: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Citation']} })
    cited_in: Optional[str] = Field(default=None, description="""Where in the graph's own record this item is cited; the biblio assessment criterion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry']} })
    provenance_flag: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry']} })
    acquisition_status: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry']} })
    local_path: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Document']} })
    sha256: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Document']} })
    bytes: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry']} })
    retrieved_date: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry']} })
    verification_status: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry']} })
    notes: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry']} })
    admitting_since: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry']} })


class EventEnvelope(ConfiguredBaseModel):
    """
    One line of the ledger.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/schema/core',
         'slot_usage': {'event_kind': {'name': 'event_kind', 'required': True},
                        'run_id': {'name': 'run_id', 'required': True},
                        'ts': {'name': 'ts', 'required': True},
                        'type': {'name': 'type', 'required': True}}})

    event_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope']} })
    run_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope']} })
    event_stage: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope']} })
    type: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope']} })
    event_kind: EventKind = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope']} })
    ts: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope']} })
    schema_version: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope']} })
    doc_id: Optional[str] = Field(default=None, description="""The Document a child node belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope', 'Section', 'Ruling', 'Citation', 'Passage']} })
    provenance: Optional[Any] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope']} })
    payload: Optional[Any] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope']} })


class Document(Node):
    """
    One governed markdown file. `id` is its repo-relative path slugged; `path` is the live edit surface; `content_hash` is what identity actually rests on (AD-030-R4).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/seldon/governed/schema',
         'slot_usage': {'title': {'name': 'title', 'required': True}}})

    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Document', 'Citation']} })
    local_path: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Document']} })
    sha256: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Document']} })
    content_hash: Optional[str] = Field(default=None, description="""sha256 of the file as it stood when the assertion was made (AD-030-R4).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document', 'Section', 'Ruling', 'Passage']} })
    disposition: Optional[ManifestDisposition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Document']} })
    reason: Optional[str] = Field(default=None, description="""Why a declined document was declined, or why a CiTO edge disagrees. Required on both by AD-030-R5 and R7; a refusal with no reason cannot be argued with later.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document', 'Supersedes', 'Cites']} })
    identifiers: Optional[list[str]] = Field(default=None, description="""Every identifier reference the node's text names (`AD-030`, `DN-4`, an eight-hex task id prefix), recovered lexically. Squiddy turns the ones that resolve inside THIS graph into `Mentions` edges; the rest are carried here because they resolve in Seldon's graph, not in this one, and `seldon governed sync` is what can see them (AD-030-R10: the coupling is a stream, not awareness). A reference that is dropped rather than carried is a link the graph can never recover.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document', 'Section', 'Ruling']} })
    path: str = Field(default=..., description="""Repo-relative path, the edit surface. Governed documents stay in place.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document']} })
    doc_kind: DocKind = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Document']} })
    manifest_state: ManifestState = Field(default=..., description="""AD-030-R5. No content edge may point at a document that is not `admitted`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document']} })
    decided_by: Optional[str] = Field(default=None, description="""Who decided a `declined` state.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document']} })
    decided_date: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Document']} })
    seldon_artifact_id: Optional[str] = Field(default=None, description="""The artifact_id of the ArchitecturalDecision or DesignNote node Seldon already holds for this path, when there is one. Carried so the import matches rather than double-minting.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document']} })
    byte_length: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Document']} })
    section_count: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Document']} })
    ruling_count: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Document']} })
    id: str = Field(default=..., description="""The readable, source-scoped key the graph minted at admission. It never changes and is never reused; a name is a property (DI-060, DI-062, OD-4 §3.1).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'ManifestEntry']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Section(Node):
    """
    An addressable child of a Document with a stable id and a verbatim span (doco:Section). The id is `<doc>#<slug of section path>`, so a citation survives every edit that leaves the heading alone.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/seldon/governed/schema',
         'slot_usage': {'doc_id': {'name': 'doc_id', 'required': True},
                        'text': {'name': 'text', 'required': True}}})

    doc_id: str = Field(default=..., description="""The Document a child node belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope', 'Section', 'Ruling', 'Citation', 'Passage']} })
    text: str = Field(default=..., description="""The verbatim span. Never paraphrased; the hash is over the file, not over this.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section', 'Ruling', 'Citation', 'Passage']} })
    section_path: Optional[str] = Field(default=None, description="""The heading stack, joined, as the parser produced it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section', 'Ruling']} })
    span_start: Optional[int] = Field(default=None, description="""Character offset of the node's verbatim text in the document.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section', 'Ruling', 'Passage']} })
    span_end: Optional[int] = Field(default=None, description="""End offset, exclusive.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section', 'Ruling', 'Passage']} })
    content_hash: Optional[str] = Field(default=None, description="""sha256 of the file as it stood when the assertion was made (AD-030-R4).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document', 'Section', 'Ruling', 'Passage']} })
    identifiers: Optional[list[str]] = Field(default=None, description="""Every identifier reference the node's text names (`AD-030`, `DN-4`, an eight-hex task id prefix), recovered lexically. Squiddy turns the ones that resolve inside THIS graph into `Mentions` edges; the rest are carried here because they resolve in Seldon's graph, not in this one, and `seldon governed sync` is what can see them (AD-030-R10: the coupling is a stream, not awareness). A reference that is dropped rather than carried is a link the graph can never recover.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document', 'Section', 'Ruling']} })
    heading: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Section']} })
    level: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Section']} })
    ordinal: Optional[int] = Field(default=None, description="""Position in reading order within the document.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section']} })
    id: str = Field(default=..., description="""The readable, source-scoped key the graph minted at admission. It never changes and is never reused; a name is a property (DI-060, DI-062, OD-4 §3.1).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'ManifestEntry']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Ruling(Node):
    """
    A Section or paragraph whose text is deontic (AD-030 section 4). A Ruling is the unit a task is `constrained_by`; the nanopublication assertion is the model (Groth et al. 2010).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/seldon/governed/schema',
         'slot_usage': {'doc_id': {'name': 'doc_id', 'required': True},
                        'text': {'name': 'text', 'required': True}}})

    doc_id: str = Field(default=..., description="""The Document a child node belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope', 'Section', 'Ruling', 'Citation', 'Passage']} })
    text: str = Field(default=..., description="""The verbatim span. Never paraphrased; the hash is over the file, not over this.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section', 'Ruling', 'Citation', 'Passage']} })
    section_path: Optional[str] = Field(default=None, description="""The heading stack, joined, as the parser produced it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section', 'Ruling']} })
    span_start: Optional[int] = Field(default=None, description="""Character offset of the node's verbatim text in the document.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section', 'Ruling', 'Passage']} })
    span_end: Optional[int] = Field(default=None, description="""End offset, exclusive.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section', 'Ruling', 'Passage']} })
    content_hash: Optional[str] = Field(default=None, description="""sha256 of the file as it stood when the assertion was made (AD-030-R4).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document', 'Section', 'Ruling', 'Passage']} })
    identifiers: Optional[list[str]] = Field(default=None, description="""Every identifier reference the node's text names (`AD-030`, `DN-4`, an eight-hex task id prefix), recovered lexically. Squiddy turns the ones that resolve inside THIS graph into `Mentions` edges; the rest are carried here because they resolve in Seldon's graph, not in this one, and `seldon governed sync` is what can see them (AD-030-R10: the coupling is a stream, not awareness). A reference that is dropped rather than carried is a link the graph can never recover.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document', 'Section', 'Ruling']} })
    ruling_identifier: Optional[str] = Field(default=None, description="""The document's own label for it, e.g. `AD-030-R9`, when the text carries one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Ruling']} })
    force: DeonticForce = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Ruling']} })
    matched_pattern: str = Field(default=..., description="""The configured pattern that classified this text as deontic. Recorded so a Ruling can be argued with: a wrong match is a pattern to fix, not a judgement to relitigate.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Ruling']} })
    section_id: Optional[str] = Field(default=None, description="""The Section this ruling sits in, when it is a paragraph rather than a section.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Ruling']} })
    id: str = Field(default=..., description="""The readable, source-scoped key the graph minted at admission. It never changes and is never reused; a name is a property (DI-060, DI-062, OD-4 §3.1).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'ManifestEntry']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Citation(Node):
    """
    Any citation appearing in a governed document, captured at ingest in state `proposed` (AD-030-R6). Verification is a transition carrying method, date and by.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/seldon/governed/schema'})

    doc_id: Optional[str] = Field(default=None, description="""The Document a child node belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope', 'Section', 'Ruling', 'Citation', 'Passage']} })
    title: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Document', 'Citation']} })
    source_url: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Citation']} })
    text: Optional[str] = Field(default=None, description="""The verbatim span. Never paraphrased; the hash is over the file, not over this.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section', 'Ruling', 'Citation', 'Passage']} })
    citation_state: CitationState = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Citation']} })
    raw: str = Field(default=..., description="""The citation exactly as the document writes it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Citation']} })
    authors: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Citation']} })
    year: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Citation']} })
    doi: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Citation']} })
    verification_method: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Citation']} })
    verification_date: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Citation']} })
    verified_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Citation']} })
    id: str = Field(default=..., description="""The readable, source-scoped key the graph minted at admission. It never changes and is never reused; a name is a property (DI-060, DI-062, OD-4 §3.1).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'ManifestEntry']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Passage(Node):
    """
    A quoted span in a source, with the hash of the quoted text (AD-030-R6; the micropublication model, Clark et al. 2014). Minted only when a document actually quotes something.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/seldon/governed/schema',
         'slot_usage': {'text': {'name': 'text', 'required': True}}})

    doc_id: Optional[str] = Field(default=None, description="""The Document a child node belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope', 'Section', 'Ruling', 'Citation', 'Passage']} })
    text: str = Field(default=..., description="""The verbatim span. Never paraphrased; the hash is over the file, not over this.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section', 'Ruling', 'Citation', 'Passage']} })
    span_start: Optional[int] = Field(default=None, description="""Character offset of the node's verbatim text in the document.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section', 'Ruling', 'Passage']} })
    span_end: Optional[int] = Field(default=None, description="""End offset, exclusive.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Section', 'Ruling', 'Passage']} })
    content_hash: Optional[str] = Field(default=None, description="""sha256 of the file as it stood when the assertion was made (AD-030-R4).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document', 'Section', 'Ruling', 'Passage']} })
    quoted_in_section: Optional[str] = Field(default=None, description="""The Section id the quotation appears in.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Passage']} })
    id: str = Field(default=..., description="""The readable, source-scoped key the graph minted at admission. It never changes and is never reused; a name is a property (DI-060, DI-062, OD-4 §3.1).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'ManifestEntry']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Contains(Edge):
    """
    (Document)-[:CONTAINS]->(Section | Ruling | Citation | Passage). Structural parenthood.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/seldon/governed/schema'})

    subject: str = Field(default=..., description="""The id of the source node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    object: str = Field(default=..., description="""The id of the target node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class ConstrainedBy(Edge):
    """
    (task)-[:CONSTRAINED_BY]->(Ruling). Written by `seldon cc register` from identifier reference and concept overlap; the edge AD-030 exists to create.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/seldon/governed/schema'})

    match_method: Optional[str] = Field(default=None, description="""identifier | concept_overlap""", json_schema_extra = { "linkml_meta": {'domain_of': ['ConstrainedBy']} })
    match_score: Optional[float] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ConstrainedBy']} })
    matched_terms: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ConstrainedBy']} })
    subject: str = Field(default=..., description="""The id of the source node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    object: str = Field(default=..., description="""The id of the target node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Satisfies(Edge):
    """
    (task | Script)-[:SATISFIES]->(Requirement).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/seldon/governed/schema'})

    subject: str = Field(default=..., description="""The id of the source node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    object: str = Field(default=..., description="""The id of the target node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Supersedes(Edge):
    """
    (Ruling)-[:SUPERSEDES]->(Ruling), or decision to decision.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/seldon/governed/schema'})

    reason: Optional[str] = Field(default=None, description="""Why a declined document was declined, or why a CiTO edge disagrees. Required on both by AD-030-R5 and R7; a refusal with no reason cannot be argued with later.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document', 'Supersedes', 'Cites']} })
    subject: str = Field(default=..., description="""The id of the source node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    object: str = Field(default=..., description="""The id of the target node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Extends(Edge):
    """
    (Document)-[:EXTENDS]->(Document), from the `Extends:` header field.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/seldon/governed/schema'})

    raw_field: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Extends', 'DependsOn']} })
    subject: str = Field(default=..., description="""The id of the source node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    object: str = Field(default=..., description="""The id of the target node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class DependsOn(Edge):
    """
    (Document)-[:DEPENDS_ON]->(Document), from the `Depends on:` header field.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/seldon/governed/schema'})

    raw_field: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Extends', 'DependsOn']} })
    subject: str = Field(default=..., description="""The id of the source node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    object: str = Field(default=..., description="""The id of the target node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Mentions(Edge):
    """
    (any)-[:MENTIONS]->(any), recovered lexically from an identifier reference: `AD-NNN`, `DN-`, `S-NNN`, `TN-N`, or an eight-hex task id prefix. The weakest edge in the set, and the one that finds the most.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/seldon/governed/schema'})

    identifier: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Mentions']} })
    identifier_kind: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Mentions']} })
    occurrences: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Mentions']} })
    subject: str = Field(default=..., description="""The id of the source node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    object: str = Field(default=..., description="""The id of the target node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Cites(Edge):
    """
    (Section | Document)-[:CITES]->(Citation | Passage), typed with a CiTO intent (AD-030-R7).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/seldon/governed/schema'})

    reason: Optional[str] = Field(default=None, description="""Why a declined document was declined, or why a CiTO edge disagrees. Required on both by AD-030-R5 and R7; a refusal with no reason cannot be argued with later.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Document', 'Supersedes', 'Cites']} })
    cito_type: CitoType = Field(default=CitoType.cites_for_information, json_schema_extra = { "linkml_meta": {'domain_of': ['Cites'], 'ifabsent': 'string(cites_for_information)'} })
    raw_reference: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Cites']} })
    subject: str = Field(default=..., description="""The id of the source node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    object: str = Field(default=..., description="""The id of the target node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class GovernedGraph(ConfiguredBaseModel):
    """
    The graph as two lists, the shape of the node-link export.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/seldon/governed/schema',
         'tree_root': True})

    nodes: Optional[list[Node]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['GovernedGraph']} })
    edges: Optional[list[Edge]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['GovernedGraph']} })


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
Node.model_rebuild()
Edge.model_rebuild()
ManifestEntry.model_rebuild()
EventEnvelope.model_rebuild()
Document.model_rebuild()
Section.model_rebuild()
Ruling.model_rebuild()
Citation.model_rebuild()
Passage.model_rebuild()
Contains.model_rebuild()
ConstrainedBy.model_rebuild()
Satisfies.model_rebuild()
Supersedes.model_rebuild()
Extends.model_rebuild()
DependsOn.model_rebuild()
Mentions.model_rebuild()
Cites.model_rebuild()
GovernedGraph.model_rebuild()
