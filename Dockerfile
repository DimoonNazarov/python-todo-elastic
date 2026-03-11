FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt /
RUN pip3 install --no-cache -r /requirements.txt

COPY scripts /code/scripts
COPY docker_scripts /code/docker_scripts
COPY app /code/app
COPY tests /code/tests
COPY alembic.ini /code/alembic.ini
COPY pyproject.toml /code/pyproject.toml
COPY migrations /code/migrations
WORKDIR /code/

RUN chmod a+x /code/docker_scripts/app.sh