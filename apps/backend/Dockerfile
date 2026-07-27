# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements requirements/
ARG REQUIREMENTS_FILE=requirements/production.txt
RUN pip install --no-cache-dir -r ${REQUIREMENTS_FILE}

COPY . .

RUN adduser --disabled-password --no-create-home appuser
USER appuser

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
