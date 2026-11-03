# YottaFlex Workforce Intelligence & Scheduling

A reproducible, AI-assisted workforce scheduling and optimization project designed to manage employee availability, leave requests, skills, shift coverage, attendance, overtime, and shift swaps.

The project generates synthetic workforce data, validates business rules, identifies scheduling anomalies, and optimizes workforce allocation while considering coverage and fairness.

## 1. Technology Stack

| Component | Technologies |
|---|---|
| Backend | Python 3.11+, FastAPI |
| Optimization | Google OR-Tools CP-SAT |
| Data Processing | Pandas, NumPy, Faker |
| Database | SQLite / MySQL |
| Frontend | React, Vite, TypeScript, Tailwind CSS |
| Version Control | Git, GitHub |

## 2. Project Features

- Synthetic workforce dataset generation.
- Employee, team, skill, shift, and leave management.
- Shift coverage requirement management.
- Employee skill and availability validation.
- Approved leave and shift-overlap detection.
- Overtime and weekly working-hour constraints.
- Conditional cross-team staffing.
- Shift swap approval tracking.
- Workforce scheduling optimization using OR-Tools CP-SAT.
- Coverage gap analysis.
- Weekly workforce fairness analysis.
- Anomaly detection and ground-truth verification.
- CSV, JSON, and SQL data exports.

## 3. Repository Structure

```text
yottaflex-workforce/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── scheduling.py
│   │   └── optimizer.py
│   ├── scripts/
│   │   ├── generate_data.py
│   │   ├── validate_data.py
│   │   ├── reproducibility_check.py
│   │   ├── import_data.py
│   │   └── analyze_weekly_fairness.py
│   └── requirements.txt
├── frontend/
├── data/
│   ├── schema.sql
│   ├── source_manifest.json
│   └── validation_summary.json
├── docs/
│   ├── AI_DISCLOSURE.md
│   ├── DATA_DICTIONARY.md
│   └── IMPLEMENTATION_NOTES.md
├── .gitignore
└── README.md
```

## 4. Installation and Setup

### Backend setup

Run these commands from the repository root:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Generate starter dataset

From the `backend` directory:

```powershell
python scripts/generate_data.py --scale starter --seed 20261022 --out ../data --start 2026-01-01
```

### Validate starter dataset

```powershell
python scripts/validate_data.py --input ../data
```

### Start the backend API

```powershell
uvicorn app.main:app --reload
```

API documentation:

http://127.0.0.1:8000/docs

Health endpoint:

http://127.0.0.1:8000/health

## 5. Full-Scale Dataset Generation

The full-scale dataset uses the same deterministic generator as the starter dataset.

From the repository root:

```powershell
python backend/scripts/generate_data.py --scale full --seed 20261022 --out data_full --start 2026-01-01
```

Full-scale configuration:

- 2,000 employees
- 100 teams
- 90 scheduling days
- 5,000 baseline leave requests
- Five intentionally injected anomaly records

The generated full-scale dataset is retained locally and excluded from Git version control.

### Full-scale validation

```powershell
python backend/scripts/validate_data.py --input data_full
```

### Full-scale reproducibility

```powershell
python backend/scripts/reproducibility_check.py --scale full --seed 20261022
```

## 6. Data Generation and Validation

The generator creates master records before dependent records and uses a fixed random seed for reproducibility.

Generated outputs include:

- CSV datasets
- JSON datasets
- Source manifest
- SQL database schema
- Validation summary
- Separate ground-truth anomaly records

Ground-truth labels are maintained separately and must not be used as optimizer input features.

### Injected anomalies

The dataset includes five intentionally introduced anomaly types:

1. APPROVED_LEAVE_OVERLAP
2. DOUBLE_BOOKED
3. OVERTIME_CAP_EXCEEDED
4. REQUIRED_SKILL_ABSENT
5. SWAP_WITHOUT_APPROVAL

The validator checks the generated data and compares detected anomaly identifiers against the ground-truth records.

## 7. Scheduling and Optimization

The scheduling optimizer uses Google OR-Tools CP-SAT.

Key scheduling considerations include:

- Employee availability and employment status.
- Required skills and skill validity dates.
- Approved leave restrictions.
- Shift overlap prevention.
- Minimum rest periods.
- Weekly working-hour limits.
- Coverage requirements.
- Conditional cross-team staffing.
- Workforce fairness.

The optimization process uses two phases:

1. Minimize uncovered staffing positions.
2. Optimize workload fairness while preserving the minimum uncovered-position result.

Coverage gaps are reported rather than silently assigning employees who violate hard scheduling constraints.

## 8. Workforce Fairness and Coverage Analysis

The project includes reporting scripts for:

- Weekly employee workload distribution.
- Team-level workload fairness.
- Coverage shortfalls.
- Unfilled staffing requirements.
- Cross-team staffing analysis.

Run weekly fairness analysis from the repository root:

```powershell
python backend/scripts/analyze_weekly_fairness.py
```

Refer to the generated reports in the `data/` directory.

## 9. Database

The operational database schema is provided in:

```text
data/schema.sql
```

The database import utility is:

```text
backend/scripts/import_data.py
```

The operational schema contains 12 tables covering teams, skills, employees, shifts, leave, attendance, assignments, and shift swaps.

The ground-truth anomaly dataset is deliberately excluded from the operational schema.

Consult the import script and implementation notes for database configuration and execution requirements.

## 10. Validation Results

The full-scale dataset was successfully validated.

| Metric | Verified result |
|---|---:|
| Employees | 2,000 |
| Teams | 100 |
| Shifts | 27,001 |
| Coverage requirements | 32,400 |
| Leave requests | 5,001 |
| Shift assignments | 112,151 |
| Attendance events | 109,792 |
| Ground-truth anomalies | 5 |
| Validation issues | 0 |

### Reproducibility results

Full-scale reproducibility testing was completed using seed `20261022`.

- CSV files checked: 13
- Hash mismatches: 0
- Reproducibility status: PASS

All five injected anomaly types were detected and matched against ground truth.

## 11. API Endpoints

The documented API endpoints include:

- `GET /health`
- `GET /api/v1/summary`
- `GET /api/v1/employees`
- `GET /api/v1/shifts`
- `POST /api/v1/schedule/generate`
- `GET /api/v1/exceptions`

## 12. Limitations

This project is a candidate-project baseline and is not a jurisdiction-specific labor-law compliance product.

Labor limits and workforce policies use synthetic assumptions. Production deployment requires reviewed policies for the relevant jurisdiction, employment contracts, collective agreements, and HR rules.

The full-scale synthetic dataset is retained locally rather than committed to GitHub.

Overtime detection relies on the stored `weekly_hours_after_assignment` field; actual weekly hours are not independently reconstructed by the validator.

Ground-truth matching verifies labelled anomaly IDs and does not establish the correctness of every possible business rule.

## 13. AI Use Disclosure

AI tools were used as development assistance during implementation and review.

The disclosure document should describe:

- AI tools used.
- Tasks for which AI assistance was used.
- Generated code or recommendations accepted or rejected.
- Manual review and modifications.
- Testing and validation evidence.
- Known limitations.

See `docs/AI_DISCLOSURE.md` for the detailed disclosure.

## 14. License and Data

This project uses synthetic workforce data and does not contain real employee personal information.

See the repository license and individual dependency licenses for applicable usage terms.

---

**Project:** YottaFlex Workforce Intelligence & Scheduling  
**Repository:** https://github.com/Shiva3670/yottaflex-workforce