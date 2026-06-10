FROM python:3.10-slim

# System deps for graphify optional extras (cairo for SVG, git for hook install)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libcairo2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python tooling
RUN curl -Ls https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install graphifyy into a uv-managed tool environment so the binary is on PATH
# Include anthropic for the optional semantic labeling feature
RUN uv tool install graphifyy --with anthropic

# Make the graphify binary available
ENV PATH="/root/.local/share/uv/tools/graphifyy/bin:$PATH"

WORKDIR /app

# Copy graphify-build service
COPY requirements.txt .
COPY cli.py .
COPY service/ ./service/

# /repos  — mount your source repos here (read-only safe)
# /graphs — mount your graphify-out-repos directory here (read-write)
RUN mkdir -p /repos /graphs

# Verify graphify is importable from the uv tool Python
RUN /root/.local/share/uv/tools/graphifyy/bin/python -c "import graphify; print('graphify OK')"

ENTRYPOINT ["/root/.local/share/uv/tools/graphifyy/bin/python", "/app/cli.py"]
CMD ["--help"]
