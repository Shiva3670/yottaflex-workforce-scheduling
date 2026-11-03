
import argparse
import json
from pathlib import Path

import pandas as pd


TABLES = [
    "team",
    "skill",
    "shift_template",
    "employee",
    "employee_skill",
    "holiday_calendar",
    "shift",
    "coverage_requirement",
    "leave_request",
    "shift_assignment",
    "attendance_event",
    "swap_request",
]

PRIMARY_KEYS = {
    "team": "team_id",
    "skill": "skill_id",
    "shift_template": "shift_template_id",
    "employee": "employee_id",
    "holiday_calendar": "holiday_id",
    "shift": "shift_id",
    "coverage_requirement": "requirement_id",
    "leave_request": "leave_request_id",
    "shift_assignment": "shift_assignment_id",
    "attendance_event": "attendance_event_id",
    "swap_request": "swap_request_id",
}

EXPECTED_ANOMALIES = {
    "APPROVED_LEAVE_OVERLAP",
    "DOUBLE_BOOKED",
    "REQUIRED_SKILL_ABSENT",
    "OVERTIME_CAP_EXCEEDED",
    "SWAP_WITHOUT_APPROVAL",
}


def load_table(directory, name, issues):
    path = directory / f"{name}.csv"

    if not path.exists():
        issues.append(f"MISSING_FILE:{name}.csv")
        return pd.DataFrame()

    return pd.read_csv(path, dtype=str).fillna("")


def add_issue(issues, message):
    issues.append(message)


def main():
    parser = argparse.ArgumentParser(
        description="Validate YottaFlex workforce datasets"
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
    )

    args = parser.parse_args()
    directory = args.input

    issues = []
    counts = {}

    # --------------------------------------------------------
    # 1. Load tables
    # --------------------------------------------------------

    data = {}

    for name in TABLES:
        data[name] = load_table(
            directory,
            name,
            issues,
        )
        counts[name] = len(data[name])

    ground_truth = load_table(
        directory,
        "ground_truth",
        issues,
    )

    counts["ground_truth"] = len(ground_truth)

    # --------------------------------------------------------
    # 2. Required column validation
    # --------------------------------------------------------

    required_columns = {
        "team": [
            "team_id",
            "team_name",
        ],
        "skill": [
            "skill_id",
            "skill_code",
        ],
        "shift_template": [
            "shift_template_id",
            "shift_code",
        ],
        "employee": [
            "employee_id",
            "team_id",
            "email",
            "weekly_hours_cap",
        ],
        "employee_skill": [
            "employee_id",
            "skill_id",
            "effective_from",
            "effective_to",
        ],
        "shift": [
            "shift_id",
            "team_id",
            "shift_template_id",
            "start_at",
            "end_at",
        ],
        "coverage_requirement": [
            "requirement_id",
            "shift_id",
            "skill_id",
            "minimum_staff",
        ],
        "leave_request": [
            "leave_request_id",
            "employee_id",
            "start_date",
            "end_date",
            "status",
        ],
        "shift_assignment": [
            "shift_assignment_id",
            "shift_id",
            "employee_id",
            "start_at",
            "end_at",
            "assigned_skill_id",
            "status",
        ],
        "attendance_event": [
            "attendance_event_id",
            "employee_id",
            "shift_id",
        ],
        "swap_request": [
            "swap_request_id",
            "source_assignment_id",
            "requester_employee_id",
            "target_employee_id",
            "status",
        ],
    }

    for table, columns in required_columns.items():
        missing = set(columns) - set(data[table].columns)

        if missing:
            add_issue(
                issues,
                f"MISSING_COLUMNS:{table}:{sorted(missing)}",
            )

    # --------------------------------------------------------
    # 3. Primary key validation
    # --------------------------------------------------------

    for table, pk in PRIMARY_KEYS.items():
        df = data[table]

        if pk not in df.columns:
            continue

        if df[pk].duplicated().any():
            add_issue(
                issues,
                f"DUPLICATE_PRIMARY_KEY:{table}",
            )

        if (df[pk].astype(str).str.strip() == "").any():
            add_issue(
                issues,
                f"EMPTY_PRIMARY_KEY:{table}",
            )

    employee_skill = data["employee_skill"]

    if not employee_skill.empty:
        key_columns = [
            "employee_id",
            "skill_id",
            "effective_from",
        ]

        if all(
            col in employee_skill.columns
            for col in key_columns
        ):
            if employee_skill.duplicated(
                key_columns
            ).any():
                add_issue(
                    issues,
                    "DUPLICATE_COMPOSITE_KEY:employee_skill",
                )

    # --------------------------------------------------------
    # 4. Foreign key validation
    # --------------------------------------------------------

    def check_fk(child, child_column, parent, parent_column):
        if (
            child_column not in child.columns
            or parent_column not in parent.columns
        ):
            return

        valid_values = set(
            parent[parent_column].astype(str)
        )

        invalid = set(
            child[child_column].astype(str)
        ) - valid_values - {"", "nan"}

        if invalid:
            add_issue(
                issues,
                f"FOREIGN_KEY:{child_column}:{len(invalid)}",
            )

    team = data["team"]
    skill = data["skill"]
    employee = data["employee"]
    employee_skill = data["employee_skill"]
    templates = data["shift_template"]
    shifts = data["shift"]
    requirements = data["coverage_requirement"]
    leaves = data["leave_request"]
    assignments = data["shift_assignment"]
    attendance = data["attendance_event"]
    swaps = data["swap_request"]

    check_fk(employee, "team_id", team, "team_id")

    check_fk(
        employee_skill,
        "employee_id",
        employee,
        "employee_id",
    )

    check_fk(
        employee_skill,
        "skill_id",
        skill,
        "skill_id",
    )

    check_fk(
        shifts,
        "team_id",
        team,
        "team_id",
    )

    check_fk(
        shifts,
        "shift_template_id",
        templates,
        "shift_template_id",
    )

    check_fk(
        requirements,
        "shift_id",
        shifts,
        "shift_id",
    )

    check_fk(
        requirements,
        "skill_id",
        skill,
        "skill_id",
    )

    check_fk(
        leaves,
        "employee_id",
        employee,
        "employee_id",
    )

    check_fk(
        assignments,
        "shift_id",
        shifts,
        "shift_id",
    )

    assigned = assignments[
        assignments["employee_id"] != ""
    ] if "employee_id" in assignments.columns else pd.DataFrame()

    check_fk(
        assigned,
        "employee_id",
        employee,
        "employee_id",
    )

    check_fk(
        assignments,
        "assigned_skill_id",
        skill,
        "skill_id",
    )

    check_fk(
        attendance,
        "employee_id",
        employee,
        "employee_id",
    )

    check_fk(
        attendance,
        "shift_id",
        shifts,
        "shift_id",
    )

    check_fk(
        swaps,
        "source_assignment_id",
        assignments,
        "shift_assignment_id",
    )

    check_fk(
        swaps,
        "requester_employee_id",
        employee,
        "employee_id",
    )

    check_fk(
        swaps,
        "target_employee_id",
        employee,
        "employee_id",
    )

    # --------------------------------------------------------
    # 5. Date and numeric validation
    # --------------------------------------------------------

    def check_date_order(df, start_col, end_col, table):
        if df.empty:
            return

        if not {
            start_col,
            end_col,
        }.issubset(df.columns):
            return

        start = pd.to_datetime(
            df[start_col],
            errors="coerce",
        )

        end = pd.to_datetime(
            df[end_col],
            errors="coerce",
        )

        invalid = start.isna() | end.isna() | (start > end)

        if invalid.any():
            add_issue(
                issues,
                f"DATE_ORDER_OR_FORMAT:{table}:{int(invalid.sum())}",
            )

    check_date_order(
        leaves,
        "start_date",
        "end_date",
        "leave_request",
    )

    check_date_order(
        shifts,
        "start_at",
        "end_at",
        "shift",
    )

    check_date_order(
        assignments,
        "start_at",
        "end_at",
        "shift_assignment",
    )

    if not employee.empty and "weekly_hours_cap" in employee:
        caps = pd.to_numeric(
            employee["weekly_hours_cap"],
            errors="coerce",
        )

        if caps.isna().any() or (caps <= 0).any():
            add_issue(
                issues,
                "INVALID_WEEKLY_HOURS_CAP",
            )

    if not requirements.empty:
        minimum_staff = pd.to_numeric(
            requirements["minimum_staff"],
            errors="coerce",
        )

        if (
            minimum_staff.isna().any()
            or (minimum_staff < 0).any()
        ):
            add_issue(
                issues,
                "INVALID_MINIMUM_STAFF",
            )

    # --------------------------------------------------------
    # 6. Detect scheduling anomalies
    # --------------------------------------------------------

    detected = []

    def record_anomaly(issue_type, entity_type, entity_id):
        detected.append({
            "issue_type": issue_type,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
        })

    # Anomaly 1: Approved leave overlap.
    # Index approved leave intervals by employee. This avoids comparing
    # every assignment with every leave request in the complete dataset.

    approved_leave_by_employee = {}

    if not leaves.empty and not assigned.empty:
        approved = leaves[leaves["status"] == "APPROVED"]

        for leave in approved.itertuples(index=False):
            leave_start = pd.to_datetime(
                getattr(leave, "start_date"), errors="coerce"
            )
            leave_end = pd.to_datetime(
                getattr(leave, "end_date"), errors="coerce"
            )

            if pd.isna(leave_start) or pd.isna(leave_end):
                continue

            approved_leave_by_employee.setdefault(
                getattr(leave, "employee_id"), []
            ).append((leave_start.date(), leave_end.date()))

        for row in assigned.itertuples(index=False):
            employee_id = getattr(row, "employee_id")
            employee_leaves = approved_leave_by_employee.get(employee_id, [])
            if not employee_leaves:
                continue

            assignment_start = pd.to_datetime(
                getattr(row, "start_at"), errors="coerce"
            )
            assignment_end = pd.to_datetime(
                getattr(row, "end_at"), errors="coerce"
            )
            if pd.isna(assignment_start) or pd.isna(assignment_end):
                continue

            start_day = assignment_start.date()
            end_day = assignment_end.date()

            if any(
                start_day <= leave_end and end_day >= leave_start
                for leave_start, leave_end in employee_leaves
            ):
                record_anomaly(
                    "APPROVED_LEAVE_OVERLAP",
                    "ShiftAssignment",
                    getattr(row, "shift_assignment_id"),
                )

    # Anomaly 2: Employee double-booking.
    # Sort each employee's assignments by start time and maintain only
    # intervals that are still active. Each assignment is reported once
    # if it overlaps at least one earlier-starting assignment.

    if not assigned.empty:
        overlap_data = assigned[
            ["employee_id", "start_at", "end_at", "shift_assignment_id"]
        ].copy()
        overlap_data["_start"] = pd.to_datetime(
            overlap_data["start_at"], errors="coerce"
        )
        overlap_data["_end"] = pd.to_datetime(
            overlap_data["end_at"], errors="coerce"
        )
        overlap_data = overlap_data[
            overlap_data["_start"].notna()
            & overlap_data["_end"].notna()
            & (overlap_data["_start"] < overlap_data["_end"])
        ]

        for employee_id, group in overlap_data.groupby(
            "employee_id", sort=False
        ):
            group = group.sort_values("_start", kind="mergesort")
            active_ends = []

            for current_start, current_end, assignment_id in group[
                ["_start", "_end", "shift_assignment_id"]
            ].itertuples(index=False, name=None):
                active_ends = [
                    previous_end
                    for previous_end in active_ends
                    if previous_end > current_start
                ]

                if active_ends:
                    record_anomaly(
                        "DOUBLE_BOOKED",
                        "ShiftAssignment",
                        assignment_id,
                    )

                active_ends.append(current_end)

    # Anomaly 3: Employee does not hold the assigned skill on the
    # assignment date. Skill effective dates are inclusive.
    # Index intervals by (employee_id, skill_id) for fast lookup.

    skills_by_employee_skill = {}

    if not employee_skill.empty:
        for row in employee_skill.itertuples(index=False):
            effective_from = pd.to_datetime(
                getattr(row, "effective_from"), errors="coerce"
            )
            effective_to_value = getattr(row, "effective_to")
            effective_to = (
                pd.to_datetime(effective_to_value, errors="coerce")
                if effective_to_value
                else pd.NaT
            )

            if pd.isna(effective_from):
                continue

            skills_by_employee_skill.setdefault(
                (getattr(row, "employee_id"), getattr(row, "skill_id")), []
            ).append((
                effective_from.date(),
                effective_to.date() if pd.notna(effective_to) else None,
            ))

    if not assigned.empty:
        for row in assigned.itertuples(index=False):
            assignment_start = pd.to_datetime(
                getattr(row, "start_at"), errors="coerce"
            )
            if pd.isna(assignment_start):
                continue

            assignment_day = assignment_start.date()
            skill_intervals = skills_by_employee_skill.get(
                (getattr(row, "employee_id"), getattr(row, "assigned_skill_id")),
                [],
            )

            valid_skill = any(
                effective_from <= assignment_day
                and (effective_to is None or effective_to >= assignment_day)
                for effective_from, effective_to in skill_intervals
            )

            if not valid_skill:
                record_anomaly(
                    "REQUIRED_SKILL_ABSENT",
                    "ShiftAssignment",
                    getattr(row, "shift_assignment_id"),
                )

    # Anomaly 4: Recorded weekly hours exceed employee cap.
    # This checks the stored weekly-hours field, not independently
    # reconstructed working hours.

    if (
        not assignments.empty
        and not employee.empty
        and "weekly_hours_after_assignment" in assignments.columns
        and "weekly_hours_cap" in employee.columns
    ):
        cap_map = dict(
            zip(
                employee["employee_id"],
                pd.to_numeric(employee["weekly_hours_cap"], errors="coerce"),
            )
        )
        caps = pd.to_numeric(
            assignments["employee_id"].map(cap_map), errors="coerce"
        )
        hours = pd.to_numeric(
            assignments["weekly_hours_after_assignment"], errors="coerce"
        )
        overtime_rows = assignments.loc[
            assignments["employee_id"].ne("")
            & caps.notna()
            & hours.notna()
            & hours.gt(caps),
            "employee_id",
        ]

        for employee_id in overtime_rows:
            record_anomaly(
                "OVERTIME_CAP_EXCEEDED",
                "Employee",
                employee_id,
            )

    # Anomaly 5: Swap applied without approval.

    if not swaps.empty:
        for row in swaps.itertuples():
            if row.status == "APPLIED":
                manager_id = getattr(
                    row,
                    "manager_id",
                    "",
                )

                decided_at = getattr(
                    row,
                    "decided_at",
                    "",
                )

                if not manager_id or not decided_at:
                    record_anomaly(
                        "SWAP_WITHOUT_APPROVAL",
                        "SwapRequest",
                        row.swap_request_id,
                    )

    # --------------------------------------------------------
    # 7. Compare detections against ground truth
    # --------------------------------------------------------

    ground_truth_types = set()
    ground_truth_pairs = set()

    if not ground_truth.empty:
        ground_truth_types = set(
            ground_truth["issue_type"].astype(str)
        )

        for row in ground_truth.itertuples():
            ground_truth_pairs.add((
                row.issue_type,
                str(row.entity_id),
            ))

    detected_types = {row["issue_type"] for row in detected}
    detected_ids_by_type = {}
    for row in detected:
        detected_ids_by_type.setdefault(row["issue_type"], set()).add(
            row["entity_id"]
        )
    detected_counts_by_type = {}
    for row in detected:
        detected_counts_by_type[row["issue_type"]] = (
            detected_counts_by_type.get(row["issue_type"], 0) + 1
        )

    expected_ids_by_type = {}
    for issue_type, entity_id in ground_truth_pairs:
        expected_ids_by_type.setdefault(issue_type, set()).add(entity_id)

    anomaly_verification = {}

    for anomaly_type in sorted(EXPECTED_ANOMALIES):
        matching_count = detected_counts_by_type.get(anomaly_type, 0)

        expected_ids = expected_ids_by_type.get(anomaly_type, set())
        detected_ids = detected_ids_by_type.get(anomaly_type, set())

        matches_ground_truth = (
            expected_ids == detected_ids
            and anomaly_type in ground_truth_types
        )

        anomaly_verification[anomaly_type] = {
            "detected_count": matching_count,
            "ground_truth_count": len(expected_ids),
            "matches_ground_truth": matches_ground_truth,
            "detected_entity_ids": sorted(detected_ids),
        }

    anomaly_verification_pass = all(
        item["matches_ground_truth"]
        for item in anomaly_verification.values()
    )

    # --------------------------------------------------------
    # 8. Final report
    # --------------------------------------------------------

    report = {
        "status": (
            "PASS"
            if not issues and anomaly_verification_pass
            else "FAIL"
        ),
        "row_counts": counts,
        "issues": issues,
        "ground_truth_rows": len(ground_truth),
        "anomaly_verification": {
            "status": (
                "PASS"
                if anomaly_verification_pass
                else "FAIL"
            ),
            "expected_anomaly_types": sorted(
                EXPECTED_ANOMALIES
            ),
            "detected_anomaly_types": sorted(
                detected_types
            ),
            "details": anomaly_verification,
        },
        "limitations": [
            "Overtime detection checks the stored weekly_hours_after_assignment field; actual weekly hours are not independently reconstructed.",
            "Ground-truth matching validates labelled anomaly IDs, not the correctness of every business rule.",
        ],
    }

    output_path = directory / "validation_summary.json"

    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2))

    if issues or not anomaly_verification_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
