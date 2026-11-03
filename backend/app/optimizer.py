import math
import argparse
import os
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import mysql.connector
import pandas as pd
from ortools.sat.python import cp_model


PROJECT_ROOT = Path(__file__).resolve().parents[2]

REST_HOURS = 11
PHASE_1_TIME_LIMIT = 60
PHASE_2_TIME_LIMIT = 60
NUM_SEARCH_WORKERS = 8


def load_cross_team_rules():
    """Load explicit home-team -> permitted destination-team rules.

    Example environment variable:
      YOTTAFLEX_CROSS_TEAM_RULES={"TEAM-0002":["TEAM-0001"]}

    An unset/empty value disables cross-team assignments. This is a
    conservative default: no cross-team move is allowed without approval.
    """
    raw_rules = os.getenv("YOTTAFLEX_CROSS_TEAM_RULES", "").strip()
    if not raw_rules:
        return {}

    try:
        parsed = json.loads(raw_rules)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "YOTTAFLEX_CROSS_TEAM_RULES must be valid JSON, e.g. "
            '{"TEAM-0002":["TEAM-0001"]}'
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError("Cross-team rules must be a JSON object.")

    rules = {}
    for home_team, destination_teams in parsed.items():
        if not isinstance(home_team, str) or not isinstance(destination_teams, list):
            raise ValueError(
                "Each cross-team rule must map a home-team string to a list of destination-team strings."
            )
        if not all(isinstance(team_id, str) and team_id for team_id in destination_teams):
            raise ValueError("Destination team IDs must be non-empty strings.")
        rules[home_team] = set(destination_teams)

    return rules


def is_team_assignment_allowed(employee, destination_team_id, cross_team_rules):
    """Check same-team assignment or an explicitly approved cross-team route."""
    home_team_id = employee["team_id"]
    return (
        home_team_id == destination_team_id
        or destination_team_id in cross_team_rules.get(home_team_id, set())
    )


def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "yottaflex_workforce"),
    )


def fetch_data():
    connection = get_connection()

    queries = {
        "employees": """
            SELECT employee_id, team_id, weekly_hours_cap
            FROM employee
            WHERE employment_status = 'ACTIVE'
        """,
        "shifts": """
            SELECT shift_id, team_id, start_at, end_at
            FROM shift
            WHERE status = 'PLANNED'
            ORDER BY start_at
        """,
        "requirements": """
            SELECT requirement_id, shift_id, skill_id, minimum_staff
            FROM coverage_requirement
        """,
        "skills": """
            SELECT employee_id, skill_id, effective_from, effective_to
            FROM employee_skill
        """,
        "leaves": """
            SELECT employee_id, start_date, end_date
            FROM leave_request
            WHERE status = 'APPROVED'
        """,
    }

    try:
        result = {}

        for name, query in queries.items():
            result[name] = pd.read_sql(query, connection)

        return result

    finally:
        connection.close()


def prepare_data(data):
    employees = data["employees"].to_dict("records")
    shifts = data["shifts"].to_dict("records")
    requirements = data["requirements"].to_dict("records")
    skills = data["skills"].to_dict("records")
    leaves = data["leaves"].to_dict("records")

    # Keep each employee skill together with its validity period.
    skill_map = defaultdict(list)

    for row in skills:
        skill_map[row["employee_id"]].append({
            "skill_id": row["skill_id"],
            "effective_from": row["effective_from"],
            "effective_to": row["effective_to"],
        })

    leave_map = defaultdict(list)

    for row in leaves:
        leave_map[row["employee_id"]].append(
            (row["start_date"], row["end_date"])
        )

    requirements_by_shift = defaultdict(list)

    for row in requirements:
        requirements_by_shift[row["shift_id"]].append(row)

    return (
        employees,
        shifts,
        requirements_by_shift,
        skill_map,
        leave_map,
    )


def overlaps(start_a, end_a, start_b, end_b):
    return start_a < end_b and start_b < end_a


def as_date(value):
    """Convert database/Pandas date values to date; preserve NULL as None."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "date") and not isinstance(value, type(value.date())):
        # Handles pandas Timestamp without affecting datetime.date values.
        return value.date()
    return value


def has_valid_skill(employee_id, skill_id, shift_start, skill_map):
    """Return True only when the employee's skill is valid on shift date.

    effective_from and effective_to are treated as inclusive dates.
    A NULL boundary is treated as open-ended.
    """
    shift_date = as_date(shift_start)

    for record in skill_map[employee_id]:
        if record["skill_id"] != skill_id:
            continue

        effective_from = as_date(record["effective_from"])
        effective_to = as_date(record["effective_to"])

        starts_valid = effective_from is None or effective_from <= shift_date
        ends_valid = effective_to is None or shift_date <= effective_to

        if starts_valid and ends_valid:
            return True

    return False


def is_on_leave(employee_id, shift_start, shift_end, leave_map):
    for leave_start, leave_end in leave_map[employee_id]:

        if isinstance(leave_start, datetime):
            leave_start = leave_start.date()

        if isinstance(leave_end, datetime):
            leave_end = leave_end.date()

        leave_start = datetime.combine(
            leave_start,
            datetime.min.time()
        )

        leave_end = datetime.combine(
            leave_end,
            datetime.max.time()
        )

        if overlaps(
            shift_start,
            shift_end,
            leave_start,
            leave_end,
        ):
            return True

    return False


def optimize_schedule(data):
    (
        employees,
        shifts,
        requirements_by_shift,
        skill_map,
        leave_map,
    ) = prepare_data(data)

    cross_team_rules = load_cross_team_rules()
    print("Cross-team staffing policy:")
    if cross_team_rules:
        for home_team, destination_teams in sorted(cross_team_rules.items()):
            print(f"  {home_team} may support: {', '.join(sorted(destination_teams))}")
    else:
        print("  Disabled (no approved cross-team routes configured).")

    model = cp_model.CpModel()
    candidates = {}
    employee_shift_vars = defaultdict(list)
    requirement_vars = defaultdict(list)
    requirement_by_id = {}
    shift_by_id = {shift["shift_id"]: shift for shift in shifts}

    all_requirements = [
        req for reqs in requirements_by_shift.values() for req in reqs
    ]
    requirement_by_id = {req["requirement_id"]: req for req in all_requirements}

    # Candidate generation: same-team by default; cross-team only through
    # an explicit home-team -> destination-team permission rule.
    for shift in shifts:
        shift_id = shift["shift_id"]
        shift_start = shift["start_at"]
        shift_end = shift["end_at"]

        for requirement in requirements_by_shift[shift_id]:
            requirement_id = requirement["requirement_id"]
            required_skill = requirement["skill_id"]

            for employee in employees:
                employee_id = employee["employee_id"]

                if not is_team_assignment_allowed(
                    employee, shift["team_id"], cross_team_rules
                ):
                    continue

                if not has_valid_skill(
                    employee_id, required_skill, shift_start, skill_map
                ):
                    continue

                if is_on_leave(
                    employee_id, shift_start, shift_end, leave_map
                ):
                    continue

                key = (requirement_id, employee_id)
                if key not in candidates:
                    variable = model.NewBoolVar(
                        f"assign_{requirement_id}_{employee_id}"
                    )
                    candidates[key] = variable
                    employee_shift_vars[employee_id].append((shift, variable))

                requirement_vars[requirement_id].append(candidates[key])

    # Every requirement is either staffed or explicitly recorded as uncovered.
    uncovered = {}
    for requirement in all_requirements:
        requirement_id = requirement["requirement_id"]
        minimum_staff = int(requirement["minimum_staff"])
        uncovered[requirement_id] = model.NewIntVar(
            0, minimum_staff, f"uncovered_{requirement_id}"
        )
        model.Add(
            sum(requirement_vars[requirement_id]) + uncovered[requirement_id]
            == minimum_staff
        )

    # A person cannot work overlapping shifts or violate the minimum rest gap.
    for employee_id, assignments in employee_shift_vars.items():
        for i in range(len(assignments)):
            shift_a, var_a = assignments[i]
            for j in range(i + 1, len(assignments)):
                shift_b, var_b = assignments[j]
                if overlaps(
                    shift_a["start_at"], shift_a["end_at"],
                    shift_b["start_at"], shift_b["end_at"],
                ):
                    model.Add(var_a + var_b <= 1)
                elif (
                    shift_a["end_at"] <= shift_b["start_at"]
                    and shift_b["start_at"]
                    < shift_a["end_at"] + timedelta(hours=REST_HOURS)
                ):
                    model.Add(var_a + var_b <= 1)
                elif (
                    shift_b["end_at"] <= shift_a["start_at"]
                    and shift_a["start_at"]
                    < shift_b["end_at"] + timedelta(hours=REST_HOURS)
                ):
                    model.Add(var_a + var_b <= 1)

    # Weekly contracted-hours caps apply across home-team and borrowed shifts.
    for employee in employees:
        employee_id = employee["employee_id"]
        weekly_cap_minutes = int(
            round(float(employee["weekly_hours_cap"]) * 60)
        )
        weekly_vars = defaultdict(list)
        for shift, variable in employee_shift_vars[employee_id]:
            week_key = shift["start_at"].date().isocalendar()[:2]
            duration_minutes = int(
                (shift["end_at"] - shift["start_at"]).total_seconds() // 60
            )
            weekly_vars[week_key].append((variable, duration_minutes))

        for entries in weekly_vars.values():
            model.Add(
                sum(variable * minutes for variable, minutes in entries)
                <= weekly_cap_minutes
            )

    total_uncovered = sum(uncovered.values())

    # Fairness is measured against employees' home teams. Borrowed shifts
    # count toward the borrowed employee's own weekly workload.
    cap_minutes_by_employee = {
        employee["employee_id"]: int(
            round(float(employee["weekly_hours_cap"]) * 60)
        )
        for employee in employees
    }
    employee_team = {
        employee["employee_id"]: employee["team_id"]
        for employee in employees
    }

    if shifts:
        period_start = min(s["start_at"].date() for s in shifts)
        period_end = max(s["start_at"].date() for s in shifts)
    else:
        period_start = period_end = None

    shifts_by_week = defaultdict(list)
    for shift in shifts:
        week_key = shift["start_at"].date().isocalendar()[:2]
        shifts_by_week[week_key].append(shift)

    days_in_week = {}
    for week_key in shifts_by_week:
        week_start = datetime.fromisocalendar(
            week_key[0], week_key[1], 1
        ).date()
        week_end = week_start + timedelta(days=6)
        overlap_start = max(period_start, week_start)
        overlap_end = min(period_end, week_end)
        days_in_week[week_key] = (overlap_end - overlap_start).days + 1

    team_week_employee_vars = defaultdict(lambda: defaultdict(list))
    for employee_id, entries in employee_shift_vars.items():
        home_team_id = employee_team[employee_id]
        for shift, variable in entries:
            week_key = shift["start_at"].date().isocalendar()[:2]
            duration_minutes = int(
                (shift["end_at"] - shift["start_at"]).total_seconds() // 60
            )
            team_week_employee_vars[(home_team_id, week_key)][employee_id].append(
                (variable, duration_minutes)
            )

    denominators = [
        cap_minutes_by_employee[employee_id] * days_in_week[week_key]
        for (_, week_key), employee_entries in team_week_employee_vars.items()
        for employee_id in employee_entries
    ]
    normalization_factor = math.lcm(*denominators) if denominators else 1

    weekly_unfairness_terms = []
    for (home_team_id, week_key), employee_entries in team_week_employee_vars.items():
        week_days = days_in_week[week_key]
        normalized_workloads = []
        upper_bounds = []

        for employee_id, entries in sorted(employee_entries.items()):
            multiplier = (
                7 * normalization_factor
                // (cap_minutes_by_employee[employee_id] * week_days)
            )
            workload = sum(
                variable * minutes * multiplier
                for variable, minutes in entries
            )
            normalized_workloads.append(workload)
            upper_bounds.append(
                sum(minutes * multiplier for _, minutes in entries)
            )

        group_upper_bound = max(upper_bounds, default=0)
        if not normalized_workloads:
            continue

        max_workload = model.NewIntVar(
            0, group_upper_bound,
            f"max_weekly_workload_{home_team_id}_{week_key[0]}_{week_key[1]}"
        )
        min_workload = model.NewIntVar(
            0, group_upper_bound,
            f"min_weekly_workload_{home_team_id}_{week_key[0]}_{week_key[1]}"
        )
        for workload in normalized_workloads:
            model.Add(workload <= max_workload)
            model.Add(workload >= min_workload)
        weekly_unfairness_terms.append(max_workload - min_workload)

    total_weekly_unfairness = (
        sum(weekly_unfairness_terms) if weekly_unfairness_terms else 0
    )

    # PHASE 1: coverage only. This avoids a large weighted objective and
    # establishes the best uncovered-position count found by the solver.
    model.Minimize(total_uncovered)
    coverage_solver = cp_model.CpSolver()
    coverage_solver.parameters.max_time_in_seconds = PHASE_1_TIME_LIMIT
    coverage_solver.parameters.num_search_workers = NUM_SEARCH_WORKERS
    coverage_status = coverage_solver.Solve(model)

    print("Phase 1 - coverage status:", coverage_solver.StatusName(coverage_status))
    if coverage_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(
            "Coverage optimization did not find a feasible solution: "
            f"{coverage_solver.StatusName(coverage_status)}"
        )

    best_uncovered = int(round(coverage_solver.Value(total_uncovered)))
    coverage_proven_optimal = coverage_status == cp_model.OPTIMAL
    print("Best uncovered staff count:", best_uncovered)
    print("Coverage minimum proven:", coverage_proven_optimal)

    # PHASE 2: lock coverage to the Phase 1 incumbent, then optimize fairness.
    model.Add(total_uncovered == best_uncovered)
    model.Minimize(total_weekly_unfairness)

    fairness_solver = cp_model.CpSolver()
    fairness_solver.parameters.max_time_in_seconds = PHASE_2_TIME_LIMIT
    fairness_solver.parameters.num_search_workers = NUM_SEARCH_WORKERS
    fairness_status = fairness_solver.Solve(model)

    print("Phase 2 - fairness status:", fairness_solver.StatusName(fairness_status))
    if fairness_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        solver = fairness_solver
        final_status = (
            f"COVERAGE_{coverage_solver.StatusName(coverage_status)}; "
            f"FAIRNESS_{fairness_solver.StatusName(fairness_status)}"
        )
        print(f"Fairness objective value: {fairness_solver.ObjectiveValue():.0f}")
        print(f"Fairness best bound: {fairness_solver.BestObjectiveBound():.0f}")
    else:
        # Preserve the valid Phase 1 coverage solution if Phase 2 times out
        # before finding a feasible fairness-improved schedule.
        solver = coverage_solver
        final_status = (
            f"COVERAGE_{coverage_solver.StatusName(coverage_status)}; "
            "FAIRNESS_PHASE2_NO_FEASIBLE_SOLUTION"
        )
        print("WARNING: Phase 2 found no feasible solution; using Phase 1 schedule.")

    output = []
    for (requirement_id, employee_id), variable in candidates.items():
        if solver.Value(variable) != 1:
            continue
        requirement = requirement_by_id[requirement_id]
        shift = shift_by_id[requirement["shift_id"]]
        home_team_id = next(
            employee["team_id"] for employee in employees
            if employee["employee_id"] == employee_id
        )
        output.append({
            "requirement_id": requirement_id,
            "shift_id": shift["shift_id"],
            "employee_id": employee_id,
            "employee_home_team_id": home_team_id,
            "shift_team_id": shift["team_id"],
            "cross_team_assignment": home_team_id != shift["team_id"],
            "assigned_skill_id": requirement["skill_id"],
            "start_at": shift["start_at"],
            "end_at": shift["end_at"],
            "status": "ASSIGNED",
        })

    uncovered_rows = []
    for requirement_id, variable in uncovered.items():
        gap = solver.Value(variable)
        if gap > 0:
            uncovered_rows.append({
                "requirement_id": requirement_id,
                "uncovered_staff": gap,
            })

    print("Cross-team assignments:", sum(row["cross_team_assignment"] for row in output))
    print("Coverage minimum proven:", coverage_proven_optimal)
    return output, uncovered_rows, final_status

def build_coverage_analysis(data, assignments, gaps):
    requirements = data["requirements"][
        ["requirement_id", "shift_id", "skill_id", "minimum_staff"]
    ].copy()

    shifts = data["shifts"][
        ["shift_id", "team_id", "start_at", "end_at"]
    ].copy()

    # Count assignments for every requirement.
    if assignments:
        assigned_counts = (
            pd.DataFrame(assignments)
            .groupby("requirement_id")
            .size()
            .reset_index(name="assigned_staff")
        )
    else:
        assigned_counts = pd.DataFrame(
            columns=["requirement_id", "assigned_staff"]
        )

    # Convert uncovered positions into a DataFrame.
    gaps_df = pd.DataFrame(
        gaps,
        columns=["requirement_id", "uncovered_staff"]
    )

    # Combine requirement, shift, assignment and gap information.
    analysis = requirements.merge(
        shifts,
        on="shift_id",
        how="left"
    )

    analysis = analysis.merge(
        assigned_counts,
        on="requirement_id",
        how="left"
    )

    analysis = analysis.merge(
        gaps_df,
        on="requirement_id",
        how="left"
    )

    analysis["assigned_staff"] = (
        analysis["assigned_staff"].fillna(0).astype(int)
    )

    analysis["uncovered_staff"] = (
        analysis["uncovered_staff"].fillna(0).astype(int)
    )

    analysis["required_staff"] = analysis["minimum_staff"]

    analysis["coverage_status"] = analysis.apply(
        lambda row: (
            "FULLY_COVERED"
            if row["uncovered_staff"] == 0
            else "PARTIALLY_COVERED"
        ),
        axis=1
    )

    analysis["reason"] = analysis["uncovered_staff"].apply(
        lambda value: (
            "UNFILLED_AFTER_SCHEDULING_CONSTRAINTS"
            if value > 0
            else "NONE"
        )
    )

    analysis = analysis[
        [
            "requirement_id",
            "shift_id",
            "team_id",
            "skill_id",
            "start_at",
            "end_at",
            "required_staff",
            "assigned_staff",
            "uncovered_staff",
            "coverage_status",
            "reason",
        ]
    ]

    return analysis



def build_coverage_diagnostics(data, assignments, gaps):
    """Explain likely blockers for each requirement with uncovered positions.

    Diagnostics are evaluated against the final optimized schedule. Skill
    qualification is checked against effective_from/effective_to on the shift
    date. Results are evidence of constraints affecting the schedule, not
    proof that one constraint was the sole cause of every uncovered position.
    """
    employees, shifts, requirements_by_shift, skill_map, leave_map = prepare_data(data)

    cross_team_rules = load_cross_team_rules()
    shift_by_id = {s["shift_id"]: s for s in shifts}
    requirement_by_id = {
        req["requirement_id"]: req
        for reqs in requirements_by_shift.values()
        for req in reqs
    }

    assignments_by_employee = defaultdict(list)
    weekly_minutes_by_employee = defaultdict(lambda: defaultdict(int))

    for assignment in assignments:
        employee_id = assignment["employee_id"]
        start = assignment["start_at"]
        end = assignment["end_at"]
        assignments_by_employee[employee_id].append((start, end))
        week_key = start.date().isocalendar()[:2]
        duration = int((end - start).total_seconds() // 60)
        weekly_minutes_by_employee[employee_id][week_key] += duration

    rows = []

    for gap in gaps:
        requirement_id = gap["requirement_id"]
        requirement = requirement_by_id[requirement_id]
        shift = shift_by_id[requirement["shift_id"]]
        required_skill = requirement["skill_id"]
        shift_start = shift["start_at"]
        shift_end = shift["end_at"]
        target_week = shift_start.date().isocalendar()[:2]
        target_minutes = int((shift_end - shift_start).total_seconds() // 60)

        # Candidate pool follows the exact same approved cross-team policy
        # as the optimizer; home-team employees are always included.
        team_employees = [
            employee for employee in employees
            if is_team_assignment_allowed(
                employee, shift["team_id"], cross_team_rules
            )
        ]
        qualified = [
            employee for employee in team_employees
            if has_valid_skill(
                employee["employee_id"], required_skill, shift_start, skill_map
            )
        ]
        on_leave = [
            employee for employee in qualified
            if is_on_leave(
                employee["employee_id"], shift_start, shift_end, leave_map
            )
        ]

        available_after_leave = [e for e in qualified if e not in on_leave]
        overlap_count = 0
        rest_count = 0
        weekly_cap_count = 0
        eligible_count = 0

        for employee in available_after_leave:
            employee_id = employee["employee_id"]
            reasons = set()

            for assigned_start, assigned_end in assignments_by_employee[employee_id]:
                if overlaps(shift_start, shift_end, assigned_start, assigned_end):
                    reasons.add("SHIFT_OVERLAP")
                elif (
                    assigned_end <= shift_start
                    and shift_start < assigned_end + timedelta(hours=REST_HOURS)
                ) or (
                    shift_end <= assigned_start
                    and assigned_start < shift_end + timedelta(hours=REST_HOURS)
                ):
                    reasons.add("MINIMUM_REST_PERIOD")

            if "SHIFT_OVERLAP" in reasons:
                overlap_count += 1
            if "MINIMUM_REST_PERIOD" in reasons:
                rest_count += 1

            weekly_cap = int(round(float(employee["weekly_hours_cap"]) * 60))
            already_worked = weekly_minutes_by_employee[employee_id][target_week]
            if already_worked + target_minutes > weekly_cap:
                reasons.add("WEEKLY_HOURS_CAP")
                weekly_cap_count += 1

            if not reasons:
                eligible_count += 1

        if not qualified:
            diagnostic = "INSUFFICIENT_QUALIFIED_EMPLOYEES"
        elif not available_after_leave:
            diagnostic = "QUALIFIED_EMPLOYEES_ON_APPROVED_LEAVE"
        else:
            blockers = []
            if overlap_count:
                blockers.append("SHIFT_OVERLAP")
            if rest_count:
                blockers.append("MINIMUM_REST_PERIOD")
            if weekly_cap_count:
                blockers.append("WEEKLY_HOURS_CAP")
            if eligible_count:
                blockers.append("ELIGIBLE_CANDIDATE_NOT_SELECTED_OR_SOLVER_LIMIT")
            diagnostic = ";".join(blockers) if blockers else "NO_BLOCKER_IDENTIFIED"

        rows.append({
            "requirement_id": requirement_id,
            "shift_id": shift["shift_id"],
            "team_id": shift["team_id"],
            "skill_id": required_skill,
            "required_staff": int(requirement["minimum_staff"]),
            "uncovered_staff": int(gap["uncovered_staff"]),
            "team_employee_count": sum(
                employee["team_id"] == shift["team_id"]
                for employee in employees
            ),
            "cross_team_candidate_count": sum(
                employee["team_id"] != shift["team_id"]
                for employee in team_employees
            ),
            "candidate_policy_pool_count": len(team_employees),
            "qualified_employee_count": len(qualified),
            "qualified_on_approved_leave": len(on_leave),
            "qualified_available_after_leave": len(available_after_leave),
            "blocked_by_overlap": overlap_count,
            "blocked_by_rest_period": rest_count,
            "blocked_by_weekly_hours_cap": weekly_cap_count,
            "apparently_eligible_candidates": eligible_count,
            "diagnostic": diagnostic,
        })

    return pd.DataFrame(rows)

def main():
    parser = argparse.ArgumentParser(
        description="YottaFlex workforce scheduling optimizer"
    )

    parser.add_argument(
        "--output",
        default="data/optimized_schedule.csv",
    )

    args = parser.parse_args()

    print("Loading workforce data from MySQL...")

    data = fetch_data()

    print("Building and solving scheduling model...")

    assignments, gaps, status = optimize_schedule(data)

    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(assignments).to_csv(
        output_path,
        index=False,
    )

    gap_path = output_path.with_name("coverage_gaps.csv")

    pd.DataFrame(gaps).to_csv(
        gap_path,
        index=False,
    )

    print("\nOPTIMIZATION COMPLETED")
    print(f"Solver status: {status}")
    print(f"Assignments generated: {len(assignments)}")
    print(f"Uncovered requirements: {len(gaps)}")
    print(
        "Total uncovered staff:",
        sum(row["uncovered_staff"] for row in gaps),
    )
    print(f"Schedule saved: {output_path}")
    print(f"Coverage gaps saved: {gap_path}")

    # Generate coverage explainability report.
    coverage_analysis = build_coverage_analysis(
        data,
        assignments,
        gaps
    )

    analysis_path = output_path.with_name(
        "coverage_analysis.csv"
    )

    coverage_analysis.to_csv(
        analysis_path,
        index=False
    )

    print(f"Coverage analysis saved: {analysis_path}")

    diagnostics = build_coverage_diagnostics(data, assignments, gaps)
    diagnostics_path = output_path.with_name("coverage_diagnostics.csv")
    diagnostics.to_csv(diagnostics_path, index=False)
    print(f"Coverage diagnostics saved: {diagnostics_path}")


if __name__ == "__main__":
    main()
