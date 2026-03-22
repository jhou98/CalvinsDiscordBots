.PHONY: lint test check fmt
 
# Run ruff linter only (no fixes)
lint:
	ruff check src/ tests/
 
# Run tests only
test:
	pytest
 
# Lint + test in one shot — use this during development
check: lint test
 
# Auto-fix safe lint issues, then format
fmt:
	ruff check --fix src/ tests/
	ruff format src/ tests/