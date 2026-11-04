import importlib,traceback,sys
try:
    importlib.import_module('app.main')
    print('imported')
except Exception:
    traceback.print_exc()
    sys.exit(1)
