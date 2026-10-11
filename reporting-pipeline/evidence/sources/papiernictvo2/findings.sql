-- Evidence nevie postaviť stránku nad dotazom s 0 riadkami → pri prázdnom výsledku jeden riadok placeholder = true
-- (stránky a tools/evidence_check.py ho ignorujú; v DB behu placeholder nie je).
with q as (
select seq, rule, key, text from board_findings t, run_meta r where r.verdict <> 'NESEDÍ' order by seq
)
select *, false as placeholder from q
union all
select 0, '—', '—', 'stroj nenašiel zistenie nad prahmi profilu', true where not exists (select 1 from q)
