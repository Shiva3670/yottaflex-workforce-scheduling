import argparse, json
from pathlib import Path
import pandas as pd

def main():
    p=argparse.ArgumentParser(); p.add_argument('--input',type=Path,required=True); args=p.parse_args(); d=args.input
    issues=[]; counts={}
    def load(n):
        f=d/f'{n}.csv'
        if not f.exists(): issues.append(f'MISSING:{n}.csv'); return pd.DataFrame()
        return pd.read_csv(f).fillna('')
    for n in ['team','skill','shift_template','employee','employee_skill','holiday_calendar','shift','coverage_requirement','leave_request','shift_assignment','attendance_event','swap_request']:
        df=load(n); counts[n]=len(df)
        pk={'team':'team_id','skill':'skill_id','shift_template':'shift_template_id','employee':'employee_id','holiday_calendar':'holiday_id','shift':'shift_id','coverage_requirement':'requirement_id','leave_request':'leave_request_id','shift_assignment':'shift_assignment_id','attendance_event':'attendance_event_id','swap_request':'swap_request_id'}.get(n)
        if pk and len(df) and df[pk].duplicated().any(): issues.append(f'DUPLICATE_PRIMARY_KEY:{n}')
        if n=='employee_skill' and len(df) and df.duplicated(['employee_id','skill_id','effective_from']).any(): issues.append('DUPLICATE_COMPOSITE_KEY:employee_skill')
    team,skill,emp,es,sh,req,lv,asg,att,sw=[load(n) for n in ['team','skill','employee','employee_skill','shift','coverage_requirement','leave_request','shift_assignment','attendance_event','swap_request']]
    def fk(child,col,parent,pcol):
        if col in child and pcol in parent:
            bad=set(child[col].astype(str))-set(parent[pcol].astype(str))-{'','nan'}
            if bad: issues.append(f'FOREIGN_KEY:{col}:{len(bad)}')
    fk(emp,'team_id',team,'team_id'); fk(es,'employee_id',emp,'employee_id'); fk(es,'skill_id',skill,'skill_id'); fk(sh,'team_id',team,'team_id'); fk(req,'shift_id',sh,'shift_id'); fk(req,'skill_id',skill,'skill_id'); fk(lv,'employee_id',emp,'employee_id'); fk(asg,'shift_id',sh,'shift_id'); fk(asg[asg.employee_id!=''],'employee_id',emp,'employee_id'); fk(att,'employee_id',emp,'employee_id')
    for n,df,a,b in [('leave_request',lv,'start_date','end_date'),('shift',sh,'start_at','end_at')]:
        if len(df) and (pd.to_datetime(df[a])>pd.to_datetime(df[b])).any(): issues.append(f'DATE_ORDER:{n}')
    report={'status':'PASS' if not issues else 'FAIL','row_counts':counts,'issues':issues,'ground_truth_rows':len(load('ground_truth'))}
    (d/'validation_summary.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
    raise SystemExit(0 if not issues else 1)
if __name__=='__main__': main()
