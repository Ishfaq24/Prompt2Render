# Prompt2Render - Self-contained reproducible video synthesis container
FROM python:3.12-slim-bookworm

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    P2R_IN_DOCKER=1

# Install system dependencies:
# - ffmpeg for video encoding, concatenation, audio mastering, and Whisper filter
# - texlive & dvisvgm for Manim LaTeX/MathTex formula rendering
# - cairo & pango libraries for Manim graphics rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    dvisvgm \
    dvipng \
    libcairo2-dev \
    libpango1.0-dev \
    fonts-noto-core \
    fonts-noto-ui-core \
    fonts-noto-extra \
    fonts-dejavu-core \
    pkg-config \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir opencv-python-headless

# Copy codebase
COPY . .

# Create persistent mount points
RUN mkdir -p /app/projects /app/models /app/tools/kokoro

# Expose Web Studio port
EXPOSE 8000

# Default command: run Prompt2Render Studio Web Dashboard
CMD ["python", "prompt2render.py", "serve", "--host", "0.0.0.0", "--port", "8000"]
