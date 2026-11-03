# Implementation notes

## Decision hierarchy
Hard constraints: employee active status, skill eligibility, leave exclusion, no overlap, and configurable hour caps. Soft objectives: distribute hours evenly, rotate night shifts, minimize preference violations, and reduce avoidable overtime. Coverage gaps remain explicit when the feasible employee pool is insufficient.

## Metrics
- Coverage fulfilment = staffed required slots / total required slots.
- Coverage gap count = required slots without an eligible assigned employee.
- Overtime rate = employees exceeding configured weekly cap / scheduled employees.
- Fairness dispersion = standard deviation of scheduled hours across comparable employees.
- Leave conflict count = assignments overlapping approved leave.
- Swap compliance = applied swaps with prior approval / all applied swaps.

## Next engineering increments
1. Implement CP-SAT decision variables indexed by employee × shift × skill and add hard/soft constraints.
2. Add append-only status event tables and manager approval APIs.
3. Add role-based authentication and authorization.
4. Add MySQL migrations and transaction-level FK/unique/check constraints.
5. Add pytest coverage for lifecycle transitions, optimizer infeasibility and all five labelled edge cases.
