-- Evidence nevie postaviť stránku nad dotazom s 0 riadkami → pri prázdnom výsledku jeden riadok placeholder = true
-- (stránky a tools/evidence_check.py ho ignorujú; v DB behu placeholder nie je).
with q as (
select rk, key, shop, row, round(act, 2) as act, round(plan, 2) as plan,
       round(d_plan, 2) as d_plan, round(d_ly, 2) as d_ly, cause
from (select row_number() over () as rk, * from bp_variance_items) t, run_meta r where r.verdict <> 'NESEDÍ' order by rk
)
select *, false as placeholder from q
union all
select 0, '—', '—', '—', 0, 0, 0, 0, '—', true where not exists (select 1 from q)
