# Odoo rollout — implementation decisions

> **Work in progress.** This folder is a skeleton. It will hold the decision log
> of an ERP rollout for the fictional **Demo Retail s.r.o.** No Odoo Enterprise
> code and no configuration secrets are, or will be, stored here.

## Why a decision log

ERP rollouts rarely fail on software. They fail on decisions nobody wrote down:
why stores are analytic accounts and not companies, who closes the till, which
bank format is imported. Six months later nobody remembers, and the same
discussion starts again.

Each decision is one short file: **context → options → decision → consequence →
how we will know it was wrong.**

## Decision log

| # | Decision | Status |
|---|---|---|
| [001](decisions/001-stores-as-analytic-accounts.md) | Stores are analytic accounts in one company, not separate companies | example |
| … | further decisions will be added here | |

## Template

See [`decisions/000-template.md`](decisions/000-template.md).
