---
title: OpenQuant API
emoji: 📈
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# OpenQuant API

FastAPI service for the [openquant engine](https://github.com/A-bv/openquant-engine):
corporate-finance valuation, risk and portfolio math on live SEC EDGAR filings
and market prices.

This Space is built from the Dockerfile beside this file, which clones and
installs the engine. It powers the live-ticker labs at
[a-bv.github.io/openquant-engine](https://a-bv.github.io/openquant-engine/).

Health check: `/health`. Interactive docs: `/docs`.
