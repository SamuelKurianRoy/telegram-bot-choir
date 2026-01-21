#pragma once

#include <string>
#include <vector>
#include <memory>
#include <nlohmann/json.hpp>

namespace ChoirBot {

using json = nlohmann::json;

/**
 * Google Drive Service for API interactions
 * Handles authentication and file operations
 */
class DriveService {
public:
    DriveService();
    ~DriveService();
    
    // Initialize with service account credentials
    bool initialize();
    
    // File operations
    std::string downloadFile(const std::string& fileId);
    std::vector<uint8_t> downloadBinaryFile(const std::string& fileId);
    bool uploadFile(const std::string& fileId, const std::string& content);
    bool uploadBinaryFile(const std::string& fileId, const std::vector<uint8_t>& data);
    
    // Export operations (for Google Sheets/Docs)
    std::string exportAsExcel(const std::string& fileId);
    std::string exportAsText(const std::string& fileId);
    
    // Folder operations
    std::vector<std::string> listFiles(const std::string& folderId);
    
    // Document operations
    bool appendToDocument(const std::string& docId, const std::string& text);
    
    // Authentication
    std::string getAccessToken();
    
private:
    struct Impl;
    std::unique_ptr<Impl> pImpl;
    
    std::string accessToken;
    std::chrono::system_clock::time_point tokenExpiry;
    
    bool refreshAccessToken();
    std::string createJWT();
    std::string makeRequest(const std::string& url, const std::string& method, 
                           const std::string& body = "");
};

/**
 * Get global Drive service instance
 */
DriveService& getDriveService();

} // namespace ChoirBot
