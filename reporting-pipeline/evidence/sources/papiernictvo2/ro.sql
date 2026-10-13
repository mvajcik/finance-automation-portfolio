-- poradie rk = poradie hárku Riziká a príležitosti v overview.xlsx (kotva v tools/evidence_check.py)
-- Evidence nevie postaviť stránku nad dotazom s 0 riadkami → pri prázdnom výsledku jeden riadok placeholder = true
-- (stránky a tools/evidence_check.py ho ignorujú; v DB behu placeholder nie je).
with q as (
select rk, key, kind, grp, round(number, 2) as number, text
from (select row_number() over () as rk, * from bp_ro_items) t, run_meta r where r.verdict <> 'DOES NOT TIE' order by rk
)
select *, false as placeholder from q
union all
select 0, '—', '—', '—', 0, 'the machine found no item above the profile thresholds', true where not exists (select 1 from q)
