# CLAUDE.md — stock-screeners

Instructions for Claude Code when working in this repo.

---

## Repo layout

```
shared/               # cross-tool utilities (no CLI, no domain models)
  md_table.py         # generic markdown table parse + format
  market_data.py      # yfinance fetch + JSON cache (QuoteResult dataclass)

dividend/             # "divvy" CLI — buy-and-hold dividend portfolio
  cli.py              # Click entry point; registers all commands
  config.py           # Config dataclass + YAML loader (load_config)
  md_io.py            # Holding / WatchlistItem / Transaction models + file I/O
  scoring.py          # Scoring heuristics for recommend (score_candidates)
  commands/
    buy.py            # divvy buy   — records a purchase
    sell.py           # divvy sell  — records a sale
    status.py         # divvy status — live portfolio dashboard
    review.py         # divvy review — flags yield/price deterioration
    recommend.py      # divvy recommend — ranks watchlist candidates

tests/                # pytest; all market data mocked, no network
  test_md_table.py
  test_dividend_md_io.py
  test_dividend_config.py
  test_market_data.py
  test_scoring.py
  test_dividend_commands.py   # uses CliRunner end-to-end

dividend/data/        # committed to git (private repo)
  portfolio.md
  watchlist.md
  transactions.md

.cache/               # gitignored — yfinance JSON cache
```

---

## Key design decisions

- **Tickers stored plain** (`HDFCBANK`, not `HDFCBANK.NS`) in markdown.
  The `.ns_ticker` property on `Holding` / `WatchlistItem` appends `.NS`.
  Use `.BO` suffix explicitly for BSE-only tickers.

- **Markdown files are fully managed** by the tool. `write_portfolio` / `write_watchlist`
  overwrite the entire file on every write. Do not add extra markdown sections to
  `portfolio.md`, `watchlist.md`, or `transactions.md`.

- **`transactions.md` is append-only.** Never delete rows.

- **`entry_yield_pct`** on `Holding` is the trailing yield captured at buy time.
  It defaults to `0.0` for backward compatibility with old files missing the column.
  The `review` command skips the yield-drop check when `entry_yield_pct == 0`.

- **Goal progress** in `status` = current market value (shares × live price) vs. target,
  not cost basis.

- **Cache** lives in `.cache/market_data.json` (gitignored). Each ticker entry has a
  `fetched_at` ISO timestamp. `_is_stale()` checks against `cache_expiry_hours`.
  Pass `force_refresh=True` to bypass.

- **Graceful degradation**: if yfinance fails for a ticker, `QuoteResult.error` is set
  and `is_valid` returns `False`. All commands handle this without crashing — they mark
  the affected holding with ⚠ / ❌ and exclude it from numeric totals.

---

## Development conventions

- **Python ≥ 3.10.** Uses `X | Y` union types and `match` where appropriate.
- **Immutable updates**: never mutate a `Holding` / `WatchlistItem` / `Transaction`
  in place. Create a new instance (see `_replace()` helper in `review.py`).
- **No silent failures**: every except clause either re-raises or sets an error field.
- **Tests mock yfinance** via `patch("shared.market_data.yf.Ticker")` or
  `patch("dividend.commands.<cmd>.fetch_quotes")`. No live network calls in tests.
- **CliRunner** (`click.testing`) is used for all command tests. Pass
  `catch_exceptions=False` so assertion errors surface clearly.

---

## Running locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
pip install -r requirements-dev.txt   # adds pytest

divvy --help
pytest tests/ -v
```

Always run from the **repo root** — config paths are relative to it.

---

## AI skill system

### Architecture
```
shared/llm/
  runner.py              # LLMRunner ABC + LLMResponse dataclass + create_runner() factory
  skill.py               # load_skill(dir) → SkillDef;  render_prompt(skill, ctx) → str
  providers/
    anthropic.py         # AnthropicRunner  (optional dep: pip install anthropic)
    openai.py            # OpenAIRunner     (optional dep: pip install openai)
    ollama.py            # OllamaRunner     (no extra dep; needs `ollama serve`)

dividend/skills/<name>/
  skill.yaml             # name, system_prompt, inputs[], output.max_tokens, compatible_models
  prompt.md              # Jinja2 template; uses StrictUndefined (missing vars raise)
  context.py             # gather(cfg, **kwargs) → dict — all data assembly lives here
```

### Adding a new skill
1. Create `dividend/skills/<snake_name>/` with `skill.yaml`, `prompt.md`, `context.py`
2. `skill_name.replace("-","_")` must match the directory name
3. No CLI changes needed — `ai_cmd` auto-discovers skills by directory name

### Key conventions
- `context.py` is responsible for all I/O (portfolio reads, yfinance calls). The skill infra
  (`runner.py`, `skill.py`) is pure — no file I/O, no network.
- Providers are imported lazily inside `create_runner()` so missing optional deps don't
  break unrelated commands.
- Test providers by injecting mocks via `patch.dict(sys.modules, {"anthropic": mock_mod})`
  followed by `importlib.reload(mod)` — avoids needing the real SDK installed in CI.

---

## Adding a new command to divvy

1. Write the implementation in `dividend/commands/<name>.py`
2. Export a Click command named `<name>_cmd`
3. Register it in `dividend/cli.py` (`cli.add_command(...)`)
4. Add tests in `tests/test_dividend_commands.py`

## Adding a new tool (e.g. `trade/`)

1. Mirror the `dividend/` structure under `trade/`
2. Put reusable logic in `shared/`
3. Add entry point in `pyproject.toml`: `tradr = "trade.cli:main"`
4. `pip install -e .`
