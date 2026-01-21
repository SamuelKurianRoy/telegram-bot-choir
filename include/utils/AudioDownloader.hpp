#pragma once

#include <string>
#include <vector>
#include <memory>
#include <functional>

namespace ChoirBot {

/**
 * Audio download platform
 */
enum class DownloadPlatform {
    YouTube,
    Spotify,
    Unknown
};

/**
 * Audio quality
 */
enum class AudioQuality {
    High,      // 320 kbps
    Medium,    // 192 kbps
    Low,       // 128 kbps
    Ask
};

/**
 * Download result
 */
struct DownloadResult {
    bool success;
    std::string filePath;
    std::string error;
    std::string title;
    std::string artist;
    size_t fileSize;
};

/**
 * Download progress callback
 * Parameters: (downloaded bytes, total bytes, percentage)
 */
using ProgressCallback = std::function<void(size_t, size_t, double)>;

/**
 * Audio downloader
 * Supports YouTube and Spotify downloads
 */
class AudioDownloader {
public:
    AudioDownloader();
    ~AudioDownloader();
    
    // Detect platform from URL
    DownloadPlatform detectPlatform(const std::string& url) const;
    
    // Download audio
    DownloadResult download(const std::string& url,
                           AudioQuality quality = AudioQuality::High,
                           ProgressCallback callback = nullptr);
    
    // Download playlist
    std::vector<DownloadResult> downloadPlaylist(const std::string& url,
                                                AudioQuality quality = AudioQuality::High,
                                                ProgressCallback callback = nullptr);
    
    // Check if URL is playlist
    bool isPlaylist(const std::string& url) const;
    
    // Setup FFmpeg
    bool setupFFmpeg();
    
    // Cleanup temporary files
    void cleanup();
    
private:
    std::string tempDir;
    std::string ffmpegPath;
    
    // Platform-specific downloads
    DownloadResult downloadYouTube(const std::string& url, AudioQuality quality,
                                  ProgressCallback callback);
    DownloadResult downloadSpotify(const std::string& url, AudioQuality quality,
                                  ProgressCallback callback);
    
    // Convert quality enum to bitrate
    std::string qualityToBitrate(AudioQuality quality) const;
};

} // namespace ChoirBot
