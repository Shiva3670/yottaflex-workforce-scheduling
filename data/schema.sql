-- Logical seed schema; CSV exports are the canonical generated records.
CREATE TABLE team (team_id VARCHAR(16) PRIMARY KEY, team_name VARCHAR(120) NOT NULL, location VARCHAR(120), active BOOLEAN NOT NULL);
CREATE TABLE skill (skill_id VARCHAR(16) PRIMARY KEY, skill_code VARCHAR(40) UNIQUE NOT NULL, skill_name VARCHAR(80) NOT NULL);
CREATE TABLE employee (employee_id VARCHAR(16) PRIMARY KEY, team_id VARCHAR(16) NOT NULL REFERENCES team(team_id), email VARCHAR(180) UNIQUE NOT NULL, employment_status VARCHAR(20) NOT NULL);
CREATE TABLE shift_template (shift_template_id VARCHAR(16) PRIMARY KEY, shift_code VARCHAR(8) UNIQUE NOT NULL);
CREATE TABLE shift (shift_id VARCHAR(80) PRIMARY KEY, team_id VARCHAR(16) NOT NULL REFERENCES team(team_id), shift_template_id VARCHAR(16) NOT NULL REFERENCES shift_template(shift_template_id), start_at TIMESTAMP NOT NULL, end_at TIMESTAMP NOT NULL);
CREATE TABLE employee_skill (employee_id VARCHAR(16) REFERENCES employee(employee_id), skill_id VARCHAR(16) REFERENCES skill(skill_id), effective_from DATE NOT NULL, effective_to DATE, PRIMARY KEY(employee_id, skill_id, effective_from));
CREATE TABLE coverage_requirement (requirement_id VARCHAR(120) PRIMARY KEY, shift_id VARCHAR(80) REFERENCES shift(shift_id), skill_id VARCHAR(16) REFERENCES skill(skill_id), minimum_staff INTEGER NOT NULL CHECK(minimum_staff >= 0));
CREATE TABLE leave_request (leave_request_id VARCHAR(24) PRIMARY KEY, employee_id VARCHAR(16) REFERENCES employee(employee_id), start_date DATE NOT NULL, end_date DATE NOT NULL, status VARCHAR(16) NOT NULL);
CREATE TABLE shift_assignment (shift_assignment_id VARCHAR(140) PRIMARY KEY, shift_id VARCHAR(80) REFERENCES shift(shift_id), employee_id VARCHAR(16) REFERENCES employee(employee_id), status VARCHAR(20) NOT NULL);
CREATE TABLE attendance_event (attendance_event_id VARCHAR(100) PRIMARY KEY, employee_id VARCHAR(16) REFERENCES employee(employee_id), shift_id VARCHAR(80) REFERENCES shift(shift_id), event_type VARCHAR(16) NOT NULL);
CREATE TABLE holiday_calendar (holiday_id VARCHAR(32) PRIMARY KEY, holiday_date DATE NOT NULL, holiday_name VARCHAR(80) NOT NULL);
CREATE TABLE swap_request (swap_request_id VARCHAR(24) PRIMARY KEY, source_assignment_id VARCHAR(140) REFERENCES shift_assignment(shift_assignment_id), requester_employee_id VARCHAR(16) REFERENCES employee(employee_id), target_employee_id VARCHAR(16) REFERENCES employee(employee_id), status VARCHAR(16) NOT NULL);
