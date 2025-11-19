# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

.PHONY: all format lint test coverage clean publish pip reuse

all: format lint coverage build

pip:
	python -m pip install --upgrade pip
	python -m pip install -e ".[dev]"

reuse:
	reuse annotate \
		--copyright "Alexandre Gomes Gaigalas <alganet@gmail.com>" \
		--license ISC \
		--recursive .

# if it gets too slow, separate reuse from format
format: reuse
	python -m black .
	python -m isort .

lint:
	python -m reuse lint
	python -m flake8 .
	python -m mypy .

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

publish:
	python -m twine upload dist/*