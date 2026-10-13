-- tržby po mesiacoch a strediskách (hárok Mesiace x strediská)
-- Evidence nevie postaviť stránku nad dotazom s 0 riadkami → pri prázdnom výsledku jeden riadok placeholder = true
-- (stránky a tools/evidence_check.py ho ignorujú; v DB behu placeholder nie je).
with q as (
select b.ym, b.shop, round(b.amount, 2) as revenue
from pl_base b, run_meta r where b.row = 'Revenue' and r.verdict <> 'DOES NOT TIE' order by b.ym, b.shop
)
select *, false as placeholder from q
union all
select '—', '—', 0, true where not exists (select 1 from q)
