-- CORE — účtovné zápisy ako pohyby na účtoch (jeden riadok denníka = MD pohyb + D pohyb).
-- Znamienko: D − MD (výnosy +, náklady −); počiatočný stav (doklady PS) sa do výsledovky nedostane.
CREATE TABLE core_postings AS
SELECT ym, day, cc, doklad, md AS account, -amount AS amount, text FROM stg_journal WHERE doklad NOT LIKE 'PS%'
UNION ALL
SELECT ym, day, cc, doklad, d AS account, amount, text FROM stg_journal WHERE doklad NOT LIKE 'PS%';
