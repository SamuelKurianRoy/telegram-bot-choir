#pragma once

#include "models/Song.hpp"
#include <set>
#include <string>
#include <algorithm>

namespace ChoirBot {

/**
 * Song vocabulary management
 * Validates and standardizes song identifiers
 */
class Vocabulary {
public:
    Vocabulary();
    
    // Build vocabulary from song lists
    void buildFromSongs(const std::vector<Song>& hymns,
                       const std::vector<Song>& lyrics,
                       const std::vector<Song>& conventions);
    
    // Check if song code exists
    bool isValid(const std::string& songCode) const;
    bool isValid(const std::string& songCode, SongCategory category) const;
    
    // Standardize song code format
    std::string standardize(const std::string& input) const;
    
    // Get all codes
    const std::set<std::string>& getAllCodes() const { return allVocabulary; }
    const std::set<std::string>& getHymnCodes() const { return hymnVocabulary; }
    const std::set<std::string>& getLyricCodes() const { return lyricVocabulary; }
    const std::set<std::string>& getConventionCodes() const { return conventionVocabulary; }
    
    // Statistics
    size_t size() const { return allVocabulary.size(); }
    size_t hymnCount() const { return hymnVocabulary.size(); }
    size_t lyricCount() const { return lyricVocabulary.size(); }
    size_t conventionCount() const { return conventionVocabulary.size(); }
    
private:
    std::set<std::string> allVocabulary;
    std::set<std::string> hymnVocabulary;
    std::set<std::string> lyricVocabulary;
    std::set<std::string> conventionVocabulary;
    
    void addToVocabulary(const Song& song);
};

/**
 * Get global vocabulary instance
 */
Vocabulary& getVocabulary();

} // namespace ChoirBot
