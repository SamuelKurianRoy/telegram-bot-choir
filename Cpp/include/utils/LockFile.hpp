#pragma once

#include <string>
#include <chrono>
#include <atomic>

namespace ChoirBot {

/**
 * Process locking mechanism
 * Prevents multiple bot instances from running
 */
class LockFile {
public:
    LockFile(const std::string& lockFilePath = "/tmp/telegram_bot.lock");
    ~LockFile();
    
    // Acquire lock
    bool acquire();
    
    // Release lock
    void release();
    
    // Check if locked
    bool isLocked() const;
    
    // Get PID of locking process
    int getLockedPID() const;
    
    // Check stop signal
    static bool checkStopSignal();
    static void createStopSignal();
    static void removeStopSignal();
    
private:
    std::string lockPath;
    std::string stopSignalPath;
    bool locked;
    
    bool createLockFile();
    bool removeLockFile();
    bool isStale() const;
};

} // namespace ChoirBot
