#pragma once

#include "models/Song.hpp"
#include <vector>
#include <map>
#include <optional>
#include <memory>
#include <chrono>

namespace ChoirBot {

using TimePoint = std::chrono::system_clock::time_point;

/**
 * Main database manager for song data
 * Loads and manages all song databases from Google Drive
 */
class Database {
public:
    Database();
    ~Database();
    
    // Load all datasets from Google Drive
    bool loadAllDatasets();
    
    // Reload datasets (for /refresh command)
    bool reloadAllDatasets();
    
    // Song queries
    std::optional<Song> getSong(const std::string& songCode);
    std::vector<Song> getSongsByCategory(SongCategory category);
    std::vector<Song> getAllSongs();
    
    // Date queries
    std::optional<TimePoint> getLastSungDate(const std::string& songCode);
    std::vector<TimePoint> getAllDates(const std::string& songCode);
    std::vector<Song> getSongsByDate(const TimePoint& date);
    
    // Tune queries
    std::string getTuneName(const std::string& songCode);
    std::vector<Song> getSongsByTune(const std::string& tuneName);
    
    // Index queries
    std::optional<Song> findByIndex(const std::string& index, SongCategory category);
    std::optional<Song> findByNumber(int number, SongCategory category);
    
    // Statistics
    size_t getSongCount() const;
    size_t getSongCountByCategory(SongCategory category) const;
    
private:
    struct DataFrames {
        std::vector<Song> hymns;
        std::vector<Song> lyrics;
        std::vector<Song> conventions;
        std::map<std::string, std::vector<TimePoint>> sungDates;  // songCode -> dates
        std::map<std::string, std::string> tunes;  // songCode -> tune name
        std::map<std::string, int> pageNumbers;    // tune name -> page number
    };
    
    std::unique_ptr<DataFrames> data;
    
    // Helper methods
    void preprocessYearData();
    void cleanData();
    void buildIndices();
    bool loadHymnLyricConvention();
    bool loadMainDatabase();
    bool loadTuneDatabase();
};

/**
 * Get global database instance
 */
Database& getDatabase();

} // namespace ChoirBot
