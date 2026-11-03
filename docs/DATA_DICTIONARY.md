# Data dictionary (v0.1)

All IDs are immutable strings. Dates use ISO-8601; timestamps are ISO-8601 local-naive synthetic timestamps. Empty values represent optional fields.

| Entity | Primary key | Fields and validation | Relationships |
|---|---|---|---|
| Employee | employee_id (`EMP-000001`) | first_name, last_name required; email unique; team_id required; employment_status ACTIVE/INACTIVE; hire_date date; weekly_hours_cap positive hours; contract_type FULL_TIME/PART_TIME | Team 1:N Employee; Employee N:M Skill via EmployeeSkill |
| Team | team_id (`TEAM-0001`) | team_name required; location optional; active boolean | Team 1:N Employee and Shift |
| Skill | skill_id (`SKL-001`) | skill_code unique; skill_name required | Skill N:M Employee; Skill 1:N CoverageRequirement |
| ShiftTemplate | shift_template_id (`TPL-A`) | shift_code unique; start_time/end_time HH:MM; duration_hours positive; is_overnight boolean | Template 1:N Shift |
| ShiftAssignment | shift_assignment_id | shift_id required; employee_id optional only for explicit uncovered placeholder; assigned_skill_id; status ASSIGNED/UNCOVERED/CANCELLED; start_at/end_at; weekly_hours_after_assignment hours; coverage_gap boolean | Shift 1:N Assignment; Employee 1:N Assignment |
| LeaveRequest | leave_request_id (`LVE-YYYY-000001`) | employee_id required; leave_type ANNUAL/SICK/PERSONAL; start_date <= end_date; status PENDING/APPROVED/REJECTED; submitted_at required; decided_at optional | Employee 1:N LeaveRequest |
| HolidayCalendar | holiday_id | holiday_date required; holiday_name required; location defaults ALL | Independent calendar dimension |
| AttendanceEvent | attendance_event_id (`ATT-EMP...`) | employee_id, shift_id required; event_type PRESENT/LATE/ABSENT; event_at timestamp; source required | Employee 1:N AttendanceEvent; Shift 1:N AttendanceEvent |
| CoverageRequirement | requirement_id | shift_id, skill_id required; minimum_staff integer >= 0 | Shift 1:N Requirement; Skill 1:N Requirement |
| SwapRequest | swap_request_id (`SWP-YYYY-000001`) | source_assignment_id, requester_employee_id, target_employee_id required; status PENDING/APPROVED/REJECTED/APPLIED; manager_id and decision timestamps optional until decision | Assignment 1:N SwapRequest; Employee 1:N requester/target |

## Bridge and event tables
`employee_skill` is the Employee–Skill N:M bridge with proficiency and effective dates. `attendance_event` and `swap_request` preserve operational events. A production implementation should add append-only `leave_status_event`, `swap_status_event`, and `assignment_event` tables; current starter exports retain request/decision fields and do not overwrite source history.

## Effective dating and lifecycle
Employee skills have `effective_from` and optional `effective_to`. Leave: PENDING -> APPROVED or REJECTED. Swap: PENDING -> APPROVED/REJECTED; only APPROVED may transition to APPLIED. Assignment: PLANNED -> ASSIGNED/CANCELLED; uncovered slots remain explicit.

## Known limitations
The starter generator emits 12 core tables plus the EmployeeSkill bridge. A later iteration should split shift instances and assignments more strictly, add explicit event-history tables, and enforce all foreign keys in the operational database.
