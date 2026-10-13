# reporting-pipeline — papiernictvo2 (a fictional stationery chain), one engine, company = profile.
#
#   make demo      — generates the data → clean delivery (TIES, board pack) → delivery with planted errors (DOES NOT TIE);
#                    one readable page summary.html for each
#   make test      — tests: clean run, 7 planted errors by name, teeth of the checks, report contract, pivot, panel
#   make data      — generator only (deterministic: same seed → byte-identical files)
#   make evidence  — dashboard in the browser (needs node; not part of the demo)
PY ?= $(shell cd .. && pwd)/.venv/bin/python
P2 := profiles/papiernictvo2

.PHONY: demo demo-clean demo-errors data test deps evidence clean

deps:
	"$(PY)" -m pip install -q -r requirements.txt

data:
	@"$(PY)" tools/gen_papiernictvo2.py

$(P2)/data/clean:
	@"$(PY)" tools/gen_papiernictvo2.py

demo: $(P2)/data/clean demo-clean demo-errors

demo-clean:
	@echo "== 1/2 clean delivery (21 months, 9 sources) =="
	@mkdir -p exports
	@"$(PY)" pipeline/engine.py --profile $(P2) --input $(P2)/data/clean --out exports/papiernictvo2 \
		--truth $(P2)/truth.json --db warehouse/papiernictvo2.duckdb > exports/papiernictvo2.log; rc=$$?; \
	echo "   checks PASS: $$(grep -c '^\[PASS\]' exports/papiernictvo2.log), FAIL: $$(grep -c '^\[FAIL\]' exports/papiernictvo2.log)"; \
	grep -E "^\[BOARD\]|CONTRACT|VERDICT|STOP" exports/papiernictvo2.log | sed 's/^/   /'; \
	if [ $$rc -ne 0 ]; then echo "UNEXPECTED: the clean delivery returned exit $$rc (log: exports/papiernictvo2.log)"; exit 1; fi
	@echo "   board pack: exports/papiernictvo2/overview.xlsx · pivot: exports/papiernictvo2/pivot.xlsx"
	@"$(PY)" tools/summary_page.py exports/papiernictvo2/overview.xlsx

demo-errors:
	@echo "== 2/2 delivery with 7 planted errors — must be DOES NOT TIE =="
	@mkdir -p exports
	@"$(PY)" pipeline/engine.py --profile $(P2) --input $(P2)/data/with_errors --out exports/papiernictvo2_errors \
		--db warehouse/papiernictvo2_errors.duckdb > exports/papiernictvo2_errors.log; rc=$$?; \
	grep -c "^\[FAIL\]" exports/papiernictvo2_errors.log | sed 's/^/   checks FAIL: /'; \
	grep -E "VERDICT|CONTRACT" exports/papiernictvo2_errors.log | sed 's/^/   /'; \
	if [ $$rc -eq 1 ]; then echo "   (expected: errors caught, board pack not issued)"; else echo "UNEXPECTED: exit $$rc"; exit 1; fi
	@"$(PY)" tools/summary_page.py exports/papiernictvo2_errors/overview.xlsx

test:
	@"$(PY)" -m pytest -q

evidence: demo-clean
	cd evidence && npm install --no-fund --no-audit && npm run sources && cd .. && \
	"$(PY)" tools/evidence_check.py && cd evidence && npm run dev

clean:
	rm -rf exports warehouse $(P2)/data
