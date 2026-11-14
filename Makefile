.PHONY: run rund services logs stop gen load setup teardown test
.DEFAULT_GOAL = run
COMPOSE = docker compose --env-file .env.local
PYTHON ?= python3

run:
	$(COMPOSE) up -d --build --wait --wait-timeout 120

rund:
	$(COMPOSE) up --build

services:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs --tail=100

stop:
	$(COMPOSE) down

gen:
	$(PYTHON) -m scripts.generate

load:
	$(PYTHON) -m scripts.database load

setup:
	$(PYTHON) -m scripts.database schema
	$(MAKE) gen
	$(MAKE) load

teardown:
	$(PYTHON) -m scripts.database teardown

test:
	$(PYTHON) -m unittest discover -s tests -v
