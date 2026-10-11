-- riadky board packu (SQL mart bp_rows) v poradí výsledovky profilu; čísla boardu len pri verdikte SEDÍ
-- Evidence nevie postaviť stránku nad dotazom s 0 riadkami → pri prázdnom výsledku jeden riadok placeholder = true
-- (stránky a tools/evidence_check.py ho ignorujú; v DB behu placeholder nie je).
with q as (
select p.ord, b.shop, b.row, p.is_subtotal,
       round(b.ytd_act, 2) as ytd_act, round(b.ytd_plan, 2) as ytd_plan, round(b.ytd_act - b.ytd_plan, 2) as d_plan,
       round(b.ytd_ly, 2) as ytd_ly, round(b.ytd_act - b.ytd_ly, 2) as d_ly,
       round(b.fy_est, 2) as fy_est, round(b.fy_plan, 2) as fy_plan, round(b.fy_est - b.fy_plan, 2) as d_fy, round(b.fy_ly, 2) as fy_ly
from bp_rows b join pl_rows p using (row), run_meta r
where r.verdict <> 'NESEDÍ'
order by case when b.shop = 'Spolu' then 1 else 0 end, b.shop, p.ord
)
select *, false as placeholder from q
union all
select 0, '—', '—', false, 0, 0, 0, 0, 0, 0, 0, 0, 0, true where not exists (select 1 from q)
