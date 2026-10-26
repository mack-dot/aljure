"""Fixed in-container bootstrap. This program never runs generated code on host."""
import json
import os
from pathlib import Path
import sys
import subprocess
import time

request = json.loads(sys.stdin.buffer.readline(65537))
if set(request) != {"mode", "prompt", "context", "script"} or request["mode"] != "fixture":
    raise ValueError("Only explicit scripted fixtures are implemented; live gateway is missing")
if not isinstance(request["script"], dict) or not isinstance(request["script"].get("responses"), list):
    raise ValueError("Scripted provider responses are required")
Path('/work/context.json').write_text(json.dumps(request['context']))
Path('/work/agent').mkdir(exist_ok=True)
Path('/work/sessions').mkdir(exist_ok=True)
os.environ['PRIME_AGENT_FAUX_SCRIPT'] = json.dumps(request['script'])
status = subprocess.run(['/usr/local/bin/prime-agent', '--mode', 'json', '--print',
                         '--session-dir', '/work/sessions', request['prompt']], stdin=subprocess.DEVNULL).returncode
print(json.dumps({'type': 'aljure_fixture_complete', 'native_exit_code': status}), flush=True)
# A stopped container loses tmpfs. Hold it for the external collector, which
# removes the complete container in its finally block. This wait is bounded too.
time.sleep(30)
