# crypto_bot_investment

A Binance BTCUSDT scalping bot, built in stages. **Stage 1 (data layer + backtester) is
implemented; Stages 2-5 are stubs.**

## What works today (Stage 1)

- Fetch historical 1-minute kline (candle) data from Binance's public REST API.
- Cache it locally in SQLite (`data/klines.db`) so repeated backtests don't re-fetch.
- Replay data bar-by-bar through a backtesting engine that simulates market-order fills
  with Binance's real taker fees and configurable slippage.
- Report total return, win rate, max drawdown, a Sharpe-like ratio, and fee drag.
- A null/random strategy is included as a sanity check: it should reliably *lose* money
  to fees and slippage. If it doesn't, the fee model is broken.

## Build stages (do not skip ahead)

| Stage | Module | Status |
|-------|--------|--------|
| 1. Data layer + backtester | `datafeed/`, `backtest/` | **Done** |
| 2. Strategy module | `strategies/` | Interface + random baseline only |
| 3. Risk manager | `risk/` | Minimal (position-size checks + decision logging); daily-loss kill switch pending |
| 4. Paper trading | `execution/paper.py` | Stub |
| 5. Live trading | `execution/live.py` | Stub (hard-disabled by default) |

## Setup

```powershell
cd "D:\Dev - Projects\investment\crypto_bot_investment"
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy config\.env.example .env
```

## Usage

```powershell
# Backtest the random baseline strategy on the last 7 days of BTCUSDT 1m data
py main.py --mode backtest --symbol BTCUSDT --days 7 --strategy random

# Explicit date range
py main.py --mode backtest --start 2026-06-01 --end 2026-06-15

# Paper / live modes exist but exit immediately (Stages 4-5 not built yet)
py main.py --mode paper
py main.py --mode live
```

Run tests:

```powershell
pytest --cov=.
```

## Fee and slippage assumptions

All fee/slippage numbers live in [config/settings.py](config/settings.py) and can be
overridden via environment variables (see `config/.env.example`).

- **Default fees: 0.10% maker / 0.10% taker** — Binance spot standard (VIP 0) schedule,
  *without* the BNB 25% fee discount. Verify against
  <https://www.binance.com/en/fee/schedule> before trusting backtest results.
- **The backtester charges the taker fee on every fill**, because a scalping bot using
  market orders is a taker. The maker rate is configured for later stages that may post
  limit orders.
- **Default slippage: 1 basis point (0.01%) per fill**, applied against you (buys fill
  higher, sells fill lower). This is a guess, not a measurement — tune it once paper
  trading (Stage 4) gives you real fill data.
- Fills execute at the **next bar's open** after a signal, never the same bar's close,
  to avoid look-ahead bias.

## Safety rules (non-negotiable, from the build spec)

- No API keys in source. Secrets load from `.env`, which is gitignored. Stage 1 uses
  only public endpoints and needs no keys at all.
- Binance API keys, when eventually needed, must be created **without withdrawal
  permission** (set in the Binance UI). The bot never requires withdrawal access.
- Every order path — backtest, paper, live — goes through `risk/risk_manager.py`.
  No mode bypasses it.
- Live trading requires `LIVE_TRADING_ENABLED=true` in the environment; it defaults to
  disabled and `execution/live.py` refuses to construct without it.

## Repo structure

```
crypto_bot_investment/
  core/          # shared data models (orders, fills, account state)
  data/          # cached historical data (gitignored)
  datafeed/      # Binance kline fetching + SQLite caching
  strategies/    # swappable strategy modules (common Strategy interface)
  risk/          # risk manager — every order passes through here
  backtest/      # bar-by-bar backtesting engine + performance metrics
  execution/     # paper + live order execution (Stages 4-5 stubs)
  config/        # settings, .env.example (no real secrets)
  tests/
  main.py        # entry point, mode selector: backtest | paper | live
```
