from dotenv import load_dotenv


from celery_worker.celery_app import app  # noqa: E402, F401 — triggers autodiscover
import celery_worker.tasks.agent_task  # noqa: F401
import celery_worker.tasks.workflow_task  # noqa: F401

load_dotenv()

if __name__ == '__main__':
    app.start()
