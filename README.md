# Zephyrwerk Energy Analytics Platform

Production-grade data engineering platform ingesting live German electricity market data (SMARD / Bundesnetzagentur), transforming it with dbt, serving ML-powered predictions via a FastAPI REST API, and visualising results in a Streamlit dashboard — deployed on AWS.

Built as a portfolio project demonstrating end-to-end data platform engineering: from raw API ingestion to ML inference to cloud deployment.

---

## Architecture

> Full architecture diagram added after Phase 7.

**Stack:** Python · dbt Core · PostgreSQL · FastAPI · Streamlit · XGBoost · AWS (S3, RDS, ECS Fargate, Step Functions, EventBridge) · Docker · GitHub Actions

---

## Phases

| Phase | Scope | Status |
|---|---|---|
| 1 — Ingestion | SMARD + Open-Meteo clients, S3 raw layer, LocalStack | 🔜 Not started |
| 2 — EDA | Jupyter notebooks, energy mix analysis, findings | 🔜 Not started |
| 3 — dbt | Staging + analytics models, dbt tests, first Dockerfile | 🔜 Not started |
| 4 — ML | XGBoost price + generation forecasting, model registry | 🔜 Not started |
| 5 — API | FastAPI service, all endpoints, pytest suite | 🔜 Not started |
| 6 — Dashboard | Streamlit multipage dashboard, Docker Compose | 🔜 Not started |
| 7 — AWS | Full cloud deployment, CI/CD, v1.0.0 release | 🔜 Not started |

---

## Local Setup

```bash
git clone https://github.com/hasanerdin/zephyrwerk-platform.git
cd zephyrwerk-platform

uv sync --extra dev

cp .env.example .env
# Edit .env with your values
```

> Full setup and deployment instructions added as each phase completes.

---

## Data Sources

- **SMARD** (Bundesnetzagentur) — German electricity generation, consumption, and day-ahead prices · CC BY 4.0
- **Open-Meteo** — Historical and forecast weather for key German regions · Free for non-commercial use

---

## Author

Hasan Erdin — Data Engineer & Applied Data Scientist, Munich
[GitHub](https://github.com/hasanerdin) · [LinkedIn](https://linkedin.com/in/hasanerdin)