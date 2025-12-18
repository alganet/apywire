# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC


.PHONY: all sync sync-frozen format lint test coverage clean build dist repair-wheels publish reuse docs-serve docs-build docs-deploy-dev-main docs-deploy-versioned

all: format lint coverage build

sync:
	uv sync --extra dev

sync-frozen:
	uv sync --frozen --extra dev

reuse:
	uv run reuse annotate \
		--copyright "Alexandre Gomes Gaigalas <alganet@gmail.com>" \
		--license ISC \
		--recursive .

format: reuse
	uv run black apywire tests
	uv run isort apywire tests

lint:
	uv run reuse lint
	uv run flake8 apywire tests
	uv run mypy apywire tests

test:
	uv run pytest -q

coverage:
	rm -f apywire/*.so apywire/wiring.c
	uv run pytest --cov

clean:
	find . -name __pycache__ -type d -exec rm -rf {} +
	rm -f *.pyc *.pyo *.pyd .coverage
	rm -f apywire/*.so apywire/wiring.c
	rm -rf .mypy_cache .pytest_cache *.egg-info dist build

build:
	uv run python setup.py build_ext --inplace

dist:
	uv run python -m build

repair-wheels:
	uv run auditwheel repair dist/*.whl -w dist/repaired
	rm -f dist/*.whl
	mv dist/repaired/*.whl dist/
	rm -rf dist/repaired

publish: dist repair-wheels
	uv run twine upload dist/*

docs-serve:
	uv run mkdocs serve

docs-build:
	uv run mkdocs build

docs-deploy-dev-main:
	uv run mike deploy --push --branch website dev-main

docs-deploy-versioned:
	@if [ -z "$(VERSION)" ]; then \
		echo "VERSION is required (e.g. make $@ VERSION=0.2.0)"; \
		exit 2; \
	fi
	uv run mike deploy --push --update-aliases --branch website $(VERSION) latest
	uv run mike set-default --push --branch website latest
