FROM python:3.12-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/broker

RUN pip install --no-cache-dir \
      docker==7.2.0 \
      fastapi==0.135.3 \
      httpx==0.28.1 \
      pydantic==2.12.5 \
      'uvicorn[standard]==0.43.0'

WORKDIR /opt/broker

COPY apps/api/src/open_work_hub_api/__init__.py open_work_hub_api/__init__.py
COPY apps/api/src/open_work_hub_api/domains/__init__.py open_work_hub_api/domains/__init__.py
COPY apps/api/src/open_work_hub_api/domains/hermes_terminal/__init__.py open_work_hub_api/domains/hermes_terminal/__init__.py
COPY apps/api/src/open_work_hub_api/domains/hermes_terminal/broker_app.py open_work_hub_api/domains/hermes_terminal/broker_app.py
COPY apps/api/src/open_work_hub_api/domains/hermes_terminal/broker_runtime.py open_work_hub_api/domains/hermes_terminal/broker_runtime.py

EXPOSE 18765

CMD ["uvicorn", "open_work_hub_api.domains.hermes_terminal.broker_app:app", "--host", "0.0.0.0", "--port", "18765", "--no-access-log"]
