# Gunicorn configuration
import multiprocessing

bind = "127.0.0.1:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
timeout = 120
keepalive = 5
errorlog = "/var/log/oj-tracker/gunicorn-error.log"
accesslog = "/var/log/oj-tracker/gunicorn-access.log"
loglevel = "info"
