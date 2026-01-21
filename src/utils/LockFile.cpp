#include "utils/LockFile.hpp"
#include <fstream>
#include <unistd.h>
#include <sys/stat.h>
#include <csignal>

namespace ChoirBot {

LockFile::LockFile(const std::string& lockFilePath)
    : lockPath(lockFilePath)
    , stopSignalPath("/tmp/telegram_bot_stop_signal")
    , locked(false) {
}

LockFile::~LockFile() {
    release();
}

bool LockFile::acquire() {
    // Check if lock file exists
    if (std::ifstream(lockPath)) {
        // Check if it's stale
        if (isStale()) {
            removeLockFile();
        } else {
            return false;  // Another instance is running
        }
    }
    
    return createLockFile();
}

void LockFile::release() {
    if (locked) {
        removeLockFile();
        locked = false;
    }
}

bool LockFile::isLocked() const {
    return locked;
}

int LockFile::getLockedPID() const {
    std::ifstream file(lockPath);
    if (file) {
        int pid;
        file >> pid;
        return pid;
    }
    return -1;
}

bool LockFile::checkStopSignal() {
    struct stat buffer;
    return (stat("/tmp/telegram_bot_stop_signal", &buffer) == 0);
}

void LockFile::createStopSignal() {
    std::ofstream file("/tmp/telegram_bot_stop_signal");
    file << std::time(nullptr);
}

void LockFile::removeStopSignal() {
    std::remove("/tmp/telegram_bot_stop_signal");
}

bool LockFile::createLockFile() {
    std::ofstream file(lockPath);
    if (file) {
        file << getpid();
        locked = true;
        return true;
    }
    return false;
}

bool LockFile::removeLockFile() {
    return std::remove(lockPath.c_str()) == 0;
}

bool LockFile::isStale() const {
    int pid = getLockedPID();
    if (pid <= 0) return true;
    
    // Check if process exists
    return (kill(pid, 0) != 0);
}

} // namespace ChoirBot
