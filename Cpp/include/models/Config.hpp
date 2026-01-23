#pragma once

#include <string>
#include <vector>
#include <map>
#include <optional>
#include <memory>
#include <fstream>
#include <nlohmann/json.hpp>

namespace ChoirBot {

using json = nlohmann::json;

/**
 * Configuration management class
 * Loads configuration from JSON file and environment variables
 */
class Config {
public:
    // Bot Authentication
    std::string token;
    int64_t adminId;
    std::vector<int64_t> authorizedUsers;
    
    // Google Drive File IDs
    struct GoogleDriveFiles {
        std::string hlcFileId;          // Hymn/Lyric/Convention index
        std::string tuneFileId;         // Tune database
        std::string mainFileId;         // Main song database
        std::string hymnSheetMusic;     // Hymn sheet music folder
        std::string botLogId;           // Bot log document
        std::string userLogId;          // User log document
        std::string youtubeLogId;       // YouTube download log
        std::string commentLogId;       // Comment/feedback log
        std::string gameScoreId;        // Bible game scores
        std::string userDatabaseId;     // User database
        std::string organistRosterId;   // Organist roster
        std::string disabledDbId;       // Feature control database
    } driveFiles;
    
    // Service Account
    struct ServiceAccount {
        std::string type;
        std::string projectId;
        std::string privateKeyId;
        std::string privateKey;
        std::string clientEmail;
        std::string clientId;
        std::string authUri;
        std::string tokenUri;
        std::string authProviderCertUrl;
        std::string clientCertUrl;
        std::string universeDomain;
    } serviceAccount;
    
    // API Keys
    std::string geminiApiKey;
    std::string groqApiKey;
    
    // Settings
    int logUploadInterval;  // seconds
    std::string keyPath;
    
    // Singleton pattern
    static Config& getInstance();
    
    // Load configuration
    bool loadFromFile(const std::string& filename);
    bool loadFromEnvironment();
    
    // Getters
    bool isAuthorized(int64_t userId) const;
    bool isAdmin(int64_t userId) const;
    
    ~Config() = default;
    
private:
    Config();
    
    // Prevent copying
    Config(const Config&) = delete;
    Config& operator=(const Config&) = delete;
    
    // Helper methods
    std::string getEnv(const std::string& key, const std::string& defaultValue = "") const;
    int64_t getEnvInt(const std::string& key, int64_t defaultValue = 0) const;
    std::vector<int64_t> parseUserIds(const std::string& commaSeparated) const;
    
    static std::unique_ptr<Config> instance;
};

/**
 * Get global configuration instance
 */
inline Config& getConfig() {
    return Config::getInstance();
}

} // namespace ChoirBot
