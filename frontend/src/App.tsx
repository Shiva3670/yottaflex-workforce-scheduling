import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowLeftRight,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  Download,
  FileSpreadsheet,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  Users,
  XCircle,
} from "lucide-react";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

interface Summary {
  employees: number;
  teams: number;
  assignments: number;
  leave_requests: number;
  coverage_requirements: number;
}

interface ScheduleAssignment {
  requirement_id: string;
  shift_id: string;
  employee_id: string;
  employee_home_team_id: string;
  shift_team_id: string;
  cross_team_assignment: boolean;
  assigned_skill_id: string;
  start_at: string;
  end_at: string;
  status: string;
}

interface CoverageRow {
  requirement_id: string;
  shift_id: string;
  team_id: string;
  skill_id: string;
  start_at: string;
  end_at: string;
  required_staff: number;
  assigned_staff: number;
  uncovered_staff: number;
  coverage_status: string;
  reason: string;
}

interface DiagnosticRow {
  requirement_id: string;
  shift_id: string;
  team_id: string;
  skill_id: string;
  required_staff: number;
  uncovered_staff: number;
  team_employee_count: number;
  cross_team_candidate_count: number;
  candidate_policy_pool_count?: number;
  qualified_employee_count: number;
  qualified_on_approved_leave: number;
  qualified_available_after_leave: number;
  blocked_by_overlap: number;
  blocked_by_rest_period: number;
  blocked_by_weekly_hours_cap: number;
  apparently_eligible_candidates: number;
  diagnostic: string;
}

interface EmployeeWeeklyFairness {
  employee_id: string;
  team_id: string;
  iso_year: number;
  iso_week: number;
  week_start: string;
  assigned_shifts: number;
  scheduled_hours: number;
  weekly_hours_cap: number;
  fairness_reference_hours: number;
  utilization_pct: number;
}

interface TeamWeeklyFairness {
  team_id: string;
  iso_year: number;
  iso_week: number;
  week_start: string;
  employees_count: number;
  employees_with_assignments: number;
  total_scheduled_hours: number;
  mean_utilization_pct: number;
  min_utilization_pct: number;
  max_utilization_pct: number;
  utilization_range_pct: number;
}

interface FairnessReport {
  employee_weekly: EmployeeWeeklyFairness[];
  team_weekly: TeamWeeklyFairness[];
  methodology: string;
}

interface ScheduleResult {
  requested_start: string;
  requested_days: number;
  requested_end: string;
  assignment_count: number;
  overlap_conflicts: number;
  rest_period_violations: number;
  overtime_assignments: number;
  overtime_employee_weeks: number;
  approved_leave_overlaps: number;
  invalid_skill_assignments: number;
  cross_team_assignments: number;
  coverage_gaps: number;
  solver_status: string;
  coverage_optimal: boolean;
  independent_validation: string;
  uncovered_requirements: number;
  total_uncovered_positions: number;
  hard_rules: string[];
  assignments: ScheduleAssignment[];
  gaps: Array<{ requirement_id: string; uncovered_staff: number }>;
  coverage_analysis: CoverageRow[];
  diagnostics: DiagnosticRow[];
  fairness_report?: FairnessReport;
}

interface ValidationCheck {
  label: string;
  value: number;
}

interface AggregateCoverage {
  key: string;
  required: number;
  assigned: number;
  uncovered: number;
  requirements: number;
  coveragePct: number;
}

function formatNumber(value: number | undefined | null): string {
  return (value ?? 0).toLocaleString("en-IN");
}

function formatHours(value: number | undefined | null): string {
  return `${(value ?? 0).toFixed(1)} h`;
}

function formatDateTime(value: string): string {
  if (!value) return "—";
  return value.replace("T", " ").slice(0, 16);
}

function csvCell(value: unknown): string {
  let text = value == null ? "" : String(value);
  // Prevent spreadsheet formula execution when exported values begin with
  // formula-significant characters. These data files are for analysis only.
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

function downloadCsv(
  filename: string,
  rows: Array<Record<string, unknown>>,
): void {
  if (!rows.length) return;

  const columns = Array.from(
    rows.reduce((keys, row) => {
      Object.keys(row).forEach((key) => keys.add(key));
      return keys;
    }, new Set<string>()),
  );

  const csv = [
    columns.map(csvCell).join(","),
    ...rows.map((row) => columns.map((key) => csvCell(row[key])).join(",")),
  ].join("\r\n");

  const blob = new Blob(["\uFEFF", csv], {
    type: "text/csv;charset=utf-8;",
  });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
}

function aggregateCoverage(
  rows: CoverageRow[],
  field: "team_id" | "skill_id",
): AggregateCoverage[] {
  const groups = new Map<string, AggregateCoverage>();

  for (const row of rows) {
    const key = row[field] || "UNKNOWN";
    const current = groups.get(key) ?? {
      key,
      required: 0,
      assigned: 0,
      uncovered: 0,
      requirements: 0,
      coveragePct: 0,
    };

    current.required += Number(row.required_staff || 0);
    current.assigned += Number(row.assigned_staff || 0);
    current.uncovered += Number(row.uncovered_staff || 0);
    current.requirements += 1;
    groups.set(key, current);
  }

  return Array.from(groups.values())
    .map((row) => ({
      ...row,
      coveragePct:
        row.required > 0
          ? (row.assigned / row.required) * 100
          : 0,
    }))
    .sort((a, b) => a.coveragePct - b.coveragePct || b.uncovered - a.uncovered);
}

function App() {
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [result, setResult] = useState<ScheduleResult | null>(null);
  const [startDate, setStartDate] = useState("2026-01-01");
  const [days, setDays] = useState(7);
  const [search, setSearch] = useState("");

  async function load(): Promise<void> {
    setLoadingSummary(true);
    setError("");

    try {
      const response = await fetch(`${API}/api/v1/summary`);
      if (!response.ok) {
        throw new Error(`Unable to load dashboard summary (${response.status}).`);
      }
      setData((await response.json()) as Summary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "API unavailable.");
    } finally {
      setLoadingSummary(false);
    }
  }

  async function optimize(): Promise<void> {
    if (!startDate) {
      setError("Select a scheduling start date.");
      return;
    }

    setBusy(true);
    setError("");
    setResult(null);
    setSearch("");

    try {
      const response = await fetch(`${API}/api/v1/schedule/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start_date: startDate, days }),
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(`Optimization failed (${response.status}): ${message}`);
      }

      setResult((await response.json()) as ScheduleResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to generate the schedule.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const coverageRows = result?.coverage_analysis ?? [];
  const diagnosticRows = result?.diagnostics ?? [];
  const fairnessReport = result?.fairness_report;

  const coverageStats = useMemo(() => {
    const required = coverageRows.reduce(
      (sum, row) => sum + Number(row.required_staff || 0),
      0,
    );
    const assigned = coverageRows.reduce(
      (sum, row) => sum + Number(row.assigned_staff || 0),
      0,
    );
    const fullyCovered = coverageRows.filter(
      (row) => Number(row.uncovered_staff) === 0,
    ).length;
    const partiallyCovered = coverageRows.filter(
      (row) => Number(row.uncovered_staff) > 0,
    ).length;

    return {
      required,
      assigned,
      fullyCovered,
      partiallyCovered,
      percentage: required > 0 ? (assigned / required) * 100 : 0,
    };
  }, [coverageRows]);

  const teamCoverage = useMemo(
    () => aggregateCoverage(coverageRows, "team_id"),
    [coverageRows],
  );

  const skillCoverage = useMemo(
    () => aggregateCoverage(coverageRows, "skill_id").sort(
      (a, b) => b.uncovered - a.uncovered || a.coveragePct - b.coveragePct,
    ),
    [coverageRows],
  );

  const visibleAssignments = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (result?.assignments ?? [])
      .filter((row) => {
        if (!query) return true;
        return [
          row.employee_id,
          row.shift_id,
          row.requirement_id,
          row.employee_home_team_id,
          row.shift_team_id,
          row.assigned_skill_id,
        ]
          .join(" ")
          .toLowerCase()
          .includes(query);
      })
      .slice(0, 25);
  }, [result, search]);

  const coverageSolverStatus =
    result?.solver_status.match(/COVERAGE_([^;]+)/)?.[1] ?? "—";
  const fairnessSolverStatus =
    result?.solver_status.match(/FAIRNESS_([^;]+)/)?.[1] ?? "—";
  const validationPassed = result?.independent_validation === "PASS";

  const validationChecks: ValidationCheck[] = result
    ? [
        { label: "Overlap conflicts", value: result.overlap_conflicts },
        { label: "Rest-period violations", value: result.rest_period_violations },
        { label: "Overtime assignments", value: result.overtime_assignments },
        { label: "Approved leave overlaps", value: result.approved_leave_overlaps },
        { label: "Invalid skill assignments", value: result.invalid_skill_assignments },
      ]
    : [];

  const assignmentExportRows = (result?.assignments ?? []).map((row) => ({
    requirement_id: row.requirement_id,
    shift_id: row.shift_id,
    employee_id: row.employee_id,
    employee_home_team_id: row.employee_home_team_id,
    shift_team_id: row.shift_team_id,
    cross_team_assignment: row.cross_team_assignment,
    assigned_skill_id: row.assigned_skill_id,
    start_at: row.start_at,
    end_at: row.end_at,
    status: row.status,
  }));

  const coverageExportRows = coverageRows.map((row) => ({ ...row }));
  const diagnosticExportRows = diagnosticRows.map((row) => ({ ...row }));
  const employeeFairnessExportRows = (fairnessReport?.employee_weekly ?? []).map(
    (row) => ({ ...row }),
  );
  const teamFairnessExportRows = (fairnessReport?.team_weekly ?? []).map(
    (row) => ({ ...row }),
  );

  return (
    <main className="dashboard">
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon"><Activity size={23} /></div>
          <div>
            <div className="eyebrow">WORKFORCE INTELLIGENCE</div>
            <h1>YottaFlex <span>Operations</span></h1>
            <p>Intelligent scheduling, workforce coverage and operational compliance.</p>
          </div>
        </div>
        <button className="secondary-button" onClick={load} disabled={loadingSummary}>
          <RefreshCw size={16} className={loadingSummary ? "spin" : ""} />
          {loadingSummary ? "Refreshing..." : "Refresh data"}
        </button>
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <AlertTriangle size={19} />
          <div>
            <strong>Something needs attention</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      <section className="section-heading">
        <div>
          <div className="eyebrow">DATA OVERVIEW</div>
          <h2>Workforce snapshot</h2>
        </div>
        <span className="period-label"><Activity size={14} /> Generated dataset</span>
      </section>

      <section className="overview-grid">
        <article className="overview-card">
          <div className="overview-icon purple"><Users size={20} /></div>
          <div className="card-label">Employees</div>
          <strong>{formatNumber(data?.employees)}</strong>
          <small>Workforce records</small>
        </article>
        <article className="overview-card">
          <div className="overview-icon blue"><Users size={20} /></div>
          <div className="card-label">Teams</div>
          <strong>{formatNumber(data?.teams)}</strong>
          <small>Operational teams</small>
        </article>
        <article className="overview-card">
          <div className="overview-icon teal"><CalendarDays size={20} /></div>
          <div className="card-label">Baseline assignments</div>
          <strong>{formatNumber(data?.assignments)}</strong>
          <small>Original dataset records</small>
        </article>
        <article className="overview-card">
          <div className="overview-icon orange"><ClipboardList size={20} /></div>
          <div className="card-label">Leave requests</div>
          <strong>{formatNumber(data?.leave_requests)}</strong>
          <small>Submitted requests</small>
        </article>
      </section>

      <section className="engine-panel">
        <div className="engine-info">
          <div className="eyebrow">CP-SAT OPTIMIZATION ENGINE</div>
          <h2>Generate optimized workforce schedule</h2>
          <p>
            Optimize employee allocation using skill eligibility, leave restrictions,
            weekly hour limits, minimum rest periods and workforce fairness.
          </p>
          <div className="engine-tags">
            <span>Coverage optimization</span>
            <span>Fairness optimization</span>
            <span>11-hour rest rule</span>
          </div>
        </div>
        <div className="engine-controls">
          <label htmlFor="startDate">Scheduling start date</label>
          <input
            id="startDate"
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
            disabled={busy}
          />
          <label htmlFor="days">Scheduling horizon</label>
          <select
            id="days"
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
            disabled={busy}
          >
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
            <option value={30}>30 days</option>
            <option value={60}>60 days</option>
            <option value={90}>90 days</option>
          </select>
          <button
            className="primary-button"
            onClick={optimize}
            disabled={busy || !data || !startDate}
          >
            {busy ? <><RefreshCw size={17} className="spin" /> Optimizing schedule...</> : <><Play size={17} fill="currentColor" /> Generate schedule</>}
          </button>
          {busy && (
            <small className="running-note">
              CP-SAT is solving coverage and fairness objectives. Keep this page open.
            </small>
          )}
        </div>
      </section>

      {!result && !busy && (
        <section className="empty-state">
          <div className="empty-icon"><CalendarDays size={27} /></div>
          <h3>No optimization results yet</h3>
          <p>Select a scheduling period and generate a schedule to view coverage, fairness and validation results.</p>
        </section>
      )}

      {busy && (
        <section className="empty-state loading-state">
          <RefreshCw size={28} className="spin" />
          <h3>Optimizing workforce allocation</h3>
          <p>The engine is evaluating staffing coverage and balancing employee workloads.</p>
        </section>
      )}

      {result && (
        <>
          <section className="section-heading results-heading">
            <div>
              <div className="eyebrow">OPTIMIZATION RESULTS</div>
              <h2>Scheduling performance</h2>
              <p>{result.requested_start} to {result.requested_end} · {result.requested_days} days</p>
            </div>
            <div className={`validation-pill ${validationPassed ? "passed" : "failed"}`}>
              {validationPassed ? <CheckCircle2 size={17} /> : <XCircle size={17} />}
              Independent validation: {result.independent_validation ?? "NOT AVAILABLE"}
            </div>
          </section>

          <section className="solver-grid">
            <article className="solver-card">
              <div className="solver-card-top"><span>Coverage optimization</span><ShieldCheck size={19} /></div>
              <strong>{coverageSolverStatus}</strong>
              <small>{result.coverage_optimal ? "Minimum uncovered staffing proven" : "Coverage optimality not proven"}</small>
            </article>
            <article className="solver-card">
              <div className="solver-card-top"><span>Fairness optimization</span><Activity size={19} /></div>
              <strong>{fairnessSolverStatus}</strong>
              <small>Solver status; FEASIBLE does not mean fairness optimality was proven.</small>
            </article>
          </section>

          <section className="metric-grid">
            <article className="metric-card">
              <span className="metric-icon blue"><CalendarDays size={19} /></span>
              <small>Optimized assignments</small>
              <strong>{formatNumber(result.assignment_count)}</strong>
            </article>
            <article className="metric-card">
              <span className="metric-icon orange"><AlertTriangle size={19} /></span>
              <small>Uncovered positions</small>
              <strong>{formatNumber(result.coverage_gaps)}</strong>
            </article>
            <article className="metric-card">
              <span className="metric-icon teal"><ArrowLeftRight size={19} /></span>
              <small>Cross-team assignments</small>
              <strong>{formatNumber(result.cross_team_assignments)}</strong>
            </article>
            <article className="metric-card">
              <span className="metric-icon purple"><ClipboardList size={19} /></span>
              <small>Requirements with gaps</small>
              <strong>{formatNumber(result.uncovered_requirements)}</strong>
            </article>
          </section>

          <section className="content-grid">
            <article className="content-card coverage-card">
              <div className="card-heading">
                <div><div className="eyebrow">STAFFING FULFILLMENT</div><h3>Coverage performance</h3></div>
                <span className="coverage-percent">{coverageStats.percentage.toFixed(1)}%</span>
              </div>
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${Math.min(100, coverageStats.percentage)}%` }} />
              </div>
              <div className="coverage-legend">
                <div><span className="legend-dot green-dot" /> Fully covered <strong>{coverageStats.fullyCovered}</strong></div>
                <div><span className="legend-dot orange-dot" /> With staffing gaps <strong>{coverageStats.partiallyCovered}</strong></div>
              </div>
              <div className="coverage-numbers">
                <div><small>Required positions</small><strong>{formatNumber(coverageStats.required)}</strong></div>
                <div><small>Assigned positions</small><strong>{formatNumber(coverageStats.assigned)}</strong></div>
                <div><small>Uncovered positions</small><strong>{formatNumber(result.coverage_gaps)}</strong></div>
              </div>
            </article>

            <article className="content-card validation-card">
              <div className="card-heading">
                <div><div className="eyebrow">CONSTRAINT AUDIT</div><h3>Independent validation</h3></div>
                {validationPassed ? <CheckCircle2 className="success-icon" size={23} /> : <XCircle className="danger-icon" size={23} />}
              </div>
              {validationChecks.map((check) => (
                <div className="validation-row" key={check.label}>
                  <span>{check.label}</span>
                  <strong className={check.value === 0 ? "zero" : "nonzero"}>
                    {formatNumber(check.value)}
                    {check.value === 0 ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
                  </strong>
                </div>
              ))}
              <div className={`validation-footer ${validationPassed ? "" : "validation-warning"}`}>
                {validationPassed ? "All five independent checks passed." : "One or more independent checks need attention."}
              </div>
            </article>
          </section>

          {/* Team-wise coverage comparison */}
          <section className="content-card chart-card">
            <div className="table-heading">
              <div>
                <div className="eyebrow">TEAM PERFORMANCE</div>
                <h3>Team-wise coverage comparison</h3>
                <p>Coverage rate by destination team, ranked from lowest to highest.</p>
              </div>
              <button
                className="export-button"
                onClick={() => downloadCsv(`team-coverage-${startDate}.csv`, teamCoverage.map((row) => ({
                  team_id: row.key,
                  required_staff: row.required,
                  assigned_staff: row.assigned,
                  uncovered_staff: row.uncovered,
                  requirements: row.requirements,
                  coverage_percent: Number(row.coveragePct.toFixed(2)),
                })))}
                disabled={teamCoverage.length === 0}
              ><Download size={15} /> Export teams</button>
            </div>
            {teamCoverage.length === 0 ? <p className="no-data">No team coverage data is available.</p> : (
              <div className="bar-chart-list">
                {teamCoverage.map((row) => (
                  <div className="bar-chart-row" key={row.key}>
                    <div className="bar-label"><strong>{row.key}</strong><span>{row.coveragePct.toFixed(1)}% · {row.uncovered} uncovered</span></div>
                    <div className="bar-track"><div className={`bar-fill ${row.uncovered > 0 ? "bar-warning" : "bar-good"}`} style={{ width: `${Math.min(100, row.coveragePct)}%` }} /></div>
                    <small>{row.assigned}/{row.required}</small>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Skill-wise shortages */}
          <section className="content-card chart-card">
            <div className="table-heading">
              <div>
                <div className="eyebrow">SKILL CAPACITY</div>
                <h3>Skill-wise staffing shortage</h3>
                <p>Required, assigned and uncovered positions grouped by required skill.</p>
              </div>
              <button
                className="export-button"
                onClick={() => downloadCsv(`skill-shortages-${startDate}.csv`, skillCoverage.map((row) => ({
                  skill_id: row.key,
                  required_staff: row.required,
                  assigned_staff: row.assigned,
                  uncovered_staff: row.uncovered,
                  requirements: row.requirements,
                  coverage_percent: Number(row.coveragePct.toFixed(2)),
                })))}
                disabled={skillCoverage.length === 0}
              ><Download size={15} /> Export skills</button>
            </div>
            {skillCoverage.length === 0 ? <p className="no-data">No skill coverage data is available.</p> : (
              <div className="skill-grid">
                {skillCoverage.map((row) => (
                  <article className="skill-card" key={row.key}>
                    <div className="skill-card-top"><strong>{row.key}</strong><span className={row.uncovered > 0 ? "shortage-label" : "covered-label"}>{row.uncovered > 0 ? `${row.uncovered} short` : "Covered"}</span></div>
                    <div className="skill-progress"><div style={{ width: `${Math.min(100, row.coveragePct)}%` }} /></div>
                    <div className="skill-values"><span>{row.assigned} assigned</span><span>{row.required} required</span></div>
                    <small>{row.coveragePct.toFixed(1)}% coverage · {row.requirements} requirements</small>
                  </article>
                ))}
              </div>
            )}
          </section>

          {/* Weekly workload fairness */}
          <section className="content-card table-card">
            <div className="table-heading">
              <div>
                <div className="eyebrow">POST-SOLVE WORKLOAD ANALYSIS</div>
                <h3>Weekly workload fairness report</h3>
                <p>Compare scheduled hours and normalized workload utilization across home teams and ISO weeks.</p>
              </div>
              <div className="export-actions">
                <button className="export-button" onClick={() => downloadCsv(`employee-weekly-workload-${startDate}.csv`, employeeFairnessExportRows)} disabled={employeeFairnessExportRows.length === 0}>
                  <Download size={15} /> Employee report
                </button>
                <button className="export-button" onClick={() => downloadCsv(`team-weekly-fairness-${startDate}.csv`, teamFairnessExportRows)} disabled={teamFairnessExportRows.length === 0}>
                  <Download size={15} /> Team report
                </button>
              </div>
            </div>

            {!fairnessReport ? (
              <div className="notice-banner"><AlertTriangle size={17} /> The API has not returned a fairness report yet. Add the backend fairness-report helper described below.</div>
            ) : (
              <>
                <div className="methodology-note">{fairnessReport.methodology}</div>
                <div className="table-scroll">
                  <table>
                    <thead><tr>
                      <th>Team</th><th>ISO week</th><th>Employees</th><th>Assigned employees</th>
                      <th>Total hours</th><th>Mean utilization</th><th>Min utilization</th><th>Max utilization</th><th>Range</th>
                    </tr></thead>
                    <tbody>
                      {fairnessReport.team_weekly.slice(0, 30).map((row) => (
                        <tr key={`${row.team_id}-${row.iso_year}-${row.iso_week}`}>
                          <td className="id-cell">{row.team_id}</td>
                          <td>{row.iso_year}-W{String(row.iso_week).padStart(2, "0")}</td>
                          <td>{row.employees_count}</td>
                          <td>{row.employees_with_assignments}</td>
                          <td>{formatHours(row.total_scheduled_hours)}</td>
                          <td>{row.mean_utilization_pct.toFixed(1)}%</td>
                          <td>{row.min_utilization_pct.toFixed(1)}%</td>
                          <td>{row.max_utilization_pct.toFixed(1)}%</td>
                          <td>{row.utilization_range_pct.toFixed(1)} pp</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="table-footnote">Showing up to 30 team-week rows. Export the full report for all rows. Utilization is a post-solve workload indicator, not the CP-SAT fairness objective value.</p>
              </>
            )}
          </section>

          {/* Coverage gap diagnostics */}
          <section className="content-card table-card">
            <div className="table-heading">
              <div>
                <div className="eyebrow">EXPLAINABLE OPTIMIZATION</div>
                <h3>Coverage gap diagnostics</h3>
                <p>Requirements that could not be fully staffed under the current scheduling constraints.</p>
              </div>
              <div className="export-actions">
                <span className="count-pill">{diagnosticRows.length} diagnostics</span>
                <button className="export-button" onClick={() => downloadCsv(`coverage-diagnostics-${startDate}.csv`, diagnosticExportRows)} disabled={diagnosticExportRows.length === 0}>
                  <Download size={15} /> Export CSV
                </button>
              </div>
            </div>
            {diagnosticRows.length === 0 ? (
              <div className="table-empty"><CheckCircle2 size={22} /> No uncovered requirements in this schedule.</div>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead><tr>
                    <th>Requirement</th><th>Team</th><th>Skill</th><th>Uncovered</th>
                    <th>Overlap blockers</th><th>Rest blockers</th><th>Hours blockers</th><th>Diagnostic</th>
                  </tr></thead>
                  <tbody>
                    {diagnosticRows.map((row) => (
                      <tr key={row.requirement_id}>
                        <td className="id-cell">{row.requirement_id}</td>
                        <td>{row.team_id}</td><td>{row.skill_id}</td>
                        <td><span className="gap-badge">{row.uncovered_staff}</span></td>
                        <td>{row.blocked_by_overlap}</td><td>{row.blocked_by_rest_period}</td>
                        <td>{row.blocked_by_weekly_hours_cap}</td>
                        <td className="diagnostic-cell">{row.diagnostic}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="table-footnote">Diagnostic blockers can overlap. They identify potential constraints affecting staffing and are not additive proof of infeasibility.</p>
          </section>

          {/* Optimized assignments */}
          <section className="content-card table-card">
            <div className="table-heading assignment-heading">
              <div>
                <div className="eyebrow">GENERATED WORKFORCE PLAN</div>
                <h3>Optimized shift assignments</h3>
                <p>Employee allocations selected by the CP-SAT scheduling engine.</p>
              </div>
              <div className="export-actions">
                <div className="search-box">
                  <Search size={17} />
                  <input type="search" placeholder="Search employee, shift, team..." value={search} onChange={(event) => setSearch(event.target.value)} />
                </div>
                <button className="export-button" onClick={() => downloadCsv(`optimized-assignments-${startDate}.csv`, assignmentExportRows)} disabled={assignmentExportRows.length === 0}>
                  <Download size={15} /> Export CSV
                </button>
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <thead><tr>
                  <th>Employee</th><th>Shift</th><th>Start</th><th>End</th>
                  <th>Home team</th><th>Assigned team</th><th>Skill</th><th>Allocation</th>
                </tr></thead>
                <tbody>
                  {visibleAssignments.map((row, index) => (
                    <tr key={`${row.requirement_id}-${row.employee_id}-${index}`}>
                      <td className="id-cell">{row.employee_id}</td>
                      <td>{row.shift_id}</td><td>{formatDateTime(row.start_at)}</td>
                      <td>{formatDateTime(row.end_at)}</td><td>{row.employee_home_team_id}</td>
                      <td>{row.shift_team_id}</td><td>{row.assigned_skill_id}</td>
                      <td><span className={`allocation-badge ${row.cross_team_assignment ? "borrowed" : "home"}`}>
                        {row.cross_team_assignment ? "Cross-team" : "Home team"}
                      </span></td>
                    </tr>
                  ))}
                  {visibleAssignments.length === 0 && <tr><td colSpan={8} className="no-results">No assignments match your search.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="table-bottom">
              Showing {formatNumber(visibleAssignments.length)} of {formatNumber(result.assignments.length)} assignments
              {result.assignments.length > 25 && " · Showing the first 25 matching rows"}
            </div>
          </section>

          {/* Other exports */}
          <section className="export-strip">
            <div><FileSpreadsheet size={19} /><div><strong>Export analysis data</strong><small>Download the current optimization outputs as CSV files.</small></div></div>
            <div className="export-actions">
              <button className="export-button" onClick={() => downloadCsv(`coverage-analysis-${startDate}.csv`, coverageExportRows)} disabled={!coverageExportRows.length}><Download size={15} /> Coverage CSV</button>
              <button className="export-button" onClick={() => downloadCsv(`employee-weekly-workload-${startDate}.csv`, employeeFairnessExportRows)} disabled={!employeeFairnessExportRows.length}><Download size={15} /> Workload CSV</button>
            </div>
          </section>

          <section className="rules-panel">
            <div><div className="eyebrow">OPTIMIZATION CONSTRAINTS</div><h3>Scheduling rules applied</h3></div>
            <div className="rule-list">
              {(result.hard_rules ?? []).map((rule) => (
                <span key={rule}><CheckCircle2 size={14} />{rule.replace(/_/g, " ")}</span>
              ))}
            </div>
          </section>
        </>
      )}

      <footer className="footer">
        <span>YottaFlex Workforce Intelligence</span>
        <span>Candidate Project · Synthetic data only · v0.1.0</span>
      </footer>
    </main>
  );
}

export default App;
