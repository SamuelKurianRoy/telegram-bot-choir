#include "utils/SongParser.hpp"
#include <algorithm>
#include <cctype>

namespace ChoirBot {

// Regex pattern: matches H-27, h-27, H27, h27, L-5, l-5, etc.
const std::regex SongParser::songCodePattern(
    R"([HhLlCc]-?\d+)",
    std::regex::icase
);

std::optional<SongParser::ParsedCode> SongParser::parse(const std::string& text) {
    if (text.empty()) {
        return std::nullopt;
    }
    
    // Make uppercase copy
    std::string upper = text;
    std::transform(upper.begin(), upper.end(), upper.begin(), ::toupper);
    
    // Remove spaces and hyphens
    std::string cleaned;
    for (char c : upper) {
        if (c != ' ' && c != '-') {
            cleaned += c;
        }
    }
    
    // Check format: first char must be H, L, or C
    if (cleaned.empty() || (cleaned[0] != 'H' && cleaned[0] != 'L' && cleaned[0] != 'C')) {
        return std::nullopt;
    }
    
    // Extract category
    SongCategory category;
    switch (cleaned[0]) {
        case 'H': category = SongCategory::Hymn; break;
        case 'L': category = SongCategory::Lyric; break;
        case 'C': category = SongCategory::Convention; break;
        default: return std::nullopt;
    }
    
    // Extract number
    std::string numberStr = cleaned.substr(1);
    if (numberStr.empty()) {
        return std::nullopt;
    }
    
    // Check all digits
    for (char c : numberStr) {
        if (!std::isdigit(c)) {
            return std::nullopt;
        }
    }
    
    try {
        int number = std::stoi(numberStr);
        if (number <= 0) {
            return std::nullopt;
        }
        
        ParsedCode result;
        result.category = category;
        result.number = number;
        result.original = text;
        return result;
        
    } catch (...) {
        return std::nullopt;
    }
}

bool SongParser::containsSongCode(const std::string& text) {
    return std::regex_search(text, songCodePattern);
}

std::optional<SongParser::ParsedCode> SongParser::extractFirst(const std::string& text) {
    std::smatch match;
    if (std::regex_search(text, match, songCodePattern)) {
        return parse(match.str());
    }
    return std::nullopt;
}

std::string SongParser::format(SongCategory category, int number) {
    char prefix;
    switch (category) {
        case SongCategory::Hymn: prefix = 'H'; break;
        case SongCategory::Lyric: prefix = 'L'; break;
        case SongCategory::Convention: prefix = 'C'; break;
        default: prefix = '?'; break;
    }
    return std::string(1, prefix) + "-" + std::to_string(number);
}

} // namespace ChoirBot
