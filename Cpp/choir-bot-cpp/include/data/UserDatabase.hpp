#pragma once

#include "models/User.hpp"
#include <vector>
#include <map>
#include <optional>
#include <memory>
#include <mutex>

namespace ChoirBot {

/**
 * User database manager
 * Handles user data persistence with Google Drive
 */
class UserDatabase {
public:
    UserDatabase();
    ~UserDatabase();
    
    // Load database from Google Drive
    bool load();
    
    // Save database to Google Drive
    bool save();
    
    // User operations
    bool addUser(const User& user);
    bool updateUser(const User& user);
    bool removeUser(int64_t userId);
    std::optional<User> getUser(int64_t userId);
    bool userExists(int64_t userId) const;
    
    // Track user interaction (fast, non-blocking)
    std::pair<bool, bool> trackUserFast(int64_t userId, const std::string& username, 
                                        const std::string& name);
    
    // Track with command logging
    void trackInteraction(int64_t userId, const std::string& command);
    
    // Bulk operations
    std::vector<User> getAllUsers();
    std::vector<User> getAuthorizedUsers();
    std::vector<User> getRecentUsers(int limit = 10);
    
    // Preferences
    bool updatePreference(int64_t userId, const std::string& key, const std::string& value);
    std::string getPreference(int64_t userId, const std::string& key, 
                             const std::string& defaultValue = "");
    
    // Statistics
    size_t getUserCount() const;
    size_t getAuthorizedUserCount() const;
    
    // Pending saves flag (for batch updates)
    bool hasPendingSaves() const { return pendingSaves; }
    void markSaved() { pendingSaves = false; }
    
private:
    std::map<int64_t, User> users;
    mutable std::mutex mutex;
    bool pendingSaves;
    
    // Helper methods
    void ensureUserStructure(User& user);
    json serializeToJson() const;
    bool deserializeFromJson(const json& j);
};

/**
 * Get global user database instance
 */
UserDatabase& getUserDatabase();

} // namespace ChoirBot
