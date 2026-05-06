import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'devlog.settings')

app = Celery('devlog')
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')