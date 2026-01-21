#pragma once

#include <string>
#include <vector>
#include <map>
#include <set>
#include <optional>
#include <memory>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace ChoirBot {

/**
 * Feature definition
 */
struct Feature {
    std::string name;
    std::string displayName;
    std::string description;
    std::string commands;
    bool enabled;
    std::vector<int64_t> restrictedTo;  // Empty = all users, otherwise specific users
    
    json toJson() const;
    static Feature fromJson(const json& j);
};

/**
 * Feature control system
 * Manages feature enable/disable states
 */
class FeatureControl {
public:
    FeatureControl();
    ~FeatureControl();
    
    // Load features from Google Drive
    bool load();
    
    // Save features to Google Drive
    bool save();
    
    // Feature queries
    bool isEnabled(const std::string& featureName) const;
    bool isEnabledForUser(const std::string& featureName, int64_t userId) const;
    std::optional<Feature> getFeature(const std::string& featureName) const;
    std::vector<Feature> getAllFeatures() const;
    
    // Feature management
    bool enableFeature(const std::string& featureName);
    bool disableFeature(const std::string& featureName);
    bool restrictFeature(const std::string& featureName, const std::vector<int64_t>& userIds);
    bool unrestrictFeature(const std::string& featureName);
    
    // Bulk operations
    bool restoreAllFeatures();
    bool addMissingFeatures();
    
    // Default features
    static std::map<std::string, Feature> getDefaultFeatures();
    
private:
    std::map<std::string, Feature> features;
    mutable std::mutex mutex;
    
    void initializeDefaults();
};

/**
 * Get global feature control instance
 */
FeatureControl& getFeatureControl();

} // namespace ChoirBot
