-- STG — typované tabuľky zo surových exportov (raw_* = text tak, ako prišiel).
-- Stĺpec `bad` vymenuje polia, ktoré sa nedali prečítať; kontrola stg_parse_contract ho vyžaduje
-- prázdny v každej stg_* tabuľke — nič sa ticho nestratí ako NULL.
CREATE OR REPLACE MACRO sk_num(x) AS TRY_CAST(replace(replace(x, ' ', ''), ',', '.') AS DECIMAL(18, 2));
CREATE OR REPLACE MACRO file_ym(f) AS regexp_extract(f, '([0-9]{4}-[0-9]{2})', 1);

-- pokladňa: bločky (desatinná čiarka, dátum dd.mm.rrrr hh:mm)
CREATE TABLE stg_pos AS
SELECT r.file, r.line, regexp_extract(r.file, 'pos_([A-Z0-9]+)_', 1) AS cc, r.receipt AS doklad,
       CAST(try_strptime(r.datetime, '%d.%m.%Y %H:%M') AS DATE) AS day,
       TRY_CAST(r.till AS INT) AS register, r.category AS category, TRY_CAST(r.quantity AS INT) AS qty,
       sk_num(r.unit_price_incl_vat) AS unit_price, TRY_CAST(r.vat_rate AS INT) AS vat_rate,
       sk_num(r.total_incl_vat) AS gross, r.payment AS payment,
       concat_ws(',',
         CASE WHEN coalesce(r.receipt, '') = '' THEN 'receipt' END,
         CASE WHEN try_strptime(r.datetime, '%d.%m.%Y %H:%M') IS NULL THEN 'datetime' END,
         CASE WHEN strftime(try_strptime(r.datetime, '%d.%m.%Y %H:%M'), '%Y-%m') <> file_ym(r.file) THEN 'file_month' END,
         CASE WHEN NOT regexp_full_match(coalesce(r.total_incl_vat, ''), '-?[0-9]+,[0-9]{2}') THEN 'total_incl_vat' END,
         CASE WHEN coalesce(TRY_CAST(r.vat_rate AS INT), -1) NOT IN (5, 19, 23) THEN 'vat_rate' END,
         CASE WHEN r.category NOT IN (SELECT k FROM raw_dims WHERE sheet = 'Categories') OR r.category IS NULL THEN 'category' END,
         -- vratka zákazníka = záporné množstvo aj záporná suma; nula ani nesúlad znamienok nie
         CASE WHEN NOT regexp_full_match(coalesce(r.quantity, ''), '-?[1-9][0-9]*') THEN 'quantity' END,
         CASE WHEN NOT regexp_full_match(coalesce(r.unit_price_incl_vat, ''), '[0-9]+,[0-9]{2}') THEN 'unit_price_incl_vat' END,
         CASE WHEN sk_num(r.unit_price_incl_vat) * TRY_CAST(r.quantity AS INT) <> sk_num(r.total_incl_vat) THEN 'quantity*price<>total' END,
         CASE WHEN coalesce(r.payment, '') NOT IN ('cash', 'card') THEN 'payment' END) AS bad
FROM raw_pos r;

CREATE TABLE stg_pos_footer AS
SELECT file, 0 AS line, regexp_extract(file, 'pos_([A-Z0-9]+)_', 1) AS cc, file_ym(file) AS ym, sk_num(total) AS total,
       CASE WHEN sk_num(total) IS NULL THEN 'TOTAL' ELSE '' END AS bad
FROM raw_pos_footer;

-- účtovný denník (desatinná bodka, dátum dd.mm.rrrr)
CREATE TABLE stg_journal AS
SELECT r.file, r.line, r.document AS doklad, CAST(try_strptime(r.date, '%d.%m.%Y') AS DATE) AS day, r.dr AS md, r.cr AS d,
       TRY_CAST(r.amount AS DECIMAL(18, 2)) AS amount, r.cost_centre AS cc, r.description AS text,
       strftime(try_strptime(r.date, '%d.%m.%Y'), '%Y-%m') AS ym,
       concat_ws(',',
         CASE WHEN coalesce(r.document, '') = '' THEN 'document' END,
         CASE WHEN try_strptime(r.date, '%d.%m.%Y') IS NULL THEN 'date' END,
         CASE WHEN strftime(try_strptime(r.date, '%d.%m.%Y'), '%Y-%m') <> file_ym(r.file) THEN 'file_month' END,
         CASE WHEN NOT regexp_full_match(coalesce(r.dr, ''), '[0-9]{3,6}') THEN 'dr' END,
         CASE WHEN NOT regexp_full_match(coalesce(r.cr, ''), '[0-9]{3,6}') THEN 'cr' END,
         CASE WHEN NOT regexp_full_match(coalesce(r.amount, ''), '[0-9]+\.[0-9]{2}') THEN 'amount' END,
         CASE WHEN coalesce(r.cost_centre, '') = '' THEN 'cost_centre' END) AS bad
FROM raw_journal r;

-- kniha došlých faktúr (xlsx: čísla ako čísla, dátumy ako dátumy)
CREATE TABLE stg_invoices AS
SELECT r.file, r.line, r.number AS invoice, r.supplier AS supplier, r.company_id AS ico, TRY_CAST(r.issue_date AS DATE) AS day,
       TRY_CAST(r.due_date AS DATE) AS due, r.account AS account, r.cost_centre AS cc, r.text,
       TRY_CAST(r.net AS DECIMAL(18, 2)) AS base, TRY_CAST(r.vat AS DECIMAL(18, 2)) AS vat,
       TRY_CAST(r.total AS DECIMAL(18, 2)) AS total, file_ym(r.file) AS ym,
       concat_ws(',',
         CASE WHEN coalesce(r.number, '') = '' THEN 'number' END,
         CASE WHEN TRY_CAST(r.issue_date AS DATE) IS NULL THEN 'issue_date' END,
         CASE WHEN strftime(TRY_CAST(r.issue_date AS DATE), '%Y-%m') <> file_ym(r.file) THEN 'file_month' END,
         CASE WHEN TRY_CAST(r.net AS DECIMAL(18, 2)) IS NULL THEN 'net' END,
         CASE WHEN TRY_CAST(r.vat AS DECIMAL(18, 2)) IS NULL THEN 'vat' END,
         CASE WHEN TRY_CAST(r.total AS DECIMAL(18, 2)) IS NULL THEN 'total' END,
         CASE WHEN TRY_CAST(r.net AS DECIMAL(18, 2)) + TRY_CAST(r.vat AS DECIMAL(18, 2))
                   <> TRY_CAST(r.total AS DECIMAL(18, 2)) THEN 'net+vat<>total' END) AS bad
FROM raw_invoices r;

-- mzdy (Windows-1250, desatinná čiarka)
CREATE TABLE stg_payroll AS
SELECT r.file, r.line, r.employee_no AS employee, r.cost_centre AS cc, r.position AS position, file_ym(r.file) AS ym,
       sk_num(r.gross_pay) AS gross, sk_num(r.employer_contributions) AS employer, sk_num(r.employee_contributions) AS employee_contrib,
       sk_num(r.tax) AS tax, sk_num(r.net_pay) AS net,
       concat_ws(',',
         CASE WHEN coalesce(r.employee_no, '') = '' THEN 'employee_no' END,
         CASE WHEN coalesce(r.cost_centre, '') = '' THEN 'cost_centre' END,
         CASE WHEN NOT regexp_full_match(coalesce(r.gross_pay, ''), '[0-9]+,[0-9]{2}') THEN 'gross_pay' END,
         CASE WHEN NOT regexp_full_match(coalesce(r.employer_contributions, ''), '[0-9]+,[0-9]{2}') THEN 'employer_contributions' END,
         CASE WHEN NOT regexp_full_match(coalesce(r.employee_contributions, ''), '[0-9]+,[0-9]{2}') THEN 'employee_contributions' END,
         CASE WHEN NOT regexp_full_match(coalesce(r.tax, ''), '[0-9]+,[0-9]{2}') THEN 'tax' END,
         CASE WHEN NOT regexp_full_match(coalesce(r.net_pay, ''), '[0-9]+,[0-9]{2}') THEN 'net_pay' END,
         CASE WHEN sk_num(r.gross_pay) - sk_num(r.employee_contributions) - sk_num(r.tax) <> sk_num(r.net_pay)
              THEN 'gross-contributions-tax<>net' END) AS bad
FROM raw_payroll r;

-- banka (výpis: zostatky v hlavičke a pätičke)
CREATE TABLE stg_bank AS
SELECT r.file, r.line, CAST(try_strptime(r.date, '%d.%m.%Y') AS DATE) AS day, r.counterparty AS counterparty,
       r.counterparty_iban AS iban, r.reference AS vs, sk_num(r.amount) AS amount, r.currency AS ccy, r.description AS text,
       file_ym(r.file) AS ym,
       concat_ws(',',
         CASE WHEN try_strptime(r.date, '%d.%m.%Y') IS NULL THEN 'date' END,
         CASE WHEN strftime(try_strptime(r.date, '%d.%m.%Y'), '%Y-%m') <> file_ym(r.file) THEN 'file_month' END,
         CASE WHEN NOT regexp_full_match(coalesce(r.amount, ''), '-?[0-9]+,[0-9]{2}') THEN 'amount' END,
         CASE WHEN coalesce(r.currency, '') <> 'EUR' THEN 'currency' END) AS bad
FROM raw_bank r;

CREATE TABLE stg_bank_meta AS
SELECT file, 0 AS line, file_ym(file) AS ym, sk_num(opening) AS opening, sk_num(closing) AS closing,
       concat_ws(',', CASE WHEN sk_num(opening) IS NULL THEN 'opening_balance' END,
                      CASE WHEN sk_num(closing) IS NULL THEN 'closing_balance' END) AS bad
FROM raw_bank_meta;

-- sklad (desatinná bodka, dátum ISO)
CREATE TABLE stg_stock_moves AS
SELECT r.file, r.line, r.document AS doklad, TRY_CAST(r.date AS DATE) AS day, r.type AS kind, r.store AS cc, r.category AS category,
       TRY_CAST(r.cost_value AS DECIMAL(18, 2)) AS value, file_ym(r.file) AS ym,
       concat_ws(',',
         CASE WHEN TRY_CAST(r.date AS DATE) IS NULL THEN 'date' END,
         CASE WHEN coalesce(r.type, '') NOT IN ('receipt', 'issue') THEN 'type' END,
         CASE WHEN TRY_CAST(r.cost_value AS DECIMAL(18, 2)) IS NULL THEN 'cost_value' END,
         CASE WHEN r.category NOT IN (SELECT k FROM raw_dims WHERE sheet = 'Categories') THEN 'category' END) AS bad
FROM raw_stock_moves r;

CREATE TABLE stg_stock_state AS
SELECT r.file, r.line, r.store AS cc, r.category AS category, file_ym(r.file) AS ym,
       TRY_CAST(r.opening AS DECIMAL(18, 2)) AS opening, TRY_CAST(r.received AS DECIMAL(18, 2)) AS received,
       TRY_CAST(r.issued AS DECIMAL(18, 2)) AS issued, TRY_CAST(r.closing AS DECIMAL(18, 2)) AS closing,
       concat_ws(',',
         CASE WHEN TRY_CAST(r.opening AS DECIMAL(18, 2)) IS NULL THEN 'opening' END,
         CASE WHEN TRY_CAST(r.received AS DECIMAL(18, 2)) IS NULL THEN 'received' END,
         CASE WHEN TRY_CAST(r.issued AS DECIMAL(18, 2)) IS NULL THEN 'issued' END,
         CASE WHEN TRY_CAST(r.closing AS DECIMAL(18, 2)) IS NULL THEN 'closing' END,
         CASE WHEN r.category NOT IN (SELECT k FROM raw_dims WHERE sheet = 'Categories') THEN 'category' END) AS bad
FROM raw_stock_state r;

-- plán (xlsx) a číselníky
CREATE TABLE stg_plan AS
SELECT file, line, ucet AS account, stredisko AS cc, mesiac AS ym, TRY_CAST(suma AS DECIMAL(18, 2)) AS amount,
       CASE WHEN suma IS NOT NULL AND TRY_CAST(suma AS DECIMAL(18, 2)) IS NULL THEN 'amount' ELSE '' END AS bad
FROM raw_plan;
