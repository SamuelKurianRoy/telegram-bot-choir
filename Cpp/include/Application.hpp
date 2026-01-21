#pragma once

#include <tgbot/tgbot.h>
#include <memory>
#include <atomic>
#include <thread>

namespace ChoirBot {

/**
 * Main bot application class
 * Manages the Telegram bot lifecycle and handlers
 */
class Application {
public:
    explicit Application(const std::string& token);
    ~Application();
    
    // Prevent copying
    Application(const Application&) = delete;
    Application& operator=(const Application&) = delete;
    
    // Initialize the application
    bool initialize();
    
    // Start the bot (blocking)
    void run();
    
    // Stop the bot
    void stop();
    
    // Get bot instance
    TgBot::Bot& getBot() { return *bot; }
    
private:
    std::unique_ptr<TgBot::Bot> bot;
    std::atomic<bool> running;
    
    // Handler registration
    void registerHandlers();
    void registerBasicCommands();
    void registerSongCommands();
    void registerSearchCommands();
    void registerBibleCommands();
    void registerDownloadCommands();
    void registerOrganistCommands();
    void registerAdminCommands();
    void registerSettingsCommands();
    void registerAIHandler();
    
    // Helper methods
    bool isAuthorized(int64_t userId) const;
    bool isAdmin(int64_t userId) const;
    void logUserInteraction(const TgBot::Message::Ptr& message);
};

// Global functions
void runBot();
void stopBot();

} // namespace ChoirBot
