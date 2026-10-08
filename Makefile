# AOCI · 智慧农业生态 — 开发入口
# 零第三方依赖，直接用系统 python 即可。Windows(Git Bash) / Linux 通用。
PY ?= python

.PHONY: help test verify quality gate ci clean

help:
	@echo "AOCI 开发命令："
	@echo "  make test     全量单测回归 (unittest discover scripts/)"
	@echo "  make verify   端到端主门禁 verify_all.py"
	@echo "  make quality  数据质量门禁 data_quality_gate.py"
	@echo "  make gate     test + verify + quality 全套"
	@echo "  make ci       本地复现 CI 关键步骤"
	@echo "  make clean    清理 __pycache__"

test:
	$(PY) -m unittest discover scripts/

verify:
	$(PY) scripts/verify_all.py

quality:
	$(PY) scripts/data_quality_gate.py

gate: test verify quality

ci: gate
	$(PY) -m core.trust_layer
	$(PY) -m engine.flywheel

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
