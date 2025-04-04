.PHONY: build all shell stop services api test typecheck check

all:
	make api

build:
	docker build -t docker.vercly.it/yente:4.2.1 .

shell: build
	docker compose run --rm app bash

stop:
	docker compose down

services:
	docker compose -f docker-compose.yml up --remove-orphans -d index

api: build services
	docker compose up --remove-orphans app

test:
	pytest --cov-report html --cov-report term --cov=yente -v tests

typecheck:
	mypy --strict yente

check: typecheck test