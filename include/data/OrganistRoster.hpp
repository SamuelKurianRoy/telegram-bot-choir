#pragma once

#include "models/Song.hpp"
#include <string>
#include <vector>
#include <map>
#include <optional>
#include <chrono>

namespace ChoirBot {

using TimePoint = std::chrono::system_clock::time_point;

/**
 * Organist assignment
 */
struct OrganistAssignment {
    std::string songOrResponse;
    std::string organistName;
    
    json toJson() const;
    static OrganistAssignment fromJson(const json& j);
};

/**
 * Organist roster management
 * Handles organist assignments and Sunday song updates
 */
class OrganistRoster {
public:
    OrganistRoster();
    ~OrganistRoster();
    
    // Load roster from Google Drive
    bool load();
    
    // Save roster to Google Drive
    bool save();
    
    // Query assignments
    std::vector<OrganistAssignment> getAllAssignments() const;
    std::vector<OrganistAssignment> getAssignmentsForOrganist(const std::string& organistName) const;
    std::vector<std::string> getUniqueOrganists() const;
    std::optional<std::string> getOrganistForSong(const std::string& songCode) const;
    
    // Modify assignments
    bool assignSongToOrganist(const std::string& songCode, const std::string& organistName);
    bool removeAssignment(const std::string& songCode);
    
    // Sunday updates
    std::tuple<bool, std::string, TimePoint> updateSongsForSunday();
    bool updateSongsForDate(const TimePoint& date);
    
    // Unused songs
    std::vector<Song> getUnusedSongs(SongCategory category, int monthsThreshold);
    
private:
    std::vector<OrganistAssignment> assignments;
    mutable std::mutex mutex;
    
    TimePoint getNextSunday() const;
    std::vector<Song> getSongsForDate(const TimePoint& date) const;
    bool updateRosterSheet(const std::vector<Song>& songs);
};

/**
 * Get global organist roster instance
 */
OrganistRoster& getOrganistRoster();

} // namespace ChoirBot
