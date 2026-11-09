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


linkml_meta = LinkMLMeta({'default_prefix': 'seldonbib',
     'default_range': 'string',
     'description': "The works, standards and software Seldon's design notes and "
                    'tasks rest on, each resolved to its identifier (DOI, OpenAlex '
                    'id, ISBN, standard number, or repository and release) with '
                    'its citation metadata, its licence, the governed notes and '
                    'tasks that cite it, and its text where the licence allows; a '
                    'source no host would serve to a script is recorded with its '
                    'access posture and marked for manual acquisition.',
     'id': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/schema',
     'imports': ['linkml:types', '/Users/brock/GitHub/squiddy/squiddy/schema/core'],
     'license': 'MIT',
     'name': 'seldon_biblio',
     'prefixes': {'cito': {'prefix_prefix': 'cito',
                           'prefix_reference': 'http://purl.org/spar/cito/'},
                  'fabio': {'prefix_prefix': 'fabio',
                            'prefix_reference': 'http://purl.org/spar/fabio/'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'},
                  'prov': {'prefix_prefix': 'prov',
                           'prefix_reference': 'http://www.w3.org/ns/prov#'},
                  'seldonbib': {'prefix_prefix': 'seldonbib',
                                'prefix_reference': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/'},
                  'squiddy': {'prefix_prefix': 'squiddy',
                              'prefix_reference': 'https://github.com/brockwebb/squiddy/schema/core/'}},
     'source_file': '/Users/brock/GitHub/seldon/.claude/worktrees/jaunty-nibbling-brook/graphs/seldon-biblio/schema/seldon_biblio.yaml',
     'title': "Seldon's bibliographic graph"} )

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


class CitoIntent(str, Enum):
    """
    CiTO citation intents, the subset a bibliographic evidence graph needs (Peroni and Shotton 2012, peroni2012fabio). The default is the weakest claim.
    """
    citesForInformation = "citesForInformation"
    citesAsAuthority = "citesAsAuthority"
    citesAsEvidence = "citesAsEvidence"
    usesMethodIn = "usesMethodIn"
    supports = "supports"
    disagreesWith = "disagreesWith"
    extends = "extends"
    """
    Fillable by extraction (S-007); no deterministic source sets it.
    """


class DecisionDisposition(str, Enum):
    """
    What a repository did with a decision it inherited (S-008 Part B). Read from the register's own tag column; absent where the register states none, and that absence is the signal that the decision is this repository's own rather than one it took over.
    """
    inherit = "inherit"
    """
    the kit implements the decision as stated
    """
    adapt = "adapt"
    """
    the decision is right and its store-specific expression moves into configuration
    """
    does_not_apply = "does_not_apply"
    """
    it belongs to a graph or to Seldon and the kit must not carry it
    """


class DecisionKind(str, Enum):
    R = "R"
    """
    a numbered ruling in one of this repository's design notes (DN-001 to DN-003)
    """
    T = "T"
    """
    a TEVV requirement in DN-003 R-17
    """
    AD = "AD"
    """
    an architectural decision in Seldon's own register
    """
    DI = "DI"
    """
    a row of docs/DECISIONS_INHERITED.md
    """
    OD = "OD"
    """
    an open decision in docs/KIT_BOUNDARY.md or its memo
    """
    CK = "CK"
    """
    a candidate verdict in docs/CANDIDATE_KITS.md
    """
    CLAUDE = "CLAUDE"
    """
    an invariant stated in CLAUDE.md
    """
    TASK = "TASK"
    """
    a task file's own standards list
    """


class ExpressionRelation(str, Enum):
    is_preprint_of = "is_preprint_of"
    is_version_of = "is_version_of"


class DocKind(str, Enum):
    """
    The sort of record an internal document is (S-008 Part A, fixed by the task). Decided by the path and the file name under the ordered rules in `engine.repodocs.doc_kind_rules`.
    """
    decision_record = "decision_record"
    handoff = "handoff"
    lab_note = "lab_note"
    delivery_report = "delivery_report"
    design_note = "design_note"
    cc_task = "cc_task"
    other = "other"



class GroundingSpan(ConfiguredBaseModel):
    """
    Character offsets into the parsed intermediate's `plain_text`, the sha256 of the located text (so anyone holding the intermediate can verify the slice), and the sha256 of the whole plain text (so a re-parse that moves the offsets is detectable rather than silent).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/schema/core'})

    start: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['GroundingSpan']} })
    end: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['GroundingSpan']} })
    sha256: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['GroundingSpan', 'ManifestEntry', 'Work', 'Standard']} })
    parsed_sha256: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['GroundingSpan']} })


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
    prov_extractor: Optional[str] = Field(default=None, description="""The instrument that made an extracted assertion, as `<provider>:<alias asked for>` (`claude_cli_max_oauth:sonnet`). Absent on a deterministic assertion, and that absence is itself the signal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor_version: Optional[str] = Field(default=None, description="""The model id the client ACTUALLY RESOLVED the alias to, read from the CLI envelope of the call that made the assertion; never the alias (DI-023: recording an alias as the model is citing a document that quotes a statute as if it were the statute).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_prompt_sha256: Optional[str] = Field(default=None, description="""The sha256 of the prompt template the extraction ran under; a prompt change is a new extractor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_run_id: Optional[str] = Field(default=None, description="""The run id of the extraction that proposed this assertion (also the envelope's run_id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    grounding_span: Optional[GroundingSpan] = Field(default=None, description="""Where in the source the harness located the text behind this assertion. Located and cut by the harness from the parsed intermediate, never quoted by the model (ai-readiness-kg's anchor contract, S-001 finding 2). A span the harness cannot locate is a failed extraction, never a stored assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


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
    prov_extractor: Optional[str] = Field(default=None, description="""The instrument that made an extracted assertion, as `<provider>:<alias asked for>` (`claude_cli_max_oauth:sonnet`). Absent on a deterministic assertion, and that absence is itself the signal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor_version: Optional[str] = Field(default=None, description="""The model id the client ACTUALLY RESOLVED the alias to, read from the CLI envelope of the call that made the assertion; never the alias (DI-023: recording an alias as the model is citing a document that quotes a statute as if it were the statute).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_prompt_sha256: Optional[str] = Field(default=None, description="""The sha256 of the prompt template the extraction ran under; a prompt change is a new extractor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_run_id: Optional[str] = Field(default=None, description="""The run id of the extraction that proposed this assertion (also the envelope's run_id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    grounding_span: Optional[GroundingSpan] = Field(default=None, description="""Where in the source the harness located the text behind this assertion. Located and cut by the harness from the parsed intermediate, never quoted by the model (ai-readiness-kg's anchor contract, S-001 finding 2). A span the harness cannot locate is a failed extraction, never a stored assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


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
    disposition: ManifestDisposition = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software', 'Decision']} })
    title: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software', 'Decision']} })
    source_url: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software']} })
    cited_in: Optional[str] = Field(default=None, description="""Where in the graph's own record this item is cited; the biblio assessment criterion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software']} })
    provenance_flag: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry']} })
    acquisition_status: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry']} })
    local_path: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard']} })
    sha256: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['GroundingSpan', 'ManifestEntry', 'Work', 'Standard']} })
    bytes: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry']} })
    retrieved_date: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry']} })
    verification_status: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Standard', 'Software']} })
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
    doc_id: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope']} })
    provenance: Optional[Any] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope']} })
    payload: Optional[Any] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['EventEnvelope']} })


class Work(Node):
    """
    A published or preprinted scholarly work; identity is DOI plus OpenAlex work id.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/schema',
         'slot_usage': {'cited_in': {'multivalued': True, 'name': 'cited_in'},
                        'title': {'name': 'title', 'required': True}}})

    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software', 'Decision']} })
    source_url: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software']} })
    cited_in: Optional[list[str]] = Field(default=None, description="""Where in the graph's own record this item is cited; the biblio assessment criterion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software']} })
    local_path: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard']} })
    sha256: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['GroundingSpan', 'ManifestEntry', 'Work', 'Standard']} })
    disposition: Optional[ManifestDisposition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software', 'Decision']} })
    doi: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Work', 'ExternalReference']} })
    openalex_id: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    arxiv_id: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    year: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    publication_date: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    venue: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    work_type: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    oa_status: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    oa_url: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    licence: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Work', 'Software']} })
    abstract: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    authors_raw: Optional[list[str]] = Field(default=None, description="""The author strings as the resolver returned them, kept for the pilot's gold.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    references_total: Optional[int] = Field(default=None, description="""References in the resolver's reference list (Crossref).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    references_keyed: Optional[int] = Field(default=None, description="""Of those, references that carry a DOI and so became a Cites edge. The difference is the logged abstention for references the graph cannot key (DI-046).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    doc_kind: Optional[DocKind] = Field(default=None, description="""What sort of record this is, for an internal document (S-008 Part A). Absent on a published work, and that absence is the signal that it came from a publisher.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    repo: Optional[str] = Field(default=None, description="""The repository the document lives in, as the catalog's source names it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    commit: Optional[str] = Field(default=None, description="""That repository's HEAD when the document was cataloged.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    file_type: Optional[str] = Field(default=None, description="""The file extension, without the dot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    first_heading: Optional[str] = Field(default=None, description="""The document's first heading, which is also its title when it has one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    doc_date: Optional[str] = Field(default=None, description="""The date in the file name or the YAML frontmatter, never the file's mtime: a date invented from the disk orders the record by when it was last touched.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    headings: Optional[list[str]] = Field(default=None, description="""Every heading, in reading order. This is what the mention layer scans for an internal document (Part E). The body prose is never stored: the graph holds the path, the hashes and the headings, and the file is the text.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Work']} })
    id: str = Field(default=..., description="""The readable, source-scoped key the graph minted at admission. It never changes and is never reused; a name is a property (DI-060, DI-062, OD-4 §3.1).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'ManifestEntry']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor: Optional[str] = Field(default=None, description="""The instrument that made an extracted assertion, as `<provider>:<alias asked for>` (`claude_cli_max_oauth:sonnet`). Absent on a deterministic assertion, and that absence is itself the signal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor_version: Optional[str] = Field(default=None, description="""The model id the client ACTUALLY RESOLVED the alias to, read from the CLI envelope of the call that made the assertion; never the alias (DI-023: recording an alias as the model is citing a document that quotes a statute as if it were the statute).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_prompt_sha256: Optional[str] = Field(default=None, description="""The sha256 of the prompt template the extraction ran under; a prompt change is a new extractor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_run_id: Optional[str] = Field(default=None, description="""The run id of the extraction that proposed this assertion (also the envelope's run_id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    grounding_span: Optional[GroundingSpan] = Field(default=None, description="""Where in the source the harness located the text behind this assertion. Located and cut by the harness from the parsed intermediate, never quoted by the model (ai-readiness-kg's anchor contract, S-001 finding 2). A span the harness cannot locate is a failed extraction, never a stored assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Person(Node):
    """
    A person named as an author. The key is local and readable (OD-4 §3.1); ORCID is a declared authority id carried as a property and used as the exactMatch key.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/schema'})

    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Person', 'Organization']} })
    name_normalized: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Person']} })
    orcid: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Person']} })
    openalex_author_id: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Person']} })
    id: str = Field(default=..., description="""The readable, source-scoped key the graph minted at admission. It never changes and is never reused; a name is a property (DI-060, DI-062, OD-4 §3.1).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'ManifestEntry']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor: Optional[str] = Field(default=None, description="""The instrument that made an extracted assertion, as `<provider>:<alias asked for>` (`claude_cli_max_oauth:sonnet`). Absent on a deterministic assertion, and that absence is itself the signal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor_version: Optional[str] = Field(default=None, description="""The model id the client ACTUALLY RESOLVED the alias to, read from the CLI envelope of the call that made the assertion; never the alias (DI-023: recording an alias as the model is citing a document that quotes a statute as if it were the statute).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_prompt_sha256: Optional[str] = Field(default=None, description="""The sha256 of the prompt template the extraction ran under; a prompt change is a new extractor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_run_id: Optional[str] = Field(default=None, description="""The run id of the extraction that proposed this assertion (also the envelope's run_id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    grounding_span: Optional[GroundingSpan] = Field(default=None, description="""Where in the source the harness located the text behind this assertion. Located and cut by the harness from the parsed intermediate, never quoted by the model (ai-readiness-kg's anchor contract, S-001 finding 2). A span the harness cannot locate is a failed extraction, never a stored assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Organization(Node):
    """
    An institution an author is affiliated with; ROR is the declared authority id.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/schema'})

    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Person', 'Organization']} })
    ror: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Organization']} })
    openalex_institution_id: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Organization']} })
    country_code: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Organization']} })
    id: str = Field(default=..., description="""The readable, source-scoped key the graph minted at admission. It never changes and is never reused; a name is a property (DI-060, DI-062, OD-4 §3.1).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'ManifestEntry']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor: Optional[str] = Field(default=None, description="""The instrument that made an extracted assertion, as `<provider>:<alias asked for>` (`claude_cli_max_oauth:sonnet`). Absent on a deterministic assertion, and that absence is itself the signal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor_version: Optional[str] = Field(default=None, description="""The model id the client ACTUALLY RESOLVED the alias to, read from the CLI envelope of the call that made the assertion; never the alias (DI-023: recording an alias as the model is citing a document that quotes a statute as if it were the statute).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_prompt_sha256: Optional[str] = Field(default=None, description="""The sha256 of the prompt template the extraction ran under; a prompt change is a new extractor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_run_id: Optional[str] = Field(default=None, description="""The run id of the extraction that proposed this assertion (also the envelope's run_id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    grounding_span: Optional[GroundingSpan] = Field(default=None, description="""Where in the source the harness located the text behind this assertion. Located and cut by the harness from the parsed intermediate, never quoted by the model (ai-readiness-kg's anchor contract, S-001 finding 2). A span the harness cannot locate is a failed extraction, never a stored assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Standard(Node):
    """
    A specification with no DOI; identity is its canonical URL plus its version date. A specification that also publishes a vocabulary file carries what was imported from it (S-008 Part D): the prefix, the namespace IRI, the hash of the file that was read and how many terms it yielded, so a vocabulary that changes under the graph is a changed hash and not a silent drift.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/schema',
         'slot_usage': {'cited_in': {'multivalued': True, 'name': 'cited_in'},
                        'title': {'name': 'title', 'required': True}}})

    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software', 'Decision']} })
    source_url: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software']} })
    cited_in: Optional[list[str]] = Field(default=None, description="""Where in the graph's own record this item is cited; the biblio assessment criterion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software']} })
    verification_status: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Standard', 'Software']} })
    disposition: Optional[ManifestDisposition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software', 'Decision']} })
    local_path: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard']} })
    sha256: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['GroundingSpan', 'ManifestEntry', 'Work', 'Standard']} })
    version: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Standard', 'Software']} })
    version_date: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Standard', 'Software']} })
    publisher: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Standard']} })
    vocab_prefix: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Standard']} })
    vocab_iri: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Standard']} })
    vocab_term_count: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Standard']} })
    vocab_retrieved_date: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Standard']} })
    id: str = Field(default=..., description="""The readable, source-scoped key the graph minted at admission. It never changes and is never reused; a name is a property (DI-060, DI-062, OD-4 §3.1).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'ManifestEntry']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor: Optional[str] = Field(default=None, description="""The instrument that made an extracted assertion, as `<provider>:<alias asked for>` (`claude_cli_max_oauth:sonnet`). Absent on a deterministic assertion, and that absence is itself the signal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor_version: Optional[str] = Field(default=None, description="""The model id the client ACTUALLY RESOLVED the alias to, read from the CLI envelope of the call that made the assertion; never the alias (DI-023: recording an alias as the model is citing a document that quotes a statute as if it were the statute).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_prompt_sha256: Optional[str] = Field(default=None, description="""The sha256 of the prompt template the extraction ran under; a prompt change is a new extractor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_run_id: Optional[str] = Field(default=None, description="""The run id of the extraction that proposed this assertion (also the envelope's run_id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    grounding_span: Optional[GroundingSpan] = Field(default=None, description="""Where in the source the harness located the text behind this assertion. Located and cut by the harness from the parsed intermediate, never quoted by the model (ai-readiness-kg's anchor contract, S-001 finding 2). A span the harness cannot locate is a failed extraction, never a stored assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Software(Node):
    """
    A named implementation cited as prior art; identity is its repository plus a release.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/schema',
         'slot_usage': {'cited_in': {'multivalued': True, 'name': 'cited_in'},
                        'title': {'name': 'title', 'required': True}}})

    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software', 'Decision']} })
    source_url: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software']} })
    cited_in: Optional[list[str]] = Field(default=None, description="""Where in the graph's own record this item is cited; the biblio assessment criterion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software']} })
    verification_status: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Standard', 'Software']} })
    disposition: Optional[ManifestDisposition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software', 'Decision']} })
    repository: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Software']} })
    licence: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Work', 'Software']} })
    version: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Standard', 'Software']} })
    version_date: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Standard', 'Software']} })
    last_push: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Software']} })
    id: str = Field(default=..., description="""The readable, source-scoped key the graph minted at admission. It never changes and is never reused; a name is a property (DI-060, DI-062, OD-4 §3.1).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'ManifestEntry']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor: Optional[str] = Field(default=None, description="""The instrument that made an extracted assertion, as `<provider>:<alias asked for>` (`claude_cli_max_oauth:sonnet`). Absent on a deterministic assertion, and that absence is itself the signal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor_version: Optional[str] = Field(default=None, description="""The model id the client ACTUALLY RESOLVED the alias to, read from the CLI envelope of the call that made the assertion; never the alias (DI-023: recording an alias as the model is citing a document that quotes a statute as if it were the statute).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_prompt_sha256: Optional[str] = Field(default=None, description="""The sha256 of the prompt template the extraction ran under; a prompt change is a new extractor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_run_id: Optional[str] = Field(default=None, description="""The run id of the extraction that proposed this assertion (also the envelope's run_id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    grounding_span: Optional[GroundingSpan] = Field(default=None, description="""Where in the source the harness located the text behind this assertion. Located and cut by the harness from the parsed intermediate, never quoted by the model (ai-readiness-kg's anchor contract, S-001 finding 2). A span the harness cannot locate is a failed extraction, never a stored assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Decision(Node):
    """
    A recorded decision of this repository (a DI row, an OD memo, a candidate verdict, a numbered ruling in a design note, a TEVV requirement, a Seldon AD) as a node, so the graph can answer \"what does this decision cite\" and \"what did we decide about this\". S-008 Part B fills the register, the statement and the disposition on the nodes the `cited_in` layer had already minted; nothing is re-minted (the task's rule for the OD-4 nodes).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/schema'})

    title: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software', 'Decision']} })
    decision_kind: Optional[DecisionKind] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Decision']} })
    source_document: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Decision']} })
    register: Optional[str] = Field(default=None, description="""Retired. Use `decision_register`.""", json_schema_extra = { "linkml_meta": {'deprecated': 'Renamed to `decision_register` on 2026-09-13 (S-008 Part B) '
                       'and DECLARED FOR REPLAY ONLY. No live node carries it: the 148 '
                       'nodes that did were retracted and asserted again under the new '
                       'name in one run. The slot stays because the projection '
                       'validates EVERY event in the ledger against the current '
                       'classes, so a slot a past event used can never be removed from '
                       'the schema, only retired. That is what an append-only record '
                       'costs and it is cheaper than the alternative (DN-003 R-19; '
                       'DI-013: append, never rewrite).',
         'domain_of': ['Decision']} })
    decision_register: Optional[str] = Field(default=None, description="""The register the decision was read from (DECISIONS_INHERITED, DN-001, SELDON_AD). Named `decision_register` and not `register`, which shadows a base-class attribute of the generated Pydantic class and makes the framework warn on every run; the projection's reserved-name rule refuses `label` and `key` for the harder version of the same problem.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Decision']} })
    disposition: Optional[DecisionDisposition] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ManifestEntry', 'Work', 'Standard', 'Software', 'Decision']} })
    statement: Optional[str] = Field(default=None, description="""The decision in its own words: the register row's statement column, or the first paragraph under a numbered ruling's heading. What the mention layer scans (Part E).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Decision']} })
    id: str = Field(default=..., description="""The readable, source-scoped key the graph minted at admission. It never changes and is never reused; a name is a property (DI-060, DI-062, OD-4 §3.1).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'ManifestEntry']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor: Optional[str] = Field(default=None, description="""The instrument that made an extracted assertion, as `<provider>:<alias asked for>` (`claude_cli_max_oauth:sonnet`). Absent on a deterministic assertion, and that absence is itself the signal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor_version: Optional[str] = Field(default=None, description="""The model id the client ACTUALLY RESOLVED the alias to, read from the CLI envelope of the call that made the assertion; never the alias (DI-023: recording an alias as the model is citing a document that quotes a statute as if it were the statute).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_prompt_sha256: Optional[str] = Field(default=None, description="""The sha256 of the prompt template the extraction ran under; a prompt change is a new extractor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_run_id: Optional[str] = Field(default=None, description="""The run id of the extraction that proposed this assertion (also the envelope's run_id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    grounding_span: Optional[GroundingSpan] = Field(default=None, description="""Where in the source the harness located the text behind this assertion. Located and cut by the harness from the parsed intermediate, never quoted by the model (ai-readiness-kg's anchor contract, S-001 finding 2). A span the harness cannot locate is a failed extraction, never a stored assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class ExternalReference(Node):
    """
    A citation target outside the graph, keyed by DOI or URL (`id` is `doi:<doi>`), so a pointer outside is a node with a key and never a bare string (fss-policy-kg practice, DI-046). No slot may be named `key` or `label`: the projection reserves both (squiddy.project).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/schema'})

    ref_kind: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ExternalReference']} })
    doi: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Work', 'ExternalReference']} })
    id: str = Field(default=..., description="""The readable, source-scoped key the graph minted at admission. It never changes and is never reused; a name is a property (DI-060, DI-062, OD-4 §3.1).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'ManifestEntry']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor: Optional[str] = Field(default=None, description="""The instrument that made an extracted assertion, as `<provider>:<alias asked for>` (`claude_cli_max_oauth:sonnet`). Absent on a deterministic assertion, and that absence is itself the signal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor_version: Optional[str] = Field(default=None, description="""The model id the client ACTUALLY RESOLVED the alias to, read from the CLI envelope of the call that made the assertion; never the alias (DI-023: recording an alias as the model is citing a document that quotes a statute as if it were the statute).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_prompt_sha256: Optional[str] = Field(default=None, description="""The sha256 of the prompt template the extraction ran under; a prompt change is a new extractor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_run_id: Optional[str] = Field(default=None, description="""The run id of the extraction that proposed this assertion (also the envelope's run_id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    grounding_span: Optional[GroundingSpan] = Field(default=None, description="""Where in the source the harness located the text behind this assertion. Located and cut by the harness from the parsed intermediate, never quoted by the model (ai-readiness-kg's anchor contract, S-001 finding 2). A span the harness cannot locate is a failed extraction, never a stored assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class AuthoredBy(Edge):
    """
    (Work)-[:AUTHORED_BY]->(Person), from the resolver's authorship record.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/schema'})

    author_position: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['AuthoredBy']} })
    raw_name: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['AuthoredBy']} })
    subject: str = Field(default=..., description="""The id of the source node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    object: str = Field(default=..., description="""The id of the target node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor: Optional[str] = Field(default=None, description="""The instrument that made an extracted assertion, as `<provider>:<alias asked for>` (`claude_cli_max_oauth:sonnet`). Absent on a deterministic assertion, and that absence is itself the signal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor_version: Optional[str] = Field(default=None, description="""The model id the client ACTUALLY RESOLVED the alias to, read from the CLI envelope of the call that made the assertion; never the alias (DI-023: recording an alias as the model is citing a document that quotes a statute as if it were the statute).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_prompt_sha256: Optional[str] = Field(default=None, description="""The sha256 of the prompt template the extraction ran under; a prompt change is a new extractor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_run_id: Optional[str] = Field(default=None, description="""The run id of the extraction that proposed this assertion (also the envelope's run_id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    grounding_span: Optional[GroundingSpan] = Field(default=None, description="""Where in the source the harness located the text behind this assertion. Located and cut by the harness from the parsed intermediate, never quoted by the model (ai-readiness-kg's anchor contract, S-001 finding 2). A span the harness cannot locate is a failed extraction, never a stored assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class AffiliatedWith(Edge):
    """
    (Person)-[:AFFILIATED_WITH]->(Organization), as declared on a work's authorship.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/schema'})

    as_of_work: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['AffiliatedWith']} })
    subject: str = Field(default=..., description="""The id of the source node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    object: str = Field(default=..., description="""The id of the target node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor: Optional[str] = Field(default=None, description="""The instrument that made an extracted assertion, as `<provider>:<alias asked for>` (`claude_cli_max_oauth:sonnet`). Absent on a deterministic assertion, and that absence is itself the signal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor_version: Optional[str] = Field(default=None, description="""The model id the client ACTUALLY RESOLVED the alias to, read from the CLI envelope of the call that made the assertion; never the alias (DI-023: recording an alias as the model is citing a document that quotes a statute as if it were the statute).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_prompt_sha256: Optional[str] = Field(default=None, description="""The sha256 of the prompt template the extraction ran under; a prompt change is a new extractor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_run_id: Optional[str] = Field(default=None, description="""The run id of the extraction that proposed this assertion (also the envelope's run_id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    grounding_span: Optional[GroundingSpan] = Field(default=None, description="""Where in the source the harness located the text behind this assertion. Located and cut by the harness from the parsed intermediate, never quoted by the model (ai-readiness-kg's anchor contract, S-001 finding 2). A span the harness cannot locate is a failed extraction, never a stored assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class SupportsDecision(Edge):
    """
    (Work | Standard | Software)-[:SUPPORTS_DECISION]->(Decision), from `cited_in`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/schema'})

    cited_in_text: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SupportsDecision']} })
    subject: str = Field(default=..., description="""The id of the source node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    object: str = Field(default=..., description="""The id of the target node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor: Optional[str] = Field(default=None, description="""The instrument that made an extracted assertion, as `<provider>:<alias asked for>` (`claude_cli_max_oauth:sonnet`). Absent on a deterministic assertion, and that absence is itself the signal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor_version: Optional[str] = Field(default=None, description="""The model id the client ACTUALLY RESOLVED the alias to, read from the CLI envelope of the call that made the assertion; never the alias (DI-023: recording an alias as the model is citing a document that quotes a statute as if it were the statute).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_prompt_sha256: Optional[str] = Field(default=None, description="""The sha256 of the prompt template the extraction ran under; a prompt change is a new extractor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_run_id: Optional[str] = Field(default=None, description="""The run id of the extraction that proposed this assertion (also the envelope's run_id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    grounding_span: Optional[GroundingSpan] = Field(default=None, description="""Where in the source the harness located the text behind this assertion. Located and cut by the harness from the parsed intermediate, never quoted by the model (ai-readiness-kg's anchor contract, S-001 finding 2). A span the harness cannot locate is a failed extraction, never a stored assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class Cites(Edge):
    """
    (Work)-[:CITES]->(Work | ExternalReference), from a public reference list; typed with a CiTO intent, default citesForInformation.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/schema'})

    cito_intent: Optional[CitoIntent] = Field(default=CitoIntent.citesForInformation, json_schema_extra = { "linkml_meta": {'domain_of': ['Cites'], 'ifabsent': 'string(citesForInformation)'} })
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
    prov_extractor: Optional[str] = Field(default=None, description="""The instrument that made an extracted assertion, as `<provider>:<alias asked for>` (`claude_cli_max_oauth:sonnet`). Absent on a deterministic assertion, and that absence is itself the signal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor_version: Optional[str] = Field(default=None, description="""The model id the client ACTUALLY RESOLVED the alias to, read from the CLI envelope of the call that made the assertion; never the alias (DI-023: recording an alias as the model is citing a document that quotes a statute as if it were the statute).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_prompt_sha256: Optional[str] = Field(default=None, description="""The sha256 of the prompt template the extraction ran under; a prompt change is a new extractor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_run_id: Optional[str] = Field(default=None, description="""The run id of the extraction that proposed this assertion (also the envelope's run_id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    grounding_span: Optional[GroundingSpan] = Field(default=None, description="""Where in the source the harness located the text behind this assertion. Located and cut by the harness from the parsed intermediate, never quoted by the model (ai-readiness-kg's anchor contract, S-001 finding 2). A span the harness cannot locate is a failed extraction, never a stored assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class ExpressionOf(Edge):
    """
    (Work | ExternalReference)-[:EXPRESSION_OF]->(Work | ExternalReference): a preprint is an expression of the version of record (OD-4 A5; FRBR, DI-152), from Crossref relations and DataCite related identifiers. An end outside the graph is an ExternalReference keyed by DOI.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/schema'})

    relation: Optional[ExpressionRelation] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ExpressionOf']} })
    subject: str = Field(default=..., description="""The id of the source node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    object: str = Field(default=..., description="""The id of the target node.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Edge']} })
    prov_wasGeneratedBy: Optional[str] = Field(default=None, description="""Run id of the activity that made the assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasGeneratedBy'} })
    prov_wasDerivedFrom: Optional[str] = Field(default=None, description="""The manifest entry or source the assertion was derived from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge'], 'slot_uri': 'prov:wasDerivedFrom'} })
    method: Optional[str] = Field(default=None, description="""How the assertion was made (manifest, crossref, openalex, github, human_ruling, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    ruling_id: Optional[str] = Field(default=None, description="""The event id of the human ruling that authorized this assertion, when one did.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    asserted_at: Optional[str] = Field(default=None, description="""When the assertion was made, ISO 8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    status: Optional[AssertionStatus] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    superseded_by: Optional[str] = Field(default=None, description="""The event id of the assertion that replaced this one. Never a deletion (DI-053, DI-064).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor: Optional[str] = Field(default=None, description="""The instrument that made an extracted assertion, as `<provider>:<alias asked for>` (`claude_cli_max_oauth:sonnet`). Absent on a deterministic assertion, and that absence is itself the signal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_extractor_version: Optional[str] = Field(default=None, description="""The model id the client ACTUALLY RESOLVED the alias to, read from the CLI envelope of the call that made the assertion; never the alias (DI-023: recording an alias as the model is citing a document that quotes a statute as if it were the statute).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_prompt_sha256: Optional[str] = Field(default=None, description="""The sha256 of the prompt template the extraction ran under; a prompt change is a new extractor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    prov_run_id: Optional[str] = Field(default=None, description="""The run id of the extraction that proposed this assertion (also the envelope's run_id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })
    grounding_span: Optional[GroundingSpan] = Field(default=None, description="""Where in the source the harness located the text behind this assertion. Located and cut by the harness from the parsed intermediate, never quoted by the model (ai-readiness-kg's anchor contract, S-001 finding 2). A span the harness cannot locate is a failed extraction, never a stored assertion.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Node', 'Edge']} })


class SeldonBiblioGraph(ConfiguredBaseModel):
    """
    The graph as two lists, the shape of the node-link export.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/brockwebb/squiddy/graphs/seldon_biblio/schema',
         'tree_root': True})

    nodes: Optional[list[Node]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Seldon_biblioGraph']} })
    edges: Optional[list[Edge]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Seldon_biblioGraph']} })


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
GroundingSpan.model_rebuild()
Node.model_rebuild()
Edge.model_rebuild()
ManifestEntry.model_rebuild()
EventEnvelope.model_rebuild()
Work.model_rebuild()
Person.model_rebuild()
Organization.model_rebuild()
Standard.model_rebuild()
Software.model_rebuild()
Decision.model_rebuild()
ExternalReference.model_rebuild()
AuthoredBy.model_rebuild()
AffiliatedWith.model_rebuild()
SupportsDecision.model_rebuild()
Cites.model_rebuild()
ExpressionOf.model_rebuild()
SeldonBiblioGraph.model_rebuild()
