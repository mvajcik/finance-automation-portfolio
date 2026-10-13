# Demo Retail s.r.o. on Odoo 17 Community — the whole demo in one command.
#
#   make demo    start the containers, build the company and the bills, import the CAMT statement,
#                write the weekly pack, read it back, break it once on purpose, render the verdict page
#   make down    stop and remove the demo containers AND their data (other Odoo installs on this machine are not touched)
#   make test    offline tests (plan, CAMT, matcher, weekly pack tampers) — no Docker needed
PY ?= $(shell cd .. && pwd)/.venv/bin/python
DOCKER ?= docker
WEEK ?= 2026-W39

.PHONY: demo up down test

up:
	@$(DOCKER) compose up -d
	@mkdir -p out

demo: up
	@echo "== 1/5 company, stores, vendors, 70 bills (idempotent) =="
	@"$(PY)" -m demo_retail_odoo.setup_demo
	@echo "== 2/5 fictional CAMT.053 statements, July to September 2026 =="
	@"$(PY)" -m demo_retail_odoo.camt out
	@echo "== 3/5 import + matching over the ORM =="
	@"$(PY)" -m demo_retail_odoo.import_camt out/camt053-2026-07.xml out/camt053-2026-08.xml out/camt053-2026-09.xml | grep -E "^CAMT|^lines|^VERDICT|FAIL"
	@echo "== 4/5 weekly pack $(WEEK): write, read back, tie to Odoo =="
	@"$(PY)" -m demo_retail_odoo.weekly_pack --week $(WEEK)
	@"$(PY)" -m demo_retail_odoo.verdict_html out/weekly-pack-$(WEEK)-checks.json
	@echo "== 5/5 three tampers on the finished file: each must be BLOCKED =="
	@for t in cent row total; do \
		"$(PY)" -m demo_retail_odoo.weekly_pack --week $(WEEK) --tamper $$t --out out/tamper_$$t > out/tamper_$$t.log; rc=$$?; \
		grep -E "^TAMPER|^\[FAIL\]|^VERDICT" out/tamper_$$t.log | cut -c1-120; \
		test $$rc -eq 1 || { echo "tamper $$t was NOT caught"; exit 1; }; \
	done
	@echo "Odoo: http://127.0.0.1:8071  (login admin / admin, database demo_retail)"

down:
	@$(DOCKER) compose down -v

test:
	@"$(PY)" -m pytest -q
