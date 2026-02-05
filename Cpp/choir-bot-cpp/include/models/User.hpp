#pragma once

#include <string>
#include <chrono>
#include <optional>
#include <nlohmann/json.hpp>

namespace ChoirBot {

using json = nlohmann::json;
using TimePoint = std::chrono::system_clock::time_point;

/**
 * User preferences structure
 */
struct UserPreferences {
    std::string bibleLanguage;      // "malayalam" or "english"
    std::string gameLanguage;       // "malayalam" or "english"
    int searchResultsLimit;         // Number of search results (1-10)
    std::string downloadPreference; // "single" or "ask"
    std::string downloadQuality;    // "high", "medium", "low", "ask"
    std::string themePreference;    // UI theme
    bool showTunesInDate;           // Show tunes in /date command
    std::string uploadPreference;   // Upload preference
    
    // Default constructor
    UserPreferences();
    
    // JSON serialization
    json toJson() const;
    static UserPreferences fromJson(const json& j);
};

/**
 * User data structure
 */
struct User {
    int64_t id;                     // Telegram user ID (primary key)
    std::string username;           // @username (without @)
    std::string name;               // Display name
    TimePoint lastSeen;             // Last interaction timestamp
    bool isAuthorized;              // Authorization status
    bool isAdmin;                   // Admin privileges
    std::string status;             // "active", "blocked", etc.
    std::string notes;              // Admin notes
    
    UserPreferences preferences;    // User preferences
    
    // Default constructor
    User();
    
    // Constructor with ID
    explicit User(int64_t userId);
    
    // Update last seen timestamp
    void updateLastSeen();
    
    // JSON serialization
    json toJson() const;
    static User fromJson(const json& j);
    
    // String representation
    std::string toString() const;
    
    // Comparison operators
    bool operator==(const User& other) const;
    bool operator<(const User& other) const;
};

} // namespace ChoirBot
