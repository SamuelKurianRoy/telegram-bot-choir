#pragma once

#include <tgbot/tgbot.h>
#include <string>
#include <memory>
#include <map>
#include <functional>

namespace ChoirBot {

/**
 * Conversation state
 */
enum class ConversationState {
    None,
    EnterSong,
    EnterLastSong,
    AskDate,
    BibleInput,
    BibleConfirm,
    SearchMethod,
    SearchIndexCategory,
    SearchIndexText,
    SearchNumberCategory,
    SearchNumberInput,
    ChooseMethod,
    GetInput,
    NotationType,
    ThemeType,
    ThemeSelection,
    YearFilter,
    TypoConfirm,
    CategorySelection,
    EnterUrl,
    PlaylistChoice,
    SelectQuality,
    Comment,
    Reply,
    BibleGameLanguage,
    BibleGameDifficulty,
    BibleGameQuestion,
    SettingMenu,
    BibleLanguageChoice,
    GameLanguageChoice,
    SearchLimitInput,
    DownloadPreferenceChoice,
    DownloadQualityChoice,
    TuneDisplayChoice,
    UploadPreferenceChoice,
    OrganistSelection,
    AssignSongSelect,
    AssignOrganistSelect,
    UnusedDurationSelect,
    UnusedCategorySelect,
    UploadFile,
    UploadFilename,
    UploadDescription,
    ReplySelectUser,
    ReplyEnterMessage
};

/**
 * Conversation context for tracking multi-step interactions
 */
struct ConversationContext {
    ConversationState state;
    std::map<std::string, std::string> data;
    
    void clear() {
        state = ConversationState::None;
        data.clear();
    }
    
    void setState(ConversationState newState) {
        state = newState;
    }
    
    void setData(const std::string& key, const std::string& value) {
        data[key] = value;
    }
    
    std::string getData(const std::string& key) const {
        auto it = data.find(key);
        return (it != data.end()) ? it->second : "";
    }
    
    bool hasData(const std::string& key) const {
        return data.find(key) != data.end();
    }
};

/**
 * Base handler class for command handling
 */
class BaseHandler {
public:
    virtual ~BaseHandler() = default;
    
    // Handle command
    virtual void handleCommand(TgBot::Message::Ptr message) = 0;
    
    // Handle callback query (button clicks)
    virtual void handleCallback(TgBot::CallbackQuery::Ptr query) {  (void)query; }
    
    // Get command name
    virtual std::string getCommand() const = 0;
    
protected:
    // Helper methods
    void sendMessage(int64_t chatId, const std::string& text, 
                    const std::string& parseMode = "");
    void sendMessageWithKeyboard(int64_t chatId, const std::string& text,
                                TgBot::GenericReply::Ptr keyboard);
    void sendPhoto(int64_t chatId, const std::string& photoPath);
    void sendAudio(int64_t chatId, const std::string& audioPath);
    void sendDocument(int64_t chatId, const std::string& docPath);
    
    // Authorization checks
    bool isAuthorized(int64_t userId) const;
    bool isAdmin(int64_t userId) const;
    bool isFeatureEnabled(const std::string& feature) const;
    bool isFeatureEnabledForUser(const std::string& feature, int64_t userId) const;
    
    // User tracking
    void trackUser(int64_t userId, const std::string& username, 
                  const std::string& name);
    void logInteraction(int64_t userId, const std::string& command);
    
    // Conversation management
    ConversationContext& getContext(int64_t userId);
    void clearContext(int64_t userId);
    
private:
    static std::map<int64_t, ConversationContext> conversations;
};

/**
 * Handler manager
 * Manages all bot handlers
 */
class HandlerManager {
public:
    using HandlerPtr = std::shared_ptr<BaseHandler>;
    using MessageCallback = std::function<void(TgBot::Message::Ptr)>;
    using CallbackQueryCallback = std::function<void(TgBot::CallbackQuery::Ptr)>;
    
    HandlerManager();
    
    // Register handlers
    void registerHandler(HandlerPtr handler);
    void registerMessageHandler(const std::string& pattern, MessageCallback callback);
    void registerCallbackHandler(const std::string& pattern, CallbackQueryCallback callback);
    
    // Find handler
    HandlerPtr findHandler(const std::string& command) const;
    
    // Get all handlers
    std::vector<HandlerPtr> getAllHandlers() const;
    
private:
    std::map<std::string, HandlerPtr> handlers;
    std::vector<std::pair<std::string, MessageCallback>> messageHandlers;
    std::vector<std::pair<std::string, CallbackQueryCallback>> callbackHandlers;
};

} // namespace ChoirBot
