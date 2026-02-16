SHELL := /bin/bash

.PHONY: up down logs migrate makemigration

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api db redis

migrate:
	docker compose run --rm api alembic upgrade head

makemigration:
	docker compose run --rm api alembic revision --autogenerate -m "$(m)"
