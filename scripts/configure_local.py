"""Prepare credentials only for this standalone workspace; never read an existing container."""
from pathlib import Path
import secrets
root=Path(__file__).resolve().parents[1]
path=root/'.env'
text=path.read_text(encoding='utf-8') if path.exists() else (root/'.env.example').read_text(encoding='utf-8')
lines=text.splitlines()
values=dict(line.split('=',1) for line in lines if '=' in line and not line.lstrip().startswith('#'))
if not values.get('NEO4J_PASS','').strip():
 password=secrets.token_hex(24)
 matches=[i for i,line in enumerate(lines) if line.startswith('NEO4J_PASS=')]
 if len(matches)>1:raise SystemExit('Duplicate NEO4J_PASS setting; review the local .env.')
 if matches:lines[matches[0]]='NEO4J_PASS='+password
 else:lines.append('NEO4J_PASS='+password)
path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Prepared ignored local .env; existing configured passwords preserved.')
