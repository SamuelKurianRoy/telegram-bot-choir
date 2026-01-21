#pragma once

#include "handlers/BaseHandler.hpp"

namespace ChoirBot {

/**
 * Start command handler
 */
class StartHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "start"; }
};

/**
 * Help command handler
 */
class HelpHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "help"; }
};

/**
 * Check song handler
 */
class CheckHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "check"; }
    
private:
    void handleEnterSong(TgBot::Message::Ptr message);
};

/**
 * Last sung handler
 */
class LastHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    void handleCallback(TgBot::CallbackQuery::Ptr query) override;
    std::string getCommand() const override { return "last"; }
    
private:
    void handleEnterLastSong(TgBot::Message::Ptr message);
    void handleShowAllDates(TgBot::CallbackQuery::Ptr query);
};

/**
 * Date command handler
 */
class DateHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "date"; }
    
private:
    void handleDateInput(TgBot::Message::Ptr message);
};

/**
 * Search handler
 */
class SearchHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    void handleCallback(TgBot::CallbackQuery::Ptr query) override;
    std::string getCommand() const override { return "search"; }
    
private:
    void handleMethodChoice(TgBot::Message::Ptr message);
    void handleIndexCategory(TgBot::Message::Ptr message);
    void handleIndexText(TgBot::Message::Ptr message);
    void handleNumberCategory(TgBot::Message::Ptr message);
    void handleNumberInput(TgBot::Message::Ptr message);
    void handleNotationCallback(TgBot::CallbackQuery::Ptr query);
};

/**
 * Tune handler
 */
class TuneHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "tune"; }
    
private:
    void handleChooseMethod(TgBot::Message::Ptr message);
    void handleGetInput(TgBot::Message::Ptr message);
};

/**
 * Notation handler
 */
class NotationHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    void handleCallback(TgBot::CallbackQuery::Ptr query) override;
    std::string getCommand() const override { return "notation"; }
    
private:
    void handleNotationInput(TgBot::Message::Ptr message);
};

/**
 * Theme handler
 */
class ThemeHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "theme"; }
    
private:
    void handleThemeType(TgBot::Message::Ptr message);
    void handleThemeSelection(TgBot::Message::Ptr message);
    void handleYearFilter(TgBot::Message::Ptr message);
};

/**
 * Bible handler
 */
class BibleHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "bible"; }
    
private:
    void handleBibleInput(TgBot::Message::Ptr message);
    void handleBibleConfirm(TgBot::Message::Ptr message);
};

/**
 * Bible games handler
 */
class GamesHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "games"; }
    
private:
    void handleLanguage(TgBot::Message::Ptr message);
    void handleDifficulty(TgBot::Message::Ptr message);
    void handleQuestion(TgBot::Message::Ptr message);
};

/**
 * Download handler
 */
class DownloadHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "download"; }
    
private:
    void handleUrlInput(TgBot::Message::Ptr message);
    void handlePlaylistChoice(TgBot::Message::Ptr message);
    void handleQualitySelection(TgBot::Message::Ptr message);
};

/**
 * Organist handler
 */
class OrganistHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "organist"; }
    
private:
    void handleOrganistSelection(TgBot::Message::Ptr message);
};

/**
 * Settings handler
 */
class SettingsHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "setting"; }
    
private:
    void handleSettingMenu(TgBot::Message::Ptr message);
    void handleBibleLanguage(TgBot::Message::Ptr message);
    void handleGameLanguage(TgBot::Message::Ptr message);
    void handleSearchLimit(TgBot::Message::Ptr message);
    void handleDownloadPreference(TgBot::Message::Ptr message);
    void handleDownloadQuality(TgBot::Message::Ptr message);
    void handleTuneDisplay(TgBot::Message::Ptr message);
};

/**
 * Upload handler
 */
class UploadHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "upload"; }
    
private:
    void handleFileReceived(TgBot::Message::Ptr message);
    void handleFilenameReceived(TgBot::Message::Ptr message);
    void handleDescriptionReceived(TgBot::Message::Ptr message);
};

/**
 * Comment handler
 */
class CommentHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "comment"; }
    
private:
    void handleCommentText(TgBot::Message::Ptr message);
};

/**
 * Refresh handler (admin)
 */
class RefreshHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "refresh"; }
};

/**
 * Admin user management handler
 */
class AdminUsersHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "users"; }
};

/**
 * Feature control handler (admin)
 */
class FeatureControlHandler : public BaseHandler {
public:
    void handleCommand(TgBot::Message::Ptr message) override;
    std::string getCommand() const override { return "feature_status"; }
};

/**
 * AI message handler
 * Handles natural language queries (must be registered last)
 */
class AIMessageHandler {
public:
    static void handleMessage(TgBot::Message::Ptr message);
};

/**
 * Direct song code handler
 * Matches patterns like H-27, L-5, C-12
 */
class SongCodeHandler {
public:
    static bool matches(const std::string& text);
    static void handleMessage(TgBot::Message::Ptr message);
};

} // namespace ChoirBot
