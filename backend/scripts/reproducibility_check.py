import argparse, subprocess, sys, tempfile, hashlib
from pathlib import Path

def hashes(folder): return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.csv')}
def main():
 p=argparse.ArgumentParser(); p.add_argument('--scale',default='starter'); p.add_argument('--seed',type=int,default=20261022); a=p.parse_args()
 with tempfile.TemporaryDirectory() as x, tempfile.TemporaryDirectory() as y:
  for target in [x,y]: subprocess.run([sys.executable,'-m','scripts.generate_data','--scale',a.scale,'--seed',str(a.seed),'--out',target],check=True)
  h1,h2=hashes(Path(x)),hashes(Path(y)); ok=h1==h2
  print({'reproducible':ok,'files_compared':len(h1),'mismatches':[k for k in h1 if h1.get(k)!=h2.get(k)]})
  raise SystemExit(0 if ok else 1)
if __name__=='__main__': main()
