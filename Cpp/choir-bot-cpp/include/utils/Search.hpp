#pragma once

#include "models/Song.hpp"
#include <string>
#include <vector>
#include <memory>

namespace ChoirBot {

/**
 * TF-IDF based search engine
 * Provides fuzzy matching and ranked results
 */
class Search {
public:
    Search();
    ~Search();
    
    // Setup search indices
    void setup(const std::vector<Song>& hymns,
               const std::vector<Song>& lyrics,
               const std::vector<Song>& conventions);
    
    // Search by text (TF-IDF similarity)
    std::vector<SongMatch> findBestMatches(const std::string& query, 
                                          SongCategory category,
                                          size_t topN = 5) const;
    
    // Search by number (exact match)
    std::optional<Song> searchByNumber(int number, SongCategory category) const;
    
    // Rebuild indices (for /refresh)
    void rebuildIndices();
    
private:
    struct Impl;
    std::unique_ptr<Impl> pImpl;
    
    // TF-IDF computation
    std::vector<double> computeTFIDF(const std::string& query, 
                                     const std::vector<std::string>& documents) const;
    double cosineSimilarity(const std::vector<double>& a, 
                           const std::vector<double>& b) const;
};

/**
 * Get global search instance
 */
Search& getSearch();

} // namespace ChoirBot
