#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Warray-bounds"
#include "models/Config.hpp"
#include "utils/Logger.hpp"
#pragma GCC diagnostic pop
#include <iostream>
#include <csignal>
#include <atomic>

namespace ChoirBot {
    extern void runBot();
    extern void stopBot();
}

std::atomic<bool> running{true};

void signalHandler(int signum) {
    std::cout << "\nInterrupt signal (" << signum << ") received.\n";
    running = false;
    ChoirBot::stopBot();
}

int main(int argc, char* argv[]) {
    // Initialize logger
    ChoirBot::Logger::initialize();
    
    LOG_BOT_INFO("=== Choir Telegram Bot Starting ===");
    LOG_BOT_INFO("Version: 1.0.0");
    LOG_BOT_INFO("Build Date: {}", __DATE__);
    
    try {
        // Load configuration
        auto& config = ChoirBot::getConfig();
        
        // Try loading from file first
        std::string configFile = "config/config.json";
        if (argc > 1) {
            configFile = argv[1];
        }
        
        bool configLoaded = false;
        if (config.loadFromFile(configFile)) {
            LOG_BOT_INFO("Configuration loaded from file: {}", configFile);
            configLoaded = true;
        } else {
            LOG_BOT_WARN("Failed to load config file, trying environment variables");
            if (config.loadFromEnvironment()) {
                LOG_BOT_INFO("Configuration loaded from environment");
                configLoaded = true;
            }
        }
        
        if (!configLoaded) {
            LOG_BOT_ERROR("Failed to load configuration");
            std::cerr << "Error: Could not load configuration from file or environment\n";
            std::cerr << "Please provide config.json or set environment variables\n";
            return 1;
        }
        
        // Validate essential configuration
        if (config.token.empty()) {
            LOG_BOT_ERROR("Bot token is empty");
            std::cerr << "Error: Bot token is required\n";
            return 1;
        }
        
        if (config.adminId == 0) {
            LOG_BOT_WARN("Admin ID not set, administrative functions will be disabled");
        }
        
        LOG_BOT_INFO("Admin ID: {}", config.adminId);
        LOG_BOT_INFO("Authorized users: {}", config.authorizedUsers.size());
        LOG_BOT_INFO("Log upload interval: {} seconds", config.logUploadInterval);
        
        // Setup signal handlers
        std::signal(SIGINT, signalHandler);
        std::signal(SIGTERM, signalHandler);
        
        LOG_BOT_INFO("Signal handlers registered");
        
        // Run the bot
        LOG_BOT_INFO("Starting bot main loop...");
        ChoirBot::runBot();
        
        LOG_BOT_INFO("Bot stopped normally");
        
    } catch (const std::exception& e) {
        LOG_BOT_ERROR("Fatal error: {}", e.what());
        std::cerr << "Fatal error: " << e.what() << std::endl;
        ChoirBot::Logger::shutdown();
        return 1;
    }
    
    // Cleanup
    LOG_BOT_INFO("=== Choir Telegram Bot Shutdown ===");
    ChoirBot::Logger::shutdown();
    
    return 0;
}
