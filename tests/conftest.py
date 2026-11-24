import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DAEP_DB_PATH']=os.path.join(tempfile.gettempdir(),'daep-test-suite-v3.db')
os.environ['DAEP_ADMIN_TOKEN']='test-admin-token-with-32-characters-minimum'
os.environ['DAEP_WORKER_TOKEN']='test-worker-token-with-32-characters-minimum'
try: os.remove(os.environ['DAEP_DB_PATH'])
except FileNotFoundError: pass
