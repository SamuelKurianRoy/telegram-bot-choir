#include "data/Vocabulary.hpp"
#include "utils/Logger.hpp"

namespace ChoirBot {

static std::unique_ptr<Vocabulary> globalVocab = nullptr;

Vocabulary::Vocabulary() {
}

void Vocabulary::buildFromSongs(const std::vector<Song>& hymns,
                                const std::vector<Song>& lyrics,
                                const std::vector<Song>& conventions) {
    allVocabulary.clear();
    hymnVocabulary.clear();
    lyricVocabulary.clear();
    conventionVocabulary.clear();
    
    for (const auto& song : hymns) {
        addToVocabulary(song);
    }
    
    for (const auto& song : lyrics) {
        addToVocabulary(song);
    }
    
    for (const auto& song : conventions) {
        addToVocabulary(song);
    }
    
    LOG_BOT_INFO("Vocabulary built: {} total songs", allVocabulary.size());
    LOG_BOT_INFO("  Hymns: {}", hymnVocabulary.size());
    LOG_BOT_INFO("  Lyrics: {}", lyricVocabulary.size());
    LOG_BOT_INFO("  Conventions: {}", conventionVocabulary.size());
}

bool Vocabulary::isValid(const std::string& songCode) const {
    std::string std = standardize(songCode);
    return allVocabulary.find(std) != allVocabulary.end();
}

bool Vocabulary::isValid(const std::string& songCode, SongCategory category) const {
    std::string std = standardize(songCode);
    
    const std::set<std::string>* vocab = nullptr;
    switch (category) {
        case SongCategory::Hymn: vocab = &hymnVocabulary; break;
        case SongCategory::Lyric: vocab = &lyricVocabulary; break;
        case SongCategory::Convention: vocab = &conventionVocabulary; break;
        default: return false;
    }
    
    return vocab->find(std) != vocab->end();
}

std::string Vocabulary::standardize(const std::string& input) const {
    // Remove whitespace and standardize format
    std::string result;
    std::string upper;
    
    // Convert to uppercase
    for (char c : input) {
        upper += std::toupper(c);
    }
    
    // Extract category and number
    char category = '\0';
    std::string number;
    
    for (char c : upper) {
        if (c == 'H' || c == 'L' || c == 'C') {
            category = c;
        } else if (std::isdigit(c)) {
            number += c;
        }
    }
    
    if (category != '\0' && !number.empty()) {
        result = category;
        result += '-';
        result += number;
    }
    
    return result;
}

void Vocabulary::addToVocabulary(const Song& song) {
    allVocabulary.insert(song.code);
    
    switch (song.category) {
        case SongCategory::Hymn:
            hymnVocabulary.insert(song.code);
            break;
        case SongCategory::Lyric:
            lyricVocabulary.insert(song.code);
            break;
        case SongCategory::Convention:
            conventionVocabulary.insert(song.code);
            break;
        default:
            break;
    }
}

Vocabulary& getVocabulary() {
    if (!globalVocab) {
        globalVocab = std::make_unique<Vocabulary>();
    }
    return *globalVocab;
}

} // namespace ChoirBot
