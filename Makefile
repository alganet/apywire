# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
# SPDX-License-Identifier: ISC

.PHONY: all format lint test coverage clean

all: format lint coverage

format:
	black .
	isort .

lint:
	reuse lint
	flake8 .
	mypy .

test:
	pytest -q

coverage:
	pytest --cov=apywire --cov-report=term-missing --cov-fail-under=95

clean:
	find . -name __pycache__ -type d -exec rm -rf {} +
	rm -f *.pyc *.pyo *.pyd .coverage
	rm -rf .mypy_cache .pytest_cache *.egg-info dist