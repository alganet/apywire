# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
# SPDX-License-Identifier: ISC

.PHONY: all format lint test coverage clean build publish pip

all: format lint coverage

pip:
	python -m pip install --upgrade pip
	python -m pip install -e ".[dev]"

format:
	python -m black .
	python -m isort .

lint:
	python -m reuse lint
	python -m flake8 .
	python -m mypy .

test:
	python -m pytest -q

coverage:
	python -m pytest --cov=apywire --cov-report=term-missing --cov-fail-under=95

clean:
	find . -name __pycache__ -type d -exec rm -rf {} +
	rm -f *.pyc *.pyo *.pyd .coverage
	rm -rf .mypy_cache .pytest_cache *.egg-info dist

build:
	python -m build

publish:
	python -m twine upload dist/*