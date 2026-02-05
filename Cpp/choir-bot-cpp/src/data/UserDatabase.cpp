#include "data/UserDatabase.hpp"
#include "data/DriveService.hpp"
#include "utils/Logger.hpp"

namespace ChoirBot {

static std::unique_ptr<UserDatabase> globalUserDB = nullptr;

UserDatabase::UserDatabase() 
    : pendingSaves(false) {
}

UserDatabase::~UserDatabase() {
    if (pendingSaves) {
        save();
    }
}

bool UserDatabase::load() {
    std::lock_guard<std::mutex> lock(mutex);
    LOG_BOT_INFO("Loading user database...");
    
    // TODO: Load from Google Drive
    
    LOG_BOT_INFO("User database loaded: {} users", users.size());
    return true;
}

bool UserDatabase::save() {
    std::lock_guard<std::mutex> lock(mutex);
    LOG_BOT_INFO("Saving user database...");
    
    // TODO: Save to Google Drive
    
    pendingSaves = false;
    LOG_BOT_INFO("User database saved: {} users", users.size());
    return true;
}

bool UserDatabase::addUser(const User& user) {
    std::lock_guard<std::mutex> lock(mutex);
    users[user.id] = user;
    pendingSaves = true;
    return true;
}

bool UserDatabase::updateUser(const User& user) {
    std::lock_guard<std::mutex> lock(mutex);
    auto it = users.find(user.id);
    if (it != users.end()) {
        it->second = user;
        pendingSaves = true;
        return true;
    }
    return false;
}

bool UserDatabase::removeUser(int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex);
    auto erased = users.erase(userId);
    if (erased > 0) {
        pendingSaves = true;
        return true;
    }
    return false;
}

std::optional<User> UserDatabase::getUser(int64_t userId) {
    std::lock_guard<std::mutex> lock(mutex);
    auto it = users.find(userId);
    if (it != users.end()) {
        return it->second;
    }
    return std::nullopt;
}

bool UserDatabase::userExists(int64_t userId) const {
    std::lock_guard<std::mutex> lock(mutex);
    return users.find(userId) != users.end();
}

std::pair<bool, bool> UserDatabase::trackUserFast(int64_t userId, 
    const std::string& username, const std::string& name) {
    std::lock_guard<std::mutex> lock(mutex);
    
    auto it = users.find(userId);
    bool isNew = (it == users.end());
    
    if (isNew) {
        User user(userId);
        user.username = username;
        user.name = name;
        user.updateLastSeen();
        users[userId] = user;
        pendingSaves = true;
        return {true, true};
    } else {
        it->second.updateLastSeen();
        pendingSaves = true;
        return {false, true};
    }
}

void UserDatabase::trackInteraction(int64_t userId, const std::string& command) {
    trackUserFast(userId, "", "");
    LOG_USER_INFO("User {} interacted with command: {}", userId, command);
}

std::vector<User> UserDatabase::getAllUsers() {
    std::lock_guard<std::mutex> lock(mutex);
    std::vector<User> result;
    for (const auto& [id, user] : users) {
        result.push_back(user);
    }
    return result;
}

std::vector<User> UserDatabase::getAuthorizedUsers() {
    std::lock_guard<std::mutex> lock(mutex);
    std::vector<User> result;
    for (const auto& [id, user] : users) {
        if (user.isAuthorized) {
            result.push_back(user);
        }
    }
    return result;
}

std::vector<User> UserDatabase::getRecentUsers(int limit) {
    std::lock_guard<std::mutex> lock(mutex);
    std::vector<User> result;
    for (const auto& [id, user] : users) {
        result.push_back(user);
    }
    
    // Sort by last seen (most recent first)
    std::sort(result.begin(), result.end(), 
        [](const User& a, const User& b) {
            return a.lastSeen > b.lastSeen;
        });
    
    if (result.size() > static_cast<size_t>(limit)) {
        result.resize(limit);
    }
    
    return result;
}

bool UserDatabase::updatePreference(int64_t userId, const std::string& key, 
                                   const std::string& value) {
    std::lock_guard<std::mutex> lock(mutex);
    auto it = users.find(userId);
    if (it != users.end()) {
        // TODO: Update specific preference based on key
        (void)key;    // Unused until implemented
        (void)value;  // Unused until implemented
        pendingSaves = true;
        return true;
    }
    return false;
}

std::string UserDatabase::getPreference(int64_t userId, const std::string& key, 
                                       const std::string& defaultValue) {
    std::lock_guard<std::mutex> lock(mutex);
    auto it = users.find(userId);
    if (it != users.end()) {
        // TODO: Get specific preference based on key
        (void)key;  // Unused until implemented
        return defaultValue;
    }
    return defaultValue;
}

size_t UserDatabase::getUserCount() const {
    std::lock_guard<std::mutex> lock(mutex);
    return users.size();
}

size_t UserDatabase::getAuthorizedUserCount() const {
    std::lock_guard<std::mutex> lock(mutex);
    return std::count_if(users.begin(), users.end(),
        [](const auto& pair) { return pair.second.isAuthorized; });
}

void UserDatabase::ensureUserStructure(User& user) {
    // Ensure user has all required fields
    (void)user;  // Unused until implemented
}

json UserDatabase::serializeToJson() const {
    json j = json::array();
    for (const auto& [id, user] : users) {
        j.push_back(user.toJson());
    }
    return j;
}

bool UserDatabase::deserializeFromJson(const json& j) {
    if (!j.is_array()) return false;
    
    users.clear();
    for (const auto& item : j) {
        User user = User::fromJson(item);
        users[user.id] = user;
    }
    return true;
}

UserDatabase& getUserDatabase() {
    if (!globalUserDB) {
        globalUserDB = std::make_unique<UserDatabase>();
        globalUserDB->load();
    }
    return *globalUserDB;
}

} // namespace ChoirBot
