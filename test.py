import sys, os, traceback
os.environ['POSTGRES_URL'] = 'postgresql://fake'
os.environ['REDIS_URL'] = 'redis://fake'
os.environ['JWT_SECRET_KEY'] = 'fake'
os.environ['PLUGIN_SECRETS_KEY'] = 'fake'

sys.path.insert(0, os.getcwd())

try:
    from backend.main import app
    print("SUCCESS: App loaded successfully!")
except Exception as e:
    traceback.print_exc()
