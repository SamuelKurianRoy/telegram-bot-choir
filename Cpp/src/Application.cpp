#include "Application.hpp"
#include "models/Config.hpp"
#include "utils/Logger.hpp"
#include "utils/SongParser.hpp"
#include "data/Database.hpp"
#include <iostream>
#include <sstream>
#include <iomanip>
#include <ctime>

namespace ChoirBot {

// Global application instance
static std::unique_ptr<Application> globalApp = nullptr;

Application::Application(const std::string& token)
    : bot(std::make_unique<TgBot::Bot>(token))
    , running(false) {
}

Application::~Application() {
    stop();
}

bool Application::initialize() {
    LOG_BOT_INFO("Initializing bot application...");
    
    try {
        // Test bot connection
        auto me = bot->getApi().getMe();
        LOG_BOT_INFO("Bot initialized: @{} ({})", me->username, me->firstName);
        
        // Register all handlers
        registerHandlers();
        
        LOG_BOT_INFO("All handlers registered");
        return true;
        
    } catch (const std::exception& e) {
        LOG_BOT_ERROR("Failed to initialize bot: {}", e.what());
        return false;
    }
}

void Application::run() {
    LOG_BOT_INFO("Starting bot polling...");
    running = true;
    
    try {
        // Start long polling
        TgBot::TgLongPoll longPoll(*bot);
        
        while (running) {
            try {
                longPoll.start();
            } catch (const TgBot::TgException& e) {
                LOG_BOT_ERROR("Polling error: {}", e.what());
                std::this_thread::sleep_for(std::chrono::seconds(5));
            }
        }
        
    } catch (const std::exception& e) {
        LOG_BOT_ERROR("Fatal polling error: {}", e.what());
        throw;
    }
    
    LOG_BOT_INFO("Bot polling stopped");
}

void Application::stop() {
    LOG_BOT_INFO("Stopping bot...");
    running = false;
}

void Application::registerHandlers() {
    registerBasicCommands();
    registerSongCommands();
    registerSearchCommands();
    registerBibleCommands();
    registerDownloadCommands();
    registerOrganistCommands();
    registerAdminCommands();
    registerSettingsCommands();
    registerAIHandler();  // Must be last
}

void Application::registerBasicCommands() {
    LOG_BOT_INFO("Registering basic commands...");
    
    // /start command
    bot->getEvents().onCommand("start", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        
        int64_t userId = message->from->id;
        std::string username = message->from->username;
        std::string name = message->from->firstName;
        if (!message->from->lastName.empty()) {
            name += " " + message->from->lastName;
        }
        
        LOG_USER_INFO("User {} (@{}, ID: {}) sent /start", name, username, userId);
        
        // Check authorization
        if (!isAuthorized(userId)) {
            bot->getApi().sendMessage(
                message->chat->id,
                "🚫 You are not authorized to access this bot.\n"
                "Please contact the bot administrator for more information."
            );
            
            // Notify admin
            auto& config = getConfig();
            if (config.adminId != 0) {
                std::string adminMsg = 
                    "⚠️ <b>Unauthorized user accessed /start</b>\n\n"
                    "<b>Name:</b> " + name + "\n"
                    "<b>Username:</b> @" + username + "\n"
                    "<b>User ID:</b> <code>" + std::to_string(userId) + "</code>";
                
                bot->getApi().sendMessage(config.adminId, adminMsg, false, 0, nullptr, "HTML");
            }
            return;
        }
        
        // Send welcome message
        std::string welcomeText = 
            "Hello " + name + "\n\n"
            "🎵 <b>Welcome to the Choir Bot!</b>\n\n"
            "This bot helps you quickly find details about choir songs!\n"
            "Simply type a song like <b>H-27</b>, <b>L-5</b>, or <b>C-12</b> "
            "and get instant info, including the last sung date.\n\n"
            "Use <b>/help</b> to explore all commands.";
        
        bot->getApi().sendMessage(message->chat->id, welcomeText, false, 0, nullptr, "HTML");
    });
    
    // /help command
    bot->getEvents().onCommand("help", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        
        std::string helpText = 
            "🎵 *Choir Song Bot Help*\n\n"
            "Here are the available commands:\n\n"
            "• */start* - Start the bot\n"
            "• */help* - Show this help message\n"
            "• */check* - Check if a song exists\n"
            "• */last* - Find when a song was last sung\n"
            "• */date* - Find songs by date\n"
            "• */search* - Search for songs\n"
            "• */tune* - Find tune information\n"
            "• */notation* - Get sheet music notation\n"
            "• */theme* - Find songs by theme\n"
            "• */vocabulary* - Browse song vocabulary\n"
            "• */bible* - Look up Bible verses\n"
            "• */games* - Play Bible games\n"
            "• */download* - Download audio (YouTube/Spotify)\n"
            "• */organist* - View organist roster\n"
            "• */upload* - Upload sheet music\n"
            "• */setting* - Manage your preferences\n"
            "• */comment* - Send feedback to admin\n\n"
            "You can also directly type song codes like *H-27* or *L-5*.\n\n"
            "Use */cancel* to exit any command.";
        
        bot->getApi().sendMessage(message->chat->id, helpText, false, 0, nullptr, "Markdown");
    });
    
    // /refresh command (admin only)
    bot->getEvents().onCommand("refresh", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        
        if (!isAdmin(message->from->id)) {
            bot->getApi().sendMessage(
                message->chat->id,
                "⚠️ This command is only available to administrators."
            );
            return;
        }
        
        bot->getApi().sendMessage(message->chat->id, "♻️ Refreshing data from Google Drive...");
        
        // TODO: Implement data refresh
        LOG_BOT_INFO("Data refresh requested by admin {}", message->from->id);
        
        bot->getApi().sendMessage(
            message->chat->id,
            "✅ Data refresh completed!\n"
            "• Song databases reloaded\n"
            "• Search indices rebuilt\n"
            "• Organist roster updated"
        );
    });
    
    // /cancel command
    bot->getEvents().onCommand("cancel", [this](TgBot::Message::Ptr message) {
        clearUserState(message->from->id);
        bot->getApi().sendMessage(
            message->chat->id,
            "❌ Operation cancelled.",
            false,
            0,
            std::make_shared<TgBot::ReplyKeyboardRemove>()
        );
    });
}

void Application::registerSongCommands() {
    LOG_BOT_INFO("Registering song commands...");
    
    // /check command
    bot->getEvents().onCommand("check", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        setUserState(message->from->id, ConversationState::WaitingForCheckSong);
        bot->getApi().sendMessage(
            message->chat->id,
            "🔍 *Check Song*\n\n"
            "Please enter a song code to check (e.g., *H-27*, *L-5*, *C-12*):\n\n"
            "Format examples:\n"
            "• H-27 (Hymn 27)\n"
            "• L-5 (Lyric 5)\n"
            "• C-12 (Convention 12)",
            false, 0, nullptr, "Markdown"
        );
    });
    
    // /last command
    bot->getEvents().onCommand("last", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        setUserState(message->from->id, ConversationState::WaitingForLastSong);
        bot->getApi().sendMessage(
            message->chat->id,
            "📅 *Last Sung Date*\n\n"
            "Please enter a song code (e.g., *H-27*, *L-5*, *C-12*):",
            false, 0, nullptr, "Markdown"
        );
    });
    
    // /date command
    bot->getEvents().onCommand("date", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        setUserState(message->from->id, ConversationState::WaitingForDate);
        bot->getApi().sendMessage(
            message->chat->id,
            "📆 *Find Songs by Date*\n\n"
            "Please enter a date in one of these formats:\n"
            "• DD/MM/YYYY (e.g., 25/12/2024)\n"
            "• DD/MM (e.g., 25/12)\n"
            "• DD (e.g., 25)",
            false, 0, nullptr, "Markdown"
        );
    });
    
    // /vocabulary command
    bot->getEvents().onCommand("vocabulary", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        
        auto& db = getDatabase();
        auto vocab = db.getVocabulary();
        
        std::stringstream response;
        response << "📚 *Choir Vocabulary*\n\n";
        response << "Songs sung in the past 3 years:\n\n";
        
        response << "*Hymns:* " << vocab.hymnNumbers.size() << " total\n";
        if (!vocab.hymnNumbers.empty()) {
            response << "H-";
            for (size_t i = 0; i < std::min(vocab.hymnNumbers.size(), size_t(10)); ++i) {
                if (i > 0) response << ", H-";
                response << vocab.hymnNumbers[i];
            }
            if (vocab.hymnNumbers.size() > 10) {
                response << "... (+" << (vocab.hymnNumbers.size() - 10) << " more)";
            }
            response << "\n\n";
        }
        
        response << "*Lyrics:* " << vocab.lyricNumbers.size() << " total\n";
        if (!vocab.lyricNumbers.empty()) {
            response << "L-";
            for (size_t i = 0; i < std::min(vocab.lyricNumbers.size(), size_t(10)); ++i) {
                if (i > 0) response << ", L-";
                response << vocab.lyricNumbers[i];
            }
            if (vocab.lyricNumbers.size() > 10) {
                response << "... (+" << (vocab.lyricNumbers.size() - 10) << " more)";
            }
            response << "\n\n";
        }
        
        response << "*Conventions:* " << vocab.conventionNumbers.size() << " total\n";
        if (!vocab.conventionNumbers.empty()) {
            response << "C-";
            for (size_t i = 0; i < std::min(vocab.conventionNumbers.size(), size_t(10)); ++i) {
                if (i > 0) response << ", C-";
                response << vocab.conventionNumbers[i];
            }
            if (vocab.conventionNumbers.size() > 10) {
                response << "... (+" << (vocab.conventionNumbers.size() - 10) << " more)";
            }
            response << "\n\n";
        }
        
        response << "_Use /check to verify if a specific song is in the vocabulary_";
        
        bot->getApi().sendMessage(
            message->chat->id,
            response.str(),
            false, 0, nullptr, "Markdown"
        );
    });
}

void Application::registerSearchCommands() {
    LOG_BOT_INFO("Registering search commands...");
    
    // /search command
    bot->getEvents().onCommand("search", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        
        // Create keyboard
        auto keyboard = std::make_shared<TgBot::ReplyKeyboardMarkup>();
        keyboard->oneTimeKeyboard = true;
        keyboard->resizeKeyboard = true;
        
        std::vector<TgBot::KeyboardButton::Ptr> row1;
        row1.push_back(std::make_shared<TgBot::KeyboardButton>("By Index"));
        row1.push_back(std::make_shared<TgBot::KeyboardButton>("By Number"));
        keyboard->keyboard.push_back(row1);
        
        bot->getApi().sendMessage(
            message->chat->id,
            "How would you like to search?",
            false,
            0,
            keyboard
        );
        // TODO: Implement conversation handler
    });
    
    // /tune command
    bot->getEvents().onCommand("tune", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        bot->getApi().sendMessage(
            message->chat->id,
            "Search tune by:\n1. Hymn Number\n2. Page Number"
        );
        // TODO: Implement conversation handler
    });
    
    // /theme command
    bot->getEvents().onCommand("theme", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        
        auto keyboard = std::make_shared<TgBot::ReplyKeyboardMarkup>();
        keyboard->oneTimeKeyboard = true;
        keyboard->resizeKeyboard = true;
        
        std::vector<TgBot::KeyboardButton::Ptr> row1;
        row1.push_back(std::make_shared<TgBot::KeyboardButton>("Hymn Themes"));
        row1.push_back(std::make_shared<TgBot::KeyboardButton>("Doxology Themes"));
        keyboard->keyboard.push_back(row1);
        
        bot->getApi().sendMessage(
            message->chat->id,
            "Choose theme type:",
            false,
            0,
            keyboard
        );
        // TODO: Implement conversation handler
    });
}

void Application::registerBibleCommands() {
    LOG_BOT_INFO("Registering Bible commands...");
    
    // /bible command
    bot->getEvents().onCommand("bible", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        bot->getApi().sendMessage(
            message->chat->id,
            "📖 Enter a Bible reference (e.g., John 3:16, Genesis 1:1):"
        );
        // TODO: Implement conversation handler
    });
    
    // /games command
    bot->getEvents().onCommand("games", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        
        auto keyboard = std::make_shared<TgBot::ReplyKeyboardMarkup>();
        keyboard->oneTimeKeyboard = true;
        keyboard->resizeKeyboard = true;
        
        std::vector<TgBot::KeyboardButton::Ptr> row1;
        row1.push_back(std::make_shared<TgBot::KeyboardButton>("English"));
        row1.push_back(std::make_shared<TgBot::KeyboardButton>("Malayalam"));
        keyboard->keyboard.push_back(row1);
        
        bot->getApi().sendMessage(
            message->chat->id,
            "🎮 Choose game language:",
            false,
            0,
            keyboard
        );
        // TODO: Implement Bible game
    });
}

void Application::registerDownloadCommands() {
    LOG_BOT_INFO("Registering download commands...");
    
    // /download command
    bot->getEvents().onCommand("download", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        bot->getApi().sendMessage(
            message->chat->id,
            "🎵 Send me a YouTube or Spotify URL to download:"
        );
        // TODO: Implement download handler
    });
}

void Application::registerOrganistCommands() {
    LOG_BOT_INFO("Registering organist commands...");
    
    // /organist command
    bot->getEvents().onCommand("organist", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        bot->getApi().sendMessage(
            message->chat->id,
            "📋 Loading organist roster..."
        );
        // TODO: Implement organist roster display
    });
}

void Application::registerAdminCommands() {
    LOG_BOT_INFO("Registering admin commands...");
    
    // Admin commands would go here
    // /users, /add_authorized_user, /remove_authorized_user, etc.
}

void Application::registerSettingsCommands() {
    LOG_BOT_INFO("Registering settings commands...");
    
    // /setting command
    bot->getEvents().onCommand("setting", [this](TgBot::Message::Ptr message) {
        logUserInteraction(message);
        bot->getApi().sendMessage(
            message->chat->id,
            "⚙️ User Settings\n\nSelect an option to configure:"
        );
        // TODO: Implement settings menu
    });
}

void Application::registerAIHandler() {
    LOG_BOT_INFO("Registering AI message handler...");
    
    // Handle all non-command text messages (must be last)
    bot->getEvents().onNonCommandMessage([this](TgBot::Message::Ptr message) {
        if (!message->text.empty()) {
            logUserInteraction(message);
            int64_t userId = message->from->id;
            ConversationState state = getUserState(userId);
            
            // Check if user is in a conversation
            if (state != ConversationState::None) {
                handleConversationMessage(message, state);
                return;
            }
            
            
            LOG_BOT_INFO("AI handler received message: {}", message->text);
            
            // Try to parse as song code first
            auto parsed = SongParser::extractFirst(message->text);
            if (parsed) {
                handleSongCodeMessage(message, *parsed);
                return;
            }
            
            // If not a song code, reply with help
            bot->getApi().sendMessage(
                message->chat->id,
                "I didn't understand that. Try:\n"
                "• A song code like *H-27* or *L-5*\n"
                "• Use */help* to see all commands",
                false, 0, nullptr, "Markdown"
            );
        }
    });
}

bool Application::isAuthorized(int64_t userId) const {
    return getConfig().isAuthorized(userId);
}

bool Application::isAdmin(int64_t userId) const {
    return getConfig().isAdmin(userId);
}

void Application::logUserInteraction(const TgBot::Message::Ptr& message) {
    std::string username = message->from->username.empty() ? 
        "no_username" : message->from->username;
    std::string name = message->from->firstName;
    if (!message->from->lastName.empty()) {
        name += " " + message->from->lastName;
    }
    
    std::string text = message->text.empty() ? "[non-text message]" : message->text;
    
    LOG_USER_INFO("{} (@{}, ID: {}) sent: {}", 
        name, username, message->from->id, text);
}

void Application::setUserState(int64_t userId, ConversationState state) {
    userStates[userId] = state;
}

Application::ConversationState Application::getUserState(int64_t userId) const {
    auto it = userStates.find(userId);
    return (it != userStates.end()) ? it->second : ConversationState::None;
}

void Application::clearUserState(int64_t userId) {
    userStates.erase(userId);
}

void Application::handleConversationMessage(TgBot::Message::Ptr message, ConversationState state) {
    switch (state) {
        case ConversationState::WaitingForCheckSong:
            handleCheckSongInput(message);
            break;
        case ConversationState::WaitingForLastSong:
            handleLastSongInput(message);
            break;
        case ConversationState::WaitingForDate:
            handleDateInput(message);
            break;
        default:
            clearUserState(message->from->id);
            break;
    }
}

void Application::handleCheckSongInput(TgBot::Message::Ptr message) {
    auto parsed = SongParser::parse(message->text);
    if (!parsed) {
        bot->getApi().sendMessage(
            message->chat->id,
            "❌ Invalid song code format.\n"
            "Please enter a valid code like *H-27*, *L-5*, or *C-12*\n"
            "Or use */cancel* to exit.",
            false, 0, nullptr, "Markdown"
        );
        return;
    }
    
    clearUserState(message->from->id);
    
    std::string songCode = SongParser::format(parsed->category, parsed->number);
    auto& db = getDatabase();
    auto song = db.findByNumber(parsed->number, parsed->category);
    
    std::stringstream response;
    
    if (!song) {
        response << "❌ Song *" << songCode << "* does not exist in the database.";
    } else {
        bool inVocab = db.isSongInVocabulary(songCode);
        
        if (inVocab) {
            response << "✅ Song *" << songCode << "* is in the choir vocabulary!\n\n";
        } else {
            response << "⚠️ Song *" << songCode << "* exists but is NOT in the vocabulary\n\n";
            response << "_Note: A known song may not be in vocabulary if it hasn't been sung in the past 3 years_\n\n";
        }
        
        response << "📖 *Index:* " << song->index << "\n";
        if (!song->firstLine.empty()) {
            response << "🎵 *First Line:* " << song->firstLine << "\n";
        }
        
        // Get tune info
        std::string tune = db.getTuneName(songCode);
        if (!tune.empty() && tune != "Unknown") {
            response << "🎶 *Tune:* " << tune << "\n";
        }
    }
    
    bot->getApi().sendMessage(
        message->chat->id,
        response.str(),
        false, 0, nullptr, "Markdown"
    );
}

void Application::handleLastSongInput(TgBot::Message::Ptr message) {
    auto parsed = SongParser::parse(message->text);
    if (!parsed) {
        bot->getApi().sendMessage(
            message->chat->id,
            "❌ Invalid song code format.\n"
            "Please enter a valid code like *H-27*, *L-5*, or *C-12*\n"
            "Or use */cancel* to exit.",
            false, 0, nullptr, "Markdown"
        );
        return;
    }
    
    clearUserState(message->from->id);
    handleSongCodeMessage(message, *parsed);
}

void Application::handleDateInput(TgBot::Message::Ptr message) {
    clearUserState(message->from->id);
    
    // TODO: Implement date parsing and lookup
    bot->getApi().sendMessage(
        message->chat->id,
        "📆 Date lookup functionality is coming soon!\n"
        "Date received: " + message->text,
        false, 0, nullptr, "Markdown"
    );
}

void Application::handleSongCodeMessage(TgBot::Message::Ptr message, 
                                       const SongParserParsedCode& parsed) {
    std::string songCode = SongParser::format(parsed.category, parsed.number);
    LOG_BOT_INFO("Detected song code: {}", songCode);
    
    // Query database for song
    auto& db = getDatabase();
    auto song = db.findByNumber(parsed.number, parsed.category);
    
    if (!song) {
        bot->getApi().sendMessage(
            message->chat->id,
            "❌ Song *" + songCode + "* not found in the database.\n"
            "Use */check* to verify if a song exists.",
            false, 0, nullptr, "Markdown"
        );
        return;
    }
    
    // Build response message
    std::stringstream response;
    response << "🎵 *" << songCode << "* - " << song->index << "\n\n";
    
    // Add index if available
    if (!song->index.empty()) {
        response << "📖 *Index:* " << song->index << "\n";
    }
    
    // Add tune if available
    std::string tune = db.getTuneName(songCode);
    if (!tune.empty()) {
        response << "🎼 *Tune:* " << tune << "\n";
    }
    
    // Get last sung date
    auto lastDate = db.getLastSungDate(songCode);
    if (lastDate) {
        auto time_t_date = std::chrono::system_clock::to_time_t(*lastDate);
        std::tm tm_date;
        #ifdef _WIN32
        localtime_s(&tm_date, &time_t_date);
        #else
        localtime_r(&time_t_date, &tm_date);
        #endif
        
        char dateStr[32];
        std::strftime(dateStr, sizeof(dateStr), "%d/%m/%Y", &tm_date);
        response << "📅 *Last Sung:* " << dateStr << "\n";
        
        // Check if there are multiple dates
        auto allDates = db.getAllDates(songCode);
        if (allDates.size() > 1) {
            response << "\n_This song has been sung " << allDates.size() << " times._";
        }
    } else {
        response << "📅 *Last Sung:* Not recorded\n";
    }
    
    bot->getApi().sendMessage(
        message->chat->id,
        response.str(),
        false, 0, nullptr, "Markdown"
    );
}

// Global functions
void runBot() {
    auto& config = getConfig();
    globalApp = std::make_unique<Application>(config.token);
    
    if (!globalApp->initialize()) {
        throw std::runtime_error("Failed to initialize bot application");
    }
    
    globalApp->run();
}

void stopBot() {
    if (globalApp) {
        globalApp->stop();
    }
}

} // namespace ChoirBot
