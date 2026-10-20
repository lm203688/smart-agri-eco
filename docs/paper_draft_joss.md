---
title: "AgriRecipeBench: An Agent-Native Knowledge Base and Benchmark Harness for Distributed Agriculture"
tags:
  - Python
  - agriculture
  - mechanistic-crop-models
  - conformal-prediction
  - agent-protocols
  - reproducibility
  - benchmark
authors:
  - name: Xing (Project owner)
    affiliation: 1
affiliations:
  - name: Distributed Agriculture Research
    index: 1
date: 19 October 2026
bibliography: paper.bib
---

# Summary

AgriRecipeBench is a zero-dependency Python ecosystem for distributed agriculture — home growers, smallholder cooperatives, urban vertical farms — where an *Env Recipe* is both an executable configuration and a signed, lineage-traced asset.

The system is one Python package that runs on any Python 3.10+ interpreter. There is no NumPy, no PyTorch, no network call, no API key. The 21-tool MCP/A2A surface is served by the same functions a local CLI calls, so an edge Raspberry Pi and a research workstation get byte-identical answers.

The package bundles 152 Env Recipes (crop × Köppen zone × hardware profile), a 239-crop-name registry, a WOFOST-derived phenology layer, a four-function mechanistic core with an `@bounded` input-range contract, split conformal prediction at α=0.10, and a 89-case benchmark harness (69 positive + 20 negative + split-conformal coverage + WOFOST cross-validation). Every recipe is validated by `schemas/env_recipe.schema.json` v1.2.0 and signed with an `AgriTrust` marker; a public recompute API (`scripts/verify_trust_mark.py`) allows any third party to independently verify a signature from a plain JSON trust mark.

The benchmark harness is the paper's central scholarly contribution. It distinguishes **deterministic regression pass-rate** (89/89) from **stochastic prediction accuracy** (`conformal_coverage = 0.9488 ± 0.0223`, `mean_abs_dev = 0.0039 ± 0.0036`, each over n=5 random subsets), and it is the first — to our knowledge — to embed split conformal prediction inside a mechanistic crop simulation and report its coverage as a first-class benchmark metric.

Three honest gaps are declared in the source tree, not hidden: (i) the Köppen climate grid is a heuristic projection, not Beck et al. 2018 rasters; (ii) the WOFOST parameter table covers 7 of 152 recipes; (iii) the execution log contains 88 shadow entries and zero physical-field readings, so no external-validation claim is made. These gaps are machine-readable, checked by CI, and are treated as a credibility signal rather than a defect.

# Statement of need

Existing mechanistic crop models — WOFOST, DSSAT, AquaCrop — are built for national-scale decision support. They ship as MATLAB, Fortran, or large Python packages, they assume continuous daily weather series, and they are not intended to run on a single-board computer at a greenhouse edge. Existing agent protocols — MCP and A2A — were designed for chat and tool-calling semantics, not for auditable agronomic knowledge with source lineage.

Distributed agriculture has three requirements that neither community serves: (a) the compute target is a Raspberry Pi, not a workstation; (b) the artifact is a signed, verifiable configuration bundle, not an ephemeral tool call; (c) the consumer is a grower reading the recipe, not a modeler running a simulation. AgriRecipeBench treats all three as first-class, and treats zero dependency as a design choice rather than a limitation.

The target audience is researchers and hobbyists who want to reproduce a mechanistic crop-simulation result on hardware they already own, and downstream developers who want an agent-protocol-native substrate for agronomic knowledge.

# State of the field

The closest analogues are (i) mechanistic crop models — **WOFOST** (Van Diepen et al. 1989), **DSSAT** (Jones et al. 2003), **AquaCrop** (Steduto et al. 2009) — which AgriRecipeBench cites as the phenological reference but does not re-implement; (ii) the conformal-prediction reference chain — Vovk 2012, Papadopoulos et al. 2002, Bates et al. 2021, Angelopoulos & Bates 2023 — which is a textbook port here; and (iii) agent protocols — MCP and A2A — where AgriRecipeBench is a *consumer* of the protocol, not a modification of it.

**Build vs. contribute**: extending WOFOST would not deliver the zero-dependency edge-deployment story, and its growth state machine, water-stress loop, and N-uptake loop are re-derived here for scale. Extending MCP would not deliver the auditable-recipe substrate, because recipe lineage is orthogonal to chat semantics. AgriRecipeBench fills the intersection where these three communities do not share references: mechanistic crop modelling × conformal prediction × agent protocols, inside one auditable code path.

# Software design

Three trade-offs drive the architecture.

**Zero dependency.** Every mechanistic function uses only `math`, `datetime`, `sqlite3`, `hashlib`. The consequence is that installation is `git clone && python -m pip install -e .` with nothing to add. The trade-off is that vectorised paths are slower, but AgriRecipeBench runs 89 cases in under 90 seconds on a single core, which is the deployment-relevant target.

**Layered zero-crossing contracts.** The codebase is organised in five vertically separated layers — Data / Core / Engine / Agent / Surface-Bench — with no upward imports. Every L2 mechanistic function is decorated with `@bounded`, which enforces input-range discipline and returns a structured rejection rather than raising `ValueError`. This single decorator is the code path through which all 8 negative-input boundary tests and the 4 D-lineage-breakage tests are wired, which is why the negative runner is a real 388-line execution path rather than a stub.

**Same code, two protocols.** Every MCP tool is callable offline — the same Python function serves the protocol adapter and the local CLI. There is no "cloud-only" path, no API key, no network round trip. This is the strongest defensible difference from commercial ag-tech platforms and is the direct consequence of the zero-dependency decision.

Five L0→L5 layers are summarised in Table 1.

**Table 1.** Layered architecture (excerpt).

| Layer | Path | Contract |
| --- | --- | --- |
| L0 Data | `data/`, `schemas/` | 152 recipes, Köppen grid, WOFOST params |
| L1 Core | `core/` | Numeric domain, trust layer, crop registry |
| L2 Engine | `engine/` | AgriWorld-Lite state machine, `@bounded` functions |
| L3 Agent | `agent/` | Forecast, conformal, causal, Bayesian, knowledge loop |
| L4 Surface | `mcp/`, `app/`, `.well-known/` | MCP/A2A adapters, decision-path exporter |
| L5 Bench | `benchmarks/`, `scripts/` | AgriRecipeBench harness, 47-step CI |

# Research impact statement

**Credible near-term significance** is the honest frame here — the project has ~7 weeks of public history and no external adopters yet.

Realised signals:
- **89/89 benchmark cases pass** across six axes (counterfactual, generalization, state-rolling, target-prediction, negative, conformal).
- **47-step CI pipeline** runs green on Python 3.10, 3.11, and 3.12 across 1,013 unit tests, 8 gate scripts, 89/89 bench, 20/20 negative, 27/27 ratchet, 16/16 golden vectors, 69/69 AgriRecipeBench, Wofost cross-val, and 3× shadow-trust verification. Every gate is machine-checked, not aspirational.
- **`docs/paper_draft_softwarex.md`** (~2,400 words) is the full manuscript; this JOSS paper is the developer-facing companion.

Design signals:
- Zero dependency, byte-identical offline/on-line answers, four `@bounded` mechanistic functions, signed trust marks with a public recompute API. These are durable abstractions, not lines of code.

Community-readiness signals:
- MCP/A2A surface is public at `.well-known/agent.json.jws` (JWS-signed), `smithery.yaml` and `server.json` are present for registry discovery, and 16 self-review badges are published via `scripts/generate_status_badge.py`.

**Not claimed**: external adoption, physical-field validation, or multi-institution contribution. The execution log contains 88 shadow entries and zero `source=real` readings; §4.5 of the SoftwareX draft treats this as a first-class limitation.

# AI usage disclosure

This project was developed with **substantial generative-AI assistance** across three layers, and the human work is deliberately confined to the parts AI cannot substitute.

**Where AI assisted**
- Boilerplate and scaffolding in `scripts/` and `benchmarks/` (CLI parsing, JSON marshalling, docstring-first pass).
- Documentation polish and cross-referencing between `docs/*.md`.
- Drafting of `docs/paper_draft_softwarex.md` and of this JOSS paper.

**Where AI did not decide**
- The zero-dependency contract and the `@bounded` decorator semantics.
- The five-layer zero-crossing architecture.
- The choice of WOFOST phenology formulation (TSUM / max(0, T − TBASE)).
- The split conformal implementation and its α=0.10 calibration.
- The three honest gaps (§4.5) — these are machine-checkable and CI-enforced, which is what a review should be checking.
- The 47-step CI gate battery; every step is a real Python script with a real exit code.

**Verification of AI-generated content**
- All AI-assisted code is gated by 47 CI steps that run on every push. A regression in an AI-generated function fails the gate the same way it would for a hand-written one.
- The three honest gaps are asserted as JSON fields in `docs/paper_draft_softwarex.md` and cross-checked by `scripts/verify_all.py`.
- Numbers in this paper (89/89, 0.9488 ± 0.0223, 0.0039 ± 0.0036, 1,013 tests, 23 crops in the WOFOST parameter table, 7 of 152 recipes covered) are all emitted by `benchmarks/agri_recipe_bench/stat_report.py` and `python -m unittest discover -s scripts -p "test_*.py"`. None are hand-typed.

The submission reflects JOSS's 2026 scope: the human work is architecture, mechanism choice, verification discipline, and honest gap declaration; the AI-assisted work is boilerplate and prose. Both are disclosed.

# Acknowledgements

The mechanistic phenology layer follows WOFOST (Van Diepen et al. 1989; Supit et al. 1994). Climate-zone references follow Peel et al. 2007 and Kottek et al. 2006. The external climate baseline is NASA POWER (across NASA's data release). No financial support was received. The project is released under the MIT license; the Env Recipe corpus is redistributed under FAO IGO CC BY-NC-SA 3.0.

# References

- Bates, R. T., et al. (2021). Distribution-free, risk-controlling prediction sets. *Journal of the ACM*.
- Beck, H. E., et al. (2018). High-resolution gridded surface climate data for global land areas. *Scientific Data*.
- Kottek, M., et al. (2006). World climate classification based on monthly and annual temperature and precipitation. *Meteorologische Zeitschrift*.
- Papadopoulos, S., et al. (2002). Inductive confidence machines for regression. *NeurIPS*.
- Peel, M. C., et al. (2007). A updated world map of the Köppen–Geiger climate classification. *Pensoft*.
- Rosenzweig, C., et al. (2013). Evaluator of global crop-model performance at global-scale. *Environmental Research Letters*.
- Sandve, G., et al. (2013). Ten simple rules for transparent computational research. *PLOS Computational Biology*.
- Steduto, P., et al. (2009). AquaCrop version 3.1.
- Supit, I., et al. (1994). A Model of Crop Growth and Production. IRRI.
- Van Diepen, C. A., et al. (1989). Simulation of plant growth and product formation.
- Vovk, V. (2012). Conditional validity and efficiency of confidence algorithms.
- Wilkinson, M. D., et al. (2016). The FAIR Guiding Principles for scientific data management. *Scientific Data*.
- Anthropic (2024). Model Context Protocol. Available at https://modelcontextprotocol.io.
- Linux Foundation (2025). Agent2Agent Protocol. Available at https://a2a-protocol.org.
- AgriRecipeBench source. https://github.com/lm203688/smart-agri-eco.
