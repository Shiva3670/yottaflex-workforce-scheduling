
from pathlib import Path
from datetime import datetime, timedelta
import json
import os

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv("YOTTAFLEX_DATA_DIR", str(ROOT / "data"))).resolve()

app = FastAPI(
    title="YottaFlex Workforce API",
    version="0.1.0",
    description="Explainable workforce scheduling and intelligence API",
)


class GenerateRequest(BaseModel):
    start_date: str = Field(
        default="2026-01-01",
        description="Scheduling start date in YYYY-MM-DD format",
    )
    days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="Number of days to optimize",
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# CSV DATA ACCESS
# ---------------------------------------------------------

def read_csv(name: str) -> pd.DataFrame:
    """Read a generated CSV dataset."""

    path = DATA / f"{name}.csv"

    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Dataset missing: {path}. "
                "Run the data generator first."
            ),
        )

    return pd.read_csv(path)


def load_optimizer_data(start_date: datetime, days: int) -> dict:
    """
    Load source CSV files and prepare the five DataFrames
    expected by the CP-SAT optimizer.

    Ground-truth anomaly labels are deliberately excluded.
    """

    horizon_end = start_date + timedelta(days=days)

    # -----------------------------
    # EMPLOYEES
    # -----------------------------

    employees = read_csv("employee")

    employees = employees[
        employees["employment_status"].eq("ACTIVE")
    ].copy()

    employee_ids = set(employees["employee_id"])

    # -----------------------------
    # SHIFTS
    # -----------------------------

    shifts = read_csv("shift")

    shifts["start_at"] = pd.to_datetime(
        shifts["start_at"],
        errors="raise",
    )

    shifts["end_at"] = pd.to_datetime(
        shifts["end_at"],
        errors="raise",
    )

    # Include shifts overlapping the requested horizon,
    # including overnight shifts starting before the horizon.

    shifts = shifts[
        shifts["status"].eq("PLANNED")
        & (shifts["start_at"] < horizon_end)
        & (shifts["end_at"] > start_date)
    ].copy()

    shift_ids = set(shifts["shift_id"])

    # -----------------------------
    # COVERAGE REQUIREMENTS
    # -----------------------------

    requirements = read_csv("coverage_requirement")

    requirements = requirements[
        requirements["shift_id"].isin(shift_ids)
    ].copy()

    # -----------------------------
    # EMPLOYEE SKILLS
    # -----------------------------

    skills = read_csv("employee_skill")

    skills["effective_from"] = pd.to_datetime(
        skills["effective_from"],
        errors="coerce",
    )

    skills["effective_to"] = pd.to_datetime(
        skills["effective_to"],
        errors="coerce",
    )

    skills = skills[
        skills["employee_id"].isin(employee_ids)
    ].copy()

    # -----------------------------
    # APPROVED LEAVES
    # -----------------------------

    leaves = read_csv("leave_request")

    leaves["start_date"] = pd.to_datetime(
        leaves["start_date"],
        errors="raise",
    )

    leaves["end_date"] = pd.to_datetime(
        leaves["end_date"],
        errors="raise",
    )

    leaves = leaves[
        leaves["employee_id"].isin(employee_ids)
        & leaves["status"].eq("APPROVED")
        & (leaves["start_date"] < horizon_end)
        & (
            leaves["end_date"]
            >= start_date - timedelta(days=1)
        )
    ].copy()

    return {
        "employees": employees[
            [
                "employee_id",
                "team_id",
                "weekly_hours_cap",
            ]
        ].copy(),

        "shifts": shifts[
            [
                "shift_id",
                "team_id",
                "start_at",
                "end_at",
            ]
        ].copy(),

        "requirements": requirements[
            [
                "requirement_id",
                "shift_id",
                "skill_id",
                "minimum_staff",
            ]
        ].copy(),

        "skills": skills[
            [
                "employee_id",
                "skill_id",
                "effective_from",
                "effective_to",
            ]
        ].copy(),

        "leaves": leaves[
            [
                "employee_id",
                "start_date",
                "end_date",
            ]
        ].copy(),
    }


# ---------------------------------------------------------
# JSON SERIALIZATION
# ---------------------------------------------------------

def dataframe_records(df: pd.DataFrame) -> list:
    """Convert a DataFrame into JSON-safe records."""

    if df.empty:
        return []

    return json.loads(
        df.to_json(
            orient="records",
            date_format="iso",
        )
    )


# ---------------------------------------------------------
# INDEPENDENT SCHEDULE VALIDATION
# ---------------------------------------------------------

def audit_optimized_assignments(
    assignments: list,
    data: dict,
) -> dict:
    """
    Independently validate the optimizer's selected assignments.

    Checks:
    1. Overlapping shifts
    2. Minimum rest period
    3. Employee-specific weekly hours caps
    4. Approved leave overlaps
    5. Skill validity on assignment date
    6. Cross-team assignment count

    This function does not use ground_truth.csv.
    """

    if not assignments:
        return {
            "overlap_conflicts": 0,
            "rest_period_violations": 0,
            "overtime_assignments": 0,
            "overtime_employee_weeks": 0,
            "approved_leave_overlaps": 0,
            "invalid_skill_assignments": 0,
            "cross_team_assignments": 0,
        }

    df = pd.DataFrame(assignments).copy()

    df["start_at"] = pd.to_datetime(df["start_at"])
    df["end_at"] = pd.to_datetime(df["end_at"])

    # -----------------------------
    # EMPLOYEE WEEKLY HOURS CAPS
    # -----------------------------

    employee_caps = dict(
        zip(
            data["employees"]["employee_id"],
            pd.to_numeric(
                data["employees"]["weekly_hours_cap"],
                errors="coerce",
            ),
        )
    )

    iso = df["start_at"].dt.isocalendar()

    df["week_year"] = iso["year"].astype(int)
    df["week_number"] = iso["week"].astype(int)

    overtime_assignments = 0
    overtime_employee_weeks = 0

    for (
        employee_id,
        _week_year,
        _week_number,
    ), group in df.groupby(
        [
            "employee_id",
            "week_year",
            "week_number",
        ]
    ):

        cap = employee_caps.get(employee_id)

        if cap is None or pd.isna(cap):
            continue

        used_hours = (
            group["end_at"] - group["start_at"]
        ).dt.total_seconds().sum() / 3600

        if used_hours > float(cap) + 1e-9:
            overtime_employee_weeks += 1
            overtime_assignments += len(group)

    # -----------------------------
    # OVERLAP AND REST VALIDATION
    # -----------------------------

    overlap_conflicts = 0
    rest_period_violations = 0

    minimum_rest = timedelta(hours=11)

    for _, group in df.groupby("employee_id"):

        rows = list(
            group.sort_values("start_at").itertuples()
        )

        for i in range(len(rows)):

            first = rows[i]

            for j in range(i + 1, len(rows)):

                second = rows[j]

                # Check interval overlap.
                if (
                    first.start_at < second.end_at
                    and second.start_at < first.end_at
                ):
                    overlap_conflicts += 1

                # Intervals are sorted by start time.
                # If there is no overlap, check rest duration.
                elif first.end_at <= second.start_at:

                    rest_duration = (
                        second.start_at - first.end_at
                    )

                    if rest_duration < minimum_rest:
                        rest_period_violations += 1

    # -----------------------------
    # SKILL VALIDITY VALIDATION
    # -----------------------------

    skill_map = {}

    for row in data["skills"].itertuples(index=False):

        key = (
            row.employee_id,
            row.skill_id,
        )

        skill_map.setdefault(key, []).append(
            (
                row.effective_from,
                row.effective_to,
            )
        )

    invalid_skill_assignments = 0

    for row in df.itertuples(index=False):

        key = (
            row.employee_id,
            row.assigned_skill_id,
        )

        shift_date = row.start_at.date()

        valid = False

        for effective_from, effective_to in skill_map.get(key, []):

            start_date = (
                None
                if pd.isna(effective_from)
                else pd.Timestamp(effective_from).date()
            )

            end_date = (
                None
                if pd.isna(effective_to)
                else pd.Timestamp(effective_to).date()
            )

            starts_valid = (
                start_date is None
                or start_date <= shift_date
            )

            ends_valid = (
                end_date is None
                or shift_date <= end_date
            )

            if starts_valid and ends_valid:
                valid = True
                break

        if not valid:
            invalid_skill_assignments += 1

    # -----------------------------
    # APPROVED LEAVE VALIDATION
    # -----------------------------

    leave_map = {}

    for row in data["leaves"].itertuples(index=False):

        leave_start = pd.Timestamp(
            row.start_date
        ).date()

        leave_end = pd.Timestamp(
            row.end_date
        ).date()

        start_at = datetime.combine(
            leave_start,
            datetime.min.time(),
        )

        # Leave end date is inclusive.
        end_at = datetime.combine(
            leave_end + timedelta(days=1),
            datetime.min.time(),
        )

        leave_map.setdefault(
            row.employee_id,
            [],
        ).append(
            (start_at, end_at)
        )

    approved_leave_overlaps = 0

    for row in df.itertuples(index=False):

        for leave_start, leave_end in leave_map.get(
            row.employee_id,
            [],
        ):

            if (
                row.start_at < leave_end
                and row.end_at > leave_start
            ):
                approved_leave_overlaps += 1
                break

    # -----------------------------
    # CROSS-TEAM ASSIGNMENTS
    # -----------------------------

    cross_team_assignments = int(
        df["cross_team_assignment"].astype(bool).sum()
    )

    return {
        "overlap_conflicts": overlap_conflicts,
        "rest_period_violations": rest_period_violations,
        "overtime_assignments": overtime_assignments,
        "overtime_employee_weeks": overtime_employee_weeks,
        "approved_leave_overlaps": approved_leave_overlaps,
        "invalid_skill_assignments": invalid_skill_assignments,
        "cross_team_assignments": cross_team_assignments,
    }


# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------

@app.get("/health")
def health():

    return {
        "status": "ok",
        "data_dir": str(DATA),
        "data_ready": (DATA / "employee.csv").exists(),
    }


# ---------------------------------------------------------
# DASHBOARD SUMMARY
# ---------------------------------------------------------

@app.get("/api/v1/summary")
def summary():

    employees = read_csv("employee")
    assignments = read_csv("shift_assignment")
    leaves = read_csv("leave_request")
    requirements = read_csv("coverage_requirement")

    return {
        "employees": int(len(employees)),
        "teams": int(employees["team_id"].nunique()),
        "assignments": int(len(assignments)),
        "leave_requests": int(len(leaves)),
        "coverage_requirements": int(len(requirements)),
    }


# ---------------------------------------------------------
# EMPLOYEE API
# ---------------------------------------------------------

@app.get("/api/v1/employees")
def employees(limit: int = 100):

    return (
        read_csv("employee")
        .head(min(max(limit, 1), 500))
        .fillna("")
        .to_dict(orient="records")
    )


# ---------------------------------------------------------
# SHIFT API
# ---------------------------------------------------------

@app.get("/api/v1/shifts")
def shifts(limit: int = 100):

    return (
        read_csv("shift_assignment")
        .head(min(max(limit, 1), 500))
        .fillna("")
        .to_dict(orient="records")
    )


# ---------------------------------------------------------
# ANOMALY / EXCEPTION API
# ---------------------------------------------------------

@app.get("/api/v1/exceptions")
def exceptions():

    gt = DATA / "ground_truth.csv"

    if not gt.exists():

        return {
            "count": 0,
            "items": [],
            "note": (
                "Ground truth is evaluation-only; "
                "never use it as optimizer input."
            ),
        }

    df = pd.read_csv(gt).fillna("")

    return {
        "count": int(len(df)),
        "items": df.to_dict(orient="records"),
    }


# ---------------------------------------------------------
# SCHEDULE GENERATION API
# ---------------------------------------------------------

@app.post("/api/v1/schedule/generate")
def generate_schedule(request: GenerateRequest):
    """
    Generate an optimized workforce schedule using CP-SAT.

    Process:
    1. Validate requested date.
    2. Load CSV source data.
    3. Filter requested scheduling horizon.
    4. Run CP-SAT optimizer.
    5. Generate coverage analysis.
    6. Generate coverage diagnostics.
    7. Independently validate assignments.
    8. Return JSON results to the frontend.
    """

    try:

        # -----------------------------
        # VALIDATE DATE
        # -----------------------------

        start_date = datetime.strptime(
            request.start_date,
            "%Y-%m-%d",
        )

        horizon_end = start_date + timedelta(
            days=request.days
        )

        # -----------------------------
        # IMPORT OPTIMIZER
        # -----------------------------

        from app.optimizer import (
            optimize_schedule,
            build_coverage_analysis,
            build_coverage_diagnostics,
        )

        # -----------------------------
        # LOAD CSV DATA
        # -----------------------------

        data = load_optimizer_data(
            start_date,
            request.days,
        )

        # -----------------------------
        # HANDLE EMPTY HORIZON
        # -----------------------------

        if (
            data["shifts"].empty
            or data["requirements"].empty
        ):

            audit = audit_optimized_assignments(
                [],
                data,
            )

            return {
                "requested_start": request.start_date,
                "requested_days": request.days,
                "requested_end": horizon_end.date().isoformat(),

                "assignment_count": 0,
                "overlap_conflicts": 0,
                "overtime_assignments": 0,
                "coverage_gaps": 0,

                "rest_period_violations": 0,
                "approved_leave_overlaps": 0,
                "invalid_skill_assignments": 0,
                "overtime_employee_weeks": 0,
                "cross_team_assignments": 0,

                "independent_validation": "PASS",

                "hard_rules": [
                    "no_overlapping_shifts",
                    "no_approved_leave_overlap",
                    "required_skill_present",
                    "weekly_hours_cap",
                    "minimum_rest_period",
                ],

                "solver_status": "NOT_RUN_NO_REQUIREMENTS",
                "coverage_optimal": False,

                "uncovered_requirements": 0,
                "total_uncovered_positions": 0,

                "assignments": [],
                "gaps": [],
                "coverage_analysis": [],
                "diagnostics": [],
            }

        # -----------------------------
        # RUN CP-SAT OPTIMIZER
        # -----------------------------

        assignments, gaps, status = optimize_schedule(data)

        # -----------------------------
        # COVERAGE ANALYSIS
        # -----------------------------

        coverage_analysis = build_coverage_analysis(
            data,
            assignments,
            gaps,
        )

        # -----------------------------
        # COVERAGE DIAGNOSTICS
        # -----------------------------

        diagnostics = build_coverage_diagnostics(
            data,
            assignments,
            gaps,
        )

        # -----------------------------
        # TOTAL UNCOVERED POSITIONS
        # -----------------------------

        total_uncovered = sum(
            int(row["uncovered_staff"])
            for row in gaps
        )

        # -----------------------------
        # INDEPENDENT VALIDATION
        # -----------------------------

        audit = audit_optimized_assignments(
            assignments,
            data,
        )

        validation_checks = [
            "overlap_conflicts",
            "rest_period_violations",
            "overtime_assignments",
            "approved_leave_overlaps",
            "invalid_skill_assignments",
        ]

        validation_passed = all(
            audit[key] == 0
            for key in validation_checks
        )

        # -----------------------------
        # FINAL API RESPONSE
        # -----------------------------

        return {

            # Request information.
            "requested_start": request.start_date,
            "requested_days": request.days,
            "requested_end": horizon_end.date().isoformat(),

            # Existing React dashboard metrics.
            "assignment_count": len(assignments),
            "overlap_conflicts": audit["overlap_conflicts"],
            "overtime_assignments": audit["overtime_assignments"],
            "coverage_gaps": total_uncovered,

            # Independent validation metrics.
            "rest_period_violations": (
                audit["rest_period_violations"]
            ),

            "approved_leave_overlaps": (
                audit["approved_leave_overlaps"]
            ),

            "invalid_skill_assignments": (
                audit["invalid_skill_assignments"]
            ),

            "overtime_employee_weeks": (
                audit["overtime_employee_weeks"]
            ),

            "cross_team_assignments": (
                audit["cross_team_assignments"]
            ),

            "independent_validation": (
                "PASS"
                if validation_passed
                else "FAIL"
            ),

            # Rules enforced by the optimizer.
            "hard_rules": [
                "no_overlapping_shifts",
                "no_approved_leave_overlap",
                "required_skill_present",
                "weekly_hours_cap",
                "minimum_rest_period",
            ],

            # Solver information.
            "solver_status": status,

            "coverage_optimal": (
                "COVERAGE_OPTIMAL" in status
            ),

            # Coverage information.
            "uncovered_requirements": len(gaps),

            "total_uncovered_positions": total_uncovered,

            # Generated schedule.
            "assignments": dataframe_records(
                pd.DataFrame(assignments)
            ),

            # Uncovered staffing positions.
            "gaps": gaps,

            # Explainable coverage report.
            "coverage_analysis": dataframe_records(
                coverage_analysis
            ),

            # Diagnostics.
            "diagnostics": dataframe_records(
                diagnostics
            ),
        }

    # -----------------------------
    # ERROR HANDLING
    # -----------------------------

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid scheduling request or optimizer input: {exc}"
            ),
        ) from exc

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Schedule optimization failed: {str(exc)}"
            ),
        ) from exc
