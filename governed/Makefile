# The governed-documents graph (AD-030). One file, one command.
#
#     make catalog                      # enumerate the four governed directories into the manifest
#     make admit ID=<doc_id>            # the whole pipeline for one document, including a re-ingest
#     make plan  ID=<doc_id>            # print the plan, run nothing
#     make sweep                        # admit every cataloged document, cut one release
#     make status V=<version>           # what has passed so far
#     make schema                       # regenerate the Pydantic and JSON Schema projections
#     make kit-schema                   # refresh the kit's core schema from the installed squiddy
#     make check-squiddy                # verify the pinned Squiddy commit is what is installed
#
# Everything runs through Squiddy's CLI; this file only names the graph directory. The ledger this
# writes is imported into seldon-seldon-self by `seldon governed sync`, which is Seldon's write
# path. Squiddy never touches a `seldon-*` database (DI-005).
#
# PY MUST BE AN INTERPRETER THAT HAS SQUIDDY. The kit is a build-time dependency of this graph and
# is deliberately absent from pyproject.toml (AD-030-R17), so the default `python` usually is not
# it: run `make -C governed <target> PY=/path/to/squiddy/.venv/bin/python`. `check-squiddy` is the
# first thing every target does and says so by name when it is wrong.
#
# EDITING A GOVERNED FILE IS `make admit ID=<doc_id>`, NOT A RESET (AD-030-R22). The kit compares
# the manifest's recorded hash against the file, re-extracts that one document, and retracts the
# children the new text no longer has. `reset.sh` plus `make sweep` is the reset path — for a
# recipe change, where every document's extraction moved — and never the edit path.

GRAPH := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
PY    ?= python
CANDIDATES := $(GRAPH)/work/candidates.yaml

# This graph declares ONE edge layer and it is not the kit's default name. Passing it by hand on
# every sweep is a remembered incantation, and a sweep that forgets it runs a layer over nothing
# and reports success; naming it here is the difference between a default and a convention.
LAYER      := references
SWEEPFLAGS ?= --layer $(LAYER)

# AD-030-R17: Squiddy is a build-time dependency of THIS GRAPH, pinned by commit here and absent
# from pyproject.toml. See governed/squiddy.pin for why.
SQUIDDY_COMMIT := $(shell sed -n 's/^SQUIDDY_COMMIT=//p' $(GRAPH)/squiddy.pin)
SQUIDDY_VERSION := $(shell sed -n 's/^SQUIDDY_VERSION=//p' $(GRAPH)/squiddy.pin)

.PHONY: catalog admit plan sweep status schema kit-schema check-squiddy pin

# Every build target depends on this. A graph built against an unpinned kit is not reproducible,
# and discovering that after the ledger has been appended to is discovering it too late.
check-squiddy:
	@$(PY) $(GRAPH)/check_pin.py --graph $(GRAPH)

pin: check-squiddy

catalog: check-squiddy
	$(PY) $(GRAPH)/catalog_governed.py --graph $(GRAPH) --out $(CANDIDATES)
	$(PY) -m squiddy.cli catalog --graph $(GRAPH) --from $(CANDIDATES)

# `--layer references` is not optional bookkeeping: the cross-document edges are appended between
# check-after and the export, because a layer added AFTER the export leaves the served copy behind
# by exactly those edges and the next admission's check-before reports drift.
admit: check-squiddy
	$(PY) -m squiddy.cli admit --graph $(GRAPH) --id $(ID) --layer $(LAYER) $(ADMITFLAGS)

plan: check-squiddy
	$(PY) -m squiddy.cli admit --graph $(GRAPH) --id $(ID) --dry-run

sweep: check-squiddy
	$(PY) -m squiddy.cli sweep --graph $(GRAPH) $(SWEEPFLAGS)

status:
	$(PY) -m squiddy.cli status --graph $(GRAPH) --version $(V)

schema: check-squiddy
	$(PY) -m squiddy.cli schema --graph $(GRAPH)

# The kit's core schema is materialized here rather than imported across a sibling checkout, so
# this graph builds wherever squiddy is installed rather than only where the two repos are
# neighbours. Re-run after a kit upgrade.
kit-schema:
	$(PY) -c "import squiddy, pathlib, shutil; \
	  src = pathlib.Path(squiddy.__file__).parent / 'schema' / 'core.yaml'; \
	  shutil.copy2(src, '$(GRAPH)/schema/kit/core.yaml'); \
	  print('refreshed schema/kit/core.yaml from', src)"
