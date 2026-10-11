# reporting-pipeline — papiernictvo2 (fiktívna sieť papiernictiev), jeden motor, firma = profil.
#
#   make demo      — vygeneruje dáta → čistá dodávka (SEDÍ, board pack) → dodávka so zasadenými chybami (NESEDÍ);
#                    ku každej jedna čitateľná strana summary_en.html / summary_sk.html
#   make test      — testy: čistý beh, 7 zasadených chýb menovite, zuby kontrol, zmluva reportu, pivotka, panel
#   make data      — len generátor (deterministický: rovnaký seed → bajtovo rovnaké súbory)
#   make evidence  — dashboard v prehliadači (vyžaduje node; nie je súčasť demo)
PY ?= ../.venv/bin/python
P2 := profiles/papiernictvo2

.PHONY: demo demo-clean demo-errors data test deps evidence evidence-check clean

deps:
	$(PY) -m pip install -q -r requirements.txt

data:
	@$(PY) tools/gen_papiernictvo2.py

$(P2)/data/cisty:
	@$(PY) tools/gen_papiernictvo2.py

demo: $(P2)/data/cisty demo-clean demo-errors

demo-clean:
	@echo "== 1/2 čistá dodávka (21 mesiacov, 9 zdrojov) =="
	@mkdir -p exports
	@$(PY) pipeline/engine.py --profile $(P2) --input $(P2)/data/cisty --out exports/papiernictvo2 \
		--truth $(P2)/truth.json --db warehouse/papiernictvo2.duckdb > exports/papiernictvo2.log; rc=$$?; \
	echo "   kontroly PASS: $$(grep -c '^\[PASS\]' exports/papiernictvo2.log), FAIL: $$(grep -c '^\[FAIL\]' exports/papiernictvo2.log)"; \
	grep -E "^\[BOARD\]|ZMLUVA|VERDIKT|STOP" exports/papiernictvo2.log | sed 's/^/   /'; \
	if [ $$rc -ne 0 ]; then echo "NEOČAKÁVANÉ: čistá dodávka dala exit $$rc (protokol: exports/papiernictvo2.log)"; exit 1; fi
	@echo "   board pack: exports/papiernictvo2/prehlad.xlsx · pivotka: exports/papiernictvo2/pivotka.xlsx"
	@$(PY) tools/summary_page.py exports/papiernictvo2/prehlad.xlsx

demo-errors:
	@echo "== 2/2 dodávka so 7 zasadenými chybami — musí byť NESEDÍ =="
	@mkdir -p exports
	@$(PY) pipeline/engine.py --profile $(P2) --input $(P2)/data/s_chybami --out exports/papiernictvo2_chyby \
		--db warehouse/papiernictvo2_chyby.duckdb > exports/papiernictvo2_chyby.log; rc=$$?; \
	grep -c "^\[FAIL\]" exports/papiernictvo2_chyby.log | sed 's/^/   kontroly FAIL: /'; \
	grep -E "VERDIKT|ZMLUVA" exports/papiernictvo2_chyby.log | sed 's/^/   /'; \
	if [ $$rc -eq 1 ]; then echo "   (očakávané: chyby chytené, board pack sa nevydal)"; else echo "NEOČAKÁVANÉ: exit $$rc"; exit 1; fi
	@$(PY) tools/summary_page.py exports/papiernictvo2_chyby/prehlad.xlsx

test:
	@$(PY) -m pytest -q

evidence: demo-clean
	cd evidence && npm install --no-fund --no-audit && npm run sources && cd .. && \
	$(PY) tools/evidence_check.py && cd evidence && npm run dev

clean:
	rm -rf exports warehouse $(P2)/data
