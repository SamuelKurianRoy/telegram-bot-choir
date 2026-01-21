#pragma once

#include <tgbot/tgbot.h>
#include <memory>
#include <atomic>
#include <thread>

namespace ChoirBot {

// Forward declarations
class SongParser;

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
    
    // Conversation state management
    enum class ConversationState {
        None,
        WaitingForCheckSong,
        WaitingForLastSong,
        WaitingForDate
    };
    std::map<int64_t, ConversationState> userStates;
    
    void setUserState(int64_t userId, ConversationState state);
    ConversationState getUserState(int64_t userId) const;
    void clearUserState(int64_t userId);
    
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
    
    // Song code handling
    void handleSongCodeMessage(TgBot::Message::Ptr message, 
                               const struct SongParser::ParsedCode& parsed);
    
    // Conversation handling
    void handleConversationMessage(TgBot::Message::Ptr message, ConversationState state);
    void handleCheckSongInput(TgBot::Message::Ptr message);
    void handleLastSongInput(TgBot::Message::Ptr message);
    void handleDateInput(TgBot::Message::Ptr message);
    
    // Helper methods
    bool isAuthorized(int64_t userId) const;
    bool isAdmin(int64_t userId) const;
    void logUserInteraction(const TgBot::Message::Ptr& message);
};

// Global functions
void runBot();
void stopBot();

} // namespace ChoirBot
