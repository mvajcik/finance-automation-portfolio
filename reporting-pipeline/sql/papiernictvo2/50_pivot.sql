-- PIVOTKA — plochá tabuľka faktov pre Excel: mesiac × stredisko × účet × skutočnosť/plán.
-- Jedna definícia čísla: skutočnosť z core_postings (ten istý základ ako pl_base), plán zo stg_plan
-- (ten istý prevodník účet → riadok pl_map). Znamienko ako pl_base: výnosy +, náklady −.
-- Len účty výsledovky (pl_map); súvahové účty do pivotky nevstupujú (ako do výsledovky).
CREATE TABLE mart_facts AS
SELECT 'actual' AS kind, p.ym, p.cc, c.shop, p.account, coalesce(d.v1, '') AS account_name, m.row,
       CAST(sum(p.amount) AS DECIMAL(18, 2)) AS amount, count(*) AS postings
FROM core_postings p JOIN pl_map m USING (account) JOIN cost_centers c USING (cc)
LEFT JOIN raw_dims d ON d.sheet = 'Accounts' AND d.k = p.account
GROUP BY ALL
UNION ALL
SELECT 'plan', s.ym, s.cc, c.shop, s.account, coalesce(d.v1, ''), m.row,
       CAST(sum(CASE WHEN s.account LIKE '6%' THEN s.amount ELSE -s.amount END) AS DECIMAL(18, 2)), count(*)
FROM stg_plan s JOIN pl_map m USING (account) JOIN cost_centers c USING (cc)
LEFT JOIN raw_dims d ON d.sheet = 'Accounts' AND d.k = s.account
GROUP BY ALL;
