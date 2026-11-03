import os
from pathlib import Path

import mysql.connector
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SCHEDULE_FILE = ROOT / "data" / "optimized_schedule.csv"
OUTPUT_FILE = ROOT / "data" / "weekly_fairness_report.csv"
SUMMARY_FILE = ROOT / "data" / "weekly_fairness_summary.csv"


def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "yottaflex_workforce"),
    )


def main():
    print("Loading optimized schedule...")

    schedule = pd.read_csv(SCHEDULE_FILE)

    schedule["start_at"] = pd.to_datetime(schedule["start_at"])
    schedule["end_at"] = pd.to_datetime(schedule["end_at"])

    schedule["assigned_hours"] = (
        schedule["end_at"] - schedule["start_at"]
    ).dt.total_seconds() / 3600

    schedule["iso_year"] = schedule["start_at"].dt.isocalendar().year
    schedule["iso_week"] = schedule["start_at"].dt.isocalendar().week

    schedule["week_key"] = (
        schedule["iso_year"].astype(str)
        + "-W"
        + schedule["iso_week"].astype(str).str.zfill(2)
    )

    print("Connecting to MySQL...")

    connection = get_connection()

    try:
        employees = pd.read_sql(
            """
            SELECT employee_id, team_id, weekly_hours_cap
            FROM employee
            WHERE employment_status = 'ACTIVE'
            """,
            connection,
        )

        shifts = pd.read_sql(
            """
            SELECT MIN(DATE(start_at)) AS period_start,
                   MAX(DATE(start_at)) AS period_end
            FROM shift
            WHERE status = 'PLANNED'
            """,
            connection,
        )
    finally:
        connection.close()

    if employees.empty:
        raise ValueError("No active employees found.")

    if shifts.empty or pd.isna(shifts.iloc[0]["period_start"]):
        raise ValueError("No planned shifts found.")

    period_start = pd.Timestamp(shifts.iloc[0]["period_start"]).date()
    period_end = pd.Timestamp(shifts.iloc[0]["period_end"]).date()

    employees["weekly_hours_cap"] = pd.to_numeric(
        employees["weekly_hours_cap"],
        errors="raise",
    )

    if employees["weekly_hours_cap"].isna().any():
        raise ValueError("An employee has a missing weekly hours cap.")

    # Generate every ISO week intersecting the scheduling horizon.
    weeks = []

    current_date = pd.Timestamp(period_start)

    while current_date.date() <= period_end:
        iso = current_date.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"

        if week_key not in weeks:
            weeks.append(week_key)

        current_date += pd.Timedelta(days=1)

    # Include every active employee in every scheduling week.
    employee_weeks = employees.assign(_key=1).merge(
        pd.DataFrame({"week_key": weeks, "_key": 1}),
        on="_key",
    ).drop(columns="_key")

    # Aggregate assigned hours.
    assigned = (
        schedule.groupby(
            ["employee_id", "week_key"],
            as_index=False,
        )
        .agg(assigned_hours=("assigned_hours", "sum"))
    )

    # Left join preserves employees with zero assignments.
    report = employee_weeks.merge(
        assigned,
        on=["employee_id", "week_key"],
        how="left",
    )

    report["assigned_hours"] = report["assigned_hours"].fillna(0)

    def get_available_days(week_key):
        year, week = map(int, week_key.replace("-W", " ").split())

        week_start = pd.Timestamp.fromisocalendar(
            year, week, 1
        ).date()

        week_end = pd.Timestamp.fromisocalendar(
            year, week, 7
        ).date()

        effective_start = max(week_start, period_start)
        effective_end = min(week_end, period_end)

        return (effective_end - effective_start).days + 1

    report["available_days"] = report["week_key"].apply(
        get_available_days
    )

    report["available_contract_hours"] = (
        report["weekly_hours_cap"]
        * report["available_days"]
        / 7
    )

    # Actual ISO-week cap utilization.
    report["actual_cap_utilization_percent"] = (
        report["assigned_hours"]
        / report["weekly_hours_cap"]
        * 100
    )

    # Partial-week normalized utilization.
    report["normalized_utilization_percent"] = (
        report["assigned_hours"]
        / report["available_contract_hours"]
        * 100
    )

    report["exceeds_weekly_cap"] = (
        report["assigned_hours"]
        > report["weekly_hours_cap"]
    )

    report = report.sort_values(
        ["team_id", "week_key", "employee_id"]
    )

    summary = (
        report.groupby(["team_id", "week_key"])
        .agg(
            employees=("employee_id", "nunique"),
            assigned_hours=("assigned_hours", "sum"),
            average_assigned_hours=("assigned_hours", "mean"),
            average_actual_utilization=(
                "actual_cap_utilization_percent", "mean"
            ),
            minimum_normalized_utilization=(
                "normalized_utilization_percent", "min"
            ),
            maximum_normalized_utilization=(
                "normalized_utilization_percent", "max"
            ),
            average_normalized_utilization=(
                "normalized_utilization_percent", "mean"
            ),
            employees_exceeding_weekly_cap=(
                "exceeds_weekly_cap", "sum"
            ),
        )
        .reset_index()
    )

    summary["normalized_utilization_spread"] = (
        summary["maximum_normalized_utilization"]
        - summary["minimum_normalized_utilization"]
    )

    report.to_csv(OUTPUT_FILE, index=False)
    summary.to_csv(SUMMARY_FILE, index=False)

    print("\nWEEKLY FAIRNESS SUMMARY")
    print(summary.round(2).to_string(index=False))

    print("\nOVERALL VALIDATION")
    print("Active employees:", len(employees))
    print("Scheduling weeks:", len(weeks))
    print("Employee-week records:", len(report))
    print(
        "Employees exceeding weekly cap:",
        int(report["exceeds_weekly_cap"].sum()),
    )

    print("\nReports saved:")
    print(OUTPUT_FILE)
    print(SUMMARY_FILE)


if __name__ == "__main__":
    main()