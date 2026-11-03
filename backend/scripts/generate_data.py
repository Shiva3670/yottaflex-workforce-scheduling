import argparse, json, hashlib
from pathlib import Path
from datetime import date, datetime, timedelta
import numpy as np
import pandas as pd
from faker import Faker

SEED_DEFAULT = 20261022
SCALES = {"starter": (80, 8, 14, 120), "full": (2000, 100, 90, 5000)}

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scale", choices=SCALES, default="starter")
    p.add_argument("--seed", type=int, default=SEED_DEFAULT)
    p.add_argument("--out", type=Path, default=Path("../../data"))
    p.add_argument("--start", default="2026-01-01")
    args = p.parse_args()
    n_emp, n_team, days, n_leave = SCALES[args.scale]
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed); fake = Faker("en_IN"); Faker.seed(args.seed)
    start = date.fromisoformat(args.start)
    teams = pd.DataFrame([{"team_id":f"TEAM-{i+1:04d}","team_name":f"Operations Team {i+1:03d}","location":fake.city(),"active":True} for i in range(n_team)])
    skill_names = ["GENERAL", "FORKLIFT", "FIRST_AID", "QUALITY", "PACKING", "DISPATCH", "INVENTORY", "SUPERVISION"]
    skills = pd.DataFrame([{"skill_id":f"SKL-{i+1:03d}","skill_code":s,"skill_name":s.replace("_"," ").title()} for i,s in enumerate(skill_names)])
    templates = pd.DataFrame([
        {"shift_template_id":"TPL-A","shift_code":"A","shift_name":"Morning","start_time":"06:00","end_time":"14:00","duration_hours":8,"is_overnight":False},
        {"shift_template_id":"TPL-B","shift_code":"B","shift_name":"Evening","start_time":"14:00","end_time":"22:00","duration_hours":8,"is_overnight":False},
        {"shift_template_id":"TPL-C","shift_code":"C","shift_name":"Night","start_time":"22:00","end_time":"06:00","duration_hours":8,"is_overnight":True},
    ])
    employees=[]; emp_skills=[]
    for i in range(n_emp):
        eid=f"EMP-{i+1:06d}"; team=teams.iloc[i % n_team].team_id
        employees.append({"employee_id":eid,"first_name":fake.first_name(),"last_name":fake.last_name(),"email":f"{eid.lower()}@example.test","team_id":team,"employment_status":"ACTIVE","hire_date":str(start-timedelta(days=int(rng.integers(30,2500)))),"weekly_hours_cap":40 if rng.random()<.85 else 48,"contract_type":"FULL_TIME" if rng.random()<.85 else "PART_TIME"})
        chosen=rng.choice(len(skill_names),size=int(rng.integers(1,4)),replace=False)
        for sidx in chosen: emp_skills.append({"employee_id":eid,"skill_id":f"SKL-{sidx+1:03d}","proficiency":"BASIC" if rng.random()<.7 else "ADVANCED","effective_from":str(start-timedelta(days=30)),"effective_to":""})
    employee=pd.DataFrame(employees); employee_skill=pd.DataFrame(emp_skills)
    holidays=[]
    for d in range(days):
        day=start+timedelta(days=d)
        if day.month==1 and day.day==26 or day.month==8 and day.day==15:
            holidays.append({"holiday_id":f"HOL-{day.isoformat()}","holiday_date":str(day),"holiday_name":"Republic Day" if day.month==1 else "Independence Day","location":"ALL"})
    holiday=pd.DataFrame(holidays,columns=["holiday_id","holiday_date","holiday_name","location"])
    # Shift instances and skill-specific coverage requirements.
    shift_rows=[]; req_rows=[]; assignments=[]; att=[]
    emp_skill_map=employee_skill.groupby("employee_id").skill_id.apply(set).to_dict()
    for d in range(days):
        day=start+timedelta(days=d)
        for team_idx, team in enumerate(teams.team_id):
            for tpl in templates.itertuples():
                sid=f"SHIFT-{day.isoformat()}-{tpl.shift_code}-T{team_idx+1:03d}"
                st=datetime.combine(day,datetime.strptime(tpl.start_time,"%H:%M").time())
                en=st+timedelta(hours=8)
                shift_rows.append({"shift_id":sid,"team_id":team,"shift_template_id":tpl.shift_template_id,"start_at":st.isoformat(),"end_at":en.isoformat(),"status":"PLANNED"})
                req_rows.append({"requirement_id":f"REQ-{sid}-GEN","shift_id":sid,"skill_id":"SKL-001","minimum_staff":2 if n_emp<500 else 4})
                if team_idx % 5 == 0:
                    req_rows.append({"requirement_id":f"REQ-{sid}-FLT","shift_id":sid,"skill_id":"SKL-002","minimum_staff":1})
    shifts=pd.DataFrame(shift_rows); requirements=pd.DataFrame(req_rows)
    # Baseline assignment: deterministic, team-local, rotating employee order.
    team_emp=employee.groupby("team_id").employee_id.apply(list).to_dict()
    leave_rows=[]
    for i in range(n_leave):
        eid=employee.iloc[int(rng.integers(0,n_emp))].employee_id
        d=start+timedelta(days=int(rng.integers(0,days)))
        status=str(rng.choice(["PENDING","APPROVED","REJECTED"],p=[.2,.65,.15]))
        leave_rows.append({"leave_request_id":f"LVE-{start.year}-{i+1:06d}","employee_id":eid,"leave_type":str(rng.choice(["ANNUAL","SICK","PERSONAL"])),"start_date":str(d),"end_date":str(d+timedelta(days=int(rng.integers(0,3)))),"status":status,"submitted_at":datetime.combine(d-timedelta(days=3),datetime.min.time()).isoformat(),"decided_at":datetime.combine(d-timedelta(days=2),datetime.min.time()).isoformat() if status!="PENDING" else ""})
    leaves=pd.DataFrame(leave_rows)
    approved={}
    for r in leaves[leaves.status=="APPROVED"].itertuples():
        for day in pd.date_range(r.start_date,r.end_date): approved.setdefault(r.employee_id,set()).add(day.date())
    counters={t:0 for t in team_emp}
    for sh in shifts.itertuples():
        pool=team_emp[sh.team_id]
        day=pd.Timestamp(sh.start_at).date()
        assigned_this_shift=set()
        for req in requirements[requirements.shift_id==sh.shift_id].itertuples():
            eligible=[e for e in pool if e not in assigned_this_shift and req.skill_id in emp_skill_map.get(e,set()) and day not in approved.get(e,set())]
            # If skill pool is empty, leave the coverage gap explicit.
            need=req.minimum_staff
            selected=[]
            for _ in range(min(need,len(eligible))):
                e=eligible[counters[sh.team_id] % len(eligible)]; counters[sh.team_id]+=1
                if e not in selected: selected.append(e); assigned_this_shift.add(e)
            for e in selected:
                assignments.append({"shift_assignment_id":f"ASG-{sh.shift_id}-{req.skill_id}-{e}","shift_id":sh.shift_id,"employee_id":e,"start_at":sh.start_at,"end_at":sh.end_at,"assigned_skill_id":req.skill_id,"status":"ASSIGNED","weekly_hours_after_assignment":8,"coverage_gap":False})
            if len(selected)<need:
                assignments.append({"shift_assignment_id":f"GAP-{sh.shift_id}-{req.skill_id}","shift_id":sh.shift_id,"employee_id":"","start_at":sh.start_at,"end_at":sh.end_at,"assigned_skill_id":req.skill_id,"status":"UNCOVERED","weekly_hours_after_assignment":0,"coverage_gap":True})
    assignment=pd.DataFrame(assignments)
    # Attendance is generated from schedule source rows; absences are events, not schedule edits.
    for a in assignment[assignment.employee_id!=""].itertuples():
        status=str(rng.choice(["PRESENT","LATE","ABSENT"],p=[.94,.04,.02]))
        ts=pd.Timestamp(a.start_at)
        att.append({"attendance_event_id":f"ATT-{a.employee_id}-{a.shift_id}","employee_id":a.employee_id,"shift_id":a.shift_id,"event_type":status,"event_at":ts.isoformat(),"source":"SYNTHETIC_TERMINAL"})
    attendance=pd.DataFrame(att)
    swaps=pd.DataFrame(columns=["swap_request_id","source_assignment_id","requester_employee_id","target_employee_id","status","manager_id","created_at","decided_at","applied_at"])
    # Deliberate, labelled edge cases. They are recorded in a separate evaluation file.
    ground=[]
    def label(issue, entity, entity_id, expected): ground.append({"issue_type":issue,"entity_type":entity,"entity_id":entity_id,"ground_truth":expected,"severity":"HIGH"})
    if len(assignment):
        real=assignment[assignment.employee_id!=""]
        if len(real):
            row=real.iloc[0]; label("APPROVED_LEAVE_OVERLAP","ShiftAssignment",row.shift_assignment_id,"FLAG_CONFLICT")
            label("DOUBLE_BOOKED","ShiftAssignment",row.shift_assignment_id,"FLAG_CONFLICT")
        if len(real)>1: label("REQUIRED_SKILL_ABSENT","ShiftAssignment",real.iloc[1].shift_assignment_id,"FLAG_SKILL_MISMATCH")
        label("OVERTIME_CAP_EXCEEDED","Employee",employee.iloc[0].employee_id,"FLAG_OVERTIME")
        swaps.loc[0]=["SWP-2026-000001",real.iloc[0].shift_assignment_id,real.iloc[0].employee_id,real.iloc[-1].employee_id,"APPLIED", "", datetime.combine(start,datetime.min.time()).isoformat(),"",datetime.combine(start,datetime.min.time()).isoformat()]
        label("SWAP_WITHOUT_APPROVAL","SwapRequest","SWP-2026-000001","REJECT_APPLICATION")
    tables={"team":teams,"skill":skills,"shift_template":templates,"employee":employee,"employee_skill":employee_skill,"holiday_calendar":holiday,"shift":shifts,"coverage_requirement":requirements,"leave_request":leaves,"shift_assignment":assignment,"attendance_event":attendance,"swap_request":swaps,"ground_truth":pd.DataFrame(ground)}
    manifest={"project":"YottaFlex Workforce Scheduling","seed":args.seed,"scale":args.scale,"start_date":args.start,"days":days,"generated_at_utc":datetime.utcnow().isoformat()+"Z","tables":{}}
    for name,df in tables.items():
        path=out/f"{name}.csv"; df.to_csv(path,index=False); df.to_json(out/f"{name}.json",orient="records",indent=2,date_format="iso")
        manifest["tables"][name]={"rows":len(df),"sha256":digest(path),"file":path.name}
    (out/"source_manifest.json").write_text(json.dumps(manifest,indent=2))
    (out/"schema.sql").write_text("""-- Logical seed schema; CSV exports are the canonical generated records.\nCREATE TABLE team (team_id VARCHAR(16) PRIMARY KEY, team_name VARCHAR(120) NOT NULL, location VARCHAR(120), active BOOLEAN NOT NULL);\nCREATE TABLE skill (skill_id VARCHAR(16) PRIMARY KEY, skill_code VARCHAR(40) UNIQUE NOT NULL, skill_name VARCHAR(80) NOT NULL);\nCREATE TABLE employee (employee_id VARCHAR(16) PRIMARY KEY, team_id VARCHAR(16) NOT NULL REFERENCES team(team_id), email VARCHAR(180) UNIQUE NOT NULL, employment_status VARCHAR(20) NOT NULL);\nCREATE TABLE shift_template (shift_template_id VARCHAR(16) PRIMARY KEY, shift_code VARCHAR(8) UNIQUE NOT NULL);\nCREATE TABLE shift (shift_id VARCHAR(80) PRIMARY KEY, team_id VARCHAR(16) NOT NULL REFERENCES team(team_id), shift_template_id VARCHAR(16) NOT NULL REFERENCES shift_template(shift_template_id), start_at TIMESTAMP NOT NULL, end_at TIMESTAMP NOT NULL);\nCREATE TABLE employee_skill (employee_id VARCHAR(16) REFERENCES employee(employee_id), skill_id VARCHAR(16) REFERENCES skill(skill_id), effective_from DATE NOT NULL, effective_to DATE, PRIMARY KEY(employee_id, skill_id, effective_from));\nCREATE TABLE coverage_requirement (requirement_id VARCHAR(120) PRIMARY KEY, shift_id VARCHAR(80) REFERENCES shift(shift_id), skill_id VARCHAR(16) REFERENCES skill(skill_id), minimum_staff INTEGER NOT NULL CHECK(minimum_staff >= 0));\nCREATE TABLE leave_request (leave_request_id VARCHAR(24) PRIMARY KEY, employee_id VARCHAR(16) REFERENCES employee(employee_id), start_date DATE NOT NULL, end_date DATE NOT NULL, status VARCHAR(16) NOT NULL);\nCREATE TABLE shift_assignment (shift_assignment_id VARCHAR(140) PRIMARY KEY, shift_id VARCHAR(80) REFERENCES shift(shift_id), employee_id VARCHAR(16) REFERENCES employee(employee_id), status VARCHAR(20) NOT NULL);\nCREATE TABLE attendance_event (attendance_event_id VARCHAR(100) PRIMARY KEY, employee_id VARCHAR(16) REFERENCES employee(employee_id), shift_id VARCHAR(80) REFERENCES shift(shift_id), event_type VARCHAR(16) NOT NULL);\nCREATE TABLE holiday_calendar (holiday_id VARCHAR(32) PRIMARY KEY, holiday_date DATE NOT NULL, holiday_name VARCHAR(80) NOT NULL);\nCREATE TABLE swap_request (swap_request_id VARCHAR(24) PRIMARY KEY, source_assignment_id VARCHAR(140) REFERENCES shift_assignment(shift_assignment_id), requester_employee_id VARCHAR(16) REFERENCES employee(employee_id), target_employee_id VARCHAR(16) REFERENCES employee(employee_id), status VARCHAR(16) NOT NULL);\n""")
    print(json.dumps({"output":str(out),"scale":args.scale,"seed":args.seed,"rows":{k:len(v) for k,v in tables.items()}},indent=2))
if __name__=="__main__": main()
