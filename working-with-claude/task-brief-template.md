# Task brief — 5 fields

An AI without a brief does plausible nonsense. These five fields are the whole
contract. If a field cannot be filled, that is the first question to answer,
not something to guess.

| Field | Question it answers | Bad | Good |
|---|---|---|---|
| **1. Goal** | Which piece of manual work disappears, and from when? | "Improve the payment process" | "From the next payment run I no longer retype payments into the bank; the bank file is generated from the approved list" |
| **2. Scope** | What is in, what is explicitly out? | (empty) | "In: SEPA EUR transfers. Out: urgent and non-EUR payments, approval workflow" |
| **3. Context** | What exists already, what must stay unchanged? | "See the folder" | "Approved list is an Excel export with these columns; the bank accepts pain.001.001.03; totals must equal the approval to the cent" |
| **4. Definition of done** | What will I observe when it works? | "It works" | "Clean run: file released. Each of these 6 broken inputs: file blocked with the reason. Two runs in a row without anyone touching it" |
| **5. STOP** | When must the agent stop and ask instead of deciding? | (empty) | "Any change to how an amount is calculated; anything sent to the bank; unclear origin of data" |

## Example (the brief behind `finance-ops-toolkit/` (a))

```
GOAL     Payment list -> bank XML without retyping, from the next payment run.
SCOPE    In: EUR SEPA credit transfers. Out: approval workflow, other currencies.
CONTEXT  List = CSV (name, IBAN, amount, currency, reference). Approved total
         is given separately. Bank format pain.001.001.03.
DONE     Clean list -> RELEASED. IBAN typo, 3 decimals, duplicate, total != approval,
         weekend date, wrong currency -> BLOCKED with reason. Finished XML edited
         by 1 cent -> caught on readback. make test green.
STOP     Changing the amount logic. Real IBANs or names. Sending anything anywhere.
```
