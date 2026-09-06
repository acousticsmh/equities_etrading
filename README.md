# Equities E-Trading Research

## Project Intent

This project is a research codebase for studying and validating market-making strategies in cash equities. Its purpose is to turn event-level market data into reproducible research results while keeping market mechanics, execution assumptions, risk controls, and experiment decisions explicit.

The first strategy target is a liquidity-providing market maker that quotes both sides of a limit order book, seeks spread capture, and manages the risks that make passive trading difficult:

- adverse selection when informed flow arrives before a price move;
- inventory accumulation and directional exposure;
- queue position and uncertain fills;
- latency between market events, decisions, and orders;
- fees, rebates, spread costs, and market impact.

Each module has a clear responsibility and can be implemented and tested independently. The design follows the development sequence in Chapter 8: validate data and book reconstruction first, then add features, signals, realistic execution, risk controls, and backtesting. The first implemented slice is the basket-oriented ingestion pipeline in `research/ingest/`.

## Research Flow

```text
raw events
    |
    v
ingest -> book -> features -> signals -> execution -> backtest -> docs
                                      |
                                      v
                                     risk
```

Data flows from raw market events toward strategy evaluation. Risk checks gate execution decisions. Documentation records the assumptions and configuration behind every experiment.

## Module Structure

### `research/`

The top-level Python package for the research system. It contains the independently testable layers below and will be the import boundary for future command-line tools, notebooks, and experiment runners.

### `research/ingest/`

Owns the boundary between external data and the research system.

Responsibilities:

- load raw trade, quote, depth, and order-level event files;
- validate schemas and required fields;
- preserve exchange timestamps, local receipt timestamps, and sequence numbers;
- detect duplicates, gaps, out-of-order events, and malformed records;
- provide reference data such as symbols, venues, corporate actions, calendars, halts, and auction schedules;
- normalise data into structures that downstream modules can consume without losing source context.

This module should not compute trading signals or silently repair questionable market data. Data-quality decisions belong in explicit validation and reporting paths.

See [`docs/ingestion.md`](docs/ingestion.md) for provider setup, API usage, normalized event fields, raw-data layout, and depth/order-level feed guidance.

See [`docs/book.md`](docs/book.md) for order-book reconstruction ownership, event lifecycle semantics, replay sequencing, validation, and snapshot behavior.

See [`docs/execution.md`](docs/execution.md) for FIFO queue-position fill simulation, execution results, diagnostics, and integration guidance.

### `research/book/`

Reconstructs venue-level order-book state from sequenced order events.

Responsibilities:

- apply add, modify, cancel, execute, and replace events in sequence;
- maintain order identifiers, side, price, remaining quantity, and queue ordering;
- expose top-of-book and multi-level depth snapshots;
- handle partial fills and order lifecycles correctly;
- provide consistency checks against independent snapshots or feed-provided checksums.

This is the controlling source for displayed liquidity features. It should remain separate from signal logic so book correctness can be tested with hand-built event sequences.

### `research/features/`

Computes measurable market-state variables from reconstructed books and aligned trades.

Initial feature families include:

- bid, ask, spread, and mid-price;
- depth-weighted microprice;
- top-of-book and multi-level imbalance;
- order-flow imbalance;
- short-horizon realised volatility;
- trade-sign and signed-volume measures;
- queue-position and replenishment indicators.

Feature definitions, units, lookback windows, and availability timestamps must be documented so that no feature uses information that was unavailable at decision time.

### `research/signals/`

Converts feature values into quoting or directional decisions.

The initial market-making signal should remain interpretable. It may combine microprice, order-flow imbalance, volatility, inventory, and recent fill or toxicity information to determine whether to quote, skew, widen, or withdraw. More complex models can be added later only after simple baselines have been validated out of sample.

This module expresses strategy intent; it should not simulate fills, bypass risk limits, or own venue connectivity.

### `research/execution/`

Models how a strategy’s decisions become orders and fills.

Responsibilities:

- represent order submission, acknowledgement, cancellation, replacement, rejection, partial fill, and completion states;
- simulate decision, network, and processing latency;
- model queue position and realistic passive fills;
- model aggressive executions, fees, rebates, spread crossing, and market impact;
- preserve the distinction between a strategy decision and the execution outcome.

The execution layer is where a paper quote becomes a plausible historical fill. Touching a price is not sufficient evidence that a resting order was filled.

### `research/risk/`

Applies controls before and during simulated or future live execution.

Responsibilities:

- enforce maximum order size and notional limits;
- enforce inventory, exposure, price-collar, and loss limits;
- restrict symbols, venues, and strategies as configured;
- detect duplicate, stale, or runaway orders;
- provide throttles and an emergency kill-switch abstraction;
- record rejected decisions and the reason for rejection.

Risk must be a gate in the order path, not a report generated after the trade has already been accepted.

### `research/backtest/`

Runs reproducible historical experiments and evaluates strategy behaviour.

Responsibilities:

- coordinate event replay, feature calculation, signal generation, execution, and risk checks;
- support one-symbol, one-day debugging runs before larger datasets;
- run walk-forward and out-of-sample evaluations;
- calculate PnL, drawdown, turnover, inventory, fill quality, slippage, and cost attribution;
- compare market-making baselines against increasingly sophisticated variants;
- emit results together with the exact configuration and data range used.

Backtests should make look-ahead bias, survivorship bias, missing data, and unrealistic fill assumptions visible rather than hiding them behind a headline return.

### `docs/`

Stores research-specific documentation and experiment records.

Responsibilities:

- record data sources, venue assumptions, calendars, and timestamp conventions;
- document feature definitions, strategy parameters, and cost models;
- maintain experiment configurations and result summaries;
- keep a changelog for changes that affect reproducibility;
- maintain an explicit list of known biases, limitations, and unresolved questions.

The `experiments/` directory belongs here so that a result can be traced back to its inputs, assumptions, and versioned configuration.

## Dependency Rules

The intended dependency direction is:

1. `ingest` provides validated events and reference data.
2. `book` reconstructs live venue state from those events.
3. `features` derives measurements from book state and aligned market data.
4. `signals` turns measurements into strategy decisions.
5. `risk` approves or rejects decisions before execution.
6. `execution` models order lifecycle, latency, queueing, and fills.
7. `backtest` orchestrates the layers and produces metrics.
8. `docs` records the assumptions and outputs needed to reproduce the run.

Lower layers should not import higher-level strategy or reporting code. This keeps each layer testable and makes it possible to replace a simulator, signal, or data source without rewriting the whole project.

## Planned Development Sequence

1. Add a small fixture containing one symbol and one trading day of order events.
2. Implement and verify top-of-book reconstruction against hand-computed states.
3. Add unit-tested spread, mid-price, microprice, imbalance, and volatility features.
4. Implement a simple inventory-aware market-making baseline.
5. Add latency, queue-aware fills, cancellations, partial fills, fees, and rebates.
6. Add risk gates and failure-path tests.
7. Run walk-forward backtests with cost and fill-quality attribution.
8. Introduce more advanced modelling only after the baseline and simulator are credible.

## Current Scope

The current implementation loads Alpaca historical trades and quotes for a symbol basket, loads depth and order-level captures from local JSONL, JSON, or CSV files, and stores normalized raw events as partitioned JSONL. It intentionally does not claim to connect to a broker, venue, FIX gateway, or live market. Any future live-trading integration must add production-grade controls, operational monitoring, reconciliation, and compliance review beyond this research codebase.