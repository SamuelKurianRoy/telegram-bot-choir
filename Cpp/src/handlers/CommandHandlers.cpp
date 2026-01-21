#include "handlers/CommandHandlers.hpp"
#include "data/Database.hpp"
#include "utils/Search.hpp"
#include "utils/Logger.hpp"
#include "models/Config.hpp"
#include <sstream>

namespace ChoirBot {

// Implement only handleCommand methods, not getCommand (defined inline in header)

void StartHandler::handleCommand(TgBot::Message::Ptr message) {
    auto& config = Config::getInstance();
    auto user = message->from;
    
    LOG_USER_INFO("{} (@{}, ID: {}) sent: /start", 
                  user->firstName, 
                  user->username.empty() ? "N/A" : user->username, 
                  user->id);
    
    // Check authorization
    if (!config.isAuthorized(user->id)) {
        LOG_USER_WARN("Unauthorized access attempt by user {}", user->id);
        bot->getApi().sendMessage(
            message->chat->id,
            "🚫 You are not authorized to access this feature of the bot.\n"
            "Please contact the bot administrator for more information"
        );
        return;
    }
    
    std::stringstream welcomeText;
    welcomeText << "Hello " << user->firstName << "\n\n"
                << "🎵 <b>Welcome to the Choir Bot!</b>\n\n"
                << "This bot helps you quickly find details about choir songs!\n"
                << "Simply type a song like <b>H-27</b>, <b>L-5</b>, or <b>C-12</b> and get instant info, including the last sung date.\n\n"
                << "Use <b>/help</b> to explore all commands.";
    
    bot->getApi().sendMessage(
        message->chat->id,
        welcomeText.str(),
        false,
        0,
        nullptr,
        "HTML"
    );
}

void HelpHandler::handleCommand(TgBot::Message::Ptr message) {
    auto user = message->from;
    LOG_USER_INFO("{} (@{}, ID: {}) asked for: /help", 
                  user->firstName, 
                  user->username.empty() ? "N/A" : user->username, 
                  user->id);
    
    std::string help_part1 = 
        "🎵 *Choir Song Bot Help* (Part 1/3)\n\n"
        "Here are the available commands and how to use them:\n\n"
        "• **/start**\n"
        "  - *Description:* Starts the bot and shows the welcome message with basic instructions.\n"
        "  - *Example:* Simply type `/start`.\n\n"
        "• **/check**\n"
        "  - *Description:* Check if a song exists in the vocabulary or not. After typing the command, enter the song in the format H-27 (Hymn), L-14 (Lyric), or C-5 (Convention).\n"
        "  - *Example:* Type `/check`, then enter a song like `H-27`.\n\n"
        "• **/last**\n"
        "  - *Description:* Find out when a song was last sung. After typing the command, enter the song like H-27 (Hymn), L-14 (Lyric), or C-5 (Convention). You'll also have the option to view all the dates it was sung.\n"
        "  - *Example:* Type `/last`, then enter a song like `H-27`.\n\n"
        "• **/search**\n"
        "  - *Description:* Interactive search for songs.\n"
        "  - *Options:*\n"
        "     - _By Index:_ Search by entering a line from a hymn, lyric, or convention.\n"
        "     - _By Number:_ Search by entering an index number.\n"
        "  - *Example:* Type `/search` and follow the prompts.\n\n"
        "• **/tune**\n"
        "  - *Description:* Interactively find tunes by hymn number or tune index.\n"
        "  - *Options:*\n"
        "     - _By Hymn Number:_ Returns the tune(s) for a specific hymn number.\n"
        "     - _By Tune Index:_ Provides the top matching hymns using fuzzy matching on tune names.\n"
        "  - *Example:* Type `/tune` and choose either *Hymn Number* or *Tune Index*, then enter your query (e.g. `Whit` or `29`).";

    std::string help_part2 = 
        "🎵 *Choir Song Bot Help* (Part 2/3)\n\n"
        "• **/notation**\n"
        "  - *Description:* Interactive notation lookup. Start by typing `/notation`, and the bot will ask you for a hymn or lyric number (e.g. `H-86` or `L-222`). You can enter multiple hymn or lyric numbers one after another, and for hymns, select a tune to view the notation. Type `/cancel` to stop.\n"
        "  - *Example:* Type `/notation`, then enter a hymn number like `H-86` or a lyric number like `L-222`, and follow the prompts.\n\n"
        "• **/theme**\n"
        "  - *Description:* Initiates an interactive theme filter. You will be presented with a list of unique themes (collected from all comma-separated entries in the database), and you can select or type a theme to display the hymns related to it.\n"
        "  - *Example:* Type `/theme` and choose from the displayed themes, or type a custom theme like `Additional Hymns`.\n\n"
        "• **/date**\n"
        "  - *Description:* Interactive date lookup. Start by typing `/date`, and the bot will ask you to enter a date (DD/MM/YYYY, DD/MM, or DD). You can enter multiple dates one after another to see the songs sung on those dates, until you type `/cancel` to stop.\n"
        "  - *Example:* Type `/date`, then enter a date like `05/04/2024`, and keep entering dates as needed.\n\n"
        "• **/bible**\n"
        "  - *Description:* Interactive Bible passage lookup. Get Bible text directly in the chat with support for multiple languages. Malayalam is used by default.\n"
        "  - *Options:*\n"
        "     - _Direct:_ Type `/bible Gen 10` or `/bible John 3:16 english`\n"
        "     - _Interactive:_ Type `/bible` and follow prompts for book, chapter, and language\n"
        "  - *Supported Languages:* Malayalam (default), English, Hindi, Tamil, Telugu, and many more\n"
        "  - *Example:* Type `/bible` then enter `Gen 3:3` or `John 3:16 english`";

    std::string help_part3 = 
        "🎵 *Choir Song Bot Help* (Part 3/3)\n\n"
        "• **/games**\n"
        "  - *Description:* Play an interactive Bible verse guessing game! Test your knowledge by identifying Bible references from verses. Choose from Easy, Medium, or Hard difficulty levels.\n"
        "  - *Features:* Two languages (English & Malayalam), score tracking, separate leaderboards by difficulty, real-time verse fetching\n"
        "  - *Example:* Type `/games` and follow the prompts to select language and difficulty.\n\n"
        "• **/organist**\n"
        "  - *Description:* View organist assignments for songs. See which songs are assigned to each organist or view unassigned songs.\n"
        "  - *Example:* Type `/organist`, select an organist from the list, or choose 'Unassigned Songs' to see songs without an organist.\n\n"
        "• **/download**\n"
        "  - *Description:* Download audio from YouTube, or Spotify links. The bot will extract the audio and send it to you as an MP3 file.\n"
        "  - *Supported platforms:* YouTube, Spotify\n"
        "  - *Example:* Type `/download`, then paste a YouTube or Spotify link, and select your preferred audio quality.\n\n"
        "• **/comment**\n"
        "  - *Description:* Allows you to submit comments, recommendations, or feedback directly to the bot administrator.\n"
        "  - *Example:* Type `/comment Your message here` and the bot will forward it to the administrator for review.\n\n"
        "• **/setting**\n"
        "  - *Description:* Manage your personal settings including default Bible language, game language, and search results limit.\n"
        "  - *Example:* Type `/setting` to access your settings menu.\n\n"
        "• **/cancel**\n"
        "  - *Description:* Cancels the current operation.\n"
        "  - *Example:* If you are in a conversation, type `/cancel` to stop it.\n\n"
        "If you need further assistance, feel free to ask!";

    // Send the help messages in sequence
    bot->getApi().sendMessage(message->chat->id, help_part1, false, 0, nullptr, "Markdown");
    bot->getApi().sendMessage(message->chat->id, help_part2, false, 0, nullptr, "Markdown");
    bot->getApi().sendMessage(message->chat->id, help_part3, false, 0, nullptr, "Markdown");
}

void CheckHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void LastHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void LastHandler::handleCallback(TgBot::CallbackQuery::Ptr query) {
    (void)query;
}

void DateHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void SearchHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void SearchHandler::handleCallback(TgBot::CallbackQuery::Ptr query) {
    (void)query;
}

void TuneHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void NotationHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void NotationHandler::handleCallback(TgBot::CallbackQuery::Ptr query) {
    (void)query;
}

void ThemeHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void BibleHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void GamesHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void DownloadHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void OrganistHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void SettingsHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void UploadHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void CommentHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void RefreshHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void AdminUsersHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

void FeatureControlHandler::handleCommand(TgBot::Message::Ptr message) {
    (void)message;
}

} // namespace ChoirBot
