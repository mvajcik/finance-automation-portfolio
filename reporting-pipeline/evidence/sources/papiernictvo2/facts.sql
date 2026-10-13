-- pivotka: tie isté fakty ako hárok Fakty v pivot.xlsx (mart_facts)
-- Evidence nevie postaviť stránku nad dotazom s 0 riadkami → pri prázdnom výsledku jeden riadok placeholder = true
-- (stránky a tools/evidence_check.py ho ignorujú; v DB behu placeholder nie je).
with q as (
select kind, ym, cc, shop, account, account_name, row, round(amount, 2) as amount, postings
from mart_facts f, run_meta r where r.verdict <> 'DOES NOT TIE' order by kind, ym, cc, account
)
select *, false as placeholder from q
union all
select '—', '—', '—', '—', '—', '—', '—', 0, 0, true where not exists (select 1 from q)
