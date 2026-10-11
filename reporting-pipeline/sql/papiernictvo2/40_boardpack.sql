-- BOARD PACK — skutočnosť, plán, minulý rok a odhad roka.
-- Vstup od motora: bp_params (parametre z profile.json → board_pack) a pl_struct (riadok → základné riadky,
-- medzisúčty z profilu rozvinuté; základný riadok ukazuje sám na seba). Znamienko ako pl_base: výnosy +, náklady −.

-- plán do riadkov výsledovky (prevodník účet → riadok je ten istý ako pre skutočnosť); DECIMAL = presné centy
CREATE TABLE plan_pl AS
SELECT p.ym, c.shop, m.row,
       CAST(sum(CASE WHEN p.account LIKE '6%' THEN p.amount ELSE -p.amount END) AS DECIMAL(18, 2)) AS amount
FROM stg_plan p JOIN pl_map m USING (account) JOIN cost_centers c USING (cc)
GROUP BY 1, 2, 3;

-- mriežka bežného roka: mesiac 1–12 × stredisko × základný riadok; skutočnosť len do as_of
-- plán dane z príjmov plán nemá → dopočíta sa sadzbou z plánu zisku pred zdanením mesiaca (na stredisko dane)
CREATE TABLE bp_grid_raw AS
WITH par AS (SELECT * FROM bp_params),
     months AS (SELECT par.y2 || '-' || lpad(CAST(g AS VARCHAR), 2, '0') AS ym,
                       par.y1 || '-' || lpad(CAST(g AS VARCHAR), 2, '0') AS ym_ly, CAST(g AS INT) AS mo
                FROM par, range(1, 13) t(g)),
     base AS (SELECT DISTINCT part AS row FROM pl_struct)
SELECT m.ym, m.mo, c.shop, b.row,
       CASE WHEN m.mo <= (SELECT as_of_m FROM par) THEN coalesce(a.amount, 0) END AS actual,
       coalesce(p.amount, CAST(0 AS DECIMAL(18, 2))) AS plan,
       coalesce(l.amount, 0) AS ly
FROM months m CROSS JOIN (SELECT DISTINCT shop FROM cost_centers) c CROSS JOIN base b
LEFT JOIN pl_base a ON a.ym = m.ym AND a.shop = c.shop AND a.row = b.row
LEFT JOIN plan_pl p ON p.ym = m.ym AND p.shop = c.shop AND p.row = b.row
LEFT JOIN pl_base l ON l.ym = m.ym_ly AND l.shop = c.shop AND l.row = b.row;

CREATE TABLE bp_grid AS
WITH par AS (SELECT * FROM bp_params),
     -- daň plánu na centy (DECIMAL, zaokrúhlenie od nuly) — polcent by inak dal nedeterministický výsledok
     ptax AS (SELECT g.mo, ROUND(-CAST(par.tax_rate AS DECIMAL(6, 4)) * sum(g.plan), 2) AS plan FROM bp_grid_raw g, par
              WHERE g.row IN (SELECT s.part FROM pl_struct s WHERE s.row = par.pbt_row) GROUP BY g.mo, par.tax_rate)
SELECT g.ym, g.mo, g.shop, g.row, g.actual,
       CAST(CASE WHEN g.row = par.tax_row THEN (CASE WHEN g.shop = par.tax_shop THEN t.plan ELSE 0 END) ELSE g.plan END
            AS DOUBLE) AS plan,
       g.ly
FROM bp_grid_raw g JOIN ptax t USING (mo), par;

-- tempo posledných N mesiacov (skutočnosť ÷ plán) po stredisku a riadku
CREATE TABLE bp_pace AS
WITH par AS (SELECT * FROM bp_params)
SELECT g.shop, g.row,
       sum(CASE WHEN g.mo > par.as_of_m - par.runrate_months THEN g.actual END) AS act_rr,
       sum(CASE WHEN g.mo > par.as_of_m - par.runrate_months AND g.mo <= par.as_of_m THEN g.plan END) AS plan_rr,
       sum(CASE WHEN g.mo > par.as_of_m - par.runrate_months AND g.mo <= par.as_of_m THEN g.ly END) AS ly_rr,
       sum(g.actual) AS act_ytd,
       sum(CASE WHEN g.mo <= par.as_of_m THEN g.plan END) AS plan_ytd
FROM bp_grid g, par GROUP BY 1, 2;

-- ODHAD zvyšku roka (metóda menovite v reporte):
--   mesiac = plán mesiaca × (skutočnosť ÷ plán za posledné N mesiacov) po stredisku a riadku;
--   riadok bez plánu v tých mesiacoch = priemer skutočnosti posledných N mesiacov;
--   daň = −sadzba × odhad zisku pred zdanením mesiaca (za firmu, na stredisko dane).
CREATE TABLE bp_forecast AS
WITH par AS (SELECT * FROM bp_params),
     fc AS (SELECT g.ym, g.mo, g.shop, g.row,
                   CASE WHEN r.plan_rr <> 0 THEN g.plan * r.act_rr / r.plan_rr
                        ELSE coalesce(r.act_rr, 0) / par.runrate_months END AS amount,
                   CASE WHEN r.plan_rr <> 0 THEN 'plán × tempo' ELSE 'priemer posledných mesiacov' END AS method
            FROM bp_grid g JOIN bp_pace r USING (shop, row), par
            WHERE g.mo > par.as_of_m AND g.row <> par.tax_row),
     pbt AS (SELECT ym, mo, sum(amount) AS amount FROM fc
             WHERE row IN (SELECT s.part FROM pl_struct s, par WHERE s.row = par.pbt_row) GROUP BY 1, 2)
SELECT ym, mo, shop, row, amount, method FROM fc
UNION ALL
SELECT pbt.ym, pbt.mo, par.tax_shop, par.tax_row, -par.tax_rate * pbt.amount, 'sadzba × odhad zisku pred zdanením'
FROM pbt, par;

-- riadky board packu: YTD, plán, minulý rok, odhad roka — základné riadky aj medzisúčty (pl_struct), aj „Spolu"
CREATE TABLE bp_rows AS
WITH par AS (SELECT * FROM bp_params),
     b AS (SELECT g.shop, g.row,
                  sum(g.actual) AS ytd_act,
                  sum(CASE WHEN g.mo <= par.as_of_m THEN g.plan ELSE 0 END) AS ytd_plan,
                  sum(CASE WHEN g.mo <= par.as_of_m THEN g.ly ELSE 0 END) AS ytd_ly,
                  sum(CASE WHEN g.mo > par.as_of_m THEN g.plan ELSE 0 END) AS rest_plan,
                  sum(CASE WHEN g.mo > par.as_of_m THEN g.ly ELSE 0 END) AS rest_ly,
                  sum(g.plan) AS fy_plan, sum(g.ly) AS fy_ly
           FROM bp_grid g, par GROUP BY 1, 2),
     f AS (SELECT shop, row, sum(amount) AS rest_fc FROM bp_forecast GROUP BY 1, 2),
     bf AS (SELECT b.*, coalesce(f.rest_fc, 0) AS rest_fc FROM b LEFT JOIN f USING (shop, row)),
     allx AS (SELECT * FROM bf
              UNION ALL
              SELECT 'Spolu', row, sum(ytd_act), sum(ytd_plan), sum(ytd_ly), sum(rest_plan), sum(rest_ly),
                     sum(fy_plan), sum(fy_ly), sum(rest_fc) FROM bf GROUP BY row)
SELECT a.shop, s.row,
       sum(a.ytd_act) AS ytd_act, sum(a.ytd_plan) AS ytd_plan, sum(a.ytd_ly) AS ytd_ly,
       sum(a.rest_fc) AS rest_fc, sum(a.rest_plan) AS rest_plan, sum(a.rest_ly) AS rest_ly,
       sum(a.ytd_act) + sum(a.rest_fc) AS fy_est, sum(a.fy_plan) AS fy_plan, sum(a.fy_ly) AS fy_ly
FROM allx a JOIN pl_struct s ON s.part = a.row
GROUP BY 1, 2;

-- odchýlky YTD voči plánu po stredisku × riadku odchýlok (bp_var_rows z profilu: zložky EBITDA, tržby a predaný
-- tovar spolu ako hrubá marža), zoradené podľa vplyvu na EBITDA
CREATE TABLE bp_variance AS
SELECT r.shop, r.row, r.ytd_act, r.ytd_plan, r.ytd_ly,
       r.ytd_act - r.ytd_plan AS d_plan, r.ytd_act - r.ytd_ly AS d_ly,
       row_number() OVER (ORDER BY abs(r.ytd_act - r.ytd_plan) DESC, r.shop, r.row) AS rk
FROM bp_rows r
WHERE r.shop <> 'Spolu' AND r.row IN (SELECT row FROM bp_var_rows);
