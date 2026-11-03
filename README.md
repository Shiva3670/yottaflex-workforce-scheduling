# YottaFlex Workforce Intelligence & Scheduling

A reproducible workforce scheduling project for leave, skills, shift coverage, attendance, overtime, and approved shift swaps.

## Stack
- Backend: Python 3.11+, FastAPI, SQLAlchemy, Pydantic
- Optimization: OR-Tools CP-SAT (optional dependency; deterministic greedy fallback is provided)
- Data: pandas, Faker, NumPy
- Frontend: React + Vite + TypeScript + Tailwind CSS
- Database: SQLite by default for zero-configuration execution; MySQL supported through `DATABASE_URL`

## Quick start (data + API)
```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.generate_data --scale starter --seed 20261022 --out ../data
python -m scripts.validate_data --input ../data
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs for the API. The starter dataset is deliberately small for fast iteration. Use `--scale full` for 2,000 employees, 100 teams, 90 days, and 5,000 leave requests.

## Frontend
```bash
cd frontend
npm install
npm run dev
```
Set `VITE_API_URL=http://127.0.0.1:8000` in `frontend/.env` if needed.

## Data generation and reproducibility
The generator creates master data before dependent records, uses immutable deterministic IDs, and derives labels from explicit rules. It writes CSVs, JSON manifest, a SQL seed schema, validation report, and a separate `ground_truth.csv`. Ground truth is for evaluation only and must never be joined into model/optimizer input features.

```bash
python -m scripts.generate_data --scale full --seed 20261022 --out ../data
python -m scripts.validate_data --input ../data
python -m scripts.reproducibility_check --scale starter --seed 20261022
```

## Scheduling rules (baseline)
1. An employee must belong to an active team and possess every required skill for the assignment.
2. Approved leave and public holidays block assignment.
3. An employee cannot be assigned overlapping shifts.
4. Weekly working hours cannot exceed the configured cap; overtime is reported separately when enabled.
5. A swap is effective only after manager approval; requests and decisions remain in the event history.
6. Coverage shortfalls are reported by shift and skill rather than silently hidden.
7. Fairness is measured using assigned hours dispersion and undesirable-shift distribution; it is a soft objective, not a reason to violate hard constraints.

## API endpoints
- `GET /health`
- `GET /api/v1/summary`
- `GET /api/v1/employees`
- `GET /api/v1/shifts`
- `POST /api/v1/schedule/generate`
- `GET /api/v1/exceptions`

## Important limitations
This is a candidate-project baseline, not a jurisdiction-specific labor-law compliance product. Labor limits are configurable synthetic assumptions. Before production use, replace them with reviewed policies for the relevant location, collective agreements, contracts, and HR rules. The included SQLite mode is for local evaluation; use MySQL and managed secrets for deployment.

## AI-use disclosure
Record prompts used, generated code accepted/rejected, manual changes, and test evidence in `docs/AI_DISCLOSURE.md`. Do not claim validation that has not been run. This repository includes a disclosure template for the candidate to complete honestly.
