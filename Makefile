PY := .venv/bin/python

.PHONY: demo test test-fast venv clean

venv: .venv/.ok
.venv/.ok: requirements.txt reporting-pipeline/requirements.txt
	python3 -m venv .venv
	$(PY) -m pip install -q -r requirements.txt -r reporting-pipeline/requirements.txt
	touch $@

demo: venv
	@echo "######## finance-ops-toolkit ########"
	cd finance-ops-toolkit && ../$(PY) demo.py
	@echo
	@echo "######## reporting-pipeline ########"
	$(MAKE) -C reporting-pipeline demo PY=../$(PY)

# all tests: toolkit + working-with-claude (seconds) + reporting pipeline (about 2 minutes)
test: test-fast
	$(MAKE) -C reporting-pipeline test PY=../$(PY)

test-fast: venv
	cd finance-ops-toolkit && ../$(PY) -m pytest -q
	cd working-with-claude && ../$(PY) -m pytest -q tests

clean:
	rm -rf .venv finance-ops-toolkit/out
	$(MAKE) -C reporting-pipeline clean
