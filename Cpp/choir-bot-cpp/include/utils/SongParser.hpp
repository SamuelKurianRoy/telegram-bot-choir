#pragma once

#include "models/Song.hpp"
#include <string>
#include <optional>
#include <regex>

namespace ChoirBot {

/**
 * Parsed song code structure
 */
struct SongParserParsedCode {
    SongCategory category;
    int number;
    std::string original;
};

/**
 * Song code parser utility
 * Parses codes like H-27, L-5, C-12
 */
class SongParser {
public:
    
    /**
     * Parse a song code from text
     * Supports formats: H-27, H27, h-27, h27, etc.
     * Returns parsed code or nullopt if invalid
     */
    static std::optional<SongParserParsedCode> parse(const std::string& text);
    
    /**
     * Check if text contains a song code
     */
    static bool containsSongCode(const std::string& text);
    
    /**
     * Extract first song code from text
     */
    static std::optional<SongParserParsedCode> extractFirst(const std::string& text);
    
    /**
     * Format a song code
     */
    static std::string format(SongCategory category, int number);
    
private:
    static const std::regex songCodePattern;
};

} // namespace ChoirBot
