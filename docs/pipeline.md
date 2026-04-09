# Pipeline Documentation

> Remove this file if this repo is not a data pipeline project.

---

## Overview

<!-- Describe the pipeline: what data flows through it, from where to where, and why. -->

---

## Architecture

```
Source → Extract → Transform → Load → Destination
```

<!-- Replace with an actual architecture diagram or description. -->

---

## Schedule

| Pipeline | Schedule | Owner |
|---|---|---|
| <!-- name --> | <!-- cron --> | Tom Fynes |

---

## Dependencies

| Tool | Purpose |
|---|---|
| Airflow | Orchestration |
| dbt | Transformation |
| Snowflake | Destination warehouse |

---

## Running Locally

```bash
# Initialise Airflow
export AIRFLOW_HOME=$(pwd)/airflow
airflow db init
airflow standalone

# Trigger a DAG manually
airflow dags trigger <dag_id>
```

---

## Data Quality

<!-- Describe any data quality checks, expectations, or SLA definitions. -->

---

## Monitoring & Alerting

<!-- Describe how pipeline failures are detected and who is notified. -->

---

## Runbook

### Pipeline fails mid-run

1. Check the Airflow logs for the failing task
2. Identify whether the failure is in extract, transform, or load
3. Fix the root cause and clear the failed task in Airflow UI
4. Re-trigger from the failed task

### Data quality check fails

1. Review the failed expectation in the logs
2. Inspect the source data for the affected date/batch
3. Decide: re-run with corrected source, or mark as known bad and skip
