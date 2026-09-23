"""Entry point for the ingestion container.

One task per invocation, so each ECS task runs a single unit of work:

    python -m ingestion --task smard
    python -m ingestion --task smard --start_date 2019-01-01 --end_date 2019-12-31

With no dates given, each task uses its daily default. Logs go to stdout only;
ECS forwards stdout to CloudWatch, and a log file inside a container is lost
when the container exits.
"""

import argparse
import logging
from datetime import datetime, timedelta, timezone

from ingestion.loader import load_range
from ingestion.tasks import run_smard_range, run_weather_forecast, run_weather_range

TASKS = ("smard", "weather", "weather_forecast", "load")

FORECAST_DAYS = 7

logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single ingestion task.")
    parser.add_argument(
        "--task",
        type=str,
        choices=TASKS,
        required=True,
        help="Which unit of work to run.",
    )
    parser.add_argument(
        "--start_date",
        type=str,
        help="Start date (YYYY-MM-DD). Defaults to the task's daily window.",
    )
    parser.add_argument(
        "--end_date",
        type=str,
        help="End date (YYYY-MM-DD). Defaults to the task's daily window.",
    )
    return parser.parse_args()


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _default_window(task: str) -> tuple[datetime, datetime]:
    """The window each task uses when no dates are passed on the command line."""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    if task in ("smard", "weather"):
        return yesterday, yesterday
    if task == "weather_forecast":
        return today, today + timedelta(days=FORECAST_DAYS)
    # load: yesterday's freshly ingested data plus the forecast window
    return yesterday, today + timedelta(days=FORECAST_DAYS)


def resolve_window(args: argparse.Namespace) -> tuple[datetime, datetime]:
    default_start, default_end = _default_window(args.task)

    start_date = _parse_date(args.start_date) if args.start_date else default_start
    end_date = _parse_date(args.end_date) if args.end_date else default_end

    if end_date < start_date:
        raise ValueError(f"end_date ({end_date.date()}) is before start_date ({start_date.date()}).")

    return start_date, end_date


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

    args = parse_arguments()
    start_date, end_date = resolve_window(args)

    logger.info(f"Starting task '{args.task}' for {start_date.date()} to {end_date.date()}.")

    if args.task == "smard":
        run_smard_range(start_date, end_date)
    elif args.task == "weather":
        run_weather_range(start_date, end_date)
    elif args.task == "weather_forecast":
        run_weather_forecast(start_date, end_date)
    else:
        load_range(start_date, end_date)

    logger.info(f"Task '{args.task}' completed.")


if __name__ == "__main__":
    main()