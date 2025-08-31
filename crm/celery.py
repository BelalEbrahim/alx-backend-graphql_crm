# crm/celery.py
# Minimal Celery app for the "crm" Django project.

import os
from celery import Celery

# Point Celery to Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crm.settings")

app = Celery("crm")
# Read settings with keys that start with "CELERY_"
app.config_from_object("django.conf:settings", namespace="CELERY")
# Find tasks.py in installed apps (incl. our crm/tasks.py)
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
