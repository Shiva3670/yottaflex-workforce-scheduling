# AI Use Disclosure – YottaFlex Workforce Intelligence & Scheduling

## 1. AI Tools Used

| Tool | Purpose |
|---|---|
| ChatGPT (OpenAI) | Technical guidance, code review, debugging, optimization suggestions, documentation, and Git workflow assistance |

## 2. AI Assistance Record

| Development activity | AI assistance | Human review and contribution | Validation evidence |
|---|---|---|---|
| Synthetic dataset generation | Guidance on deterministic generation, data relationships, and anomaly injection | Reviewed generator logic, applied code changes, and executed dataset generation | Starter and full-scale generation completed |
| Data validation | Assistance optimizing leave-overlap, double-booking, skill, overtime, and ground-truth checks | Reviewed and integrated the optimized validator | Full-scale validation: PASS, zero issues |
| Scheduling optimization | Guidance on CP-SAT constraints, coverage optimization, fairness, and conditional cross-team staffing | Reviewed optimization results and evaluated staffing trade-offs | Two-phase optimization executed; cross-team staffing experiment completed |
| Database schema | Assistance reviewing SQL schema, primary keys, foreign keys, and table relationships | Reviewed the 12 operational table definitions | Schema reviewed; database integration testing remains to be confirmed |
| Fairness analysis | Assistance with weekly workload analysis and reporting | Integrated the analysis script and generated reports | Fairness and coverage reports generated |
| Documentation | Assistance improving README structure, setup instructions, and technical explanations | Reviewed and updated project documentation | Git changes reviewed and committed |
| Version control | Guidance on staging, commit organization, and repository cleanup | Executed Git commands and pushed commits | GitHub synchronization confirmed |

## 3. Human Contributions and Decisions

The following activities involved direct human review, implementation, or decision-making:

- Selected the project scope, workforce scheduling requirements, and synthetic dataset configuration.
- Reviewed and executed the data generation and validation scripts.
- Evaluated the scheduling optimizer results and cross-team staffing trade-offs.
- Reviewed the database schema and import workflow.
- Executed the starter and full-scale reproducibility checks.
- Reviewed generated reports and validation outputs.
- Managed Git commits and pushed project changes to GitHub.
- Made final decisions about which implementation changes to retain.

AI-generated recommendations were treated as development assistance and were not accepted without review.

## 4. Testing and Validation Evidence

The following tests were executed during development:

| Test | Result |
|---|---|
| Starter dataset validation | PASS |
| Full-scale dataset validation | PASS |
| Starter reproducibility | PASS |
| Full-scale reproducibility | PASS |
| Full-scale CSV hash comparison | PASS – 13 files matched |
| Ground-truth anomaly verification | PASS – all 5 anomaly types matched |
| Git working-tree verification | PASS – clean |
| GitHub synchronization | PASS |

Full-scale dataset configuration:

- 2,000 employees
- 100 teams
- 90 days
- 5,001 leave records, including one injected anomaly
- 112,151 shift assignments
- 109,792 attendance events

## 5. Known Limitations

- Overtime validation relies on the stored `weekly_hours_after_assignment` field and does not independently reconstruct weekly working hours.
- Ground-truth matching verifies labelled anomaly identifiers, not every possible business rule.
- Scheduling optimization can return feasible rather than proven-optimal fairness results within the configured time limit.
- Database integration should be verified separately against the target MySQL environment.

## 6. Declaration

AI tools were used as development assistants for technical guidance, code review, debugging, optimization suggestions, and documentation.

The project implementation, testing, review of generated outputs, and final technical decisions were subject to human oversight.

This disclosure describes the AI assistance used during development and does not claim that AI-generated outputs were independently verified unless supporting test evidence is available.