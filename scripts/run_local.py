"""Run this standalone app without starting or inspecting any existing container."""
import argparse,os,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--legacy',action='store_true',help='Run the retained Streamlit UI on the standalone legacy port')
args=parser.parse_args()
config=root/'.env'
if config.exists():
 for line in config.read_text(encoding='utf-8').splitlines():
  if '=' not in line or line.lstrip().startswith('#'):continue
  key,value=line.split('=',1);key=key.strip();value=value.strip()
  if len(value)>=2 and value[0]==value[-1] and value[0] in ['"',"'"]:value=value[1:-1]
  if key:os.environ.setdefault(key,value)
if not os.getenv('NEO4J_AUTH') and not os.getenv('NEO4J_PASS'):
 raise SystemExit('Set NEO4J_PASS/NEO4J_AUTH, or run python scripts/configure_local.py first. Start this repo\'s graph with docker compose up -d graph.')
os.environ.setdefault('NEO4J_URI','bolt://127.0.0.1:17687')
os.environ['PYTHONPATH']=str(root/'src')+os.pathsep+os.environ.get('PYTHONPATH','')
os.environ['PYTHONDONTWRITEBYTECODE']='1'
command=[sys.executable,'-B','-m']
if args.legacy:
 command+=['streamlit','run',str(root/'app/drift_communities_entry.py'),'--server.address=127.0.0.1','--server.port='+os.getenv('LEGACY_PORT','8521'),'--server.enableCORS=true','--server.enableXsrfProtection=true']
else:
 command+=['uvicorn','drift_communities.api:app','--host','127.0.0.1','--port',os.getenv('APP_PORT','8520')]
raise SystemExit(subprocess.call(command,cwd=root,env=os.environ.copy()))
