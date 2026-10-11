PY := .venv/bin/python

.PHONY: demo test test-fast venv clean odoo-demo odoo-demo-down odoo-test

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

# Odoo 17 Community demo (needs Docker; its own containers and Postgres on port 8071, nothing else is touched)
odoo-demo: venv
	$(MAKE) -C odoo demo PY=../$(PY)

odoo-demo-down:
	$(MAKE) -C odoo down

odoo-test: venv
	cd odoo && ../$(PY) -m pytest -q

clean:
	rm -rf .venv finance-ops-toolkit/out odoo/out
	$(MAKE) -C reporting-pipeline clean
