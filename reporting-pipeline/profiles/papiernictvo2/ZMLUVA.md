# Zmluva reportu — Papiernictvo DEMO s.r.o. (board pack, `prehlad.xlsx`)

Fiktívna firma, vygenerované dáta. Zmluva v tvare pre stroj je `zmluva.json` (kontrola `report_contract`);
podpis = odtlačok obsahu zmluvy a oboch kotiev v poli `signed` (`tools/sign_contract.py`). Akákoľvek zmena
zmluvy alebo kotvy po podpise → stroj hlási „PODPIS NEPLATNÝ" a odoslanie nepovolí.

## 1. Čitateľ a účel

Majiteľ / board fiktívnej siete 4 predajní + centrály. Report k **30.9.2026** odpovedá: koľko firma zarobila
za 9 mesiacov a oproti plánu, **kam dobehne rok** oproti plánu, čo je najväčšia odchýlka a aké riziko alebo
slabina odhadu z dát vyplýva. Odosiela sa **len `prehlad.xlsx`**; `report.md` je technický záznam.

## 2. Čísla, ktoré čitateľ číta (17)

Bunka sa hľadá podľa hárka, riadka a stĺpca (alebo začiatku textu vety), nie podľa súradnice. „Kotvy" =
porovnanie s kotvou A aj B (§5); ďalšie umiestnenia toho istého čísla sa overujú tiež.

| ID | Číslo | Kde v reporte | Definícia | Tolerancia |
|---|---|---|---|---|
| P01 | Tržby YTD skutočnosť | Board pack · Tržby · YTD skutočnosť | Σ riadku Tržby (§2a), 01–09/2026 | 1 € |
| P02 | Tržby YTD plán | Board pack · Tržby · YTD plán | Σ plánu riadku Tržby 01–09 (§2b) | 1 € |
| P03 | Tržby odhad roka | Board pack · Tržby · Odhad roka | P01 + odhad 10–12 (§2c) | 1 € |
| P04 | Tržby plán roka | Board pack · Tržby · Plán roka | Σ plánu 01–12 | 1 € |
| P05 | EBITDA YTD skutočnosť | Board pack · EBITDA · YTD skutočnosť | Σ riadkov Tržby … Ostatné, 01–09 | 1 € |
| P06 | EBITDA YTD plán | Board pack · EBITDA · YTD plán | ako P02 pre riadky EBITDA | 1 € |
| P07 | EBITDA odhad roka | Board pack · EBITDA · Odhad roka | P05 + odhad 10–12 | 1 € |
| P08 | EBITDA plán roka | Board pack · EBITDA · Plán roka | Σ plánu riadkov EBITDA 01–12 | 1 € |
| P09 | Čistý zisk YTD skutočnosť | Board pack · Čistý zisk | všetky riadky §2a vrátane odpisov, úrokov a dane | 1 € |
| P10 | Čistý zisk YTD plán | Board pack · Čistý zisk · YTD plán | plán riadkov + daň plánu (§2b) | 1 € |
| P11 | Čistý zisk odhad roka | Board pack · Čistý zisk · Odhad roka | P09 + odhad 10–12 vrátane dane | 1 € |
| P12 | Čistý zisk plán roka | Board pack · Čistý zisk · Plán roka | plán + daň plánu 01–12 | 1 € |
| P13 | Najväčšia odchýlka: OC · Nájom | Odchýlky · „Predajňa OC · Nájom" | skutočnosť − plán riadku Nájom, S03, 01–09 | 1 € |
| P14 | Riziko: energie | Riziká a príležitosti · energie Q1 | minulý rok 10–12 Energie × (Q1 2026 ÷ Q1 2025) − odhad 10–12 | 1 € |
| P15 | Citlivosť odhadu: papiernictvo | Riziká a príležitosti · mix kategórií | vplyv zmeny mixu kategórie na EBITDA odhadu | 1 € |
| P16 | Hračky: medziročná zmena Q3 | Prehľad · zistenie „Hračky:" | tržby Hračky s DPH 07–09/2026 ÷ 07–09/2025 − 1 | ≤ 0,05 p. b. |
| P17 | EBITDA odhad voči plánu roka (%) | Prehľad · veta „EBITDA 2026 — odhad …" | (P07 − P08) ÷ \|P08\| | ≤ 0,05 p. b. |

### 2a. Riadky výsledovky (Σ D − MD z účtovného denníka)

Tržby 604 · Náklady na predaný tovar 504 · Personál 521, 524 · Nájom 518100 · Energie 502 · Marketing 518500 ·
Služby 511, 518200, 518300, 518400 · Ostatné 501, 568 · **EBITDA** · Odpisy 551 · Úroky a finančné 562 ·
**Zisk pred zdanením** · Daň z príjmov 591 · **Čistý zisk**.

### 2b. Plán

`plan_2026.xlsx` (účet × stredisko × mesiac). Plán dane nemá → daň plánu = −21 % × plán zisku pred zdanením.

### 2c. Odhad zvyšku roka (10–12/2026)

Mesiac = plán mesiaca × (skutočnosť ÷ plán za 07–09/2026). **Metóda je voľba** — kotvy strážia výpočet,
nie to, či je metóda správna; jej slabiny ukazuje report v časti „Citlivosť odhadu" (P15).

## 3. Podmienky odoslania (všetky naraz)

1. Verdikt stroja **SEDÍ** (všetky kontroly zdroj ↔ zdroj prešli).
2. Všetkých 17 čísel z **hotového súboru** sedí s **oboma kotvami** v tolerancii.
3. Zmluva je podpísaná a podpis platí.

Inak stroj report nevydá — len protokol s menovitým dôvodom. Výnimky: žiadne.

## 4. Kotvy (golden mimo kódu motora)

- **Kotva A — generátor** (`golden_generator.json`): 17 čísel z denníka, plánu a bločkov, z ktorých generátor
  dodávku vyrobil; viaže zmluvu na dodávku (odtlačok) a obdobie 2026-09.
- **Kotva B — nezávislý prepočet** (`tools/golden_nezavisly_papiernictvo2.py`, naživo pri každom behu): bez
  motora, generátora a DuckDB. Kotva B, ktorá importuje kód motora alebo DuckDB, sa pri behu odmietne.

## 5. Čo zmluva nekryje

Vecnú správnosť zaúčtovania, pravosť dokladov, voľbu metódy odhadu, iné obdobia a dodávky, komentáre
kontrolóra (sú označené „[kontrolór]" a nesú číslo stroja) a čísla mimo 17 bodov (výpočet stráži
`boardpack_consistency`, vykreslenie len testy).
