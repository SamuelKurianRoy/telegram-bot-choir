#include "models/Song.hpp"
#include <algorithm>
#include <regex>
#include <sstream>
#include <iomanip>

namespace ChoirBot {

SongCategory stringToCategory(const std::string& str) {
    std::string lower = str;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    
    if (lower == "hymn" || lower == "h") return SongCategory::Hymn;
    if (lower == "lyric" || lower == "l") return SongCategory::Lyric;
    if (lower == "convention" || lower == "c") return SongCategory::Convention;
    
    return SongCategory::Unknown;
}

std::string categoryToString(SongCategory category) {
    switch (category) {
        case SongCategory::Hymn: return "Hymn";
        case SongCategory::Lyric: return "Lyric";
        case SongCategory::Convention: return "Convention";
        default: return "Unknown";
    }
}

Song::Song() 
    : category(SongCategory::Unknown)
    , number(0) {
}

Song::Song(const std::string& songCode) 
    : category(SongCategory::Unknown)
    , number(0) {
    parseCode(songCode);
}

bool Song::parseCode(const std::string& songCode) {
    // Pattern: H-27, L-5, C-12, or variations like "H 27", "h27"
    std::regex pattern(R"(^([HhLlCc])\s*-?\s*(\d+)$)");
    std::smatch matches;
    
    if (std::regex_match(songCode, matches, pattern)) {
        std::string categoryChar = matches[1].str();
        std::transform(categoryChar.begin(), categoryChar.end(), 
                      categoryChar.begin(), ::toupper);
        
        category = stringToCategory(categoryChar);
        number = std::stoi(matches[2].str());
        code = getCode();  // Standardize format
        
        return true;
    }
    
    return false;
}

std::string Song::getCode() const {
    if (category == SongCategory::Unknown || number == 0) {
        return "";
    }
    
    return getCategoryPrefix() + "-" + std::to_string(number);
}

std::string Song::getCategoryPrefix() const {
    switch (category) {
        case SongCategory::Hymn: return "H";
        case SongCategory::Lyric: return "L";
        case SongCategory::Convention: return "C";
        default: return "U";
    }
}

json Song::toJson() const {
    json j;
    j["code"] = code;
    j["category"] = categoryToString(category);
    j["number"] = number;
    j["index"] = index;
    j["first_line"] = firstLine;
    j["tune"] = tune;
    
    if (pageNo.has_value()) {
        j["page_no"] = pageNo.value();
    }
    
    if (lastSung.has_value()) {
        auto time = std::chrono::system_clock::to_time_t(lastSung.value());
        std::stringstream ss;
        ss << std::put_time(std::gmtime(&time), "%Y-%m-%d");
        j["last_sung"] = ss.str();
    }
    
    if (!allDates.empty()) {
        json datesArray = json::array();
        for (const auto& date : allDates) {
            auto time = std::chrono::system_clock::to_time_t(date);
            std::stringstream ss;
            ss << std::put_time(std::gmtime(&time), "%Y-%m-%d");
            datesArray.push_back(ss.str());
        }
        j["all_dates"] = datesArray;
    }
    
    return j;
}

Song Song::fromJson(const json& j) {
    Song song;
    
    if (j.contains("code")) {
        song.parseCode(j["code"].get<std::string>());
    }
    
    if (j.contains("index")) {
        song.index = j["index"].get<std::string>();
    }
    
    if (j.contains("first_line")) {
        song.firstLine = j["first_line"].get<std::string>();
    }
    
    if (j.contains("tune")) {
        song.tune = j["tune"].get<std::string>();
    }
    
    if (j.contains("page_no")) {
        song.pageNo = j["page_no"].get<int>();
    }
    
    // Parse dates would require more complex parsing
    
    return song;
}

std::string Song::toString() const {
    std::stringstream ss;
    ss << code << " - " << index;
    if (!firstLine.empty()) {
        ss << " (" << firstLine << ")";
    }
    if (!tune.empty()) {
        ss << " [" << tune << "]";
    }
    return ss.str();
}

bool Song::operator==(const Song& other) const {
    return code == other.code;
}

bool Song::operator<(const Song& other) const {
    if (category != other.category) {
        return category < other.category;
    }
    return number < other.number;
}

} // namespace ChoirBot
