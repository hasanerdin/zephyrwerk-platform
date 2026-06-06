# Zephyrwerk GmbH — Energy Analytics Platform
### Master Reference Document
> This document is the single source of truth for the entire project.
> It must be shared at the start of every phase chat to maintain context.
> Version: 1.4 | Status: Planning Complete

---

## Table of Contents
1. [Company Brief](#1-company-brief)
2. [Business Problem](#2-business-problem)
3. [Stakeholders](#3-stakeholders)
4. [Platform Goals](#4-platform-goals)
5. [Data Sources](#5-data-sources)
6. [Architecture](#6-architecture)
7. [Tech Stack Decisions](#7-tech-stack-decisions)
8. [AWS Infrastructure](#8-aws-infrastructure)
9. [ML Models](#9-ml-models)
10. [API Design](#10-api-design)
11. [Dashboard Design](#11-dashboard-design)
12. [Git Strategy](#12-git-strategy)
13. [Phase Roadmap](#13-phase-roadmap)
14. [Cost Management](#14-cost-management)
15. [Naming Conventions](#15-naming-conventions)
16. [Development Approach](#16-development-approach)

---

## 1. Company Brief

**Zephyrwerk GmbH** is a Munich-based renewable energy producer operating a portfolio of onshore wind farms across Brandenburg and Schleswig-Holstein, and solar parks in Bavaria and Baden-Württemberg. Founded in 2012, the company sells electricity on the German day-ahead wholesale market (EPEX SPOT) and holds supply contracts with several large industrial clients in the automotive and chemical sectors.

The company has grown rapidly since 2020, adding new generation capacity each year. However, its data infrastructure has not kept pace with its operational complexity.

---

## 2. Business Problem

Zephyrwerk's operations team is making critical decisions without adequate data support:

- No unified view of how Germany's grid produces and consumes energy over time
- Cannot reliably identify when renewable surplus occurs vs. when demand peaks
- Supply chain decisions are made from weekly Excel exports — slow and error-prone
- No predictive capability for day-ahead electricity prices, causing missed opportunities on the wholesale market
- No single source of truth across generation, consumption, pricing, and weather signals

**The direct business cost:** Zephyrwerk cannot optimally time its market sales. If the day-ahead price will spike tomorrow afternoon, the operations team needs to know today to plan capacity. Currently they cannot do this.

**The mandate:** Build a production-grade data platform from scratch that ingests live German electricity market data, transforms it into a clean analytics layer, serves predictions via a REST API, and powers a business intelligence dashboard.

---

## 3. Stakeholders

| Stakeholder | Need | Touchpoint |
|---|---|---|
| Operations Manager | Daily generation overview, renewable share vs. seasonal average | Streamlit dashboard |
| Supply Chain Team | Price forecasts, surplus/deficit signals for capacity planning | FastAPI `/predict` endpoints + dashboard |
| CTO / Management | KPI trends, year-over-year comparisons, platform reliability | Streamlit summary page |
| External Systems | Automated price and generation forecasts for scheduling tools | REST API (consumed programmatically) |

---

## 4. Platform Goals

The platform is structured in three capability layers:

### Layer 1 — Historical Intelligence ("Show us what happened")
Understand Germany's energy production history: which sources dominate, how consumption patterns shift across seasons, how the energy mix has evolved as renewables scaled from 2019 to present.

### Layer 2 — Operational Monitoring ("Show us what's happening now")
A scheduled pipeline that ingests fresh SMARD data daily, keeps the data warehouse current, and powers a dashboard the ops team checks every morning. Answers: Is today's renewable output above or below seasonal average? Is the grid stressed?

### Layer 3 — Predictive Intelligence ("Tell us what will happen")
Two ML models:
- **Day-ahead electricity price forecasting** (€/MWh) — direct supply chain ROI
- **Renewable generation forecasting** (MW) — wind + solar output for next 24 hours

---

## 5. Data Sources

### Primary — SMARD (Bundesnetzagentur)
**URL:** https://www.smard.de  
**API Base:** `https://www.smard.de/app/chart_data/{filter}/{region}/`  
**License:** CC BY 4.0 — free to download, store, and use  
**Resolution:** Quarter-hourly and hourly available  
**History:** 2019 to present  
**Update frequency:** Near real-time (hourly updates)

Signals ingested:

> ✅ **VERIFIED** against the official `smard.api.bund.dev` parameter list. Region code and resolution confirmed below.

**Region:** `DE-LU` (market area DE/LU, valid from 01.10.2018 — matches our history window). For generation/consumption volumes, `DE` is also valid; use `DE-LU` for prices since the day-ahead market is the DE/LU bidding zone.

**Resolution:** `hour` (hourly) for the analytical base. `quarterhour` available if finer granularity is wanted later.

| Signal | SMARD Filter ID | Unit | German label |
|---|---|---|---|
| Wind Onshore generation | 4067 | MW | Wind Onshore |
| Wind Offshore generation | 1225 | MW | Wind Offshore |
| Solar (Photovoltaik) generation | 4068 | MW | Photovoltaik |
| Biomass generation | 4066 | MW | Biomasse |
| Hydropower generation | 1226 | MW | Wasserkraft |
| Pumped storage generation | 4070 | MW | Pumpspeicher |
| Natural Gas generation | 4071 | MW | Erdgas |
| Hard Coal generation | 4069 | MW | Steinkohle |
| Brown Coal generation | 1223 | MW | Braunkohle |
| Nuclear generation | 1224 | MW | Kernenergie |
| Other conventional | 1227 | MW | Sonstige Konventionelle |
| Other renewable | 1228 | MW | Sonstige Erneuerbare |
| Total grid consumption (load) | **410** | MW | Stromverbrauch: Gesamt (Netzlast) |
| Residual load | 4359 | MW | Residuallast |
| Day-ahead electricity price | 4169 | €/MWh | Marktpreis: Deutschland/Luxemburg |

**Optional — forecasted generation** (useful as ML baselines / features for the generation model):

| Signal | Filter ID | German label |
|---|---|---|
| Forecast: Wind Onshore | 123 | Prognostizierte Erzeugung: Onshore |
| Forecast: Wind Offshore | 3791 | Prognostizierte Erzeugung: Offshore |
| Forecast: Photovoltaik | 125 | Prognostizierte Erzeugung: Photovoltaik |
| Forecast: Wind + PV combined | 5097 | Prognostizierte Erzeugung: Wind und PV |
| Forecast: Total | 122 | Prognostizierte Erzeugung: Gesamt |

> ⚠️ **Cross-border flows correction:** The previously planned "cross-border export balance" (filter `4075`) **does not exist** in the SMARD chart_data API. This endpoint exposes *market prices per neighbouring country* (e.g. France `254`, Netherlands `256`, Poland `257`, Austria `4170`, Switzerland `259`) and forecasted generation — but **not physical cross-border flow volumes**. 
> **DECISION (chosen): option (b) — price-spread analysis.** Instead of physical flow volumes, the platform ingests day-ahead prices for neighbouring bidding zones and analyses price spreads (DE/LU vs France, Netherlands, Poland, Austria, Switzerland). This reuses the same SMARD API with no new source, and tells a stronger supply-chain story: it directly answers when German power is cheaper or more expensive than neighbours' — the basis for export-timing and arbitrage decisions.

**Neighbour price filter IDs used:**

| Zone | Filter ID |
|---|---|
| Austria | 4170 |
| France | 254 |
| Netherlands | 256 |
| Poland | 257 |
| Switzerland | 259 |
| Czechia | 261 |
| Denmark 1 | 252 |
| Denmark 2 | 253 |

The spread is computed as `neighbour_price − DE/LU_price` (filter `4169`) per hour.

### Secondary — Open-Meteo
**URL:** https://open-meteo.com  
**License:** Free for non-commercial use  
**Purpose:** Weather features for ML models  

> ⚠️ **NOTE (affects Phase 1):** Open-Meteo serves *forecast* and *recent* data through one API, but historical weather back to 2019 comes from a **separate endpoint — the Historical Weather API (ERA5 reanalysis archive)**. For backfilling training data you must use the Historical Weather API; for the daily production run you use the Forecast API. These are two different base URLs and the weather client must handle both. Verify date coverage and rate limits for each in Phase 1.

Signals ingested for key German regions (Berlin, Munich, Hamburg, Frankfurt):

| Signal | Purpose |
|---|---|
| Wind speed at 100m | Wind generation feature |
| Wind direction | Wind generation feature |
| Solar irradiance (shortwave) | Solar generation feature |
| Cloud cover | Solar generation feature |
| Temperature | Consumption feature (heating/cooling demand) |

### Ingestion Modes

The platform has **two distinct ingestion modes** with different code paths. The ingestion clients must support both:

| Mode | When | Source coverage | Trigger |
|---|---|---|---|
| **Backfill (historical)** | One-time, during Phase 1 | 2019 → present (full history) | Run manually |
| **Incremental (daily)** | Ongoing, in production | Yesterday's data only | EventBridge daily |

Both modes write to the same S3 raw layer with the same partitioning. The difference is the date range requested and idempotency: the incremental run must safely overwrite/upsert a day that may have been partially ingested before (SMARD revises recent data). Design ingestion functions to accept a `start_date` / `end_date` parameter so the same code serves both modes.

---

## 6. Architecture

### Full System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                             │
│         SMARD API                    Open-Meteo API             │
│   (generation, consumption,       (wind, solar, temperature)    │
│    prices, neighbour prices)                                    │
└────────────────────┬────────────────────────┬───────────────────┘
                     │                        │
                     ▼                        ▼
              ingestion/smard_client.py   ingestion/weather_client.py
                     │                        │
                     └───────────┬────────────┘
                                 │ raw JSON / CSV
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AWS S3 — RAW LAYER                           │
│                                                                 │
│  s3://zephyrwerk-data-lake/raw/smard/year=YYYY/month=MM/        │
│  s3://zephyrwerk-data-lake/raw/weather/year=YYYY/month=MM/      │
│                                                                 │
│  Format: Parquet, partitioned by year/month                     │
│  Retention: indefinite (source of truth)                        │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              │ dbt Core (runs as ECS Task)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              AWS RDS PostgreSQL — ANALYTICS LAYER               │
│                                                                 │
│  schema: staging                                                │
│    stg_smard_generation                                         │
│    stg_smard_prices                                             │
│    stg_weather                                                  │
│                                                                 │
│  schema: analytics                                              │
│    fct_energy_generation    (hourly generation by source)       │
│    fct_market_prices        (prices + rolling averages)         │
│    fct_weather_features     (aligned weather signals)           │
│    fct_ml_features          (joined feature table for ML)       │
│    dim_date                 (time dim + holidays + seasons)     │
└──────────────┬──────────────────────────┬───────────────────────┘
               │                          │
               ▼                          ▼
┌──────────────────────┐     ┌────────────────────────────────────┐
│     ML MODELS        │     │     FastAPI — AWS ECS Fargate       │
│  (ECS Task,          │     │                                    │
│   scheduled weekly)  │     │  GET  /health                      │
│                      │     │  GET  /energy/generation           │
│  price_forecast.pkl  │     │  GET  /energy/prices               │
│  generation_         │     │  GET  /energy/summary              │
│    forecast.pkl      │     │  POST /predict/price               │
│       │              │     │  POST /predict/generation          │
│       │ stored in S3 │     │                                    │
│       ▼              │     │  OpenAPI docs auto-generated       │
│  S3 Model Registry   │     └──────────────────┬─────────────────┘
│  s3://zephyrwerk-    │                         │
│  data-lake/models/   │                         │
└──────────────────────┘                         │
                                                 ▼
                              ┌──────────────────────────────────┐
                              │  Streamlit — AWS ECS Fargate     │
                              │                                  │
                              │  Page 1: Historical Overview     │
                              │  Page 2: Market Monitor          │
                              │  Page 3: Forecast Viewer         │
                              └──────────────────────────────────┘

─────────────────────────────────────────────────────────────────
CI/CD:  GitHub Actions → Docker build → ECR push → ECS deploy
─────────────────────────────────────────────────────────────────
ORCHESTRATION:
  Local:       orchestration/run_pipeline.py (simple Python script)
  Production:  EventBridge Scheduler → Step Functions → ECS Tasks
─────────────────────────────────────────────────────────────────
MONITORING:   AWS CloudWatch (logs + cost alerts)
─────────────────────────────────────────────────────────────────
```

### Data Flow (Daily Production Run)

```
06:00 UTC — EventBridge triggers Step Functions state machine
  │
  ├─► Step 1: ECS Task — ingestion container
  │     pulls yesterday's SMARD + weather data → writes to S3 raw
  │
  ├─► Step 2: ECS Task — dbt container
  │     runs dbt run + dbt test → writes to RDS PostgreSQL
  │
  ├─► Step 3: ECS Task — ML training container (weekly only)
  │     retrains models on fresh data → writes .pkl to S3
  │
  └─► Step 4: CloudWatch logs success/failure → alert on failure
```

---

## 7. Tech Stack Decisions

| Layer | Technology | Decision Rationale |
|---|---|---|
| Cloud provider | **AWS** | Dominant in German enterprise market (Siemens, BMW, Bosch, E.ON). Free tier sufficient for portfolio project. |
| Raw storage | **AWS S3** (Parquet) | Cheap, durable, industry-standard data lake layer. Parquet for efficient columnar reads. |
| Analytics storage | **AWS RDS PostgreSQL** | dbt-native adapter, FastAPI-compatible via SQLAlchemy, no Athena/Glue complexity. |
| Transformations | **dbt Core** | Open source, Docker-friendly, identical code runs locally and in production via env var switching. |
| Orchestration (local) | **Python script** (`orchestration/run_pipeline.py`) | Simple, no overhead, sufficient for development. |
| Orchestration (cloud) | **EventBridge + Step Functions + ECS Tasks** | Serverless, cost-effective, production-grade. No MWAA cost (~$300/month saved). |
| ML framework | **scikit-learn + XGBoost** | Sufficient for tabular time-series forecasting. Serialized with joblib. |
| Model registry | **AWS S3** | Simple, boto3-native. No MLflow server to maintain. |
| API framework | **FastAPI** | Already in Hasan's stack. Dependency injection + repository pattern. Auto OpenAPI docs. |
| Dashboard | **Streamlit** | Already in Hasan's stack. Multipage, Plotly charts, cached API client. |
| Containerization | **Docker** (per-service Dockerfiles) | Local dev parity. Images pushed to ECR for production. Docker Compose used only in Phases 6 (local) and removed in Phase 7 — see Section 16. |
| CI/CD | **GitHub Actions → ECR → ECS** | Industry standard. Free for public repos. |
| Monitoring | **AWS CloudWatch** | Native AWS. Free tier covers logs and basic metrics. |

### Explicitly Rejected Alternatives

| Technology | Reason Rejected |
|---|---|
| GCP | Less relevant for German enterprise job market |
| Snowflake | Additional cost layer on top of AWS. Overkill for this scale. |
| dbt Cloud | Abstracts away infrastructure. Less learning value. Limits portability. |
| Apache Airflow | MWAA costs ~$300/month. Docker Compose Airflow is heavy for local dev. Simple Python orchestration is sufficient. |
| AWS Athena / Glue | Adds complexity without proportional benefit at this scale. RDS PostgreSQL is simpler and faster. |
| AWS MWAA | Too expensive for a portfolio project. |

---

## 8. AWS Infrastructure

### AWS Region

**All resources are provisioned in `eu-central-1` (Frankfurt).**

Rationale: German source data, German target employers, lowest latency for the use case, and clean GDPR optics. Using the Frankfurt region is an intentional signal to German hiring managers.

### Resource Naming Convention

Resources follow the pattern `zephyrwerk-{resource-type}` with an optional `-{qualifier}` (e.g. environment) where it adds clarity. Note: the S3 bucket name must be **globally unique across all AWS accounts**, so it carries a region suffix (see note below).

> ⚠️ **NOTE (verify in Phase 7):** `zephyrwerk-data-lake` is a generic name and may already be taken globally. Plan to use a unique suffix such as `zephyrwerk-data-lake-eucentral1` or a short random suffix. Once chosen, the final bucket name must be updated consistently everywhere in this document and in all `.env` files.

| Resource | Name | Notes |
|---|---|---|
| S3 Bucket | `zephyrwerk-data-lake` *(may need unique suffix — see note)* | Single bucket, prefixes separate layers |
| RDS Instance | `zephyrwerk-rds-prod` | PostgreSQL 15, `db.t3.micro` (free tier) |
| ECS Cluster | `zephyrwerk-cluster` | Fargate launch type |
| ECS Service (API) | `zephyrwerk-api-service` | FastAPI container |
| ECS Service (Dashboard) | `zephyrwerk-dashboard-service` | Streamlit container |
| ECR Repo (API) | `zephyrwerk-api` | Docker image registry |
| ECR Repo (Dashboard) | `zephyrwerk-dashboard` | Docker image registry |
| ECR Repo (Ingestion) | `zephyrwerk-ingestion` | Docker image registry |
| ECR Repo (dbt) | `zephyrwerk-dbt` | Docker image registry |
| ECR Repo (ML) | `zephyrwerk-ml` | Docker image registry |
| Step Functions | `zephyrwerk-daily-pipeline` | State machine for daily run |
| EventBridge Rule | `zephyrwerk-daily-trigger` | Cron: `0 6 * * ? *` (06:00 UTC) |
| IAM Role (ECS) | `zephyrwerk-ecs-task-role` | Least-privilege S3 + RDS access |
| Secrets (RDS creds) | `zephyrwerk/rds/credentials` | AWS Secrets Manager (see Section 8.1) |
| CloudWatch Log Group | `/zephyrwerk/pipeline` | All ECS Task logs |

### 8.1 Secrets Management

Database passwords and any sensitive credentials are **never** stored as plain environment variables in production.

| Environment | Secret handling |
|---|---|
| Local development | `.env` file (gitignored) — acceptable for local-only fake/dev credentials |
| Production (AWS) | **AWS Secrets Manager** (or SSM Parameter Store) — ECS task pulls secrets at runtime via the task role |

The RDS connection password is stored in Secrets Manager under `zephyrwerk/rds/credentials`. The ECS task role is granted read access to that specific secret only (least privilege). Non-sensitive config (bucket name, region, endpoints) can remain as plain env vars.

### S3 Bucket Structure

```
s3://zephyrwerk-data-lake/
├── raw/
│   ├── smard/
│   │   ├── year=2019/month=01/smard_20190101.parquet
│   │   └── ...
│   └── weather/
│       ├── year=2019/month=01/weather_20190101.parquet
│       └── ...
├── models/
│   ├── price_forecast/
│   │   ├── latest/price_forecast.pkl
│   │   └── archive/price_forecast_20260101.pkl
│   └── generation_forecast/
│       ├── latest/generation_forecast.pkl
│       └── archive/generation_forecast_20260101.pkl
└── dbt-artifacts/
    └── (dbt run artifacts for lineage tracking)
```

### RDS PostgreSQL Schema Structure

```sql
-- Schema: staging (dbt staging models)
stg_smard_generation
stg_smard_prices
stg_smard_neighbour_prices
stg_weather

-- Schema: analytics (dbt mart models)
fct_energy_generation
fct_market_prices
fct_price_spreads
fct_weather_features
fct_ml_features
dim_date   -- populated via dbt seed (CSV) or generated with a date-spine macro, NOT from source data; includes German public holidays + season labels
```

---

## 9. ML Models

### Model 1 — Day-Ahead Price Forecast

**Business goal:** Predict tomorrow's average day-ahead electricity price (€/MWh) so the supply chain team can plan capacity.

**Target variable:** `day_ahead_price_eur_mwh` (next day average)

**Features:**
| Feature | Source |
|---|---|
| Hour of day | Derived |
| Day of week | Derived |
| Month / Season | Derived |
| Is public holiday (Germany) | `holidays` library |
| Previous day price | SMARD lag |
| 7-day rolling average price | SMARD rolling |
| Previous day total consumption | SMARD lag |
| Wind speed forecast | Open-Meteo |
| Solar irradiance forecast | Open-Meteo |
| Temperature forecast | Open-Meteo |
| Neighbour price spread (lag) | SMARD lag (e.g. DE−FR, DE−PL) |

**Model:** XGBoost Regressor inside sklearn Pipeline (StandardScaler + OneHotEncoder)

**Evaluation metrics:** MAE, RMSE, MAPE, directional accuracy

**Retraining schedule:** Weekly (every Monday 07:00 UTC via Step Functions)

---

### Model 2 — Renewable Generation Forecast

**Business goal:** Predict next-day wind + solar output (MW) to inform grid supply planning.

**Target variables:**
- `wind_generation_mw` (onshore + offshore combined)
- `solar_generation_mw`

**Features:**
| Feature | Source |
|---|---|
| Hour of day | Derived |
| Month / Season | Derived |
| Wind speed at 100m | Open-Meteo |
| Wind direction | Open-Meteo |
| Solar irradiance | Open-Meteo |
| Cloud cover | Open-Meteo |
| Previous day wind generation (lag) | SMARD lag |
| Previous day solar generation (lag) | SMARD lag |

**Model:** XGBoost Regressor (separate model per target)

**Evaluation metrics:** MAE, RMSE, R²

**Retraining schedule:** Weekly (every Monday 07:00 UTC)

---

### Deployment Ordering (train before first API deploy)

There is plenty of data (2019–present) to train a fully capable model from day one — this is not a data problem. It is simply a sequencing reminder: a serialized `.pkl` must exist in S3 before the API tries to load it.

So on first deployment: run the training job once → confirm the `.pkl` files are in S3 → then deploy/start the API. The API should also return a clear error (HTTP 503 "model not available") rather than crashing if a model file is ever missing, since the dashboard's Forecast page depends on these endpoints.

---

## 10. API Design

**Framework:** FastAPI  
**Deployment:** AWS ECS Fargate  
**Pattern:** Dependency injection + Repository pattern  
**Docs:** Auto-generated OpenAPI at `/docs`

### Endpoints

```
GET  /health
     → Service health check

GET  /energy/generation
     ?start=YYYY-MM-DD&end=YYYY-MM-DD&source=wind_onshore
     → Historical generation data by source

GET  /energy/prices
     ?start=YYYY-MM-DD&end=YYYY-MM-DD
     → Historical day-ahead prices

GET  /energy/summary
     ?date=YYYY-MM-DD
     → Daily summary: generation mix, avg price, renewable share

POST /predict/price
     body: { "target_date": "YYYY-MM-DD", "weather_features": {...} }
     → Predicted day-ahead price for target date

POST /predict/generation
     body: { "target_date": "YYYY-MM-DD", "weather_forecast": {...} }
     → Predicted wind + solar generation for target date
```

---

## 11. Dashboard Design

**Framework:** Streamlit multipage  
**Deployment:** AWS ECS Fargate  
**Data source:** FastAPI REST API (cached client layer)  
**Charts:** Plotly

### Pages

**Page 1 — Historical Overview**
- Germany energy mix evolution (2019–present) — stacked area chart
- Renewable share trend by year — line chart
- Seasonal generation patterns (avg by month) — heatmap
- Price distribution by season — box plot
- Key insight callouts from EDA

**Page 2 — Market Monitor**
- Last 30 days: generation by source — stacked bar
- Current renewable share vs. seasonal average — gauge
- Day-ahead price: last 30 days + 7-day rolling average
- Neighbour price spreads (DE/LU vs FR, NL, PL, AT, CH) — bar / heatmap
- Today's generation breakdown — donut chart

**Page 3 — Forecast Viewer**
- Tomorrow's price forecast with confidence range — line + band
- Next 24h renewable generation forecast — area chart
- Model performance metrics (MAE, RMSE from last evaluation)
- Last model retrain date

---

## 12. Git Strategy

### Branch Structure

```
main          ← production only. protected. requires PR + passing CI.
│
develop       ← integration branch. all phases merge here first.
│
├── phase/1-ingestion
├── phase/2-eda
├── phase/3-dbt
├── phase/4-ml
├── phase/5-api
├── phase/6-dashboard
└── phase/7-aws
```

### Workflow Per Phase

```
1. Checkout develop
2. Create branch: git checkout -b phase/X-name
3. Work on phase (commits follow convention below)
4. Open Pull Request → develop
5. GitHub Actions runs: pytest + linting
6. PR reviewed + merged into develop
7. On phase completion: develop → PR → main
8. Tag release on main
```

### Commit Message Convention (Conventional Commits)

```
feat:     new feature or capability
fix:      bug fix
chore:    configuration, dependencies, tooling
docs:     README, docstrings, architecture diagrams
test:     adding or updating tests
refactor: code restructure without behavior change
ci:       GitHub Actions workflows
infra:    AWS infrastructure changes
```

Examples:
```
feat: add SMARD ingestion client for generation data
fix: handle missing values in day-ahead price response
chore: add Docker Compose for local development
docs: update README with architecture diagram
test: add unit tests for S3 uploader
ci: add GitHub Actions pytest workflow on PR
infra: add ECS task definition for ingestion container
```

### Release Tags

```
v0.1.0 — Phase 1 complete: Ingestion pipeline
v0.2.0 — Phase 2 complete: EDA
v0.3.0 — Phase 3 complete: dbt transformation layer
v0.4.0 — Phase 4 complete: ML models
v0.5.0 — Phase 5 complete: FastAPI service
v0.6.0 — Phase 6 complete: Streamlit dashboard
v1.0.0 — Phase 7 complete: Full AWS cloud deployment
```

---

## 13. Phase Roadmap

### Phase 1 — Foundation & Data Ingestion
**Branch:** `phase/1-ingestion`  
**Goal:** Raw data lands in S3. Pipeline runs locally via simple Python orchestration.

Deliverables:
- Project scaffold with folder structure, `pyproject.toml`, `.env` management
- SMARD ingestion client — supports both backfill (2019–present) and incremental (single day) modes via `start_date`/`end_date` params
- Open-Meteo ingestion client — handles **both** the Historical Weather API (backfill) and Forecast API (daily), weather signals for 4 German regions
- S3 uploader — writes partitioned Parquet files to raw layer, idempotent for re-runs
- One-time historical backfill executed and verified in S3
- Local orchestration script: `orchestration/run_pipeline.py`
- LocalStack set up for local S3 emulation
- GitHub repo initialized, branch created, CI scaffold in place
- **Verify all SMARD filter IDs against `smard.api.bund.dev` (see note in Section 5)**

New skills: boto3 S3 client, Parquet with pyarrow, LocalStack, environment config patterns, backfill vs. incremental ingestion design

---

### Phase 2 — EDA & Data Understanding
**Branch:** `phase/2-eda`  
**Goal:** Deep, documented understanding of the data. Findings inform dashboard narrative.

Deliverables:
- Structured Jupyter notebooks in `notebooks/eda/`
- Analysis: energy mix shift 2019–2025, price spike patterns, renewable seasonality, consumption patterns, neighbour price spreads
- Key findings documented in `notebooks/eda/FINDINGS.md`
- Data quality issues identified and logged for dbt handling

New skills: Time-series EDA patterns, energy domain knowledge

---

### Phase 3 — dbt Transformation Layer
**Branch:** `phase/3-dbt`  
**Goal:** Clean, tested, documented analytics tables in RDS PostgreSQL.

Deliverables:
- dbt project scaffold with `profiles.yml` using environment variables
- Staging models for all raw sources
- Analytics models: `fct_energy_generation`, `fct_market_prices`, `fct_weather_features`, `fct_ml_features`, `dim_date`
- dbt tests: not-null, unique, accepted values, freshness checks
- Column-level documentation on all models
- dbt Dockerfile for ECS deployment

New skills: dbt Core project structure, dimensional modeling for time-series, dbt testing patterns

---

### Phase 4 — ML Models
**Branch:** `phase/4-ml`  
**Goal:** Two trained, evaluated, serialized models stored in S3.

Deliverables:
- Feature engineering pipeline in `ml/features/`
- Price forecast model: XGBoost inside sklearn Pipeline, trained + evaluated
- Generation forecast model: XGBoost, trained + evaluated
- Model evaluation report: MAE, RMSE, directional accuracy
- Serialization to S3: `s3://zephyrwerk-data-lake/models/`
- ML training Dockerfile for ECS deployment
- Experiment tracking via logged metrics (CSV or JSON artifacts in S3)

New skills: XGBoost, time-series feature engineering, model serialization to S3

---

### Phase 5 — FastAPI Service
**Branch:** `phase/5-api`  
**Goal:** Production-quality REST API serving analytics and predictions.

Deliverables:
- All endpoints implemented with Pydantic request/response models
- Dependency injection + repository pattern
- Model loader service (loads `.pkl` from S3 on startup)
- Auto-generated OpenAPI docs
- Pytest: unit + integration tests (mocked S3 + DB)
- API Dockerfile
- GitHub Actions: run pytest on PR

New skills: Model serving in FastAPI, S3 as model registry, mocking AWS in tests

---

### Phase 6 — Streamlit Dashboard
**Branch:** `phase/6-dashboard`  
**Goal:** Three-page business dashboard consuming the FastAPI service.

Deliverables:
- Multipage Streamlit app with all three pages implemented
- Plotly charts throughout
- Cached API client layer
- Dashboard Dockerfile
- Local Docker Compose runs API + Dashboard together

New skills: Streamlit multipage architecture, Plotly time-series visualizations

---

### Phase 7 — AWS Cloud Deployment
**Branch:** `phase/7-aws`  
**Goal:** Everything running on AWS. Nothing runs locally. CI/CD fully automated.

Deliverables:
- S3 bucket provisioned with correct structure and IAM policies
- RDS PostgreSQL instance provisioned
- ECR repositories for all 4 Docker images
- ECS Fargate cluster with API and Dashboard services
- Step Functions state machine for daily pipeline
- EventBridge rule: daily trigger at 06:00 UTC
- IAM roles with least-privilege policies
- CloudWatch log groups + budget alert ($20/month threshold)
- GitHub Actions:
  - On PR: pytest + dbt tests
  - On merge to main: build → ECR push → ECS deploy
- Final README with architecture diagram, setup guide, business context
- `v1.0.0` release tag on main

New skills: ECS Fargate, ECR, Step Functions, EventBridge, IAM, CloudWatch, full cloud CI/CD

---

## 14. Cost Management

### Free Tier Coverage
| Service | Free Tier | Expected Usage |
|---|---|---|
| S3 | 5GB storage, 20k GET, 2k PUT/month | Well within free tier |
| RDS PostgreSQL | 750hrs `db.t3.micro`/month (12 months) | Single instance, covered |
| ECS Fargate | No free tier | Main cost driver |
| ECR | 500MB/month | Covered |
| CloudWatch | 10 custom metrics, 5GB logs | Covered |
| Step Functions | 4,000 state transitions/month | Covered |
| EventBridge | 14M events/month | Covered |

### Cost Reduction Strategies
- Use **Fargate Spot** for all ECS Tasks (ingestion, dbt, ML training) — up to 70% cheaper
- ECS Services (API + Dashboard) on standard Fargate — ~$15–25/month combined at minimal sizing
- Set **AWS Budgets alert** at $20/month on day one
- Scale API + Dashboard to minimum task count (1 each) during development
- Consider stopping RDS instance when not actively developing (can be restarted in minutes)

### Estimated Monthly Cost (Production)
| Resource | Estimated Cost |
|---|---|
| RDS `db.t3.micro` | ~$15/month (after free tier year) |
| ECS Fargate (API + Dashboard, 24/7) | ~$15–25/month |
| ECS Tasks (ingestion + dbt + ML, daily) | ~$2–5/month with Spot |
| S3 storage | < $1/month |
| **Total** | **~$30–45/month** |

---

## 15. Naming Conventions

### Python
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`

### dbt
- Staging models: `stg_{source}_{entity}` (e.g. `stg_smard_generation`)
- Fact models: `fct_{entity}` (e.g. `fct_energy_generation`)
- Dimension models: `dim_{entity}` (e.g. `dim_date`)

### AWS Resources
- Pattern: `zephyrwerk-{resource-type}-{qualifier}`
- Examples: `zephyrwerk-data-lake`, `zephyrwerk-api-service`, `zephyrwerk-ecs-task-role`

### Docker Images
- Pattern: `zephyrwerk/{service}:{tag}`
- Tags: `latest` for production, `dev` for development, version tags for releases

### Environment Variables
- Pattern: `ZEPHYRWERK_{SERVICE}_{VARIABLE}`
- Examples: `ZEPHYRWERK_AWS_BUCKET_NAME`, `ZEPHYRWERK_RDS_HOST`, `ZEPHYRWERK_SMARD_BASE_URL`

---

## 16. Development Approach

### Core Principle: Local First, Cloud Last

Build and validate everything locally before touching AWS. Deploy to cloud only in Phase 7. This is how real engineering teams work.

**Why:**
- Debugging locally takes seconds. Debugging on ECS takes 30–60 minutes per issue
- AWS costs money even for failed experiments and test runs
- Docker images that work locally work identically on ECS — moving to cloud is a config change, not a code change

---

### Local Environment Strategy

Never connect to real AWS during development. Use local emulators that are API-identical to the real services:

| Production Service | Local Equivalent | How to Switch |
|---|---|---|
| AWS S3 | **LocalStack** (Docker container) | Change `endpoint_url` env var |
| AWS RDS PostgreSQL | **PostgreSQL in Docker** | Change `DB_HOST` env var |
| ECS Tasks | **Python scripts run directly** | No change needed — same code |
| EventBridge + Step Functions | **`orchestration/run_pipeline.py`** | Replaced entirely in Phase 7 |

**The rule:** The only difference between local and production is environment variables. Zero code changes required for deployment.

```
# Local .env
AWS_ENDPOINT_URL=http://localhost:4566     # LocalStack
DB_HOST=localhost
DB_PORT=5432

# Production .env (on ECS)
AWS_ENDPOINT_URL=                          # empty = real AWS
DB_HOST=zephyrwerk-rds-prod.xxxx.rds.amazonaws.com
DB_PORT=5432
```

---

### Docker Adoption — Progressive, Not Upfront

Never Dockerize code that doesn't work yet. Follow this progression:

```
Phase 1–2:   No Docker at all
             → just python script.py
             → prove logic works first

Phase 3:     Add dbt/Dockerfile only
             → first containerization experience
             → low risk, high production relevance

Phase 4:     Add ml/Dockerfile
             → containerize ML training

Phase 5:     Add api/Dockerfile
             → containerize FastAPI service

Phase 6:     Add dashboard/Dockerfile
             → add docker-compose.yml
             → wire all services together locally for first time

Phase 7:     Remove Docker Compose
             → push individual Dockerfiles to ECR
             → deploy to ECS Fargate
             → Docker Compose was local convenience only
```

**The golden rule:** First make the code work with `python script.py`. Then make it work in Docker. Then move on. Always in that order.

---

### Environment Parity

Every service is designed so that local and production behave identically:

```
Local dev:      Python script → LocalStack (fake S3) → PostgreSQL in Docker
Production:     ECS Task      → real AWS S3           → AWS RDS PostgreSQL
```

Same Docker image. Same Python code. Same dbt models. Same API. Only env vars differ.

This means Phase 7 deployment is purely operational — provisioning AWS resources, pushing images, setting env vars. No surprises, no rewrites.

---

### What "Done" Means Per Phase

A phase is only complete when:
1. Code works correctly running as plain Python (`python script.py`)
2. All tests pass (`pytest`)
3. Dockerfile builds and runs correctly (from Phase 3 onward)
4. PR is merged into `develop` with passing CI
5. Release tag created on `main`

Never move to the next phase until the current one meets all five criteria.

---

```
zephyrwerk-platform/
│
├── ingestion/
│   ├── __init__.py
│   ├── smard_client.py          # SMARD API client
│   ├── weather_client.py        # Open-Meteo API client
│   └── s3_uploader.py           # S3 write utilities
│
├── orchestration/
│   └── run_pipeline.py          # Local: runs ingestion → dbt → (optionally ML)
│
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml             # reads from env vars
│   ├── models/
│   │   ├── staging/
│   │   │   ├── stg_smard_generation.sql
│   │   │   ├── stg_smard_prices.sql
│   │   │   ├── stg_smard_neighbour_prices.sql
│   │   │   └── stg_weather.sql
│   │   └── analytics/
│   │       ├── fct_energy_generation.sql
│   │       ├── fct_market_prices.sql
│   │       ├── fct_price_spreads.sql
│   │       ├── fct_weather_features.sql
│   │       ├── fct_ml_features.sql
│   │       └── dim_date.sql
│   └── Dockerfile
│
├── ml/
│   ├── features/
│   │   └── feature_engineering.py
│   ├── train_price_model.py
│   ├── train_generation_model.py
│   ├── evaluate.py
│   └── Dockerfile
│
├── api/
│   ├── main.py
│   ├── routers/
│   │   ├── energy.py
│   │   └── predict.py
│   ├── services/
│   │   ├── model_loader.py
│   │   └── data_service.py
│   ├── repositories/
│   │   └── energy_repository.py
│   ├── schemas/
│   │   ├── requests.py
│   │   └── responses.py
│   └── Dockerfile
│
├── dashboard/
│   ├── app.py
│   ├── pages/
│   │   ├── 1_Historical_Overview.py
│   │   ├── 2_Market_Monitor.py
│   │   └── 3_Forecast_Viewer.py
│   ├── api_client.py            # cached FastAPI client
│   └── Dockerfile
│
├── notebooks/
│   └── eda/
│       ├── 01_energy_mix_history.ipynb
│       ├── 02_price_analysis.ipynb
│       ├── 03_renewable_seasonality.ipynb
│       ├── 04_consumption_patterns.ipynb
│       ├── 05_price_spreads.ipynb
│       └── FINDINGS.md
│
├── tests/
│   ├── ingestion/
│   ├── api/
│   └── ml/
│
├── .github/
│   └── workflows/
│       ├── ci.yml               # pytest + linting on PR
│       └── deploy.yml           # build → ECR → ECS on merge to main
│
├── docker-compose.yml           # local development only
├── .env.example                 # env var template (never commit .env)
├── pyproject.toml               # dependencies + tooling config
├── PLATFORM.md                  # this document
└── README.md                    # public-facing project description
```

---

*Document maintained by: Hasan Erdin*  
*Last updated: May 2026 — v1.4: Verified all SMARD filter IDs against official list; fixed total-consumption ID (410, not 4359); added nuclear/other/pumped-storage signals + forecast generation filters; specified region DE-LU and hourly resolution; replaced non-existent cross-border flows with neighbour price-spread analysis (option b) across all models, features, dashboard, EDA, and folder structure*  
*Next update: After Phase 1 completion*
