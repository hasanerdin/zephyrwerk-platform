# Zephyrwerk Energy Analytics Platform

Production-grade data engineering platform ingesting live German electricity market data (SMARD / Bundesnetzagentur), loading it into PostgreSQL, transforming it with dbt, forecasting prices and renewable generation with XGBoost, serving predictions via a FastAPI REST API, and visualising results in a Streamlit dashboard — deployed on AWS.

Built as a portfolio project demonstrating end-to-end data platform engineering: from raw API ingestion to ML inference to cloud deployment.

---

## Architecture

**Stack:** Python · dbt Core · PostgreSQL · FastAPI · Streamlit · XGBoost · AWS (S3, RDS, ECS Fargate, Step Functions, EventBridge) · Docker · GitHub Actions

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                             │
│         SMARD API                    Open-Meteo API             │
│   (generation, consumption,    (historical + forecast weather:  │
│    prices, neighbour prices)      wind, solar, temperature)     │
└────────────────────┬────────────────────────┬───────────────────┘
                     │                        │
                     ▼                        ▼
              ingestion/smard_client.py   ingestion/weather_client.py
                     │                  (historical + forecast fetch)
                     └───────────┬────────────┘
                                 │ raw JSON → Parquet
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AWS S3 — RAW LAYER                           │
│  s3://zephyrwerk-data-lake/raw/smard/year=YYYY/month=MM/        │
│  s3://zephyrwerk-data-lake/raw/weather/year=YYYY/month=MM/      │
│  s3://zephyrwerk-data-lake/raw/weather_forecast/ (day-ahead)    │
└─────────────────────────────┬───────────────────────────────────┘
                              │ ingestion/loader.py
                              │ (Parquet → UPSERT into Postgres)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│           AWS RDS PostgreSQL — raw schema                       │
│  smard_generation, smard_prices, smard_neighbour_prices,        │
│  weather, weather_forecast                                     │
└─────────────────────────────┬───────────────────────────────────┘
                              │ dbt Core — staging models (views)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│           AWS RDS PostgreSQL — staging schema                   │
│  stg_smard_generation, stg_smard_prices,                        │
│  stg_smard_neighbour_prices, stg_weather, stg_weather_forecast  │
└─────────────────────────────┬───────────────────────────────────┘
                              │ dbt Core — analytics models (tables)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│           AWS RDS PostgreSQL — analytics schema                 │
│  dim_date                                                       │
│  fct_energy_generation       fct_market_prices                  │
│  fct_price_spreads           fct_weather_features               │
│  fct_ml_features  ← training data: real observed values only    │
│  fct_weather_forecast_features ← day-ahead forecast, used only  │
│                                   at inference time, never in   │
│                                   training (leak-free by design) │
└──────────────┬──────────────────────────┬───────────────────────┘
               │                          │
               ▼                          ▼
┌──────────────────────┐     ┌────────────────────────────────────┐
│     ML MODELS         │     │     FastAPI — AWS ECS Fargate      │
│  3 separate XGBoost   │     │  GET  /health                      │
│  models: price, wind,  │     │  GET  /energy/generation           │
│  solar — each its own │     │  GET  /energy/prices               │
│  sklearn Pipeline     │     │  GET  /energy/summary              │
│                       │     │  POST /predict/price               │
│  s3://.../models/     │     │  POST /predict/generation          │
│    price_forecast/    │     │                                    │
│    wind_forecast/     │     │  OpenAPI docs auto-generated       │
│    solar_forecast/    │     └──────────────────┬─────────────────┘
└──────────────────────┘                        ▼
                              ┌──────────────────────────────────┐
                              │  Streamlit — AWS ECS Fargate     │
                              │  Historical Overview             │
                              │  Market Monitor                  │
                              │  Forecast Viewer                 │
                              └──────────────────────────────────┘

CI/CD:         GitHub Actions → Docker build → ECR push → ECS deploy
Orchestration: EventBridge → Step Functions → ECS Tasks (daily 06:00 UTC)
Monitoring:    AWS CloudWatch (logs + cost alerts)
```

**Three-schema design.** `loader.py` is the bridge between the S3 data lake and PostgreSQL — dbt does not read from S3 directly. The `raw` schema mirrors S3 Parquet and is fully reloadable. `staging` is dbt views (no storage cost, always fresh). `analytics` is dbt tables (pre-computed for query performance). The five historical fact tables share hourly grain and identical row counts (65,208 hours over the 2019–2026 window); `fct_weather_forecast_features` is intentionally separate — it holds only the rolling day-ahead forecast horizon, kept structurally isolated from training data so the ML models never see forecast values during training.

**Forecast/historical separation.** A live prediction request needs tomorrow's weather, but the model was trained only on real, observed values. Rather than have the API call Open-Meteo directly, a dedicated daily ingestion path fetches the day-ahead forecast, and it flows through its own raw → staging → analytics tables, joined into the feature set only at inference time. This keeps the API's only job "read Postgres" (same env-var-driven code path locally and in AWS) and keeps training data 100% free of forecast-vs-actual leakage.

---

## Phases

| Phase | Scope | Status |
|---|---|---|
| 1 — Ingestion | SMARD + Open-Meteo clients, S3 raw layer, LocalStack | ✅ Complete · `v0.1.0` |
| 2 — EDA | Jupyter notebooks, energy mix analysis, findings | ✅ Complete · `v0.2.0` |
| 3 — dbt | Loader, raw/staging/analytics schemas, dbt tests, Dockerfiles | ✅ Complete · `v0.3.0` |
| 4 — ML | XGBoost price + generation (wind/solar) forecasting, model registry | ✅ Complete · `v0.4.0` |
| 5 — API | FastAPI service, all endpoints, day-ahead prediction pipeline, pytest suite | ✅ Complete · `v0.5.0` |
| 6 — Dashboard | Streamlit multipage dashboard, Docker Compose | 🔜 Not started |
| 7 — AWS | Full cloud deployment, CI/CD, v1.0.0 release | 🔜 Not started |

---

## Key EDA Findings (Phase 2)

Seven years of German electricity data (2019–2025, ~2.6M hourly rows) across 22 SMARD signals and 4 weather locations.

### Energy Mix Evolution

- **Germany became a net electricity importer in 2023.** The nuclear phase-out removed ~8 GW of baseload; renewable additions (+4 GW) only partially offset it. Germany stabilised at ~3 GW continuous net import.
- **Renewable share grew from 43.6% to 60.2%**, but ~80% of the 2023 jump came from nuclear leaving the denominator, not new renewable capacity.
- **Solar is the only renewable source that grew consistently** (+76% over the window, 4.8 → 8.4 GW average). Wind onshore has declined two years running.
- **Coal's structural decline only began in 2023** — the 2022 gas crisis kept fossil generation elevated because coal was suddenly cheaper than gas.

### Price Dynamics

- **Three structurally distinct price regimes:** pre-crisis (mean €59/MWh), 2022 gas crisis (mean €216/MWh, peak €871), post-nuclear (mean €85/MWh with extremes of −€500 to +€936).
- **Negative prices grew from 1.6% (2021) to 6.5% (2025)** of hours — now a structural feature of the renewable-heavy grid, concentrated in spring/summer midday solar surplus hours.
- **Residual load is the primary price driver** (Pearson r = 0.831). The empirical supply curve shows three zones: negative prices at <15 GW, competitive pricing at 15–40 GW, and steep scarcity pricing above ~40 GW.
- **The duck curve is visible in German prices**: summer midday prices dip near zero or negative; winter morning prices peak as high consumption meets low solar and minimum wind.

### Consumption Patterns

- **Industrial demand destruction, not residential.** Total consumption fell ~5 GW from the 2021 peak (57.6 GW) to 2025 (53.0 GW). The weekday–Sunday load gap shrunk from 12.4 GW to 10.3 GW — a clear industrial signature.
- **Germany's highest-stress grid period is early January/February, not Christmas** — December consumption drops due to industrial shutdown.
- **Residual load volatility grew 56%** even as its mean shrank 22%, which is the structural cause of persistent European price volatility.

### Neighbour Price Spreads

- **Germany is geographically split:** structurally cheaper than Poland (+€29/MWh average spread) and France (+€19/MWh); more expensive than Alpine zones (Austria −€5.50, Switzerland −€5.23).
- **Switzerland and France carry the most predictive spread information** for next-hour DE/LU prices (lead-1h Pearson r = 0.538, 0.501), reflecting Alpine hydro storage and French nuclear as independent supply signals.
- **Danish spreads are weak predictors** despite high level-correlation — both markets are wind-coupled, so the spread collapses to noise.

> Full analysis, charts, and downstream recommendations: [`notebooks/eda/FINDINGS.md`](notebooks/eda/FINDINGS.md)

---

## ML Model Results (Phase 4)

Three separate XGBoost models — price, wind generation, solar generation — each its own sklearn `Pipeline`, evaluated against a naive persistence baseline (predict "same as this time yesterday").

| Model | MAE | vs. baseline | R² | Notes |
|---|---|---|---|---|
| **Price** (€/MWh) | 18.10 | 46% lower (baseline 33.53) | — | 0.81 deviation directional accuracy — correctly calls whether a price will beat yesterday's same hour 81% of the time |
| **Wind** (MW) | 3,121 | 65% lower (baseline 8,840) | 0.82 | Genuinely chaotic signal (turbulence); peak-hour MAE runs ~65% above average |
| **Solar** (MW) | 1,375 | 47% lower (baseline 2,583) | 0.97 | Dominated by deterministic solar geometry; model under-predicts summer noon peaks by 10–12% (documented, not corrected — a physical limit, not a bug) |

All three models beat their cross-validation mean by less than one standard deviation on the final holdout set — no overfitting. Full methodology, leakage-prevention design, and metric selection reasoning: [`PHASE_4_OUTPUTS.md`](PHASE_4_OUTPUTS.md).

---

## API (Phase 5)

FastAPI service with dependency injection + repository pattern, auto-generated OpenAPI docs at `/docs`, and a graceful-degradation contract: missing input data returns nullable fields with `200`, a missing/unavailable model returns `503` rather than crashing.

The hardest part of this phase was serving day-ahead predictions correctly: the models need real historical lag features (price 24h/168h ago, etc.) that only exist in Postgres, plus tomorrow's weather forecast, which is ingested once daily and kept in its own table — fully isolated from training data — rather than the API calling external weather APIs per request. A cascading lag-fallback (24h → 48h → 168h) handles the case where a short-horizon lag reference is itself still in the future. `target_date` is constrained to today/tomorrow, matching the horizon the models were actually trained and evaluated for.

175 tests, `ruff`-clean, containerized (`api/Dockerfile`), CI running pytest + lint on every PR.

---

## Local Setup

### Prerequisites

- **Python 3.12** managed via [`uv`](https://docs.astral.sh/uv/) — pinned to 3.12 because `dbt-core`'s `mashumaro` dependency fails on 3.14
- **Docker** — runs LocalStack (S3 emulator) and PostgreSQL locally
- **Make** — the commands below are `make` targets (see the `Makefile`); run `make help` for the full list

### Install

```bash
git clone https://github.com/hasanerdin/zephyrwerk-platform.git
cd zephyrwerk-platform

uv venv --python 3.12
uv sync --extra dev
```

### Configure environment

```bash
cp .env.example .env
# Edit .env — all required keys are documented in .env.example
```

Key variables:

| Variable | Local default | Purpose |
|---|---|---|
| `AWS_ENDPOINT_URL` | `http://localhost:4566` | Points boto3 at LocalStack; leave empty in production |
| `ZEPHYRWERK_AWS_BUCKET_NAME` | `zephyrwerk-data-lake` | S3 bucket |
| `ZEPHYRWERK_RDS_HOST` | `localhost` | PostgreSQL host |
| `ZEPHYRWERK_RDS_PORT` | `5432` | PostgreSQL port |
| `ZEPHYRWERK_RDS_DB` | `zephyrwerk` | Database name |
| `ZEPHYRWERK_RDS_USER` | `zephyrwerk` | App-level DB role — not the container's superuser, see below |

### Start local infrastructure

```bash
make infra-up
```

Starts LocalStack (S3 emulation, pinned to 3.8 — LocalStack 2026.x
requires a paid license for S3) and PostgreSQL, waits for LocalStack to
report healthy, and creates the `zephyrwerk-data-lake` bucket.
PostgreSQL's container mounts `db/init.sql`, which creates the raw,
staging, analytics schemas, all five raw tables (including
`weather_forecast`), and the `zephyrwerk` app role. Run `make
localstack-up` / `make postgres-up` individually if you only need one;
see the `Makefile` for the underlying `docker run` commands.

> If Postgres already existed before `weather_forecast` or the
> `zephyrwerk` role were added to `init.sql`, the mounted script only
> runs on first container init. Apply it manually instead:
> `docker exec -i zephyrwerk-postgres psql -U postgres -d zephyrwerk < db/init.sql`
> — safe to re-run, every statement either uses `IF NOT EXISTS` or
> checks first. The bucket creation in `make localstack-up` is also
> safe to re-run: `s3 mb` on an existing bucket is a no-op error.

### dbt one-time setup

```bash
make dbt-deps
make dbt-seed
```

Do this before the first pipeline run, not after. `run_pipeline.py`'s
`run_dbt()` runs `dbt run`/`dbt test` automatically after every
`--mode daily` and `--mode historical` ingestion (see
`run_daily_pipeline()` / `run_historical_pipeline()`) — and that `dbt
run` fails immediately if `dbt_utils` isn't installed or the German
public holidays seed hasn't been loaded yet (`dim_date` joins against
it). `--mode weekly` skips dbt entirely — it only retrains models from
data already in `fct_ml_features`.

Both targets wrap `dotenv run -- dbt ... --project-dir dbt
--profiles-dir dbt`: unlike `run_pipeline.py`, the `dbt` CLI doesn't
read `.env` on its own — `dbt/profiles.yml` pulls credentials via
`env_var(...)`, which only sees real OS environment variables — so
`dotenv run --` (from `python-dotenv`, already a project dependency)
loads `.env` for that one command. Going through `make` also means it
works regardless of your shell's current directory.

> To iterate on dbt models directly without re-running ingestion, use
> `make dbt-run` / `make dbt-test`.

### Run the ingestion pipeline

```bash
make pipeline-historical START=2019-01-01                  # one-time, full backfill through yesterday
make pipeline-historical START=2019-01-01 END=2025-12-31    # or bound it explicitly
make pipeline-daily                                         # yesterday's SMARD + weather, 8-day forecast
make pipeline-weekly                                        # retrains + republishes all 3 models
```

`START` is required; `END` is optional and defaults to yesterday, since
no future SMARD data can ever exist. `pipeline-weekly` retrains from
whatever's currently in `fct_ml_features` and is deliberately
independent of `pipeline-daily` (separate failure domain) — in
production these are two separate EventBridge/Step Functions triggers,
sequenced by time (daily at 06:00 UTC, weekly at 07:00 UTC on Mondays)
so weekly always sees that morning's fresh data. Locally, run
`pipeline-daily` first if you want the same guarantee.

The pipeline is idempotent: re-running a date range skips Parquet files already in S3, and the loader upserts into Postgres so SMARD value revisions are picked up correctly. Forecast weather is re-fetched daily and superseded by the real observed value once that day's normal ingestion runs — the loader's upsert naturally overwrites forecast with actual, no reconciliation step needed.

### Run EDA notebooks

```bash
uv run jupyter lab notebooks/eda/
```

Notebooks in order: `00_data_audit` → `01_energy_mix_history` → `02_renewable_seasonality` → `03_consumption_patterns` → `04_price_dynamics` → `05_price_spreads`

### Train / retrain the ML models

```bash
python ml/train_price_model.py
python ml/train_generation_model.py   # trains both wind and solar
```

Both scripts read `fct_ml_features` from Postgres, train, evaluate against
a persistence baseline, and publish to the S3 model registry (`latest/` +
a timestamped `archive/` copy, plus a `metadata.json` sidecar). The API
must have at least one successfully-published model per target before
`/predict/*` will return anything other than a `503`.

### Run the API

```bash
uv run uvicorn api.main:app --reload
```

Then visit `http://127.0.0.1:8000/docs` for interactive OpenAPI docs, or
check `http://127.0.0.1:8000/health` to confirm DB connectivity and that
all three models loaded successfully from S3.

### Run the dashboard

```bash
uv run streamlit run dashboard/app.py
```

Visit `http://localhost:8501`. Needs the API running (`ZEPHYRWERK_DASHBOARD_API_URL`, default `http://localhost:8000`) — see above.

### Run API + dashboard with Docker Compose

```bash
docker compose up --build
```

Requires `.env` (see "Configure environment" above) — both services load it via `env_file`, so no credentials are duplicated into `docker-compose.yml` itself. Builds `api/Dockerfile` and `dashboard/Dockerfile` and runs both containers on one network — the dashboard reaches the API at `http://api:8000` (Compose's built-in service-name DNS), not `localhost`. API at `http://localhost:8000`, dashboard at `http://localhost:8501`.

`docker-compose.yml` deliberately does **not** include Postgres or LocalStack — those stay the long-lived `make infra-up` containers (see above), reached from inside the `api` container via `host.docker.internal` rather than `localhost`, since `localhost` inside a container refers to the container itself. Run `make infra-up` first if they're not already up. `docker-compose.yml` overrides `ZEPHYRWERK_RDS_HOST` and `AWS_ENDPOINT_URL` on top of `.env` for this reason — `.env`'s `localhost` is correct for native processes, not containers.

### Run tests

```bash
uv run pytest
```

---

## Data Sources

- **SMARD** (Bundesnetzagentur) — 12 generation signals, total consumption, residual load, DE/LU day-ahead prices, and 8 neighbour-zone prices · CC BY 4.0
- **Open-Meteo** — Historical (ERA5 reanalysis) and forecast weather for 4 German regions co-located with Zephyrwerk's wind and solar assets · Free for non-commercial use

---

## Author

Hasan Erdin — Data Engineer & Applied Data Scientist, Munich
[GitHub](https://github.com/hasanerdin) · [LinkedIn](https://linkedin.com/in/hasanerdin)