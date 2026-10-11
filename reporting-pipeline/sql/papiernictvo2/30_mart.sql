-- MART — základ výstupov: výsledovka, pokladňa a plán.
-- Poctivo: medzisúčty (Hrubá marža … Čistý zisk) skladá motor v Pythone z profilu (pl_subtotals)
-- a kontroly bežia v pipeline/checks.py — definícia čísla = tento súbor + profile.json.
-- pl_base: výsledovka mesiac × stredisko × riadok (pl_map = prevodník účet → riadok z profilu).
CREATE TABLE pl_base AS
SELECT p.ym, c.shop, m.row, CAST(sum(p.amount) AS DOUBLE) AS amount
FROM core_postings p JOIN pl_map m USING (account) JOIN cost_centers c USING (cc)
GROUP BY 1, 2, 3;

-- pokladňa pre zistenia boardu (kategórie)
CREATE TABLE pos AS
SELECT s.day, c.shop, s.category, CAST(s.gross AS DOUBLE) AS gross
FROM stg_pos s JOIN cost_centers c USING (cc);

-- plán tržieb po strediskách a mesiacoch (hárok Plán vs skutočnosť)
CREATE TABLE plan AS
SELECT c.shop, CAST(substr(p.ym, 6, 2) AS INT) AS month, CAST(sum(p.amount) AS DOUBLE) AS amount
FROM stg_plan p JOIN cost_centers c USING (cc) WHERE p.account = '604' GROUP BY 1, 2;
