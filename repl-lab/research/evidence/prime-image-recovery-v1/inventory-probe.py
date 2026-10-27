from pathlib import Path
import hashlib,json,sys,importlib.metadata,subprocess
root=Path('/opt/prime')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()
paths=['/usr/local/bin/prime-agent','/opt/prime/Cargo.lock','/opt/prime/prime-agent-runtime/uv.lock','/opt/prime/default-packages.lock','/opt/prime/installed-packages.txt']
result={'artifacts':{p:sha(Path(p)) for p in paths},'python':sys.version,'native_version':subprocess.check_output(['/usr/local/bin/prime-agent','--version'],text=True).strip(),'packages':sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions()),'skills':sorted(p.parent.name for p in (root/'skills').glob('*/pyproject.toml'))}
print(json.dumps(result))
