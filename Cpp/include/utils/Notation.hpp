#pragma once

#include <string>
#include <vector>
#include <optional>
#include <map>

namespace ChoirBot {

/**
 * Music notation handling
 * Finds and generates links to sheet music
 */
class Notation {
public:
    Notation();
    
    // Get notation link for a song
    std::vector<std::string> getNotationLinks(const std::string& songCode);
    
    // Get notation by page number
    std::vector<std::string> getNotationByPage(const std::string& pageNumber);
    
    // Find page number for tune
    std::optional<int> findTunePageNumber(const std::string& tuneName, 
                                          const std::string& hymnNumber);
    
    // Save confirmed page result (machine learning)
    bool saveConfirmedPage(const std::string& tuneName, 
                          const std::string& hymnNumber,
                          int pageNumber,
                          const std::string& source);
    
    // Generate Google Drive image links
    std::string generateImageLink(const std::string& fileId, int pageNumber);
    
private:
    std::map<std::string, int> confirmedPages;  // tune+hymn -> page
    
    // Multi-source lookup
    std::optional<int> checkTuneDatabase(const std::string& tuneName, 
                                         const std::string& hymnNumber);
    std::optional<int> checkProbableResults(const std::string& tuneName);
    std::optional<int> checkHymnPageNumbers(const std::string& hymnNumber);
    
    // Parse page list (e.g., "10,12-15,20")
    std::vector<int> parsePageList(const std::string& pageStr);
};

/**
 * Get global notation instance
 */
Notation& getNotation();

} // namespace ChoirBot
