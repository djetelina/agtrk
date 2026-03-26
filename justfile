# Development justfile for agtrk
# All commands use a separate dev database to avoid touching production data.

dev_db := "/tmp/agtrk-dev.db"
export AGTRK_DB := dev_db

# Run agtrk with dev DB (pass any args)
run *args:
    uv run agtrk {{args}}

# Run tests
test *args:
    uv run pytest tests/ {{args}}

# Run linter
lint:
    uv run ruff check src/ tests/

# Run linter with auto-fix
fix:
    uv run ruff check --fix src/ tests/

# Reset the dev database
reset-db:
    rm -f {{dev_db}}

# Show dev DB path
which-db:
    @echo {{dev_db}}

# Install local checkout as the global agtrk (editable)
promote:
    pipx install -e . --force

# Reinstall the latest released version from PyPI
unpromote:
    pipx install agtrk --force
