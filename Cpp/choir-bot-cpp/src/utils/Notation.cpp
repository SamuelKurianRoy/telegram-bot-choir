#include "utils/Notation.hpp"
#include "utils/Logger.hpp"
#include <fstream>
#include <sstream>
#include <algorithm>

namespace ChoirBot {

Notation::Notation() {
}

std::vector<std::string> Notation::getNotationLinks(const std::string& songCode) {
    (void)songCode;
    return {};
}

std::vector<std::string> Notation::getNotationByPage(const std::string& pageNumber) {
    (void)pageNumber;
    return {};
}

std::optional<int> Notation::findTunePageNumber(const std::string& tuneName,
                                                 const std::string& hymnNumber) {
    std::string key = tuneName + ":" + hymnNumber;
    auto it = confirmedPages.find(key);
    if (it != confirmedPages.end()) {
        return it->second;
    }
    
    auto result = checkTuneDatabase(tuneName, hymnNumber);
    if (result) return result;
    
    result = checkProbableResults(tuneName);
    if (result) return result;
    
    return checkHymnPageNumbers(hymnNumber);
}

bool Notation::saveConfirmedPage(const std::string& tuneName,
                                  const std::string& hymnNumber,
                                  int pageNumber,
                                  const std::string& source) {
    (void)source;
    std::string key = tuneName + ":" + hymnNumber;
    confirmedPages[key] = pageNumber;
    return true;
}

std::string Notation::generateImageLink(const std::string& fileId, int pageNumber) {
    return "https://drive.google.com/uc?export=view&id=" + fileId + 
           "&page=" + std::to_string(pageNumber);
}

std::optional<int> Notation::checkTuneDatabase(const std::string& tuneName,
                                                const std::string& hymnNumber) {
    (void)tuneName;
    (void)hymnNumber;
    return std::nullopt;
}

std::optional<int> Notation::checkProbableResults(const std::string& tuneName) {
    (void)tuneName;
    return std::nullopt;
}

std::optional<int> Notation::checkHymnPageNumbers(const std::string& hymnNumber) {
    (void)hymnNumber;
    return std::nullopt;
}

std::vector<int> Notation::parsePageList(const std::string& pageStr) {
    std::vector<int> pages;
    std::stringstream ss(pageStr);
    std::string token;
    
    while (std::getline(ss, token, ',')) {
        token.erase(std::remove_if(token.begin(), token.end(), ::isspace), token.end());
        
        size_t dashPos = token.find('-');
        if (dashPos != std::string::npos) {
            int start = std::stoi(token.substr(0, dashPos));
            int end = std::stoi(token.substr(dashPos + 1));
            for (int i = start; i <= end; ++i) {
                pages.push_back(i);
            }
        } else {
            pages.push_back(std::stoi(token));
        }
    }
    
    return pages;
}

} // namespace ChoirBot
