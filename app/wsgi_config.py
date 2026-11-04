workers = 1
worker_class = "gthread"
threads = 8
preload_app = True
graceful_timeout = 27
control_socket_disable = True
accesslog = None
# The supervisor and application own the safe JSON output. Gunicorn may log raw HTTP input.
logconfig_dict = {
    "version": 1,
    "handlers": {"discard": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["discard"], "level": "INFO"},
    "loggers": {
        "gunicorn.error": {"handlers": ["discard"], "propagate": False},
        "gunicorn.access": {"handlers": ["discard"], "propagate": False},
    },
}
