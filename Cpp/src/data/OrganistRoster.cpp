#include "data/OrganistRoster.hpp"
#include "data/DriveService.hpp"
#include "data/Database.hpp"
#include "utils/Logger.hpp"
#include <algorithm>
#include <set>

namespace ChoirBot {

static std::unique_ptr<OrganistRoster> globalRoster = nullptr;

OrganistRoster::OrganistRoster() {
}

OrganistRoster::~OrganistRoster() {
}

bool OrganistRoster::load() {
    LOG_BOT_INFO("Loading organist roster...");
    
    // TODO: Load from Google Drive
    
    LOG_BOT_INFO("Organist roster loaded: {} assignments", assignments.size());
    return true;
}

bool OrganistRoster::save() {
    LOG_BOT_INFO("Saving organist roster...");
    
    // TODO: Save to Google Drive
    
    LOG_BOT_INFO("Organist roster saved");
    return true;
}

std::vector<OrganistAssignment> OrganistRoster::getAllAssignments() const {
    std::lock_guard<std::mutex> lock(mutex);
    return assignments;
}

std::vector<OrganistAssignment> OrganistRoster::getAssignmentsForOrganist(const std::string& organistName) const {
    std::lock_guard<std::mutex> lock(mutex);
    std::vector<OrganistAssignment> result;
    
    for (const auto& assignment : assignments) {
        if (assignment.organistName == organistName) {
            result.push_back(assignment);
        }
    }
    
    return result;
}

std::vector<std::string> OrganistRoster::getUniqueOrganists() const {
    std::lock_guard<std::mutex> lock(mutex);
    std::set<std::string> uniqueOrganists;
    
    for (const auto& assignment : assignments) {
        if (!assignment.organistName.empty()) {
            uniqueOrganists.insert(assignment.organistName);
        }
    }
    
    return std::vector<std::string>(uniqueOrganists.begin(), uniqueOrganists.end());
}

std::optional<std::string> OrganistRoster::getOrganistForSong(const std::string& songCode) const {
    std::lock_guard<std::mutex> lock(mutex);
    
    for (const auto& assignment : assignments) {
        if (assignment.songOrResponse == songCode) {
            return assignment.organistName;
        }
    }
    
    return std::nullopt;
}

bool OrganistRoster::assignSongToOrganist(const std::string& songCode, const std::string& organistName) {
    std::lock_guard<std::mutex> lock(mutex);
    
    // Remove existing assignment for this song
    assignments.erase(
        std::remove_if(assignments.begin(), assignments.end(),
            [&songCode](const OrganistAssignment& a) { 
                return a.songOrResponse == songCode; 
            }),
        assignments.end()
    );
    
    // Add new assignment
    assignments.push_back({songCode, organistName});
    save();
    return true;
}

bool OrganistRoster::removeAssignment(const std::string& songCode) {
    std::lock_guard<std::mutex> lock(mutex);
    
    auto originalSize = assignments.size();
    assignments.erase(
        std::remove_if(assignments.begin(), assignments.end(),
            [&songCode](const OrganistAssignment& a) { 
                return a.songOrResponse == songCode; 
            }),
        assignments.end()
    );
    
    if (assignments.size() < originalSize) {
        save();
        return true;
    }
    return false;
}

std::tuple<bool, std::string, TimePoint> OrganistRoster::updateSongsForSunday() {
    auto now = std::chrono::system_clock::now();
    
    // TODO: Implement Sunday update logic
    
    return {false, "Not implemented", now};
}

bool OrganistRoster::updateSongsForDate(const TimePoint& date) {
    // TODO: Implement date-specific update
    (void)date;
    return false;
}

std::vector<Song> OrganistRoster::getUnusedSongs(SongCategory category, int monthsThreshold) {
    // TODO: Implement unused songs query
    (void)category;
    (void)monthsThreshold;
    return {};
}

OrganistRoster& getOrganistRoster() {
    if (!globalRoster) {
        globalRoster = std::make_unique<OrganistRoster>();
        globalRoster->load();
    }
    return *globalRoster;
}

} // namespace ChoirBot
