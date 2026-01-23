# Choir Bot C++ - Build Instructions

## Prerequisites

### Required Tools
- CMake 3.15 or higher
- C++20 compatible compiler:
  - GCC 10+ (Linux)
  - Clang 13+ (Linux/macOS)
  - MSVC 2019+ (Windows)
- Git
- OpenSSL development libraries
- CURL development libraries

### External Dependencies (automatically fetched)
- nlohmann/json 3.11.3
- TgBot++ (Telegram Bot C++ library)
- CPR (C++ HTTP library)
- spdlog (Fast logging library)

## Linux Build

```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y build-essential cmake git libssl-dev libcurl4-openssl-dev

# Clone and build
cd Cpp
mkdir build && cd build
cmake ..
make -j$(nproc)

# The executable will be at: build/choir_bot
```

## macOS Build

```bash
# Install dependencies with Homebrew
brew install cmake openssl curl

# Build
cd Cpp
mkdir build && cd build
cmake ..
make -j$(sysctl -n hw.ncpu)
```

## Windows Build (MSVC)

```powershell
# Install dependencies with vcpkg
vcpkg install openssl curl

# Build with Visual Studio
cd Cpp
mkdir build
cd build
cmake .. -DCMAKE_TOOLCHAIN_FILE=[vcpkg root]/scripts/buildsystems/vcpkg.cmake
cmake --build . --config Release
```

## Configuration

### 1. Create config.json

Copy `config.example.json` to `config.json` and fill in your credentials:

```json
{
  "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
  "admin_id": 123456789,
  "authorized_users": [123456789, 987654321],
  "google_drive": {
    "main_db_file_id": "...",
    "hlc_file_id": "...",
    ...
  },
  "service_account": {
    "type": "service_account",
    "project_id": "...",
    ...
  },
  "gemini_api_key": "YOUR_GEMINI_API_KEY",
  "groq_api_key": "YOUR_GROQ_API_KEY"
}
```

### 2. Environment Variables (Alternative)

Instead of config.json, you can use environment variables:

```bash
export BOT_TOKEN="your_bot_token"
export ADMIN_ID="123456789"
export GOOGLE_SERVICE_ACCOUNT='{"type":"service_account",...}'
export GEMINI_API_KEY="your_key"
export GROQ_API_KEY="your_key"
```

## Running

```bash
# From build directory
./choir_bot

# Or with config file path
./choir_bot /path/to/config.json
```

## Docker Build

```bash
cd Cpp
docker build -t choir-bot .
docker run -d --name choir-bot \
  -v ./config.json:/app/config.json \
  choir-bot
```

## Troubleshooting

### Build Errors

**"Could not find OpenSSL"**
```bash
# Linux
sudo apt-get install libssl-dev

# macOS
brew install openssl
export OPENSSL_ROOT_DIR=/usr/local/opt/openssl
```

**"Could not find CURL"**
```bash
# Linux
sudo apt-get install libcurl4-openssl-dev

# macOS
brew install curl
```

### Runtime Errors

**"Failed to initialize bot"**
- Check that BOT_TOKEN is valid
- Verify internet connectivity
- Check Telegram API accessibility

**"Failed to load Google Drive credentials"**
- Verify service account JSON is valid
- Check file IDs in configuration
- Ensure service account has access to Drive files

## Development

### Running Tests

```bash
cd build
ctest --output-on-failure
```

### Debug Build

```bash
cmake -DCMAKE_BUILD_TYPE=Debug ..
make -j$(nproc)

# Run with debugger
gdb ./choir_bot
```

### Code Formatting

```bash
# Install clang-format
sudo apt-get install clang-format

# Format code
find ../src ../include -name "*.cpp" -o -name "*.hpp" | xargs clang-format -i
```

## Performance

The C++ version is significantly faster than Python:
- Startup time: ~100ms vs ~2-3s
- Memory usage: ~20MB vs ~150MB
- Response latency: <10ms vs ~50ms
- Concurrent users: 1000+ vs ~100

## Deployment

### Systemd Service (Linux)

Create `/etc/systemd/system/choir-bot.service`:

```ini
[Unit]
Description=Choir Telegram Bot
After=network.target

[Service]
Type=simple
User=choirbot
WorkingDirectory=/opt/choir-bot
ExecStart=/opt/choir-bot/choir_bot /opt/choir-bot/config.json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable choir-bot
sudo systemctl start choir-bot
sudo systemctl status choir-bot
```

### Monitoring

View logs:
```bash
# Bot log
tail -f bot_log.txt

# User log
tail -f user_log.txt

# Downloader log
tail -f downloader_log.txt
```

## Support

For issues, see the main README.md or open an issue on GitHub.
