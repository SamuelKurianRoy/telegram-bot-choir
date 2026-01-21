#include "models/User.hpp"
#include <sstream>
#include <iomanip>

namespace ChoirBot {

// UserPreferences implementation
UserPreferences::UserPreferences()
    : bibleLanguage("english")
    , gameLanguage("english")
    , searchResultsLimit(5)
    , downloadPreference("ask")
    , downloadQuality("ask")
    , themePreference("default")
    , showTunesInDate(false)
    , uploadPreference("default") {
}

json UserPreferences::toJson() const {
    json j;
    j["bible_language"] = bibleLanguage;
    j["game_language"] = gameLanguage;
    j["search_results_limit"] = searchResultsLimit;
    j["download_preference"] = downloadPreference;
    j["download_quality"] = downloadQuality;
    j["theme_preference"] = themePreference;
    j["show_tunes_in_date"] = showTunesInDate;
    j["upload_preference"] = uploadPreference;
    return j;
}

UserPreferences UserPreferences::fromJson(const json& j) {
    UserPreferences prefs;
    
    if (j.contains("bible_language")) {
        prefs.bibleLanguage = j["bible_language"].get<std::string>();
    }
    if (j.contains("game_language")) {
        prefs.gameLanguage = j["game_language"].get<std::string>();
    }
    if (j.contains("search_results_limit")) {
        prefs.searchResultsLimit = j["search_results_limit"].get<int>();
    }
    if (j.contains("download_preference")) {
        prefs.downloadPreference = j["download_preference"].get<std::string>();
    }
    if (j.contains("download_quality")) {
        prefs.downloadQuality = j["download_quality"].get<std::string>();
    }
    if (j.contains("theme_preference")) {
        prefs.themePreference = j["theme_preference"].get<std::string>();
    }
    if (j.contains("show_tunes_in_date")) {
        prefs.showTunesInDate = j["show_tunes_in_date"].get<bool>();
    }
    if (j.contains("upload_preference")) {
        prefs.uploadPreference = j["upload_preference"].get<std::string>();
    }
    
    return prefs;
}

// User implementation
User::User()
    : id(0)
    , lastSeen(std::chrono::system_clock::now())
    , isAuthorized(false)
    , isAdmin(false)
    , status("active") {
}

User::User(int64_t userId)
    : id(userId)
    , lastSeen(std::chrono::system_clock::now())
    , isAuthorized(false)
    , isAdmin(false)
    , status("active") {
}

void User::updateLastSeen() {
    lastSeen = std::chrono::system_clock::now();
}

json User::toJson() const {
    json j;
    j["id"] = id;
    j["username"] = username;
    j["name"] = name;
    
    // Convert timestamp to ISO 8601 string
    auto time = std::chrono::system_clock::to_time_t(lastSeen);
    std::stringstream ss;
    ss << std::put_time(std::gmtime(&time), "%Y-%m-%dT%H:%M:%SZ");
    j["last_seen"] = ss.str();
    
    j["is_authorized"] = isAuthorized;
    j["is_admin"] = isAdmin;
    j["status"] = status;
    j["notes"] = notes;
    j["preferences"] = preferences.toJson();
    
    return j;
}

User User::fromJson(const json& j) {
    User user;
    
    if (j.contains("id")) {
        user.id = j["id"].get<int64_t>();
    }
    if (j.contains("username")) {
        user.username = j["username"].get<std::string>();
    }
    if (j.contains("name")) {
        user.name = j["name"].get<std::string>();
    }
    if (j.contains("is_authorized")) {
        user.isAuthorized = j["is_authorized"].get<bool>();
    }
    if (j.contains("is_admin")) {
        user.isAdmin = j["is_admin"].get<bool>();
    }
    if (j.contains("status")) {
        user.status = j["status"].get<std::string>();
    }
    if (j.contains("notes")) {
        user.notes = j["notes"].get<std::string>();
    }
    if (j.contains("preferences")) {
        user.preferences = UserPreferences::fromJson(j["preferences"]);
    }
    
    // Parse last_seen timestamp (simplified)
    if (j.contains("last_seen")) {
        // Would need proper ISO 8601 parsing
        user.lastSeen = std::chrono::system_clock::now();
    }
    
    return user;
}

std::string User::toString() const {
    std::stringstream ss;
    ss << "User{id=" << id 
       << ", name=\"" << name << "\""
       << ", username=\"@" << username << "\""
       << ", authorized=" << (isAuthorized ? "true" : "false")
       << ", admin=" << (isAdmin ? "true" : "false")
       << "}";
    return ss.str();
}

bool User::operator==(const User& other) const {
    return id == other.id;
}

bool User::operator<(const User& other) const {
    return id < other.id;
}

} // namespace ChoirBot
