# The governed-documents graph (AD-030). One file, one command.
#
#     make catalog                      # enumerate the four governed directories into the manifest
#     make admit ID=<doc_id>            # the whole pipeline for one document
#     make plan  ID=<doc_id>            # print the plan, run nothing
#     make sweep                        # admit every cataloged document, cut one release
#     make status V=<version>           # what has passed so far
#     make schema                       # regenerate the Pydantic and JSON Schema projections
#     make kit-schema                   # refresh the kit's core schema from the installed squiddy
#
# Everything runs through Squiddy's CLI; this file only names the graph directory. The ledger this
# writes is imported into seldon-seldon-self by `seldon governed sync`, which is Seldon's write
# path. Squiddy never touches a `seldon-*` database (DI-005).

GRAPH := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
PY    ?= python
CANDIDATES := $(GRAPH)/work/candidates.yaml

.PHONY: catalog admit plan sweep status schema kit-schema

catalog:
	$(PY) $(GRAPH)/catalog_governed.py --graph $(GRAPH) --out $(CANDIDATES)
	$(PY) -m squiddy.cli catalog --graph $(GRAPH) --from $(CANDIDATES)

admit:
	$(PY) -m squiddy.cli admit --graph $(GRAPH) --id $(ID) $(ADMITFLAGS)

plan:
	$(PY) -m squiddy.cli admit --graph $(GRAPH) --id $(ID) --dry-run

sweep:
	$(PY) -m squiddy.cli sweep --graph $(GRAPH) $(SWEEPFLAGS)

status:
	$(PY) -m squiddy.cli status --graph $(GRAPH) --version $(V)

schema:
	$(PY) -m squiddy.cli schema --graph $(GRAPH)

# The kit's core schema is materialized here rather than imported across a sibling checkout, so
# this graph builds wherever squiddy is installed rather than only where the two repos are
# neighbours. Re-run after a kit upgrade.
kit-schema:
	$(PY) -c "import squiddy, pathlib, shutil; \
	  src = pathlib.Path(squiddy.__file__).parent / 'schema' / 'core.yaml'; \
	  shutil.copy2(src, '$(GRAPH)/schema/kit/core.yaml'); \
	  print('refreshed schema/kit/core.yaml from', src)"
