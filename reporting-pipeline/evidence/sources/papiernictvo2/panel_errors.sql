-- Evidence nevie postaviť stránku nad dotazom s 0 riadkami → pri prázdnom výsledku jeden riadok placeholder = true
-- (stránky a tools/evidence_check.py ho ignorujú; v DB behu placeholder nie je).
with q as (
select seq, check_id, files, line, text from panel_errors order by seq
)
select *, false as placeholder from q
union all
select 0, '—', NULL, NULL, 'žiadne nálezy — všetky kontroly prešli', true where not exists (select 1 from q)
