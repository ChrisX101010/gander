#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
G=ROOT/'build/gander'; EX=ROOT/'examples/ci-pipeline.ndjson'; GOLD=ROOT/'examples/ci-pipeline.expected.ndjson'
fail=[]
def mark(n,ok):
    print(f"{n}={'GREEN' if ok else 'RED'}")
    if not ok: fail.append(n)
def run(args,data=b''):
    return subprocess.run([str(G),*args],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
p=run(['--version']); mark('CLI_VERSION',p.returncode==0 and p.stdout==b'gander 1.0.0\n' and p.stderr==b'')
p=run(['--help']); mark('CLI_HELP',p.returncode==0 and b'Usage: gander' in p.stdout and p.stderr==b'')
p=run(['--bad-option']); mark('CLI_UNKNOWN_OPTION',p.returncode==2 and p.stdout==b'' and b'unknown option' in p.stderr)
data=EX.read_bytes(); p=run([],data)
try: decoded=[json.loads(x) for x in p.stdout.splitlines() if x]; json_ok=True
except Exception: decoded=[]; json_ok=False
mark('STDOUT_PURE_NDJSON',p.returncode==0 and json_ok)
mark('STDERR_DIAGNOSTICS',b'window=' in p.stderr and b'total_windows=' in p.stderr)
mark('EXAMPLE_GOLDEN_OUTPUT',p.stdout==GOLD.read_bytes())
q=run(['--quiet'],data); mark('CLI_QUIET',q.returncode==0 and q.stdout==p.stdout and q.stderr==b'')
s=run(['--strict','--quiet'],data); mark('CLI_STRICT_VALID',s.returncode==0 and s.stdout==p.stdout)
bad=run(['--strict','--quiet'],b'not-json\n'+data); mark('CLI_STRICT_REJECTED',bad.returncode==3 and bad.stdout==p.stdout)
state={(e['trace_id'],e['key']):e['value'] for e in decoded}
mark('CI_USE_CASE_STATE',state=={('build-8421','artifact'):'published',('build-8421','deploy'):'production',('build-8421','pipeline'):'succeeded',('build-8421','tests'):'passed'})
print('\n===== PRODUCTION CLI SUMMARY =====')
print('failure_count='+str(len(fail)))
print('GANDER_PRODUCTION_GATE='+('GREEN' if not fail else 'RED'))
if fail: sys.exit(1)
