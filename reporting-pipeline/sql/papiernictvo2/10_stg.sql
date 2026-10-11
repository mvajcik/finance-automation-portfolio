-- STG — typované tabuľky zo surových exportov (raw_* = text tak, ako prišiel).
-- Stĺpec `bad` vymenuje polia, ktoré sa nedali prečítať; kontrola stg_parse_contract ho vyžaduje
-- prázdny v každej stg_* tabuľke — nič sa ticho nestratí ako NULL.
CREATE OR REPLACE MACRO sk_num(x) AS TRY_CAST(replace(replace(x, ' ', ''), ',', '.') AS DECIMAL(18, 2));
CREATE OR REPLACE MACRO file_ym(f) AS regexp_extract(f, '([0-9]{4}-[0-9]{2})', 1);

-- pokladňa: bločky (desatinná čiarka, dátum dd.mm.rrrr hh:mm)
CREATE TABLE stg_pos AS
SELECT file, line, regexp_extract(file, 'pokladna_([A-Z0-9]+)_', 1) AS cc, doklad,
       CAST(try_strptime(datum_cas, '%d.%m.%Y %H:%M') AS DATE) AS day,
       TRY_CAST(pokladna AS INT) AS register, kategoria AS category, TRY_CAST(mnozstvo AS INT) AS qty,
       sk_num(cena_j_s_dph) AS unit_price, TRY_CAST(sadzba_dph AS INT) AS vat_rate,
       sk_num(spolu_s_dph) AS gross, platba AS payment,
       concat_ws(',',
         CASE WHEN coalesce(doklad, '') = '' THEN 'doklad' END,
         CASE WHEN try_strptime(datum_cas, '%d.%m.%Y %H:%M') IS NULL THEN 'datum_cas' END,
         CASE WHEN strftime(try_strptime(datum_cas, '%d.%m.%Y %H:%M'), '%Y-%m') <> file_ym(file) THEN 'mesiac_suboru' END,
         CASE WHEN NOT regexp_full_match(coalesce(spolu_s_dph, ''), '-?[0-9]+,[0-9]{2}') THEN 'spolu_s_dph' END,
         CASE WHEN coalesce(TRY_CAST(sadzba_dph AS INT), -1) NOT IN (5, 19, 23) THEN 'sadzba_dph' END,
         CASE WHEN kategoria NOT IN (SELECT k FROM raw_dims WHERE sheet = 'Kategórie') OR kategoria IS NULL THEN 'kategoria' END,
         -- vratka zákazníka = záporné množstvo aj záporná suma; nula ani nesúlad znamienok nie
         CASE WHEN NOT regexp_full_match(coalesce(mnozstvo, ''), '-?[1-9][0-9]*') THEN 'mnozstvo' END,
         CASE WHEN NOT regexp_full_match(coalesce(cena_j_s_dph, ''), '[0-9]+,[0-9]{2}') THEN 'cena_j_s_dph' END,
         CASE WHEN sk_num(cena_j_s_dph) * TRY_CAST(mnozstvo AS INT) <> sk_num(spolu_s_dph) THEN 'mnozstvo*cena<>spolu' END,
         CASE WHEN coalesce(platba, '') NOT IN ('H', 'K') THEN 'platba' END) AS bad
FROM raw_pos;

CREATE TABLE stg_pos_footer AS
SELECT file, 0 AS line, regexp_extract(file, 'pokladna_([A-Z0-9]+)_', 1) AS cc, file_ym(file) AS ym, sk_num(total) AS total,
       CASE WHEN sk_num(total) IS NULL THEN 'SPOLU' ELSE '' END AS bad
FROM raw_pos_footer;

-- účtovný denník (desatinná bodka, dátum dd.mm.rrrr)
CREATE TABLE stg_journal AS
SELECT file, line, doklad, CAST(try_strptime(datum, '%d.%m.%Y') AS DATE) AS day, md, d,
       TRY_CAST(suma AS DECIMAL(18, 2)) AS amount, stredisko AS cc, popis AS text,
       strftime(try_strptime(datum, '%d.%m.%Y'), '%Y-%m') AS ym,
       concat_ws(',',
         CASE WHEN coalesce(doklad, '') = '' THEN 'doklad' END,
         CASE WHEN try_strptime(datum, '%d.%m.%Y') IS NULL THEN 'datum' END,
         CASE WHEN strftime(try_strptime(datum, '%d.%m.%Y'), '%Y-%m') <> file_ym(file) THEN 'mesiac_suboru' END,
         CASE WHEN NOT regexp_full_match(coalesce(md, ''), '[0-9]{3,6}') THEN 'md' END,
         CASE WHEN NOT regexp_full_match(coalesce(d, ''), '[0-9]{3,6}') THEN 'd' END,
         CASE WHEN NOT regexp_full_match(coalesce(suma, ''), '[0-9]+\.[0-9]{2}') THEN 'suma' END,
         CASE WHEN coalesce(stredisko, '') = '' THEN 'stredisko' END) AS bad
FROM raw_journal;

-- kniha došlých faktúr (xlsx: čísla ako čísla, dátumy ako dátumy)
CREATE TABLE stg_invoices AS
SELECT file, line, cislo AS invoice, dodavatel AS supplier, ico, TRY_CAST(datum_vystavenia AS DATE) AS day,
       TRY_CAST(splatnost AS DATE) AS due, ucet AS account, stredisko AS cc, text,
       TRY_CAST(zaklad AS DECIMAL(18, 2)) AS base, TRY_CAST(dph AS DECIMAL(18, 2)) AS vat,
       TRY_CAST(spolu AS DECIMAL(18, 2)) AS total, file_ym(file) AS ym,
       concat_ws(',',
         CASE WHEN coalesce(cislo, '') = '' THEN 'cislo' END,
         CASE WHEN TRY_CAST(datum_vystavenia AS DATE) IS NULL THEN 'datum_vystavenia' END,
         CASE WHEN strftime(TRY_CAST(datum_vystavenia AS DATE), '%Y-%m') <> file_ym(file) THEN 'mesiac_suboru' END,
         CASE WHEN TRY_CAST(zaklad AS DECIMAL(18, 2)) IS NULL THEN 'zaklad' END,
         CASE WHEN TRY_CAST(dph AS DECIMAL(18, 2)) IS NULL THEN 'dph' END,
         CASE WHEN TRY_CAST(spolu AS DECIMAL(18, 2)) IS NULL THEN 'spolu' END,
         CASE WHEN TRY_CAST(zaklad AS DECIMAL(18, 2)) + TRY_CAST(dph AS DECIMAL(18, 2))
                   <> TRY_CAST(spolu AS DECIMAL(18, 2)) THEN 'zaklad+dph<>spolu' END) AS bad
FROM raw_invoices;

-- mzdy (Windows-1250, desatinná čiarka)
CREATE TABLE stg_payroll AS
SELECT file, line, os_cislo AS employee, stredisko AS cc, pozicia AS position, file_ym(file) AS ym,
       sk_num(hruba_mzda) AS gross, sk_num(odvody_zamestnavatel) AS employer, sk_num(odvody_zamestnanec) AS employee_contrib,
       sk_num(dan) AS tax, sk_num(cista_mzda) AS net,
       concat_ws(',',
         CASE WHEN coalesce(os_cislo, '') = '' THEN 'os_cislo' END,
         CASE WHEN coalesce(stredisko, '') = '' THEN 'stredisko' END,
         CASE WHEN NOT regexp_full_match(coalesce(hruba_mzda, ''), '[0-9]+,[0-9]{2}') THEN 'hruba_mzda' END,
         CASE WHEN NOT regexp_full_match(coalesce(odvody_zamestnavatel, ''), '[0-9]+,[0-9]{2}') THEN 'odvody_zamestnavatel' END,
         CASE WHEN NOT regexp_full_match(coalesce(odvody_zamestnanec, ''), '[0-9]+,[0-9]{2}') THEN 'odvody_zamestnanec' END,
         CASE WHEN NOT regexp_full_match(coalesce(dan, ''), '[0-9]+,[0-9]{2}') THEN 'dan' END,
         CASE WHEN NOT regexp_full_match(coalesce(cista_mzda, ''), '[0-9]+,[0-9]{2}') THEN 'cista_mzda' END,
         CASE WHEN sk_num(hruba_mzda) - sk_num(odvody_zamestnanec) - sk_num(dan) <> sk_num(cista_mzda)
              THEN 'hruba-odvody-dan<>cista' END) AS bad
FROM raw_payroll;

-- banka (výpis: zostatky v hlavičke a pätičke)
CREATE TABLE stg_bank AS
SELECT file, line, CAST(try_strptime(datum, '%d.%m.%Y') AS DATE) AS day, protistrana AS counterparty,
       iban_protistrany AS iban, vs, sk_num(suma) AS amount, mena AS ccy, popis AS text, file_ym(file) AS ym,
       concat_ws(',',
         CASE WHEN try_strptime(datum, '%d.%m.%Y') IS NULL THEN 'datum' END,
         CASE WHEN strftime(try_strptime(datum, '%d.%m.%Y'), '%Y-%m') <> file_ym(file) THEN 'mesiac_suboru' END,
         CASE WHEN NOT regexp_full_match(coalesce(suma, ''), '-?[0-9]+,[0-9]{2}') THEN 'suma' END,
         CASE WHEN coalesce(mena, '') <> 'EUR' THEN 'mena' END) AS bad
FROM raw_bank;

CREATE TABLE stg_bank_meta AS
SELECT file, 0 AS line, file_ym(file) AS ym, sk_num(opening) AS opening, sk_num(closing) AS closing,
       concat_ws(',', CASE WHEN sk_num(opening) IS NULL THEN 'pociatocny_zostatok' END,
                      CASE WHEN sk_num(closing) IS NULL THEN 'konecny_zostatok' END) AS bad
FROM raw_bank_meta;

-- sklad (desatinná bodka, dátum ISO)
CREATE TABLE stg_stock_moves AS
SELECT file, line, doklad, TRY_CAST(datum AS DATE) AS day, typ AS kind, predajna AS cc, kategoria AS category,
       TRY_CAST(hodnota_nakup AS DECIMAL(18, 2)) AS value, file_ym(file) AS ym,
       concat_ws(',',
         CASE WHEN TRY_CAST(datum AS DATE) IS NULL THEN 'datum' END,
         CASE WHEN coalesce(typ, '') NOT IN ('príjem', 'výdaj') THEN 'typ' END,
         CASE WHEN TRY_CAST(hodnota_nakup AS DECIMAL(18, 2)) IS NULL THEN 'hodnota_nakup' END,
         CASE WHEN kategoria NOT IN (SELECT k FROM raw_dims WHERE sheet = 'Kategórie') THEN 'kategoria' END) AS bad
FROM raw_stock_moves;

CREATE TABLE stg_stock_state AS
SELECT file, line, predajna AS cc, kategoria AS category, file_ym(file) AS ym,
       TRY_CAST(pociatocny_stav AS DECIMAL(18, 2)) AS opening, TRY_CAST(prijem AS DECIMAL(18, 2)) AS received,
       TRY_CAST(vydaj AS DECIMAL(18, 2)) AS issued, TRY_CAST(konecny_stav AS DECIMAL(18, 2)) AS closing,
       concat_ws(',',
         CASE WHEN TRY_CAST(pociatocny_stav AS DECIMAL(18, 2)) IS NULL THEN 'pociatocny_stav' END,
         CASE WHEN TRY_CAST(prijem AS DECIMAL(18, 2)) IS NULL THEN 'prijem' END,
         CASE WHEN TRY_CAST(vydaj AS DECIMAL(18, 2)) IS NULL THEN 'vydaj' END,
         CASE WHEN TRY_CAST(konecny_stav AS DECIMAL(18, 2)) IS NULL THEN 'konecny_stav' END,
         CASE WHEN kategoria NOT IN (SELECT k FROM raw_dims WHERE sheet = 'Kategórie') THEN 'kategoria' END) AS bad
FROM raw_stock_state;

-- plán (xlsx) a číselníky
CREATE TABLE stg_plan AS
SELECT file, line, ucet AS account, stredisko AS cc, mesiac AS ym, TRY_CAST(suma AS DECIMAL(18, 2)) AS amount,
       CASE WHEN suma IS NOT NULL AND TRY_CAST(suma AS DECIMAL(18, 2)) IS NULL THEN 'suma' ELSE '' END AS bad
FROM raw_plan;
