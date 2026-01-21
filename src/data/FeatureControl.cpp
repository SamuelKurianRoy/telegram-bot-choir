#include "data/FeatureControl.hpp"
#include "data/DriveService.hpp"
#include "utils/Logger.hpp"

namespace ChoirBot {

static std::unique_ptr<FeatureControl> globalFeatureControl = nullptr;

FeatureControl::FeatureControl() {
    initializeDefaults();
}

FeatureControl::~FeatureControl() = default;

bool FeatureControl::load() {
    LOG_BOT_INFO("Loading feature control configuration...");
    
    // TODO: Load from Google Drive
    
    LOG_BOT_INFO("Feature control loaded: {} features", features.size());
    return true;
}

bool FeatureControl::save() {
    LOG_BOT_INFO("Saving feature control configuration...");
    
    // TODO: Save to Google Drive
    
    LOG_BOT_INFO("Feature control saved");
    return true;
}

bool FeatureControl::isEnabled(const std::string& featureName) const {
    auto it = features.find(featureName);
    if (it != features.end()) {
        return it->second.enabled;
    }
    return false;  // Feature doesn't exist
}

bool FeatureControl::isEnabledForUser(const std::string& featureName, 
                                                int64_t userId) const {
    auto it = features.find(featureName);
    if (it != features.end()) {
        if (!it->second.enabled) {
            return false;  // Feature is disabled for everyone
        }
        
        if (it->second.restrictedTo.empty()) {
            return true;  // No restrictions
        }
        
        // If there are restricted users, only they can use it
        return std::find(it->second.restrictedTo.begin(), 
                        it->second.restrictedTo.end(), 
                        userId) != it->second.restrictedTo.end();
    }
    return false;  // Feature doesn't exist
}

bool FeatureControl::enableFeature(const std::string& featureName) {
    auto it = features.find(featureName);
    if (it != features.end()) {
        it->second.enabled = true;
        save();
        return true;
    }
    return false;
}

bool FeatureControl::disableFeature(const std::string& featureName) {
    auto it = features.find(featureName);
    if (it != features.end()) {
        it->second.enabled = false;
        save();
        return true;
    }
    return false;
}

bool FeatureControl::restrictFeature(const std::string& featureName, 
                                          const std::vector<int64_t>& userIds) {
    auto it = features.find(featureName);
    if (it != features.end()) {
        it->second.restrictedTo = userIds;
        save();
        return true;
    }
    return false;
}

bool FeatureControl::unrestrictFeature(const std::string& featureName) {
    auto it = features.find(featureName);
    if (it != features.end()) {
        it->second.restrictedTo.clear();
        save();
        return true;
    }
    return false;
}

std::vector<Feature> FeatureControl::getAllFeatures() const {
    std::vector<Feature> result;
    for (const auto& [name, feature] : features) {
        result.push_back(feature);
    }
    return result;
}

void FeatureControl::initializeDefaults() {
    // Initialize all default features as enabled
    const std::vector<std::string> defaultFeatures = {
        "check", "last", "date", "search", "tune", "notation",
        "theme", "bible", "games", "download", "organist",
        "settings", "upload", "comment", "refresh", "ai_assistant"
    };
    
    for (const auto& name : defaultFeatures) {
        features[name] = Feature{
            name,           // name
            name,           // displayName
            "",             // description
            "",             // commands
            true,           // enabled
            {}              // restrictedTo
        };
    }
}

FeatureControl& getFeatureControl() {
    if (!globalFeatureControl) {
        globalFeatureControl = std::make_unique<FeatureControl>();
        globalFeatureControl->load();
    }
    return *globalFeatureControl;
}

} // namespace ChoirBot
