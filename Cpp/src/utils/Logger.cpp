#include "utils/Logger.hpp"
#include <filesystem>
#include <iostream>

namespace ChoirBot {

std::shared_ptr<spdlog::logger> Logger::botLogger = nullptr;
std::shared_ptr<spdlog::logger> Logger::userLogger = nullptr;
std::shared_ptr<spdlog::logger> Logger::downloaderLogger = nullptr;

void Logger::initialize() {
    // Set global log level
    spdlog::set_level(spdlog::level::info);
    spdlog::set_pattern("[%Y-%m-%d %H:%M:%S.%e] [%n] [%^%l%$] %v");
    
    // Create log directory if it doesn't exist
    std::filesystem::create_directories("logs");
    
    // Create loggers
    createLogger("bot", "logs/bot_log.txt", botLogger);
    createLogger("user", "logs/user_log.txt", userLogger);
    createLogger("downloader", "logs/downloader_log.txt", downloaderLogger);
    
    LOG_BOT_INFO("Logging system initialized");
}

void Logger::createLogger(
    const std::string& name,
    const std::string& filename,
    std::shared_ptr<spdlog::logger>& logger
) {
    try {
        // Create sinks
        auto console_sink = std::make_shared<spdlog::sinks::stdout_color_sink_mt>();
        console_sink->set_level(spdlog::level::info);
        
        // Rotating file sink: 10MB max size, 3 backup files
        auto file_sink = std::make_shared<spdlog::sinks::rotating_file_sink_mt>(
            filename, 1024 * 1024 * 10, 3
        );
        file_sink->set_level(spdlog::level::trace);
        
        // Combine sinks
        std::vector<spdlog::sink_ptr> sinks{console_sink, file_sink};
        logger = std::make_shared<spdlog::logger>(name, sinks.begin(), sinks.end());
        logger->set_level(spdlog::level::trace);
        
        // Register logger
        spdlog::register_logger(logger);
    } catch (const spdlog::spdlog_ex& ex) {
        std::cerr << "Log initialization failed for " << name << ": " << ex.what() << std::endl;
    }
}

std::shared_ptr<spdlog::logger> Logger::getBotLogger() {
    if (!botLogger) {
        initialize();
    }
    return botLogger;
}

std::shared_ptr<spdlog::logger> Logger::getUserLogger() {
    if (!userLogger) {
        initialize();
    }
    return userLogger;
}

std::shared_ptr<spdlog::logger> Logger::getDownloaderLogger() {
    if (!downloaderLogger) {
        initialize();
    }
    return downloaderLogger;
}

void Logger::shutdown() {
    if (botLogger) {
        botLogger->flush();
    }
    if (userLogger) {
        userLogger->flush();
    }
    if (downloaderLogger) {
        downloaderLogger->flush();
    }
    
    spdlog::shutdown();
}

void Logger::uploadLogs() {
    // TODO: Implement Google Drive log upload
    LOG_BOT_INFO("Log upload requested (not yet implemented)");
}

} // namespace ChoirBot
