# Use a minimal Python image
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Install uv (astral-sh/uv)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy the dependency files first to leverage Docker's layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
# --frozen ensures we use the exact versions in uv.lock
# --no-dev ensures we skip installing testing/linting libraries
RUN uv sync --frozen --no-dev

# Copy the actual application source code
COPY src/ ./src/

# Place the uv-created virtual environment at the front of the PATH
# This ensures that "python" executes using the environment with our dependencies
ENV PATH="/app/.venv/bin:$PATH"

# Set the default command to run the agent
CMD ["python", "-m", "src.main"]
