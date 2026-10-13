-- riadok výsledovky × mesiac bežného roka, skutočnosť (graf na stránke Pivotka) — rovnaký súčet faktov ako hárok
-- Pivot skutočnosť v pivot.xlsx (kotva v tools/evidence_check.py); rok z as_of behu, nie natvrdo.
-- Evidence nevie postaviť stránku nad dotazom s 0 riadkami → pri prázdnom výsledku jeden riadok placeholder = true
-- (stránky a tools/evidence_check.py ho ignorujú; v DB behu placeholder nie je).
with q as (
select f.row, f.ym, round(sum(f.amount), 2) as amount
from mart_facts f, run_meta r
where r.verdict <> 'DOES NOT TIE' and f.kind = 'actual' and f.ym like left(r.as_of, 4) || '-%'
group by f.row, f.ym order by f.row, f.ym
)
select *, false as placeholder from q
union all
select '—', '—', 0, true where not exists (select 1 from q)
