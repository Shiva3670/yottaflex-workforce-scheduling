
import argparse
import hashlib
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker


# ============================================================
# CONFIGURATION
# ============================================================

SEED_DEFAULT = 20261022

# employees, teams, scheduling days, leave requests
SCALES = {
    "starter": (80, 8, 14, 120),
    "full": (2000, 100, 90, 5000),
}

SKILL_NAMES = [
    "GENERAL",
    "FORKLIFT",
    "FIRST_AID",
    "QUALITY",
    "PACKING",
    "DISPATCH",
    "INVENTORY",
    "SUPERVISION",
]

SHIFT_TEMPLATES = [
    {
        "shift_template_id": "TPL-A",
        "shift_code": "A",
        "shift_name": "Morning",
        "start_time": "06:00",
        "end_time": "14:00",
        "duration_hours": 8,
        "is_overnight": False,
    },
    {
        "shift_template_id": "TPL-B",
        "shift_code": "B",
        "shift_name": "Evening",
        "start_time": "14:00",
        "end_time": "22:00",
        "duration_hours": 8,
        "is_overnight": False,
    },
    {
        "shift_template_id": "TPL-C",
        "shift_code": "C",
        "shift_name": "Night",
        "start_time": "22:00",
        "end_time": "06:00",
        "duration_hours": 8,
        "is_overnight": True,
    },
]


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def sha256_file(path: Path) -> str:
    """Return SHA-256 checksum of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_timestamp(day: date, clock: str) -> datetime:
    """Create a timestamp from a date and HH:MM time."""
    return datetime.combine(
        day,
        datetime.strptime(clock, "%H:%M").time(),
    )


def employee_has_skill(
    employee_skill_map: dict,
    employee_id: str,
    skill_id: str,
) -> bool:
    return skill_id in employee_skill_map.get(employee_id, set())


def create_shift_id(day: date, shift_code: str, team_number: int) -> str:
    return (
        f"SHIFT-{day.isoformat()}-"
        f"{shift_code}-T{team_number:03d}"
    )


def weekly_period(timestamp: datetime):
    """Return ISO year and week for weekly-hour calculations."""
    iso = timestamp.isocalendar()
    return iso.year, iso.week


def get_assignment_hours(assignments: list, employee_id: str,
                         year: int, week: int) -> float:
    total = 0.0

    for assignment in assignments:
        if assignment["employee_id"] != employee_id:
            continue

        if assignment["status"] != "ASSIGNED":
            continue

        start = datetime.fromisoformat(assignment["start_at"])

        if weekly_period(start) == (year, week):
            end = datetime.fromisoformat(assignment["end_at"])
            total += (end - start).total_seconds() / 3600

    return total


# ============================================================
# MAIN GENERATOR
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate YottaFlex synthetic workforce data"
    )

    parser.add_argument(
        "--scale",
        choices=SCALES.keys(),
        default="starter",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=SEED_DEFAULT,
    )

    parser.add_argument(
        "--out",
        type=Path,
        default=Path("../../data"),
    )

    parser.add_argument(
        "--start",
        default="2026-01-01",
    )

    args = parser.parse_args()

    n_employees, n_teams, days, n_leave = SCALES[args.scale]

    start_date = date.fromisoformat(args.start)

    output_dir = args.out.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(args.seed)

    fake = Faker("en_IN")
    fake.seed_instance(args.seed)

    print("Generating YottaFlex synthetic data...")
    print("Scale:", args.scale)
    print("Seed:", args.seed)


    # ========================================================
    # 1. TEAM MASTER DATA
    # ========================================================

    teams = pd.DataFrame([
        {
            "team_id": f"TEAM-{i + 1:04d}",
            "team_name": f"Operations Team {i + 1:03d}",
            "location": fake.city(),
            "active": True,
        }
        for i in range(n_teams)
    ])


    # ========================================================
    # 2. SKILL MASTER DATA
    # ========================================================

    skills = pd.DataFrame([
        {
            "skill_id": f"SKL-{i + 1:03d}",
            "skill_code": name,
            "skill_name": name.replace("_", " ").title(),
        }
        for i, name in enumerate(SKILL_NAMES)
    ])

    skill_id_by_name = {
        name: f"SKL-{i + 1:03d}"
        for i, name in enumerate(SKILL_NAMES)
    }


    # ========================================================
    # 3. SHIFT TEMPLATE MASTER DATA
    # ========================================================

    shift_templates = pd.DataFrame(SHIFT_TEMPLATES)


    # ========================================================
    # 4. EMPLOYEE MASTER DATA
    # ========================================================

    employee_rows = []
    employee_skill_rows = []

    for i in range(n_employees):
        employee_id = f"EMP-{i + 1:06d}"

        team_id = f"TEAM-{(i % n_teams) + 1:04d}"

        contract_type = (
            "FULL_TIME"
            if rng.random() < 0.85
            else "PART_TIME"
        )

        weekly_cap = (
            40 if contract_type == "FULL_TIME" else 24
        )

        hire_date = start_date - timedelta(
            days=int(rng.integers(30, 2500))
        )

        employee_rows.append({
            "employee_id": employee_id,
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "email": f"{employee_id.lower()}@example.test",
            "team_id": team_id,
            "employment_status": "ACTIVE",
            "hire_date": str(hire_date),
            "weekly_hours_cap": weekly_cap,
            "contract_type": contract_type,
        })

        # GENERAL is mandatory for every employee.
        chosen_skills = {0}

        # Add optional skills.
        optional_count = int(rng.integers(1, 4))

        optional_skills = rng.choice(
            np.arange(1, len(SKILL_NAMES)),
            size=optional_count,
            replace=False,
        )

        chosen_skills.update(int(x) for x in optional_skills)

        # Ensure enough forklift-qualified employees per team.
        if i % 3 == 0:
            chosen_skills.add(1)

        for skill_index in sorted(chosen_skills):
            employee_skill_rows.append({
                "employee_id": employee_id,
                "skill_id": f"SKL-{skill_index + 1:03d}",
                "proficiency": (
                    "ADVANCED"
                    if rng.random() < 0.3
                    else "BASIC"
                ),
                "effective_from": str(
                    start_date - timedelta(days=30)
                ),
                "effective_to": "",
            })

    employees = pd.DataFrame(employee_rows)
    employee_skills = pd.DataFrame(employee_skill_rows)

    employee_skill_map = (
        employee_skills.groupby("employee_id")["skill_id"]
        .apply(set)
        .to_dict()
    )

    employee_team_map = dict(
        zip(employees["employee_id"], employees["team_id"])
    )

    employee_cap_map = dict(
        zip(
            employees["employee_id"],
            employees["weekly_hours_cap"],
        )
    )


    # ========================================================
    # 5. HOLIDAY CALENDAR
    # ========================================================

    holiday_definitions = {
        (1, 26): "Republic Day",
        (8, 15): "Independence Day",
        (10, 2): "Gandhi Jayanti",
    }

    holiday_rows = []

    for offset in range(days):
        current_date = start_date + timedelta(days=offset)

        holiday_name = holiday_definitions.get(
            (current_date.month, current_date.day)
        )

        if holiday_name:
            holiday_rows.append({
                "holiday_id": f"HOL-{current_date.isoformat()}",
                "holiday_date": str(current_date),
                "holiday_name": holiday_name,
                "location": "ALL",
            })

    holidays = pd.DataFrame(
        holiday_rows,
        columns=[
            "holiday_id",
            "holiday_date",
            "holiday_name",
            "location",
        ],
    )


    # ========================================================
    # 6. SHIFT INSTANCES
    # ========================================================

    shift_rows = []
    requirement_rows = []

    for day_offset in range(days):
        current_date = start_date + timedelta(days=day_offset)

        for team_index in range(n_teams):
            team_id = f"TEAM-{team_index + 1:04d}"

            for template in SHIFT_TEMPLATES:
                shift_id = create_shift_id(
                    current_date,
                    template["shift_code"],
                    team_index + 1,
                )

                start_at = make_timestamp(
                    current_date,
                    template["start_time"],
                )

                end_at = start_at + timedelta(
                    hours=template["duration_hours"]
                )

                shift_rows.append({
                    "shift_id": shift_id,
                    "team_id": team_id,
                    "shift_template_id": template[
                        "shift_template_id"
                    ],
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
                    "status": "PLANNED",
                })

                requirement_rows.append({
                    "requirement_id": f"REQ-{shift_id}-GEN",
                    "shift_id": shift_id,
                    "skill_id": skill_id_by_name["GENERAL"],
                    "minimum_staff": (
                        2 if args.scale == "starter" else 4
                    ),
                })

                # Forklift requirement for every fifth team.
                if team_index % 5 == 0:
                    requirement_rows.append({
                        "requirement_id": f"REQ-{shift_id}-FLT",
                        "shift_id": shift_id,
                        "skill_id": skill_id_by_name["FORKLIFT"],
                        "minimum_staff": 1,
                    })

    shifts = pd.DataFrame(shift_rows)
    coverage_requirements = pd.DataFrame(requirement_rows)


    # ========================================================
    # 7. LEAVE REQUESTS
    # ========================================================

    leave_rows = []

    for i in range(n_leave):
        employee_id = employees.iloc[
            int(rng.integers(0, n_employees))
        ]["employee_id"]

        leave_start = start_date + timedelta(
            days=int(rng.integers(0, days))
        )

        leave_end = leave_start + timedelta(
            days=int(rng.integers(0, 3))
        )

        status = str(
            rng.choice(
                ["PENDING", "APPROVED", "REJECTED"],
                p=[0.2, 0.65, 0.15],
            )
        )

        submitted_at = datetime.combine(
            leave_start - timedelta(days=3),
            time.min,
        )

        decided_at = (
            datetime.combine(
                leave_start - timedelta(days=2),
                time.min,
            )
            if status != "PENDING"
            else None
        )

        leave_rows.append({
            "leave_request_id": (
                f"LVE-{start_date.year}-{i + 1:06d}"
            ),
            "employee_id": employee_id,
            "leave_type": str(
                rng.choice(["ANNUAL", "SICK", "PERSONAL"])
            ),
            "start_date": str(leave_start),
            "end_date": str(leave_end),
            "status": status,
            "submitted_at": submitted_at.isoformat(),
            "decided_at": (
                decided_at.isoformat()
                if decided_at else ""
            ),
        })

    leaves = pd.DataFrame(leave_rows)

    approved_leave_dates = {}

    for leave in leaves[
        leaves["status"] == "APPROVED"
    ].itertuples():
        for day in pd.date_range(
            leave.start_date,
            leave.end_date,
        ):
            approved_leave_dates.setdefault(
                leave.employee_id,
                set(),
            ).add(day.date())


    # ========================================================
    # 8. BASELINE SHIFT ASSIGNMENTS
    # ========================================================

    assignments = []

    team_employee_map = (
        employees.groupby("team_id")["employee_id"]
        .apply(list)
        .to_dict()
    )

    last_assignment_end = {}
    weekly_hours = {}

    for shift in shifts.itertuples():
        shift_start = datetime.fromisoformat(shift.start_at)
        shift_end = datetime.fromisoformat(shift.end_at)

        shift_day = shift_start.date()

        team_pool = team_employee_map[shift.team_id]

        assigned_this_shift = set()

        requirements = coverage_requirements[
            coverage_requirements["shift_id"] == shift.shift_id
        ]

        for requirement in requirements.itertuples():
            eligible = []

            for employee_id in team_pool:
                if employee_id in assigned_this_shift:
                    continue

                if not employee_has_skill(
                    employee_skill_map,
                    employee_id,
                    requirement.skill_id,
                ):
                    continue

                            # Check the complete shift interval against every approved
                # leave calendar day, including overnight shifts.
                employee_leave_days = approved_leave_dates.get(
                    employee_id, set()
                )

                has_leave_overlap = any(
                    shift_start < datetime.combine(
                        leave_day + timedelta(days=1),
                        time.min,
                    )
                    and shift_end > datetime.combine(
                        leave_day,
                        time.min,
                    )
                    for leave_day in employee_leave_days
                )

                if has_leave_overlap:
                    continue
                previous_end = last_assignment_end.get(
                    employee_id
                )

                # At least 8 hours of rest between shifts.
                if previous_end is not None:
                    if shift_start < previous_end + timedelta(
                        hours=8
                    ):
                        continue

                period = weekly_period(shift_start)

                used_hours = weekly_hours.get(
                    (employee_id, period),
                    0.0,
                )

                duration = (
                    shift_end - shift_start
                ).total_seconds() / 3600

                if used_hours + duration > employee_cap_map[
                    employee_id
                ]:
                    continue

                eligible.append(employee_id)

            # Seeded random selection among eligible employees.
            if eligible:
                rng.shuffle(eligible)

            selected = eligible[
                :requirement.minimum_staff
            ]

            for employee_id in selected:
                assignment_id = (
                    f"ASG-{shift.shift_id}-"
                    f"{requirement.skill_id}-{employee_id}"
                )

                assignments.append({
                    "shift_assignment_id": assignment_id,
                    "shift_id": shift.shift_id,
                    "employee_id": employee_id,
                    "start_at": shift.start_at,
                    "end_at": shift.end_at,
                    "assigned_skill_id": requirement.skill_id,
                    "status": "ASSIGNED",
                    "weekly_hours_after_assignment": (
                        weekly_hours.get(
                            (employee_id, weekly_period(shift_start)),
                            0.0,
                        ) + duration
                    ),
                    "coverage_gap": False,
                })

                assigned_this_shift.add(employee_id)

                last_assignment_end[employee_id] = shift_end

                period = weekly_period(shift_start)

                weekly_hours[(employee_id, period)] = (
                    weekly_hours.get(
                        (employee_id, period), 0.0
                    ) + duration
                )

            if len(selected) < requirement.minimum_staff:
                assignments.append({
                    "shift_assignment_id": (
                        f"GAP-{shift.shift_id}-"
                        f"{requirement.skill_id}"
                    ),
                    "shift_id": shift.shift_id,
                    "employee_id": "",
                    "start_at": shift.start_at,
                    "end_at": shift.end_at,
                    "assigned_skill_id": requirement.skill_id,
                    "status": "UNCOVERED",
                    "weekly_hours_after_assignment": 0,
                    "coverage_gap": True,
                })


    # ========================================================
    # 9. ANOMALY INJECTION
    # ========================================================

    # Anomalies are injected AFTER baseline scheduling.
    # Ground truth is kept separate from optimizer inputs.

    ground_truth_rows = []

    def add_label(
        issue_type,
        entity_type,
        entity_id,
        expected,
        severity="HIGH",
    ):
        ground_truth_rows.append({
            "issue_type": issue_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "ground_truth": expected,
            "severity": severity,
        })

    real_assignments = [
        row for row in assignments
        if row["status"] == "ASSIGNED"
    ]

    if len(real_assignments) < 2:
        raise RuntimeError(
            "Not enough baseline assignments to inject anomalies."
        )

    # --------------------------------------------------------
    # Anomaly 1: Approved leave overlaps an assignment.
    # --------------------------------------------------------

    leave_target = real_assignments[0]

    leave_day = datetime.fromisoformat(
        leave_target["start_at"]
    ).date()

    anomaly_leave_id = (
        f"LVE-{start_date.year}-ANOM-0001"
    )

    leaves = pd.concat([
        leaves,
        pd.DataFrame([{
            "leave_request_id": anomaly_leave_id,
            "employee_id": leave_target["employee_id"],
            "leave_type": "ANNUAL",
            "start_date": str(leave_day),
            "end_date": str(leave_day),
            "status": "APPROVED",
            "submitted_at": (
                datetime.combine(
                    leave_day - timedelta(days=3),
                    time.min,
                ).isoformat()
            ),
            "decided_at": (
                datetime.combine(
                    leave_day - timedelta(days=2),
                    time.min,
                ).isoformat()
            ),
        }]),
    ], ignore_index=True)

    add_label(
        "APPROVED_LEAVE_OVERLAP",
        "ShiftAssignment",
        leave_target["shift_assignment_id"],
        "FLAG_CONFLICT",
    )

    # --------------------------------------------------------
    # Anomaly 2: Employee double-booked in same time window.
    # --------------------------------------------------------

    double_target = real_assignments[1]

    duplicate_id = (
        f"ANOM-DOUBLE-{double_target['shift_assignment_id']}"
    )

    duplicate_assignment = dict(double_target)
    duplicate_assignment["shift_assignment_id"] = duplicate_id

    # Same employee and time, but a different synthetic shift ID.
    duplicate_shift_id = (
        f"SHIFT-ANOM-DOUBLE-{duplicate_id}"
    )

    duplicate_assignment["shift_id"] = duplicate_shift_id

    original_shift = shifts[
        shifts["shift_id"] == double_target["shift_id"]
    ].iloc[0].to_dict()

    duplicate_shift = dict(original_shift)
    duplicate_shift["shift_id"] = duplicate_shift_id

    shifts = pd.concat(
        [shifts, pd.DataFrame([duplicate_shift])],
        ignore_index=True,
    )

    assignments.append(duplicate_assignment)

    add_label(
        "DOUBLE_BOOKED",
        "ShiftAssignment",
        duplicate_id,
        "FLAG_CONFLICT",
    )

    # --------------------------------------------------------
    # Anomaly 3: Assigned skill is not held by the employee.
    # --------------------------------------------------------

    skill_target = real_assignments[2]

    employee_skills_for_target = employee_skill_map.get(
        skill_target["employee_id"],
        set(),
    )

    unavailable_skills = [
        skill_id
        for skill_id in skill_id_by_name.values()
        if skill_id not in employee_skills_for_target
    ]

    if unavailable_skills:
        wrong_skill = unavailable_skills[0]
    else:
        # This fallback is deterministic and guarantees a mismatch.
        wrong_skill = skill_id_by_name["SUPERVISION"]

        employee_skill_map[
            skill_target["employee_id"]
        ].discard(wrong_skill)

    skill_target["assigned_skill_id"] = wrong_skill

    add_label(
        "REQUIRED_SKILL_ABSENT",
        "ShiftAssignment",
        skill_target["shift_assignment_id"],
        "FLAG_SKILL_MISMATCH",
    )

    # --------------------------------------------------------
    # Anomaly 4: Overtime cap exceeded.
    # --------------------------------------------------------

    overtime_employee = real_assignments[3]["employee_id"]

    overtime_assignment = None

    for row in assignments:
        if (
            row["employee_id"] == overtime_employee
            and row["status"] == "ASSIGNED"
        ):
            start_at = datetime.fromisoformat(row["start_at"])

            if weekly_period(start_at) == weekly_period(
                datetime.fromisoformat(
                    real_assignments[3]["start_at"]
                )
            ):
                overtime_assignment = row

    if overtime_assignment is None:
        overtime_assignment = real_assignments[3]

    overtime_assignment["weekly_hours_after_assignment"] = (
        employee_cap_map[overtime_employee] + 8
    )

    add_label(
        "OVERTIME_CAP_EXCEEDED",
        "Employee",
        overtime_employee,
        "FLAG_OVERTIME",
    )

    # --------------------------------------------------------
    # Anomaly 5: Swap applied without approval.
    # --------------------------------------------------------

    swap_target = real_assignments[0]

    swap_request_id = (
        f"SWP-{start_date.year}-000001"
    )

    swaps = pd.DataFrame([{
        "swap_request_id": swap_request_id,
        "source_assignment_id": (
            swap_target["shift_assignment_id"]
        ),
        "requester_employee_id": swap_target["employee_id"],
        "target_employee_id": real_assignments[-1]["employee_id"],
        "status": "APPLIED",
        "manager_id": "",
        "created_at": (
            datetime.combine(
                start_date,
                time.min,
            ).isoformat()
        ),
        "decided_at": "",
        "applied_at": (
            datetime.combine(
                start_date,
                time.min,
            ).isoformat()
        ),
    }])

    add_label(
        "SWAP_WITHOUT_APPROVAL",
        "SwapRequest",
        swap_request_id,
        "REJECT_APPLICATION",
    )


    # ========================================================
    # 10. ATTENDANCE EVENTS
    # ========================================================

    attendance_rows = []

    for assignment in assignments:
        if assignment["status"] != "ASSIGNED":
            continue

        employee_id = assignment["employee_id"]

        # One attendance event per assignment.
        event_type = str(
            rng.choice(
                ["PRESENT", "LATE", "ABSENT"],
                p=[0.94, 0.04, 0.02],
            )
        )

        attendance_rows.append({
            "attendance_event_id": (
                f"ATT-{employee_id}-{assignment['shift_id']}"
            ),
            "employee_id": employee_id,
            "shift_id": assignment["shift_id"],
            "event_type": event_type,
            "event_at": assignment["start_at"],
            "source": "SYNTHETIC_TERMINAL",
        })


    # ========================================================
    # 11. DATAFRAMES
    # ========================================================

    assignment_df = pd.DataFrame(assignments)

    attendance = pd.DataFrame(attendance_rows)

    swaps = swaps if "swaps" in locals() else pd.DataFrame(
        columns=[
            "swap_request_id",
            "source_assignment_id",
            "requester_employee_id",
            "target_employee_id",
            "status",
            "manager_id",
            "created_at",
            "decided_at",
            "applied_at",
        ]
    )

    ground_truth = pd.DataFrame(ground_truth_rows)


    # ========================================================
    # 12. OUTPUT TABLES
    # ========================================================

    tables = {
        "team": teams,
        "skill": skills,
        "shift_template": shift_templates,
        "employee": employees,
        "employee_skill": employee_skills,
        "holiday_calendar": holidays,
        "shift": shifts,
        "coverage_requirement": coverage_requirements,
        "leave_request": leaves,
        "shift_assignment": assignment_df,
        "attendance_event": attendance,
        "swap_request": swaps,
        "ground_truth": ground_truth,
    }


    # ========================================================
    # 13. EXPORT CSV AND JSON
    # ========================================================

    manifest = {
        "project": "YottaFlex Workforce Scheduling",
        "seed": args.seed,
        "scale": args.scale,
        "start_date": args.start,
        "days": days,
        "tables": {},
    }

    for table_name, dataframe in tables.items():
        csv_path = output_dir / f"{table_name}.csv"
        json_path = output_dir / f"{table_name}.json"

        dataframe.to_csv(csv_path, index=False)

        dataframe.to_json(
            json_path,
            orient="records",
            indent=2,
            date_format="iso",
        )

        manifest["tables"][table_name] = {
            "rows": len(dataframe),
            "sha256": sha256_file(csv_path),
            "file": csv_path.name,
        }

    manifest_path = output_dir / "source_manifest.json"

    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


    # ========================================================
    # 14. GENERATE BASIC SQL SCHEMA
    # ========================================================

    schema_sql = """
CREATE TABLE team (
    team_id VARCHAR(16) PRIMARY KEY,
    team_name VARCHAR(120) NOT NULL,
    location VARCHAR(120),
    active BOOLEAN NOT NULL
);

CREATE TABLE skill (
    skill_id VARCHAR(16) PRIMARY KEY,
    skill_code VARCHAR(40) UNIQUE NOT NULL,
    skill_name VARCHAR(80) NOT NULL
);

CREATE TABLE shift_template (
    shift_template_id VARCHAR(16) PRIMARY KEY,
    shift_code VARCHAR(8) UNIQUE NOT NULL,
    shift_name VARCHAR(80) NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    duration_hours DECIMAL(5,2) NOT NULL,
    is_overnight BOOLEAN NOT NULL
);

CREATE TABLE employee (
    employee_id VARCHAR(16) PRIMARY KEY,
    first_name VARCHAR(80) NOT NULL,
    last_name VARCHAR(80) NOT NULL,
    email VARCHAR(180) UNIQUE NOT NULL,
    team_id VARCHAR(16) NOT NULL,
    employment_status VARCHAR(20) NOT NULL,
    hire_date DATE NOT NULL,
    weekly_hours_cap DECIMAL(5,2) NOT NULL,
    contract_type VARCHAR(20) NOT NULL,
    FOREIGN KEY (team_id) REFERENCES team(team_id)
);

CREATE TABLE employee_skill (
    employee_id VARCHAR(16) NOT NULL,
    skill_id VARCHAR(16) NOT NULL,
    proficiency VARCHAR(20) NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    PRIMARY KEY (employee_id, skill_id, effective_from),
    FOREIGN KEY (employee_id) REFERENCES employee(employee_id),
    FOREIGN KEY (skill_id) REFERENCES skill(skill_id)
);

CREATE TABLE shift (
    shift_id VARCHAR(100) PRIMARY KEY,
    team_id VARCHAR(16) NOT NULL,
    shift_template_id VARCHAR(16) NOT NULL,
    start_at TIMESTAMP NOT NULL,
    end_at TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL,
    FOREIGN KEY (team_id) REFERENCES team(team_id),
    FOREIGN KEY (shift_template_id)
        REFERENCES shift_template(shift_template_id)
);

CREATE TABLE coverage_requirement (
    requirement_id VARCHAR(120) PRIMARY KEY,
    shift_id VARCHAR(100) NOT NULL,
    skill_id VARCHAR(16) NOT NULL,
    minimum_staff INTEGER NOT NULL,
    FOREIGN KEY (shift_id) REFERENCES shift(shift_id),
    FOREIGN KEY (skill_id) REFERENCES skill(skill_id),
    CHECK (minimum_staff >= 0)
);

CREATE TABLE leave_request (
    leave_request_id VARCHAR(32) PRIMARY KEY,
    employee_id VARCHAR(16) NOT NULL,
    leave_type VARCHAR(20) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status VARCHAR(16) NOT NULL,
    submitted_at TIMESTAMP NOT NULL,
    decided_at TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employee(employee_id),
    CHECK (end_date >= start_date)
);

CREATE TABLE shift_assignment (
    shift_assignment_id VARCHAR(160) PRIMARY KEY,
    shift_id VARCHAR(100) NOT NULL,
    employee_id VARCHAR(16),
    start_at TIMESTAMP NOT NULL,
    end_at TIMESTAMP NOT NULL,
    assigned_skill_id VARCHAR(16) NOT NULL,
    status VARCHAR(20) NOT NULL,
    weekly_hours_after_assignment DECIMAL(6,2),
    coverage_gap BOOLEAN NOT NULL,
    FOREIGN KEY (shift_id) REFERENCES shift(shift_id),
    FOREIGN KEY (employee_id) REFERENCES employee(employee_id),
    FOREIGN KEY (assigned_skill_id) REFERENCES skill(skill_id)
);

CREATE TABLE attendance_event (
    attendance_event_id VARCHAR(160) PRIMARY KEY,
    employee_id VARCHAR(16) NOT NULL,
    shift_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(16) NOT NULL,
    event_at TIMESTAMP NOT NULL,
    source VARCHAR(80) NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employee(employee_id),
    FOREIGN KEY (shift_id) REFERENCES shift(shift_id)
);

CREATE TABLE holiday_calendar (
    holiday_id VARCHAR(32) PRIMARY KEY,
    holiday_date DATE NOT NULL,
    holiday_name VARCHAR(80) NOT NULL,
    location VARCHAR(120) NOT NULL
);

CREATE TABLE swap_request (
    swap_request_id VARCHAR(32) PRIMARY KEY,
    source_assignment_id VARCHAR(160) NOT NULL,
    requester_employee_id VARCHAR(16) NOT NULL,
    target_employee_id VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    manager_id VARCHAR(16),
    created_at TIMESTAMP NOT NULL,
    decided_at TIMESTAMP,
    applied_at TIMESTAMP,
    FOREIGN KEY (source_assignment_id)
        REFERENCES shift_assignment(shift_assignment_id),
    FOREIGN KEY (requester_employee_id)
        REFERENCES employee(employee_id),
    FOREIGN KEY (target_employee_id)
        REFERENCES employee(employee_id)
);
"""

    (output_dir / "schema.sql").write_text(
        schema_sql.strip() + "\n",
        encoding="utf-8",
    )


    # ========================================================
    # 15. GENERATION SUMMARY
    # ========================================================

    summary = {
        "project": "YottaFlex Workforce Scheduling",
        "scale": args.scale,
        "seed": args.seed,
        "start_date": args.start,
        "days": days,
        "row_counts": {
            name: len(dataframe)
            for name, dataframe in tables.items()
        },
        "anomaly_count": len(ground_truth),
        "anomaly_types": (
            ground_truth["issue_type"].tolist()
            if not ground_truth.empty
            else []
        ),
    }

    print(json.dumps(summary, indent=2))

    print("\nData generation completed.")
    print("Output directory:", output_dir)


if __name__ == "__main__":
    main()
