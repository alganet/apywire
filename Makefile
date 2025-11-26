# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

.PHONY: all format lint test coverage clean publish pip reuse .venv docs-serve docs-build

all: format lint coverage build

pip:
	python -m pip install --upgrade pip
	python -m pip install -e ".[dev]"

reuse:
	reuse annotate \
		--copyright "Alexandre Gomes Gaigalas <alganet@gmail.com>" \
		--license ISC \
		--recursive .

.venv:
	python -m venv .venv
	. .venv/bin/activate && make pip

format: reuse
	python -m black apywire tests
	python -m isort apywire tests

lint:
	python -m reuse lint
	python -m flake8 apywire tests
	python -m mypy apywire tests

test:
	python -m pytest -q

coverage:
	rm -f apywire/*.so apywire/wiring.c
	python -m pytest --cov

clean:
	find . -name __pycache__ -type d -exec rm -rf {} +
	rm -f *.pyc *.pyo *.pyd .coverage
	rm -f apywire/*.so apywire/wiring.c
	rm -rf .mypy_cache .pytest_cache *.egg-info dist build

build:
	python setup.py build_ext --inplace

dist:
	python -m build

repair-wheels:
	python -m pip install --upgrade auditwheel
	auditwheel repair dist/*.whl -w dist/repaired
	rm -f dist/*.whl
	mv dist/repaired/*.whl dist/
	rm -rf dist/repaired

publish: dist repair-wheels
	python -m pip install --upgrade twine
	python -m twine upload dist/*

docs-serve:
	python -m mkdocs serve

docs-build:
	python -m mkdocs build
