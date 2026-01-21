#include "data/DriveService.hpp"
#include "models/Config.hpp"
#include "utils/Logger.hpp"
#include <cpr/cpr.h>
#include <openssl/evp.h>
#include <openssl/pem.h>
#include <openssl/bio.h>
#include <openssl/buffer.h>
#include <openssl/rsa.h>
#include <openssl/err.h>
#include <chrono>
#include <sstream>
#include <iomanip>

namespace ChoirBot {

// Helper function to base64url encode
std::string base64UrlEncode(const std::string& input) {
    BIO* bio = BIO_new(BIO_s_mem());
    BIO* b64 = BIO_new(BIO_f_base64());
    BIO_set_flags(b64, BIO_FLAGS_BASE64_NO_NL);
    bio = BIO_push(b64, bio);
    
    BIO_write(bio, input.data(), input.size());
    BIO_flush(bio);
    
    BUF_MEM* bufferPtr;
    BIO_get_mem_ptr(bio, &bufferPtr);
    
    std::string result(bufferPtr->data, bufferPtr->length);
    BIO_free_all(bio);
    
    // Convert base64 to base64url
    for (auto& c : result) {
        if (c == '+') c = '-';
        else if (c == '/') c = '_';
    }
    // Remove padding
    result.erase(std::find(result.begin(), result.end(), '='), result.end());
    
    return result;
}

// Helper function to create JWT
std::string createJWT(const std::string& privateKey, const std::string& serviceAccountEmail) {
    // Create JWT header
    json header = {
        {"alg", "RS256"},
        {"typ", "JWT"}
    };
    
    // Create JWT claims
    auto now = std::chrono::system_clock::now();
    auto iat = std::chrono::duration_cast<std::chrono::seconds>(now.time_since_epoch()).count();
    auto exp = iat + 3600; // Token valid for 1 hour
    
    json claims = {
        {"iss", serviceAccountEmail},
        {"scope", "https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/spreadsheets"},
        {"aud", "https://oauth2.googleapis.com/token"},
        {"iat", iat},
        {"exp", exp}
    };
    
    // Encode header and claims
    std::string headerEncoded = base64UrlEncode(header.dump());
    std::string claimsEncoded = base64UrlEncode(claims.dump());
    std::string message = headerEncoded + "." + claimsEncoded;
    
    // Sign with private key
    BIO* bio = BIO_new_mem_buf(privateKey.data(), privateKey.size());
    EVP_PKEY* pkey = PEM_read_bio_PrivateKey(bio, nullptr, nullptr, nullptr);
    BIO_free(bio);
    
    if (!pkey) {
        LOG_BOT_ERROR("Failed to load private key");
        return "";
    }
    
    EVP_MD_CTX* mdctx = EVP_MD_CTX_new();
    EVP_DigestSignInit(mdctx, nullptr, EVP_sha256(), nullptr, pkey);
    EVP_DigestSignUpdate(mdctx, message.data(), message.size());
    
    size_t sigLen;
    EVP_DigestSignFinal(mdctx, nullptr, &sigLen);
    std::vector<unsigned char> signature(sigLen);
    EVP_DigestSignFinal(mdctx, signature.data(), &sigLen);
    
    EVP_MD_CTX_free(mdctx);
    EVP_PKEY_free(pkey);
    
    // Encode signature
    std::string signatureStr(signature.begin(), signature.end());
    std::string signatureEncoded = base64UrlEncode(signatureStr);
    
    return message + "." + signatureEncoded;
}

struct DriveService::Impl {
    std::string privateKey;
    std::string serviceAccountEmail;
};

static std::unique_ptr<DriveService> globalDriveService = nullptr;

DriveService::DriveService() 
    : pImpl(std::make_unique<Impl>()) {
}

DriveService::~DriveService() = default;

bool DriveService::initialize() {
    LOG_BOT_INFO("Initializing Google Drive service...");
    
    auto& config = Config::getInstance();
    pImpl->privateKey = config.serviceAccount.privateKey;
    pImpl->serviceAccountEmail = config.serviceAccount.clientEmail;
    
    if (pImpl->privateKey.empty() || pImpl->serviceAccountEmail.empty()) {
        LOG_BOT_ERROR("Service account credentials not configured");
        return false;
    }
    
    // Get initial access token
    if (!refreshAccessToken()) {
        LOG_BOT_ERROR("Failed to get initial access token");
        return false;
    }
    
    LOG_BOT_INFO("Google Drive service initialized successfully");
    return true;
}

bool DriveService::refreshAccessToken() {
    std::string jwt = createJWT(pImpl->privateKey, pImpl->serviceAccountEmail);
    if (jwt.empty()) {
        return false;
    }
    
    cpr::Response response = cpr::Post(
        cpr::Url{"https://oauth2.googleapis.com/token"},
        cpr::Payload{
            {"grant_type", "urn:ietf:params:oauth:grant-type:jwt-bearer"},
            {"assertion", jwt}
        }
    );
    
    if (response.status_code != 200) {
        LOG_BOT_ERROR("Failed to get access token: " + std::to_string(response.status_code));
        return false;
    }
    
    try {
        json tokenResponse = json::parse(response.text);
        accessToken = tokenResponse["access_token"];
        int expiresIn = tokenResponse.value("expires_in", 3600);
        tokenExpiry = std::chrono::system_clock::now() + std::chrono::seconds(expiresIn - 60);
        LOG_BOT_INFO("Access token refreshed successfully");
        return true;
    } catch (const std::exception& e) {
        LOG_BOT_ERROR("Failed to parse token response: " + std::string(e.what()));
        return false;
    }
}

std::string DriveService::getAccessToken() {
    // Check if token needs refresh
    if (std::chrono::system_clock::now() >= tokenExpiry) {
        if (!refreshAccessToken()) {
            return "";
        }
    }
    return accessToken;
}

std::string DriveService::downloadFile(const std::string& fileId) {
    std::string token = getAccessToken();
    if (token.empty()) {
        return "";
    }
    
    cpr::Response response = cpr::Get(
        cpr::Url{"https://www.googleapis.com/drive/v3/files/" + fileId + "?alt=media"},
        cpr::Header{{"Authorization", "Bearer " + token}},
        cpr::Timeout{30000}
    );
    
    if (response.status_code == 200) {
        return response.text;
    }
    
    LOG_BOT_ERROR("Failed to download file " + fileId + ": " + std::to_string(response.status_code));
    return "";
}

std::vector<uint8_t> DriveService::downloadBinaryFile(const std::string& fileId) {
    std::string token = getAccessToken();
    if (token.empty()) {
        return {};
    }
    
    cpr::Response response = cpr::Get(
        cpr::Url{"https://www.googleapis.com/drive/v3/files/" + fileId + "?alt=media"},
        cpr::Header{{"Authorization", "Bearer " + token}}
    );
    
    if (response.status_code == 200) {
        return std::vector<uint8_t>(response.text.begin(), response.text.end());
    }
    
    return {};
}

std::string DriveService::exportAsExcel(const std::string& fileId) {
    std::string token = getAccessToken();
    if (token.empty()) {
        return "";
    }
    
    // Export Google Sheet as CSV (gets first sheet only)
    cpr::Response response = cpr::Get(
        cpr::Url{"https://www.googleapis.com/drive/v3/files/" + fileId + "/export?mimeType=text/csv"},
        cpr::Header{{"Authorization", "Bearer " + token}},
        cpr::Timeout{30000}
    );
    
    if (response.status_code == 200) {
        return response.text;
    }
    
    LOG_BOT_ERROR("Failed to export file " + fileId + ": " + std::to_string(response.status_code));
    return "";
}

// Helper to URL encode
static std::string urlEncode(const std::string& str) {
    std::string encoded;
    for (char c : str) {
        if (std::isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') {
            encoded += c;
        } else if (c == ' ') {
            encoded += "%20";
        } else {
            char hex[4];
            snprintf(hex, sizeof(hex), "%%%02X", static_cast<unsigned char>(c));
            encoded += hex;
        }
    }
    return encoded;
}

// Get specific sheet from Google Sheets as CSV
std::string DriveService::getSheetData(const std::string& spreadsheetId, const std::string& sheetName) {
    std::string token = getAccessToken();
    if (token.empty()) {
        return "";
    }
    
    // Use Google Sheets API to get specific sheet data
    std::string encodedSheetName = urlEncode(sheetName);
    std::string url = "https://sheets.googleapis.com/v4/spreadsheets/" + spreadsheetId + 
                      "/values/" + encodedSheetName + "?valueRenderOption=UNFORMATTED_VALUE";
    
    cpr::Response response = cpr::Get(
        cpr::Url{url},
        cpr::Header{{"Authorization", "Bearer " + token}},
        cpr::Timeout{30000}  // 30 second timeout
    );
    
    if (response.status_code == 200) {
        // Convert JSON response to CSV format
        try {
            json data = json::parse(response.text);
            if (!data.contains("values")) {
                return "";
            }
            
            std::string csv;
            for (const auto& row : data["values"]) {
                bool first = true;
                for (const auto& cell : row) {
                    if (!first) csv += ",";
                    first = false;
                    
                    // Handle different types
                    if (cell.is_string()) {
                        std::string val = cell.get<std::string>();
                        // Escape quotes and wrap in quotes if contains comma/newline
                        if (val.find(',') != std::string::npos || 
                            val.find('\n') != std::string::npos ||
                            val.find('"') != std::string::npos) {
                            // Escape quotes
                            size_t pos = 0;
                            while ((pos = val.find('"', pos)) != std::string::npos) {
                                val.replace(pos, 1, "\"\"");
                                pos += 2;
                            }
                            csv += "\"" + val + "\"";
                        } else {
                            csv += val;
                        }
                    } else if (cell.is_number()) {
                        csv += std::to_string(cell.get<double>());
                    } else if (cell.is_null()) {
                        // Empty cell
                    }
                }
                csv += "\n";
            }
            return csv;
        } catch (const std::exception& e) {
            LOG_BOT_ERROR("Failed to parse Sheets API response: " + std::string(e.what()));
            return "";
        }
    }
    
    if (response.status_code == 0) {
        LOG_BOT_ERROR("Network timeout getting sheet '{}' (check internet connection)", sheetName);
    } else {
        LOG_BOT_ERROR("Failed to get sheet '{}': HTTP {}", sheetName, response.status_code);
    }
    return "";
}

bool DriveService::uploadFile(const std::string& fileId, const std::string& content) {
    std::string token = getAccessToken();
    if (token.empty()) {
        return false;
    }
    
    cpr::Response response = cpr::Patch(
        cpr::Url{"https://www.googleapis.com/upload/drive/v3/files/" + fileId},
        cpr::Header{{"Authorization", "Bearer " + token}},
        cpr::Body{content}
    );
    
    return response.status_code == 200;
}

bool DriveService::uploadBinaryFile(const std::string& fileId, const std::vector<uint8_t>& data) {
    std::string token = getAccessToken();
    if (token.empty()) {
        return false;
    }
    
    std::string content(data.begin(), data.end());
    cpr::Response response = cpr::Patch(
        cpr::Url{"https://www.googleapis.com/upload/drive/v3/files/" + fileId},
        cpr::Header{{"Authorization", "Bearer " + token}},
        cpr::Body{content}
    );
    
    return response.status_code == 200;
}

std::string DriveService::exportAsText(const std::string& fileId) {
    return exportAsExcel(fileId);
}

std::vector<std::string> DriveService::listFiles(const std::string& folderId) {
    std::string token = getAccessToken();
    if (token.empty()) {
        return {};
    }
    
    cpr::Response response = cpr::Get(
        cpr::Url{"https://www.googleapis.com/drive/v3/files?q='" + folderId + "'+in+parents"},
        cpr::Header{{"Authorization", "Bearer " + token}}
    );
    
    std::vector<std::string> fileIds;
    if (response.status_code == 200) {
        try {
            json filesResponse = json::parse(response.text);
            for (const auto& file : filesResponse["files"]) {
                fileIds.push_back(file["id"]);
            }
        } catch (const std::exception& e) {
            LOG_BOT_ERROR("Failed to parse file list: " + std::string(e.what()));
        }
    }
    
    return fileIds;
}

bool DriveService::appendToDocument(const std::string& docId, const std::string& text) {
    // For now, just log - would need Google Docs API
    (void)docId;
    (void)text;
    LOG_BOT_WARN("appendToDocument not yet implemented");
    return false;
}

DriveService& getDriveService() {
    if (!globalDriveService) {
        globalDriveService = std::make_unique<DriveService>();
        globalDriveService->initialize();
    }
    return *globalDriveService;
}

} // namespace ChoirBot
