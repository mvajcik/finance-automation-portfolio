-- Evidence nevie postaviť stránku nad dotazom s 0 riadkami → pri prázdnom výsledku jeden riadok placeholder = true
-- (stránky a tools/evidence_check.py ho ignorujú; v DB behu placeholder nie je).
with q as (
select key, round(number, 2) as number, auto, kontrolor, final, status from bp_comments t, run_meta r where r.verdict <> 'NESEDÍ'
)
select *, false as placeholder from q
union all
select '—', 0, '—', '—', '—', '—', true where not exists (select 1 from q)
