import os,tempfile
_fd,_db=tempfile.mkstemp(suffix='.db')
os.environ['DATABASE_URL']='sqlite:///'+_db
os.environ['REDIS_URL']='redis://localhost:6379/0'
os.environ['JWT_SECRET']='test-secret'
os.environ['SEED_DEMO']='false'
