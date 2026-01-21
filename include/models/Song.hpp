#pragma once

#include <string>
#include <optional>
#include <chrono>
#include <vector>
#include <nlohmann/json.hpp>

namespace ChoirBot {

using json = nlohmann::json;
using TimePoint = std::chrono::system_clock::time_point;

/**
 * Song category enumeration
 */
enum class SongCategory {
    Hymn,
    Lyric,
    Convention,
    Unknown
};

/**
 * Convert string to SongCategory
 */
SongCategory stringToCategory(const std::string& str);

/**
 * Convert SongCategory to string
 */
std::string categoryToString(SongCategory category);

/**
 * Song data structure
 */
struct Song {
    std::string code;                       // "H-27", "L-5", "C-12"
    SongCategory category;                  // Hymn, Lyric, Convention
    int number;                             // 27, 5, 12
    std::string index;                      // Song title/index
    std::string firstLine;                  // First line of lyrics
    std::string tune;                       // Tune name (e.g., "Hursley")
    std::optional<int> pageNo;              // Sheet music page number
    std::optional<TimePoint> lastSung;      // Last sung date
    std::vector<TimePoint> allDates;        // All dates sung
    
    // Default constructor
    Song();
    
    // Constructor with code
    explicit Song(const std::string& songCode);
    
    // Parse song code (e.g., "H-27" -> category=Hymn, number=27)
    bool parseCode(const std::string& songCode);
    
    // Get formatted song code
    std::string getCode() const;
    
    // Get category prefix (H, L, C)
    std::string getCategoryPrefix() const;
    
    // JSON serialization
    json toJson() const;
    static Song fromJson(const json& j);
    
    // String representation
    std::string toString() const;
    
    // Comparison operators
    bool operator==(const Song& other) const;
    bool operator<(const Song& other) const;
};

/**
 * Song search result with similarity score
 */
struct SongMatch {
    Song song;
    double score;  // 0.0 to 1.0
    
    bool operator<(const SongMatch& other) const {
        return score > other.score;  // Higher scores first
    }
};

} // namespace ChoirBot
