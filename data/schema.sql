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
