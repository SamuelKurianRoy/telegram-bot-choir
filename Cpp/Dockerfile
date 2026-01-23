# Docker support for C++ Choir Bot

FROM ubuntu:22.04

# Install dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    libssl-dev \
    libcurl4-openssl-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy source code
COPY include/ include/
COPY src/ src/
COPY CMakeLists.txt .

# Build
RUN mkdir build && cd build && \
    cmake .. && \
    make -j$(nproc)

# Copy config (will be mounted as volume)
VOLUME ["/app/config"]

# Run bot
CMD ["./build/choir_bot", "/app/config/config.json"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep choir_bot || exit 1

# Labels
LABEL maintainer="Choir Bot Team"
LABEL description="Telegram Bot for Choir Song Management (C++ version)"
LABEL version="2.0"
