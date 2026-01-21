#include "data/Database.hpp"
#include "data/DriveService.hpp"
#include "utils/Logger.hpp"

namespace ChoirBot {

static std::unique_ptr<Database> globalDatabase = nullptr;

Database::Database() 
    : data(std::make_unique<DataFrames>()) {
}

Database::~Database() = default;

bool Database::loadAllDatasets() {
    LOG_BOT_INFO("Loading all datasets from Google Drive...");
    
    if (!loadHymnLyricConvention()) {
        LOG_BOT_ERROR("Failed to load HLC file");
        return false;
    }
    
    if (!loadMainDatabase()) {
        LOG_BOT_ERROR("Failed to load main database");
        return false;
    }
    
    if (!loadTuneDatabase()) {
        LOG_BOT_ERROR("Failed to load tune database");
        return false;
    }
    
    preprocessYearData();
    cleanData();
    buildIndices();
    
    LOG_BOT_INFO("All datasets loaded successfully");
    LOG_BOT_INFO("  Hymns: {}", data->hymns.size());
    LOG_BOT_INFO("  Lyrics: {}", data->lyrics.size());
    LOG_BOT_INFO("  Conventions: {}", data->conventions.size());
    
    return true;
}

bool Database::reloadAllDatasets() {
    LOG_BOT_INFO("Reloading all datasets...");
    data = std::make_unique<DataFrames>();
    return loadAllDatasets();
}

std::optional<Song> Database::getSong(const std::string& songCode) {
    Song temp(songCode);
    
    const auto* list = &data->hymns;
    if (temp.category == SongCategory::Lyric) list = &data->lyrics;
    else if (temp.category == SongCategory::Convention) list = &data->conventions;
    
    auto it = std::find_if(list->begin(), list->end(), 
        [&temp](const Song& s) { return s.code == temp.code; });
    
    if (it != list->end()) {
        return *it;
    }
    return std::nullopt;
}

std::vector<Song> Database::getSongsByCategory(SongCategory category) {
    switch (category) {
        case SongCategory::Hymn: return data->hymns;
        case SongCategory::Lyric: return data->lyrics;
        case SongCategory::Convention: return data->conventions;
        default: return {};
    }
}

std::vector<Song> Database::getAllSongs() {
    std::vector<Song> all;
    all.insert(all.end(), data->hymns.begin(), data->hymns.end());
    all.insert(all.end(), data->lyrics.begin(), data->lyrics.end());
    all.insert(all.end(), data->conventions.begin(), data->conventions.end());
    return all;
}

std::optional<TimePoint> Database::getLastSungDate(const std::string& songCode) {
    auto it = data->sungDates.find(songCode);
    if (it != data->sungDates.end() && !it->second.empty()) {
        return *std::max_element(it->second.begin(), it->second.end());
    }
    return std::nullopt;
}

std::vector<TimePoint> Database::getAllDates(const std::string& songCode) {
    auto it = data->sungDates.find(songCode);
    if (it != data->sungDates.end()) {
        auto dates = it->second;
        std::sort(dates.rbegin(), dates.rend());  // Descending order
        return dates;
    }
    return {};
}

std::vector<Song> Database::getSongsByDate(const TimePoint& date) {
    // TODO: Implement date-based song query
    (void)date;  // Unused until implemented
    return {};
}

std::string Database::getTuneName(const std::string& songCode) {
    auto it = data->tunes.find(songCode);
    return (it != data->tunes.end()) ? it->second : "Unknown";
}

std::vector<Song> Database::getSongsByTune(const std::string& tuneName) {
    std::vector<Song> result;
    for (const auto& [code, tune] : data->tunes) {
        if (tune == tuneName) {
            if (auto song = getSong(code)) {
                result.push_back(*song);
            }
        }
    }
    return result;
}

std::optional<Song> Database::findByIndex(const std::string& index, SongCategory category) {
    // TODO: Implement index-based search
    (void)index;     // Unused until implemented
    (void)category;  // Unused until implemented
    return std::nullopt;
}

std::optional<Song> Database::findByNumber(int number, SongCategory category) {
    const auto* list = &data->hymns;
    if (category == SongCategory::Lyric) list = &data->lyrics;
    else if (category == SongCategory::Convention) list = &data->conventions;
    
    auto it = std::find_if(list->begin(), list->end(),
        [number](const Song& s) { return s.number == number; });
    
    if (it != list->end()) {
        return *it;
    }
    return std::nullopt;
}

size_t Database::getSongCount() const {
    return data->hymns.size() + data->lyrics.size() + data->conventions.size();
}

size_t Database::getSongCountByCategory(SongCategory category) const {
    switch (category) {
        case SongCategory::Hymn: return data->hymns.size();
        case SongCategory::Lyric: return data->lyrics.size();
        case SongCategory::Convention: return data->conventions.size();
        default: return 0;
    }
}

void Database::preprocessYearData() {
    // TODO: Implement year data preprocessing
}

void Database::cleanData() {
    // TODO: Implement data cleaning
}

void Database::buildIndices() {
    // TODO: Build search indices
}

bool Database::loadHymnLyricConvention() {
    // TODO: Load from Google Drive
    return true;
}

bool Database::loadMainDatabase() {
    // TODO: Load from Google Drive
    return true;
}

bool Database::loadTuneDatabase() {
    // TODO: Load from Google Drive
    return true;
}

Database& getDatabase() {
    if (!globalDatabase) {
        globalDatabase = std::make_unique<Database>();
        globalDatabase->loadAllDatasets();
    }
    return *globalDatabase;
}

} // namespace ChoirBot
