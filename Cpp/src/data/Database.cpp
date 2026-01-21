#include "data/Database.hpp"
#include "data/DriveService.hpp"
#include "utils/Logger.hpp"
#include "models/Config.hpp"
#include <sstream>
#include <regex>
#include <iomanip>
#include <fstream>
#include <algorithm>

namespace ChoirBot {

// Helper function to parse CSV line
std::vector<std::string> parseCSVLine(const std::string& line) {
    std::vector<std::string> result;
    std::string field;
    bool inQuotes = false;
    
    for (size_t i = 0; i < line.size(); ++i) {
        char c = line[i];
        
        if (c == '"') {
            inQuotes = !inQuotes;
        } else if (c == ',' && !inQuotes) {
            result.push_back(field);
            field.clear();
        } else {
            field += c;
        }
    }
    result.push_back(field);
    
    // Trim whitespace from fields
    for (auto& f : result) {
        size_t start = f.find_first_not_of(" \t\r\n");
        size_t end = f.find_last_not_of(" \t\r\n");
        if (start != std::string::npos && end != std::string::npos) {
            f = f.substr(start, end - start + 1);
        } else {
            f.clear();
        }
    }
    
    return result;
}

// Helper function to parse CSV data
std::vector<std::vector<std::string>> parseCSV(const std::string& csvData) {
    std::vector<std::vector<std::string>> rows;
    std::istringstream stream(csvData);
    std::string line;
    
    while (std::getline(stream, line)) {
        if (!line.empty()) {
            rows.push_back(parseCSVLine(line));
        }
    }
    
    return rows;
}

// Helper to parse date from string (format: DD-MM-YYYY or similar)
std::optional<TimePoint> parseDate(const std::string& dateStr) {
    if (dateStr.empty() || dateStr == "nan" || dateStr == "NaN" || dateStr == "NaT") {
        return std::nullopt;
    }
    
    std::tm tm = {};
    std::istringstream ss(dateStr);
    
    // Try various date formats
    ss >> std::get_time(&tm, "%d-%m-%Y");
    if (ss.fail()) {
        ss.clear();
        ss.str(dateStr);
        ss >> std::get_time(&tm, "%Y-%m-%d");
    }
    if (ss.fail()) {
        ss.clear();
        ss.str(dateStr);
        ss >> std::get_time(&tm, "%m/%d/%Y");
    }
    
    if (!ss.fail()) {
        auto time = std::mktime(&tm);
        return std::chrono::system_clock::from_time_t(time);
    }
    
    return std::nullopt;
}

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
    // Sort dates for each song
    for (auto& [songCode, dates] : data->sungDates) {
        std::sort(dates.begin(), dates.end());
    }
}

void Database::cleanData() {
    // Remove duplicates and clean up data
    for (auto& [songCode, dates] : data->sungDates) {
        auto last = std::unique(dates.begin(), dates.end());
        dates.erase(last, dates.end());
    }
}

void Database::buildIndices() {
    // Build search indices
    data->songIndex.clear();
    
    for (const auto& song : data->hymns) {
        data->songIndex[song.code] = song;
    }
    for (const auto& song : data->lyrics) {
        data->songIndex[song.code] = song;
    }
    for (const auto& song : data->conventions) {
        data->songIndex[song.code] = song;
    }
    
    LOG_BOT_INFO("Built search index with {} songs", data->songIndex.size());
}

bool Database::loadHymnLyricConvention() {
    LOG_BOT_INFO("Loading HLC file (hlc_file_id)...");
    auto& config = Config::getInstance();
    auto& drive = getDriveService();
    
    // Load each sheet separately using Google Sheets API
    std::vector<std::pair<std::string, SongCategory>> sheets = {
        {"Hymn List", SongCategory::Hymn},
        {"Lyric List", SongCategory::Lyric},
        {"Convention List", SongCategory::Convention}
    };
    
    for (const auto& [sheetName, category] : sheets) {
        LOG_BOT_INFO("Loading sheet: {}", sheetName);
        std::string csvData = drive.getSheetData(config.driveFiles.hlcFileId, sheetName);
        if (csvData.empty()) {
            LOG_BOT_WARN("Failed to download sheet: {}", sheetName);
            continue;
        }
        
        auto rows = parseCSV(csvData);
        if (rows.size() < 2) continue; // Need at least header + 1 row
        
        // Skip header row, parse data rows
        for (size_t i = 1; i < rows.size(); ++i) {
            const auto& row = rows[i];
            if (row.empty()) continue;
            
            // Try to parse first column as number
            try {
                int number = static_cast<int>(std::stod(row[0]));
                if (number <= 0) continue;
                
                std::string title = row.size() > 1 ? row[1] : "";
                std::string firstLine = row.size() > 2 ? row[2] : "";
                
                Song song;
                song.number = number;
                song.index = title;
                song.firstLine = firstLine;
                song.category = category;
                
                if (category == SongCategory::Hymn) {
                    song.code = "H-" + std::to_string(number);
                    data->hymns.push_back(song);
                } else if (category == SongCategory::Lyric) {
                    song.code = "L-" + std::to_string(number);
                    data->lyrics.push_back(song);
                } else if (category == SongCategory::Convention) {
                    song.code = "C-" + std::to_string(number);
                    data->conventions.push_back(song);
                }
                
            } catch (...) {
                // Not a valid number, skip
                continue;
            }
        }
    }
    
    LOG_BOT_INFO("Loaded {} hymns, {} lyrics, {} conventions", 
                 data->hymns.size(), data->lyrics.size(), data->conventions.size());
    return true;
}

bool Database::loadMainDatabase() {
    LOG_BOT_INFO("Loading main database (main_file_id)...");
    auto& config = Config::getInstance();
    auto& drive = getDriveService();
    
    // The main_file_id is an Excel file - download as binary and parse
    LOG_BOT_INFO("Downloading Excel file as binary...");
    auto binaryData = drive.downloadBinaryFile(config.driveFiles.mainFileId);
    
    if (binaryData.empty()) {
        LOG_BOT_ERROR("Failed to download main database file");
        return false;
    }
    
    LOG_BOT_INFO("Downloaded {} bytes, parsing Excel file...", binaryData.size());
    
    // Save to temporary file for parsing
    std::string tempFile = "/tmp/choir_main_database.xlsx";
    std::ofstream out(tempFile, std::ios::binary);
    out.write(reinterpret_cast<const char*>(binaryData.data()), binaryData.size());
    out.close();
    
    LOG_BOT_INFO("Saved to temp file, attempting to parse with Python...");
    
    // Create a Python script to parse Excel
    std::string scriptPath = "/tmp/parse_excel.py";
    std::ofstream script(scriptPath);
    script << "import pandas as pd\n"
           << "import sys\n"
           << "try:\n"
           << "    for sheet in ['2023', '2024', '2025']:\n"
           << "        df = pd.read_excel('/tmp/choir_main_database.xlsx', sheet_name=sheet)\n"
           << "        df.to_csv(f'/tmp/choir_{sheet}.csv', index=False)\n"
           << "    print('SUCCESS')\n"
           << "except Exception as e:\n"
           << "    print(f'ERROR: {e}', file=sys.stderr)\n"
           << "    sys.exit(1)\n";
    script.close();
    
    // Use venv_linux Python if available, otherwise system python3
    std::string pythonCmd = "if [ -f /mnt/d/Choir/Telegram_Bot/venv_linux/bin/python3 ]; then /mnt/d/Choir/Telegram_Bot/venv_linux/bin/python3 /tmp/parse_excel.py 2>&1; else python3 /tmp/parse_excel.py 2>&1; fi";
    
    FILE* pipe = popen(pythonCmd.c_str(), "r");
    if (pipe) {
        char buffer[256];
        std::string result;
        while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
            result += buffer;
        }
        int exitCode = pclose(pipe);
        
        if (exitCode == 0 && result.find("SUCCESS") != std::string::npos) {
            LOG_BOT_INFO("Excel conversion successful, loading CSV data...");
            
            // Load each year's CSV
            std::vector<std::string> years = {"2023", "2024", "2025"};
            for (const auto& year : years) {
                std::string csvFile = "/tmp/choir_" + year + ".csv";
                std::ifstream file(csvFile);
                if (!file.is_open()) continue;
                
                std::string csvData((std::istreambuf_iterator<char>(file)),
                                   std::istreambuf_iterator<char>());
                file.close();
                
                auto rows = parseCSV(csvData);
                if (rows.size() < 2) continue;
                
                // Parse dates and songs
                for (size_t i = 1; i < rows.size(); ++i) {
                    const auto& row = rows[i];
                    if (row.empty()) continue;
                    
                    auto date = parseDate(row[0]);
                    if (!date) continue;
                    
                    // Process song columns (1-5)
                    for (size_t col = 1; col < std::min(row.size(), size_t(6)); ++col) {
                        std::string songCode = row[col];
                        if (songCode.empty() || songCode == "0" || songCode == "nan") continue;
                        
                        // Normalize song code
                        std::regex pattern("([HhLlCc])[-]?(\\d+)");
                        std::smatch match;
                        if (std::regex_search(songCode, match, pattern)) {
                            std::string prefix = match[1].str();
                            std::transform(prefix.begin(), prefix.end(), prefix.begin(), ::toupper);
                            std::string number = match[2].str();
                            std::string normalized = prefix + "-" + number;
                            data->sungDates[normalized].push_back(*date);
                        }
                    }
                }
                
                // Clean up temp file
                std::remove(csvFile.c_str());
            }
            
            LOG_BOT_INFO("Loaded sung dates for {} songs", data->sungDates.size());
        } else {
            LOG_BOT_ERROR("Excel conversion failed: {}", result);
            LOG_BOT_WARN("Install pandas: pip3 install pandas openpyxl");
            return false;
        }
    }
    
    // Clean up temp Excel file
    std::remove(tempFile.c_str());
    
    return true;
}

bool Database::loadTuneDatabase() {
    LOG_BOT_INFO("Loading tune database (tune_file_id)...");
    auto& config = Config::getInstance();
    auto& drive = getDriveService();
    
    // Load the Hymn sheet from tune database
    std::string csvData = drive.getSheetData(config.driveFiles.tuneFileId, "Hymn");
    if (csvData.empty()) {
        LOG_BOT_WARN("Failed to download tune database");
        return false;
    }
    
    auto rows = parseCSV(csvData);
    if (rows.size() < 2) return false;
    
    // Expected columns: Hymn no, Tune Index (or similar)
    // Skip header row
    for (size_t i = 1; i < rows.size(); ++i) {
        const auto& row = rows[i];
        if (row.size() < 2) continue;
        
        try {
            int number = static_cast<int>(std::stod(row[0]));
            std::string tuneName = row[1];
            
            if (number > 0 && !tuneName.empty()) {
                std::string songCode = "H-" + std::to_string(number);
                data->tunes[songCode] = tuneName;
            }
        } catch (...) {
            continue;
        }
    }
    
    LOG_BOT_INFO("Loaded {} tune mappings", data->tunes.size());
    return true;
}

Database::VocabularyData Database::getVocabulary() const {
    VocabularyData vocab;
    
    // Get all unique song codes that have been sung
    for (const auto& [songCode, dates] : data->sungDates) {
        if (dates.empty()) continue;
        
        // Parse the song code
        std::regex pattern("([HLC])-(\\d+)");
        std::smatch match;
        if (std::regex_match(songCode, match, pattern)) {
            char category = match[1].str()[0];
            int number = std::stoi(match[2].str());
            
            if (category == 'H') {
                vocab.hymnNumbers.push_back(number);
            } else if (category == 'L') {
                vocab.lyricNumbers.push_back(number);
            } else if (category == 'C') {
                vocab.conventionNumbers.push_back(number);
            }
        }
    }
    
    // Sort and remove duplicates
    auto sortAndUnique = [](std::vector<int>& vec) {
        std::sort(vec.begin(), vec.end());
        vec.erase(std::unique(vec.begin(), vec.end()), vec.end());
    };
    
    sortAndUnique(vocab.hymnNumbers);
    sortAndUnique(vocab.lyricNumbers);
    sortAndUnique(vocab.conventionNumbers);
    
    return vocab;
}

bool Database::isSongInVocabulary(const std::string& songCode) const {
    auto it = data->sungDates.find(songCode);
    return it != data->sungDates.end() && !it->second.empty();
}

Database& getDatabase() {
    if (!globalDatabase) {
        globalDatabase = std::make_unique<Database>();
        globalDatabase->loadAllDatasets();
    }
    return *globalDatabase;
}

} // namespace ChoirBot
