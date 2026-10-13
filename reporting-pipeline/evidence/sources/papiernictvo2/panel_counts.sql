-- počty kontrol podľa výsledku (dlaždice kontrolného panelu) — tie isté riadky ako panel_rows; kotva: semafor v hárku
-- Kontrolný panel (tools/evidence_check.py)
select count(*) filter (where status = 'PASS') as n_pass, count(*) filter (where status = 'FAIL') as n_fail,
       count(*) filter (where status = 'EXCEPTION') as n_exc, count(*) as n
from panel_rows
