# Practitioner Vocabulary

Terms used in AI workflow design practice for official statistics. Managed centrally
in the `seldon-ontology` master database. Project glossaries are generated projections
of this vocabulary.

**Namespace:** `ontology:practitioner`
**Per:** AD-017 (Central Validity Ontology)

Terms in the core SFV validity vocabulary (SFV, T1–T5, CF, TC, SP, SCoh, SC, compaction,
context window, confabulation, TEVV, FCSM, handoff document) are defined in
`validity/VALIDITY_VOCABULARY.md` and are not repeated here.

---

## Practitioner Terms

Terms coined or operationalized in AI workflow design practice; concepts describing the
fundamental nature and costs of LLM-based systems.

**confidence laundering**
: A pipeline architecture failure in which uncertain, unverified extraction output is converted into a structured artifact whose format implies verification that never occurred. Typed nodes, labeled edges, and clean visualizations create confidence in the content, but the content was produced by a stochastic process. The structure launders the uncertainty out of the presentation without laundering it out of the data. Distinct from automation bias (human over-trust of automated output) and epistemic opacity (opacity of model reasoning); confidence laundering is a design-level failure, not a cognitive phenomenon.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**confabulation graph**
: A knowledge graph produced by an extraction pipeline that cannot trace its edges and nodes back to specific source passages with provenance. The graph looks structured and authoritative but contains a mixture of extracted facts and model-generated inferences that cannot be distinguished after the fact. The design antidote: every extracted element must carry a citation to the source passage, model version, and prompt that produced it.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**stochastic tax**
: The overhead accepted every time a task is routed through a probabilistic language model when a deterministic or seed-reproducible method would suffice. Every unnecessary LLM invocation adds variance, cost, and audit burden. The design discipline is to minimize the stochastic tax — not eliminate LLMs, but constrain their use to where they are genuinely needed.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**stochastic liabilities**
: Properties of LLM systems that require design responses rather than debugging. The term distinguishes features of a system's fundamental nature — irreproducibility across runs, coherent-sounding wrong answers, inability to characterize error distributions in classical statistical terms — from defects that can be fixed. Stochastic liabilities are not fixed; they are designed around.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**recursive stochasticity**
: The condition in which the tools used to build stochastic pipelines are themselves stochastic. AI coding assistants ignore configuration files, reinvent debugged infrastructure, suggest deprecated APIs, and lose architectural context at session boundaries. The same design discipline required for reliable LLM data pipelines applies to LLM development tools: specification before execution, config-driven architecture, regression testing, and state serialization.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**model transience**
: The design constraint that the models available today will not be the models available in six months. Models deprecate, update silently, change pricing, and get superseded. Design implication: model-agnostic pipeline architecture (model identifiers in configuration, not hardcoded), golden test sets for detecting drift after updates, and version pinning with scheduled expiration review.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**cloud parity gap**
: The lag between availability of AI capabilities in commercial cloud environments and in authorized government cloud environments (FedRAMP-authorized regions). Typically months to over a year. New model releases and features reach commercial regions first; government regions follow. Practical consequence: federal practitioners often cannot access the most capable models when they are most useful.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**fine-tuning cost trap**
: The failure to account for the full total cost of ownership when comparing fine-tuned local models against API-based approaches. Teams typically account for API inference cost but omit training data curation, compute, evaluation harness development, retraining costs when taxonomies update, model hosting infrastructure, MLOps overhead, and staff expertise. The comparison most teams skip: total cost of fine-tuning pipeline versus total cost of API-based dual-model pipeline.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**disagreement as signal**
: The design principle that when two independently trained models produce different outputs on the same input, the disagreement is valuable information rather than noise. Disagreement surfaces genuine ambiguity, taxonomic boundary problems, and low-confidence cases. A pipeline that surfaces disagreements is more informative than one that hides them.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**90/10 rule**
: The empirical observation that the first 90% of capability from any orchestration tool is easy to achieve, while the last 10% — edge cases, error handling, integration with specific institutional infrastructure, compliance logging — consumes 90% of the effort. Evaluate tools on last-mile fit, not demo capability. Related: the last mile problem.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**last mile problem**
: The gap between a pipeline that works in a development environment and one that works in production with real institutional constraints. For federal researchers: running inside authorized cloud environments with limited service catalogs, meeting data residency requirements, satisfying audit logging requirements, and operating within security-constrained network configurations.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**token budget**
: A deliberate allocation of context window capacity to different pipeline components — system prompt, configuration, task specification, data, intermediate results. The context window is a scarce resource to be managed, not a limitless workspace. Exceeding the implicit token budget causes compaction, which is a Compression Distortion (T3) risk.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**training cutoff**
: The date beyond which a model has no knowledge from its training data. Events, models, APIs, and best practices that postdate the cutoff are unknown to the model; queries about them produce confabulation. The training cutoff is a permanent, pervasive instance of State Supersession Failure (T4): everything the model "knows" about the current environment is from before the cutoff and has been partially superseded. Config-driven architecture is the primary countermeasure.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**knowledge graph**
: A structured representation of entities and relationships extracted from a corpus. LLM-built knowledge graphs are vulnerable to confidence laundering: the visual structure of nodes and edges creates apparent authority regardless of whether the content is grounded in source documents. See also: confabulation graph.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

---

## Design Patterns

Named engineering patterns for LLM pipeline design.

**config-driven architecture**
: The design pattern of externalizing all configurable pipeline parameters (model names, API endpoints, thresholds, batch sizes, retry limits, checkpoint intervals) into version-controlled configuration files rather than hardcoding them in source code. Prevents silent configuration drift, makes settings auditable, and enables model swaps without code changes.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**dual-model cross-validation**
: A pipeline architecture in which two architecturally distinct models (different vendors, different training, different alignment) independently process the same input and their outputs are compared. Agreement indicates confidence; disagreement triggers escalation or arbitration. Directly analogous to inter-rater reliability in survey methodology.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**generator-critic loop**
: A multi-model topology in which one model generates output and a second model evaluates it, with evaluation feedback feeding back to the generator for revision. More robust than same-model self-refinement because the critic's failure modes are independent of the generator's. Key design constraints: cross-model evaluation, explicit termination conditions, maximum iteration caps, and specific actionable rejection feedback.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**parallel consensus**
: A multi-model topology in which N models independently process the same input and their outputs are compared. Agreement indicates confidence; disagreement triggers escalation. The canonical multi-model pattern for classification and coding tasks. Direct application of inter-rater reliability methodology to LLM outputs.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**confidence-based routing**
: Directing pipeline outputs along different paths based on confidence score. High-confidence results auto-accept; low-confidence results escalate to human review or arbitration. A specific implementation of the general principle that AI handles volume and humans handle judgment. Requires calibrated confidence scores.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**LLM-as-judge**
: A multi-model topology in which a model is explicitly tasked with evaluating another model's output against defined criteria (a rubric). Three variants: tie-breaking arbiter (adjudicates disagreements between two generators), quality gate (every output passes through a judge before production), and pairwise comparison (judge selects the better of two candidate outputs). Rubric design is the practitioner skill: criteria must be domain-grounded, decomposed into multiple dimensions, and versioned.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**checkpoint**
: A saved record of pipeline state at a specific point in processing, enabling resumption after failure without restarting from the beginning. Minimum contents: which records have been processed, their results, and enough state to continue from the next unprocessed record. Transaction-safe writes (write to temp file, then atomically rename) prevent checkpoint corruption.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**idempotent operation**
: An operation that produces the same result whether run once or multiple times. In LLM pipelines: a batch retried after transient failure should not produce duplicate results, corrupt state, or double-count records. Write operations (saving results, updating checkpoints) must be idempotent so that re-execution is safe.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**batch economics**
: The cost and throughput characteristics of processing large, predictable volumes of work through AI pipelines. Statistical workflows are naturally batch-oriented — thousands of records with no real-time latency requirement — which enables cost optimization through tier selection, off-peak scheduling, and efficient token use.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**model version pinning**
: Locking pipeline configuration to a specific dated model version identifier rather than a floating alias. Prevents silent behavior changes from vendor updates between pipeline runs. Required for reproducibility. Treat the model identifier as a software dependency version: pin it, test it, and document when you upgrade.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**smoke test**
: A quick sanity check run before committing to a full pipeline run. Run a small batch (10 items) before launching 50,000. Checks: does the model respond? Is the output format correct? Are the parameters accepted? Catches configuration errors and API issues before they cause failures at scale.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**regression testing**
: Automated re-execution of a test suite after any pipeline change to detect whether something previously working has broken. In LLM pipelines: run the golden test set after every model update, prompt revision, configuration change, or framework update. Catches silent regressions before they propagate to production data.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**golden test set**
: A curated collection of inputs with known-correct outputs that a pipeline must handle correctly. Design properties: domain-representative (including edge cases and genuinely ambiguous cases), version-controlled, and living (grows as new failure modes are discovered). Run after every pipeline change to detect regressions before they reach production.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**evidence chain**
: A complete, traceable record linking a published output to its inputs, the models used, the prompts sent, the confidence scores returned, and the decision rules applied at each stage. The evidence chain is the difference between a result you can defend and a result you cannot.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**bounded agency**
: The design principle that AI systems with explicit constraints, defined scope, and human oversight outperform fully autonomous systems in high-stakes contexts. The preferred operating model for AI in federal statistical work.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**counterbalancing**
: A standard experimental design technique for controlling order effects by systematically varying the sequence in which conditions are presented. In LLM evaluation, applied as position bias control: present the options in one order, then the reverse (the ABBA sequence), and check whether results are order-invariant. If results change with ordering, the judgment is unstable and should not be trusted.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**pairwise comparison**
: Asking an LLM to compare two items and select which better satisfies a criterion, rather than asking it to assign an absolute score. LLMs produce more reliable judgments from pairwise comparison than from absolute rating, because comparative judgment plays to the model's strengths (relative pattern recognition) rather than its weaknesses (absolute calibration). Aggregated via Bradley-Terry for interval-scale results.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

---

## Domain Terms

Domain-specific vocabulary tied to statistical production, methodology, and government AI deployment.

**agency**
: Granted decision-making authority. Agency is conferred by a system designer, not inherent to a model. Granting less agency is often the better design choice in high-stakes contexts.
: *Projects:* ai-workflow-design

**agent**
: An entity that performs work within a workflow. In agentic AI, the agent is typically an LLM operating with granted authority over a defined set of actions.
: *Projects:* ai-workflow-design

**agentic**
: Behavior in which an AI system exercises granted decision-making authority within a workflow. Agentic is a property of behavior, not of the system itself.
: *Projects:* ai-workflow-design

**ATO (Authority to Operate)**
: A formal security authorization that permits an information system to operate at a federal agency. Traditionally designed for stable, long-lived systems; poses significant friction for AI workflows where models, prompts, and configurations change continuously. Enterprise ATO models authorize a platform and pattern rather than a specific system version, reducing re-authorization burden.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**FedRAMP**
: Federal Risk and Authorization Management Program. The authorization framework for cloud services used by federal agencies. A service must achieve FedRAMP authorization at the appropriate impact level before agencies can use it for production workloads. A primary gate between available AI capability and deployable AI capability in government settings.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**Bradley-Terry aggregation**
: A statistical method for converting pairwise comparison judgments into interval scales. Used to aggregate multiple LLMs' pairwise comparisons of output quality into a reliable scale. Each model provides comparative judgments; Bradley-Terry converts those comparisons into a ranking with interval-scale properties.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**imputation**
: The process of filling in missing values in survey data using statistical methods. Hot-deck, regression, and multiple imputation (MICE) are the standard approaches in federal surveys. LLMs outperform MICE on categorical variables but not on continuous variables where statistical properties must be preserved.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**statistical disclosure limitation**
: The set of methods used to reduce the risk that individuals, firms, or organizations can be re-identified from released statistics, microdata, or trained models and API endpoints. Also called statistical disclosure control (SDC) or disclosure avoidance. AI workflows require the same SDC review as traditional statistical outputs regardless of how they were produced. LLM memorization of training data fragments is an additional SDC concern specific to generative models.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**inter-rater reliability**
: Statistical measures of agreement between independent raters on a classification or coding task. Cohen's kappa (two raters), Fleiss' kappa (three or more raters), and Krippendorff's alpha are the standard statistics. Applied to LLM pipelines: two independently trained models are treated as independent raters, and their agreement rates provide evidence of task well-definedness and classification confidence.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**agreement scoring**
: A quantitative measure of how often independent models produce the same output on the same input. Used as a confidence signal and quality metric in multi-model pipelines. Cohen's kappa and Fleiss' kappa are standard agreement statistics from inter-rater reliability applied to LLM outputs.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**position bias**
: The tendency of LLM outputs to vary based on the order in which options or inputs are presented. In classification: the model's preference may be influenced by which category appears first in the prompt. In pairwise evaluation: which item appears first affects the comparison result. ABBA design controls for position bias in evaluation; randomized option ordering controls for it in classification.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**fine-tuning**
: Adapting a pre-trained model to a specific task by training it further on task-specific labeled data. For statistical coding tasks (NAICS, SOC, NAPCS), fine-tuning can improve accuracy on domain-specific classification. See also: fine-tuning cost trap.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**quantization**
: A compression technique that reduces model precision (e.g., from 32-bit to 4-bit weights) to decrease memory footprint and inference cost while preserving most accuracy. Enables running capable models on agency hardware without API dependencies, relevant to data-sensitivity use cases where external API transmission is prohibited.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**small language model (SLM)**
: A language model with roughly 0.5–7 billion parameters, designed for domain-specific tasks where a fine-tuned small model can outperform a general-purpose large model at lower cost. SLMs can be quantized and deployed on agency hardware without API dependencies. Relevant to data sensitivity use cases (Title 13, CIPSEA) where external API transmission is prohibited.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**workflow**
: A defined sequence or graph of steps to accomplish a goal, executed by humans, AI, or combinations. Not all workflows involve agents; not all agents are part of complex workflows. In the context of official statistics, workflow refers specifically to structured data processing pipelines where defensibility and provenance are design requirements.
: *Projects:* ai-workflow-design

---

## Governance Terms

Governance, compliance, and policy vocabulary relevant to federal AI deployment.

**NIST AI RMF**
: The Artificial Intelligence Risk Management Framework (NIST AI 100-1), published January 2023. A voluntary, sector-agnostic framework for managing AI risks through four functions: GOVERN, MAP, MEASURE, and MANAGE. The primary federal AI governance framework. When AI participates in federal statistical production, both the FCSM quality framework and NIST AI RMF apply simultaneously.
: *Citations:* [NIST-2023]
: *Projects:* ai-workflow-design

**NIST AI 600-1**
: The Generative Artificial Intelligence Profile, published by NIST in 2024. Identifies 12 risk categories specific to generative AI, including confabulation, information integrity risks, harmful bias, and data privacy concerns. Maps suggested actions to the AI RMF GOVERN-MAP-MEASURE-MANAGE structure. Establishes "confabulation" as the precise term for outputs presented as factual but not grounded in actual inputs.
: *Citations:* [NIST-2024]
: *Projects:* ai-workflow-design

**Five Safes**
: A framework for data access governance developed at the UK ONS and adopted internationally. The five safes: safe projects (appropriate use?), safe people (trained users?), safe settings (secure environment?), safe data (appropriate protection applied?), safe outputs (non-disclosive results?). Applies naturally to AI workflows because the core question is the same: how to provide access for legitimate purposes while managing risk.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**model card**
: Standardized documentation for a trained model reporting intended use, performance metrics, training data characteristics, ethical considerations, and limitations. Agencies should require model cards as part of AI procurement and deployment review. A model card's description of training data as "internet data" without further specification is a model provenance flag.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**model provenance**
: The documented origin and transformation history of a trained model: training data sources, training process, organizational governance, fine-tuning or post-processing applied, and hosting jurisdiction. A trust decision, not just a performance decision. Models trained on unknown data from organizations under different legal jurisdictions introduce compliance risk that benchmark scores do not capture.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design

**MCP (Model Context Protocol)**
: An open protocol for connecting AI agents to external data sources and tools. MCP servers expose structured interfaces that agents can query; the agent decides what to query and when, rather than following a predefined pipeline sequence. Tool design is the observability strategy in MCP-based systems: tools designed to return structured metadata, confidence scores, and provenance enable evaluation; tools that only return final answers provide no intermediate data for monitoring.
: *Citations:* [Webb-2026b]
: *Projects:* ai-workflow-design
