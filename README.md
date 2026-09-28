# Zephyrwerk Energy Analytics Platform

Production-grade data engineering platform ingesting live German electricity market data (SMARD / Bundesnetzagentur), loading it into PostgreSQL, transforming it with dbt, forecasting prices and renewable generation with XGBoost, serving predictions via a FastAPI REST API, and visualising results in a Streamlit dashboard — deployed on AWS.

Built as a portfolio project demonstrating end-to-end data platform engineering: from raw API ingestion to ML inference to cloud deployment.

---

## Architecture

**Stack:** Python · dbt Core · PostgreSQL · FastAPI · Streamlit · XGBoost · Terraform · AWS (S3, RDS, ECR, ECS Fargate, Secrets Manager, CloudWatch, Step Functions, EventBridge) · Docker · GitHub Actions

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
                                   (ECS Service Connect: http://api:8000)
                              ┌──────────────────────────────────┐
                              │  Streamlit — AWS ECS Fargate     │
                              │  Historical Overview             │
                              │  Market Monitor                  │
                              │  Forecast Viewer                 │
                              └──────────────────────────────────┘

Infrastructure: Terraform (infra/) — VPC, RDS, S3, ECR, IAM, ECS
CI/CD:          GitHub Actions → Docker build → ECR push → ECS deploy
Orchestration:  EventBridge → Step Functions → ECS Tasks (daily 06:00 UTC)
Monitoring:     AWS CloudWatch (logs + cost alerts)
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
| 6 — Dashboard | Streamlit multipage dashboard, Docker Compose | ✅ Complete · `v0.6.0` |
| 7 — AWS | Terraform infrastructure, ECS Fargate deployment, orchestration, CI/CD | 🚧 In progress |

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

## AWS Deployment (Phase 7)

The whole platform runs on AWS in `eu-central-1` (Frankfurt), provisioned with Terraform. Nothing about the application code changes between local and cloud — only environment variables.

### Infrastructure

All infrastructure lives in `infra/` as Terraform, with state kept locally (single-developer project; `*.tfstate` is gitignored because it stores the generated database password in plain text).

| File | Contents |
|---|---|
| `main.tf` | Providers, default tags, S3 data lake |
| `network.tf` | VPC (10.0.0.0/16), 2 public + 2 private subnets across 2 AZs, internet gateway, route tables |
| `security_groups.tf` | Pipeline, API, RDS and dashboard security groups |
| `rds.tf` | DB subnet group, generated password, Secrets Manager entry, PostgreSQL 16 instance |
| `ecr.tf` | 5 image repositories with immutable tags, scan-on-push, and lifecycle policies |
| `iam.tf` | One execution role, three least-privilege task roles, CloudWatch log group |
| `ecs.tf` | Cluster, Service Connect namespace, 8 task definitions, 2 services |

```bash
cd infra
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

### Design decisions

**No NAT Gateway.** Containers run in public subnets with public IPs and are protected by security groups; only RDS sits in the private subnets. A NAT Gateway costs ~$38/month, which is more than the rest of this deployment combined. In production, containers would run in private subnets behind NAT — the trade-off here is deliberate and cost-driven.

**No load balancer.** The dashboard is reached directly at `http://<task-public-ip>:8501`. An ALB would add ~$18–20/month and is what production would use (fixed hostname, HTTPS via ACM). The consequence: the address changes whenever the task restarts, and traffic is plain HTTP.

**ARM64 / Graviton.** Images are built natively on Apple Silicon and run on ARM Fargate — no emulation during build, and ~20% cheaper compute.

**Least-privilege IAM.** The execution role pulls images, reads the RDS secret and writes logs. Task roles are split by job: ingestion/loader can read and write `raw/*`, ML can read and write `models/*`, the API can only read `models/*`. dbt and the dashboard get no task role at all — dbt only talks to Postgres, the dashboard only to the API.

**Secrets.** The database password is generated by Terraform, stored in Secrets Manager as `zephyrwerk/rds/credentials`, and injected by ECS into the container as `ZEPHYRWERK_RDS_PASSWORD`. No application code knows Secrets Manager exists.

**Service Connect.** The API registers itself as `api` in the cluster namespace, so the dashboard reaches it at `http://api:8000` — the same address shape Docker Compose provides locally, and stable across task restarts.

**Non-root containers.** Every image creates an `appuser` and switches to it before `CMD`, so application code is readable but not writable from inside a running container.

### Images

Five images, one per component; the loader and the ingestion tasks share the `ingestion` image and differ only in the command they run. Tags are the short git commit hash, and ECR repositories are immutable, so a tag always refers to exactly one build.

```bash
SHA=$(git rev-parse --short HEAD)
REGISTRY=<account-id>.dkr.ecr.eu-central-1.amazonaws.com

aws ecr get-login-password --profile zephyrwerk --region eu-central-1 \
  | docker login --username AWS --password-stdin $REGISTRY

for name in api dashboard ingestion dbt ml; do
  docker build --platform linux/arm64 --provenance=false \
    -t $REGISTRY/zephyrwerk-$name:$SHA -f $name/Dockerfile .
  docker push $REGISTRY/zephyrwerk-$name:$SHA
done
```

Then set `image_tag` in `infra/variables.tf` to the new hash and re-apply.

### Container entry points

Each ECS task runs exactly one unit of work, defined by the `command` in its task definition:

| Task definition | Image | Command |
|---|---|---|
| `zephyrwerk-init-db` | ingestion | `python -m ingestion --task init-db` |
| `zephyrwerk-ingestion-smard` | ingestion | `python -m ingestion --task smard` |
| `zephyrwerk-ingestion-weather` | ingestion | `python -m ingestion --task weather` |
| `zephyrwerk-ingestion-weather_forecast` | ingestion | `python -m ingestion --task weather_forecast` |
| `zephyrwerk-ingestion-load` | ingestion | `python -m ingestion --task load` |
| `zephyrwerk-dbt` | dbt | `dbt seed && dbt run && dbt test` |
| `zephyrwerk-ml-price` | ml | `python -m ml.train_price_model` |
| `zephyrwerk-ml-generation` | ml | `python -m ml.train_generation_model` |

With no dates passed, every ingestion task uses its own daily window (yesterday for SMARD/weather, the next 8 days for the forecast). Dates are only passed explicitly for backfills.

### Running a task manually

```bash
aws ecs run-task \
  --cluster zephyrwerk-cluster \
  --task-definition zephyrwerk-ingestion-load \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[SUBNET_1,SUBNET_2],securityGroups=[PIPELINE_SG],assignPublicIp=ENABLED}" \
  --profile zephyrwerk --region eu-central-1
```

For a one-off backfill, override the command instead of changing the task definition:

```bash
  --overrides '{"containerOverrides":[{"name":"ingestion-load","command":["python","-m","ingestion","--task","load","--start_date","2019-01-01","--end_date","2026-09-23"]}]}'
```

All logs go to the `/zephyrwerk/pipeline` CloudWatch log group, one stream prefix per task:

```bash
aws logs tail /zephyrwerk/pipeline --follow --since 10m --profile zephyrwerk --region eu-central-1
```

### One-time setup in a fresh environment

Two steps happen automatically on a local machine and therefore have to be made explicit in the cloud:

1. **Schema creation.** Locally the Postgres container applies `db/init.sql` via `docker-entrypoint-initdb.d`. On RDS, run the `zephyrwerk-init-db` task once. It applies the same file, and every statement uses `IF NOT EXISTS`, so re-running is safe.
2. **dbt seed.** `dim_date` joins against the `german_public_holidays` seed. Locally this is `make dbt-seed`; in AWS `dbt seed` is part of the dbt task's command so it can never be forgotten.

Then run, in order: `zephyrwerk-ingestion-smard` → `weather` → `weather_forecast` → `load` → `zephyrwerk-dbt` → the two ML tasks.

### Long-running services

`zephyrwerk-api` and `zephyrwerk-dashboard` run as ECS services with `desired_count = 1`; ECS restarts them if the container-level health check fails. To find the dashboard's current address:

```bash
TASK=$(aws ecs list-tasks --cluster zephyrwerk-cluster --service-name zephyrwerk-dashboard \
  --query 'taskArns[0]' --output text --profile zephyrwerk --region eu-central-1)

ENI=$(aws ecs describe-tasks --cluster zephyrwerk-cluster --tasks $TASK \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
  --output text --profile zephyrwerk --region eu-central-1)

aws ec2 describe-network-interfaces --network-interface-ids $ENI \
  --query 'NetworkInterfaces[0].Association.PublicIp' --output text \
  --profile zephyrwerk --region eu-central-1
```

### Cost

Running total is roughly $1.25/day: two Fargate services (~$0.50), two public IPv4 addresses (~$0.25), RDS `db.t3.micro` + 20 GB gp3 (~$0.58), plus a few cents for S3, ECR and Secrets Manager. VPC, subnets, gateways, security groups, IAM and task definitions are free.

To pause without destroying anything, scale both services to zero:

```bash
aws ecs update-service --cluster zephyrwerk-cluster --service zephyrwerk-api --desired-count 0 --profile zephyrwerk --region eu-central-1
aws ecs update-service --cluster zephyrwerk-cluster --service zephyrwerk-dashboard --desired-count 0 --profile zephyrwerk --region eu-central-1
```

To tear everything down: `terraform destroy`. `force_delete` on the ECR repositories and `skip_final_snapshot` on RDS are set specifically so that this completes without manual cleanup — both would be the opposite in production. Afterwards, search the console for resources tagged `Project = zephyrwerk` to confirm nothing was left behind.

---

## Local Setup

### Prerequisites

- **Python 3.12** managed via [`uv`](https://docs.astral.sh/uv/) — pinned to 3.12 because `dbt-core`'s `mashumaro` dependency fails on 3.14
- **Docker** — runs LocalStack (S3 emulator) and PostgreSQL locally
- **Make** — the commands below are `make` targets (see the `Makefile`); run `make help` for the full list
- **Terraform** and the **AWS CLI v2** — only needed for the cloud deployment (see above)

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

`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` are only meaningful locally, where LocalStack accepts any value. In AWS they are absent on purpose: credentials come from the ECS task role, and setting them would override it.

### Start local infrastructure

```bash
make infra-up
```

Starts LocalStack (S3 emulation, pinned to 3.8 — LocalStack 2026.x
requires a paid license for S3) and PostgreSQL, waits for LocalStack to
report healthy, and creates the `zephyrwerk-data-lake` bucket.
PostgreSQL's container mounts two SQL files from `db/`: `init.sql`
creates the raw, staging and analytics schemas plus all five raw
tables, and `init_local_role.sql` creates the local `zephyrwerk` app
role. The role file is deliberately separate — it is local-only
(RDS has a single managed user) and contains a throwaway password that
must never run against a real database.

> If Postgres already existed before either file changed, the mounted
> scripts only run on first container init. Apply them manually instead:
> `docker exec -i zephyrwerk-postgres psql -U postgres -d zephyrwerk < db/init.sql`
> — safe to re-run, every statement either uses `IF NOT EXISTS` or
> checks first. The bucket creation in `make localstack-up` is also
> safe to re-run: `s3 mb` on an existing bucket is a no-op error.

### dbt one-time setup

```bash
make dbt-deps
make dbt-seed
```

Do this before the first pipeline run, not after. `dbt run` fails
immediately if `dbt_utils` isn't installed or the German public
holidays seed hasn't been loaded yet (`dim_date` joins against it).

Both targets wrap `dotenv run -- dbt ... --project-dir dbt
--profiles-dir dbt`: the `dbt` CLI doesn't read `.env` on its own —
`dbt/profiles.yml` pulls credentials via `env_var(...)`, which only
sees real OS environment variables — so `dotenv run --` (from
`python-dotenv`, already a project dependency) loads `.env` for that
one command. Going through `make` also means it works regardless of
your shell's current directory.

> To iterate on dbt models directly without re-running ingestion, use
> `make dbt-run` / `make dbt-test`.

### Run the ingestion pipeline

Individual tasks, the same units of work that run as separate ECS tasks in AWS:

```bash
python -m ingestion --task smard                                    # yesterday
python -m ingestion --task weather
python -m ingestion --task weather_forecast                         # next 8 days
python -m ingestion --task load                                     # S3 → Postgres
python -m ingestion --task smard --start_date 2019-01-01 --end_date 2025-12-31   # backfill
python -m ingestion --task init-db                                  # apply db/init.sql
```

Or the whole sequence at once via the local orchestrator:

```bash
make pipeline-historical START=2019-01-01                  # one-time, full backfill through yesterday
make pipeline-historical START=2019-01-01 END=2025-12-31    # or bound it explicitly
make pipeline-daily                                         # yesterday's SMARD + weather, 8-day forecast
make pipeline-weekly                                        # retrains + republishes all 3 models
```

`orchestration/run_pipeline.py` is local-only: it calls the same
functions the containers call, in the same order, and exists so the
full pipeline can be exercised on one machine. In AWS its job belongs
to Step Functions (sequencing) and EventBridge (scheduling).

`START` is required; `END` is optional and defaults to yesterday, since
no future SMARD data can ever exist. `pipeline-weekly` retrains from
whatever's currently in `fct_ml_features` and is deliberately
independent of `pipeline-daily` (separate failure domain) — in
production these are two separate EventBridge/Step Functions triggers,
sequenced by time (daily at 06:00 UTC, weekly at 07:00 UTC on Mondays)
so weekly always sees that morning's fresh data. Locally, run
`pipeline-daily` first if you want the same guarantee.

The pipeline is idempotent: re-running a date range skips Parquet files already in S3, and the loader upserts into Postgres so SMARD value revisions are picked up correctly. Forecast weather is re-fetched daily and superseded by the real observed value once that day's normal ingestion runs — the loader's upsert naturally overwrites forecast with actual, no reconciliation step needed.

Every task exits non-zero if any part of its work failed, even when it
continues past individual failures — that exit code is the only signal
Step Functions has to work with.

### Run EDA notebooks

```bash
uv run jupyter lab notebooks/eda/
```

Notebooks in order: `00_data_audit` → `01_energy_mix_history` → `02_renewable_seasonality` → `03_consumption_patterns` → `04_price_dynamics` → `05_price_spreads`

### Train / retrain the ML models

```bash
python -m ml.train_price_model
python -m ml.train_generation_model   # trains both wind and solar
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

The ingestion, dbt and ML images are not in Compose — they are
run-once jobs rather than services. Build and run them individually:

```bash
docker build --platform linux/arm64 -t zephyrwerk-ingestion:test -f ingestion/Dockerfile .
docker run --rm --env-file .env \
  -e ZEPHYRWERK_RDS_HOST=host.docker.internal \
  -e AWS_ENDPOINT_URL=http://host.docker.internal:4566 \
  zephyrwerk-ingestion:test python -m ingestion --task smard
```

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