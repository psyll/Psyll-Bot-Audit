# Psyll Bot Audit

Psyll Bot Audit is a Python application that compares trading logs from [Psyll](https://psyll.com) trading bots with live Binance market data.
It helps to **verify trades, analyze differences, and audit bot performance** in real time.

## ✨ Features
- Fetches trading logs directly from Psyll bot pages
- Queries live Binance market data (via official API)
- Matches trades within a configurable time window
- Calculates price differences and % deviations
- Displays results in a live interactive console table (using [rich](https://github.com/Textualize/rich))
- Exports detailed CSV reports with full data for further analysis
- Summary statistics with matched/unmatched trades
