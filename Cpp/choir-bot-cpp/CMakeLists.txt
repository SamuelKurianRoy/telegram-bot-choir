cmake_minimum_required(VERSION 3.15)
project(choir_bot VERSION 1.0.0 LANGUAGES CXX)

# C++20 standard
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Output directories
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)

# Find required packages
find_package(CURL REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(Threads REQUIRED)

# Include directories
include_directories(
    ${CMAKE_SOURCE_DIR}/include
    ${CURL_INCLUDE_DIRS}
    ${OPENSSL_INCLUDE_DIR}
)

# Fetch external dependencies
include(FetchContent)

# nlohmann/json
FetchContent_Declare(
    json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG v3.11.3
)

# TgBot-CPP
FetchContent_Declare(
    tgbot
    GIT_REPOSITORY https://github.com/reo7sp/tgbot-cpp.git
    GIT_TAG v1.7.2
)

# spdlog
FetchContent_Declare(
    spdlog
    GIT_REPOSITORY https://github.com/gabime/spdlog.git
    GIT_TAG v1.12.0
)

# CPR (C++ Requests)
FetchContent_Declare(
    cpr
    GIT_REPOSITORY https://github.com/libcpr/cpr.git
    GIT_TAG 1.10.5
)

# Make dependencies available
FetchContent_MakeAvailable(json tgbot spdlog cpr)

# Source files
set(SOURCES
    src/main.cpp
    src/Application.cpp
    src/models/Config.cpp
    src/models/Song.cpp
    src/models/User.cpp
    src/data/Database.cpp
    src/data/DriveService.cpp
    src/data/FeatureControl.cpp
    src/data/OrganistRoster.cpp
    src/data/UserDatabase.cpp
    src/data/Vocabulary.cpp
    src/handlers/BaseHandler.cpp
    src/handlers/CommandHandlers.cpp
    src/utils/AIAssistant.cpp
    src/utils/AudioDownloader.cpp
    src/utils/LockFile.cpp
    src/utils/Logger.cpp
    src/utils/Notation.cpp
    src/utils/Search.cpp
    src/utils/SongParser.cpp
)

# Create executable
add_executable(choir_bot ${SOURCES})

# Link libraries
target_link_libraries(choir_bot
    PRIVATE
    TgBot
    nlohmann_json::nlohmann_json
    spdlog::spdlog
    cpr::cpr
    ${CURL_LIBRARIES}
    ${OPENSSL_LIBRARIES}
    Threads::Threads
)

# Compiler warnings
if(MSVC)
    target_compile_options(choir_bot PRIVATE /W4)
else()
    target_compile_options(choir_bot PRIVATE -Wall -Wextra -Wpedantic)
endif()

# Installation
install(TARGETS choir_bot DESTINATION bin)
install(FILES ${CMAKE_SOURCE_DIR}/config.json.example DESTINATION share/choir_bot)

# Print build info
message(STATUS "Choir Bot Build Configuration:")
message(STATUS "  Version: ${PROJECT_VERSION}")
message(STATUS "  C++ Standard: C++${CMAKE_CXX_STANDARD}")
message(STATUS "  Build Type: ${CMAKE_BUILD_TYPE}")
message(STATUS "  Install Prefix: ${CMAKE_INSTALL_PREFIX}")
