#include "utils/AudioDownloader.hpp"
#include "utils/Logger.hpp"
#include <filesystem>

namespace ChoirBot {

DownloadResult AudioDownloader::download(const std::string& url,
                                          AudioQuality quality,
                                          ProgressCallback callback) {
    (void)url; (void)quality; (void)callback;
    return {false, "", "Stub implementation", "", "", 0};
}

std::vector<DownloadResult> AudioDownloader::downloadPlaylist(const std::string& url,
                                                                AudioQuality quality,
                                                                ProgressCallback callback) {
    (void)url; (void)quality; (void)callback;
    return {};
}

DownloadResult AudioDownloader::downloadYouTube(const std::string& url,
                                                  AudioQuality quality,
                                                  ProgressCallback callback) {
    (void)url; (void)quality; (void)callback;
    return {false, "", "Stub implementation", "", "", 0};
}

DownloadResult AudioDownloader::downloadSpotify(const std::string& url,
                                                  AudioQuality quality,
                                                  ProgressCallback callback) {
    (void)url; (void)quality; (void)callback;
    return {false, "", "Stub implementation", "", "", 0};
}

} // namespace ChoirBot
