import os
import multiprocessing

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"
backlog = 2048

# Worker processes
workers = int(os.getenv('WORKERS', 1))
worker_class = os.getenv('WORKER_CLASS', 'uvicorn.workers.UvicornWorker')
worker_connections = 1000
timeout = int(os.getenv('WORKER_TIMEOUT', 300))
keepalive = int(os.getenv('KEEP_ALIVE', 2))

# Restart workers
max_requests = int(os.getenv('MAX_REQUESTS', 1000))
max_requests_jitter = int(os.getenv('MAX_REQUESTS_JITTER', 100))
preload_app = os.getenv('PRELOAD_APP', 'true').lower() == 'true'

# Logging
loglevel = os.getenv('LOG_LEVEL', 'info')
accesslog = '-' if os.getenv('ACCESS_LOG', 'true').lower() == 'true' else None
errorlog = '-' if os.getenv('ERROR_LOG', 'true').lower() == 'true' else None
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'flowintent-api'

# Server mechanics
daemon = False
pidfile = None
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
keyfile = None
certfile = None

# Application
pythonpath = os.getenv('PYTHONPATH', '/app/src')
chdir = '/app'

# Worker process behavior
capture_output = os.getenv('CAPTURE_OUTPUT', 'true').lower() == 'true'
enable_stdio_inheritance = os.getenv('ENABLE_STDIO_INHERITANCE', 'true').lower() == 'true'

# Hooks
def on_starting(server):
    server.log.info("Starting FlowIntent API server...")

def on_reload(server):
    server.log.info("Reloading FlowIntent API server...")

def worker_int(worker):
    worker.log.info("Worker received INT or QUIT signal")

def pre_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_worker_init(worker):
    worker.log.info("Worker initialized (pid: %s)", worker.pid)

def worker_abort(worker):
    worker.log.info("Worker received SIGABRT signal")