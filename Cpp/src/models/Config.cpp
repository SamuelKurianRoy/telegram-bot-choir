#include "models/Config.hpp"
#include <cstdlib>
#include <sstream>
#include <stdexcept>

namespace ChoirBot {

std::unique_ptr<Config> Config::instance = nullptr;

Config::Config() 
    : adminId(0)
    , logUploadInterval(3600)
    , keyPath("/tmp/service_account.json") {
}

Config& Config::getInstance() {
    if (!instance) {
        instance = std::unique_ptr<Config>(new Config());
    }
    return *instance;
}

bool Config::loadFromFile(const std::string& filename) {
    try {
        std::ifstream file(filename);
        if (!file.is_open()) {
            return false;
        }
        
        json config;
        file >> config;
        
        // Bot Authentication
        if (config.contains("token")) {
            token = config["token"].get<std::string>();
        }
        if (config.contains("admin_id")) {
            adminId = config["admin_id"].get<int64_t>();
        }
        if (config.contains("authorized_users")) {
            if (config["authorized_users"].is_array()) {
                for (const auto& user : config["authorized_users"]) {
                    authorizedUsers.push_back(user.get<int64_t>());
                }
            } else if (config["authorized_users"].is_string()) {
                authorizedUsers = parseUserIds(config["authorized_users"].get<std::string>());
            }
        }
        
        // Google Drive Files
        if (config.contains("drive_files")) {
            const auto& df = config["drive_files"];
            driveFiles.hlcFileId = df.value("hlc_file_id", "");
            driveFiles.tuneFileId = df.value("tune_file_id", "");
            driveFiles.mainFileId = df.value("main_file_id", "");
            driveFiles.hymnSheetMusic = df.value("hymn_sheet_music", "");
            driveFiles.botLogId = df.value("bot_log_id", "");
            driveFiles.userLogId = df.value("user_log_id", "");
            driveFiles.youtubeLogId = df.value("youtube_log_id", "");
            driveFiles.commentLogId = df.value("comment_log_id", "");
            driveFiles.gameScoreId = df.value("game_score_id", "");
            driveFiles.userDatabaseId = df.value("user_database_id", "");
            driveFiles.organistRosterId = df.value("organist_roster_id", "");
            driveFiles.disabledDbId = df.value("disabled_db_id", "");
        }
        
        // Service Account
        if (config.contains("service_account")) {
            const auto& sa = config["service_account"];
            serviceAccount.type = sa.value("type", "");
            serviceAccount.projectId = sa.value("project_id", "");
            serviceAccount.privateKeyId = sa.value("private_key_id", "");
            serviceAccount.privateKey = sa.value("private_key", "");
            serviceAccount.clientEmail = sa.value("client_email", "");
            serviceAccount.clientId = sa.value("client_id", "");
            serviceAccount.authUri = sa.value("auth_uri", "");
            serviceAccount.tokenUri = sa.value("token_uri", "");
            serviceAccount.authProviderCertUrl = sa.value("auth_provider_x509_cert_url", "");
            serviceAccount.clientCertUrl = sa.value("client_x509_cert_url", "");
            serviceAccount.universeDomain = sa.value("universe_domain", "");
        }
        
        // API Keys
        if (config.contains("gemini_api_key")) {
            geminiApiKey = config["gemini_api_key"].get<std::string>();
        }
        if (config.contains("groq_api_key")) {
            groqApiKey = config["groq_api_key"].get<std::string>();
        }
        
        // Settings
        if (config.contains("log_upload_interval")) {
            logUploadInterval = config["log_upload_interval"].get<int>();
        }
        
        return true;
    } catch (const std::exception& e) {
        return false;
    }
}

bool Config::loadFromEnvironment() {
    // Bot Authentication
    token = getEnv("TOKEN");
    adminId = getEnvInt("ADMIN_ID");
    
    std::string authUsers = getEnv("AUTHORIZED_USERS");
    if (!authUsers.empty()) {
        authorizedUsers = parseUserIds(authUsers);
    }
    
    // Google Drive File IDs
    driveFiles.hlcFileId = getEnv("HLCFILE_ID");
    driveFiles.tuneFileId = getEnv("TFILE_ID");
    driveFiles.mainFileId = getEnv("FILE_ID");
    driveFiles.hymnSheetMusic = getEnv("H_SHEET_MUSIC");
    driveFiles.botLogId = getEnv("BFILE_ID");
    driveFiles.userLogId = getEnv("UFILE_ID");
    driveFiles.youtubeLogId = getEnv("YFILE_ID");
    driveFiles.commentLogId = getEnv("COMFILE_ID");
    driveFiles.gameScoreId = getEnv("GAME_SCORE");
    driveFiles.userDatabaseId = getEnv("U_DATABASE");
    driveFiles.organistRosterId = getEnv("ORGANIST_ROSTER_SHEET_ID");
    driveFiles.disabledDbId = getEnv("DISABLED_DB");
    
    // Service Account (simplified - would need proper parsing)
    serviceAccount.type = getEnv("type");
    serviceAccount.projectId = getEnv("project_id");
    serviceAccount.privateKeyId = getEnv("private_key_id");
    serviceAccount.clientEmail = getEnv("client_email");
    serviceAccount.clientId = getEnv("client_id");
    
    // API Keys
    geminiApiKey = getEnv("GEMINI_API_KEY");
    groqApiKey = getEnv("GROQ_API_KEY");
    
    // Settings
    logUploadInterval = getEnvInt("LOG_UPLOAD_INTERVAL", 3600);
    
    return !token.empty() && adminId != 0;
}

bool Config::isAuthorized(int64_t userId) const {
    return std::find(authorizedUsers.begin(), authorizedUsers.end(), userId) 
           != authorizedUsers.end();
}

bool Config::isAdmin(int64_t userId) const {
    return userId == adminId;
}

std::string Config::getEnv(const std::string& key, const std::string& defaultValue) const {
    const char* value = std::getenv(key.c_str());
    return value ? std::string(value) : defaultValue;
}

int64_t Config::getEnvInt(const std::string& key, int64_t defaultValue) const {
    const char* value = std::getenv(key.c_str());
    if (!value) return defaultValue;
    
    try {
        return std::stoll(value);
    } catch (...) {
        return defaultValue;
    }
}

std::vector<int64_t> Config::parseUserIds(const std::string& commaSeparated) const {
    std::vector<int64_t> ids;
    std::stringstream ss(commaSeparated);
    std::string item;
    
    while (std::getline(ss, item, ',')) {
        // Trim whitespace
        item.erase(0, item.find_first_not_of(" \t\n\r"));
        item.erase(item.find_last_not_of(" \t\n\r") + 1);
        
        if (!item.empty()) {
            try {
                ids.push_back(std::stoll(item));
            } catch (...) {
                // Skip invalid IDs
            }
        }
    }
    
    return ids;
}

} // namespace ChoirBot
