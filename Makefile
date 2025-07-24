.PHONY: install install-dev test clean lint format help

# Default target
help:
	@echo "Available targets:"
	@echo "  install      - Install the package"
	@echo "  install-dev  - Install package and development dependencies"
	@echo "  test         - Run tests"
	@echo "  lint         - Run linting checks"
	@echo "  format       - Format code"
	@echo "  clean        - Clean up build artifacts"
	@echo "  setup        - Run development setup"

# Install package
install:
	pip install -e .

# Install development environment
install-dev:
	python setup_dev.py

# Run tests
test:
	python -m pytest tests/ -v

# Run tests with coverage
test-cov:
	python -m pytest tests/ --cov=spack_installer --cov-report=html --cov-report=term

# Lint code
lint:
	flake8 spack_installer/ tests/
	mypy spack_installer/

# Format code
format:
	black spack_installer/ tests/ examples/

# Clean up
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Development setup
setup: install-dev

# Run example
example:
	python examples/basic_usage.py
