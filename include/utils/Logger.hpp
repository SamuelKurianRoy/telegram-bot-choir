#pragma once

#include <spdlog/spdlog.h>
#include <spdlog/sinks/basic_file_sink.h>
#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/sinks/rotating_file_sink.h>
#include <memory>
#include <string>

namespace ChoirBot {

/**
 * Logger utility class
 * Provides structured logging to files and console
 */
class Logger {
public:
    // Initialize logging system
    static void initialize();
    
    // Get loggers
    static std::shared_ptr<spdlog::logger> getBotLogger();
    static std::shared_ptr<spdlog::logger> getUserLogger();
    static std::shared_ptr<spdlog::logger> getDownloaderLogger();
    
    // Shutdown logging system
    static void shutdown();
    
    // Upload logs to Google Drive
    static void uploadLogs();
    
private:
    static std::shared_ptr<spdlog::logger> botLogger;
    static std::shared_ptr<spdlog::logger> userLogger;
    static std::shared_ptr<spdlog::logger> downloaderLogger;
    
    static void createLogger(
        const std::string& name,
        const std::string& filename,
        std::shared_ptr<spdlog::logger>& logger
    );
};

// Convenience macros
#define LOG_BOT_INFO(...)    ChoirBot::Logger::getBotLogger()->info(__VA_ARGS__)
#define LOG_BOT_WARN(...)    ChoirBot::Logger::getBotLogger()->warn(__VA_ARGS__)
#define LOG_BOT_ERROR(...)   ChoirBot::Logger::getBotLogger()->error(__VA_ARGS__)
#define LOG_BOT_DEBUG(...)   ChoirBot::Logger::getBotLogger()->debug(__VA_ARGS__)

#define LOG_USER_INFO(...)   ChoirBot::Logger::getUserLogger()->info(__VA_ARGS__)
#define LOG_USER_WARN(...)   ChoirBot::Logger::getUserLogger()->warn(__VA_ARGS__)
#define LOG_USER_ERROR(...)  ChoirBot::Logger::getUserLogger()->error(__VA_ARGS__)

#define LOG_DL_INFO(...)     ChoirBot::Logger::getDownloaderLogger()->info(__VA_ARGS__)
#define LOG_DL_ERROR(...)    ChoirBot::Logger::getDownloaderLogger()->error(__VA_ARGS__)

} // namespace ChoirBot
