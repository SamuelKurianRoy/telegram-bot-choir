#include "utils/AIAssistant.hpp"
#include "models/Config.hpp"
#include "utils/Logger.hpp"

namespace ChoirBot {

AIAssistant::AIAssistant()
    : preferredProvider(Provider::Gemini)
    , geminiInitialized(false)
    , groqInitialized(false) {
}

AIAssistant::~AIAssistant() = default;

bool AIAssistant::initializeGemini() {
    auto& config = Config::getInstance();
    geminiApiKey = config.geminiApiKey;
    geminiInitialized = !geminiApiKey.empty();
    return geminiInitialized;
}

bool AIAssistant::initializeGroq() {
    auto& config = Config::getInstance();
    groqApiKey = config.groqApiKey;
    groqInitialized = !groqApiKey.empty();
    return groqInitialized;
}

Intent AIAssistant::parseUserIntent(const std::string& userMessage) {
    if (preferredProvider == Provider::Gemini && geminiInitialized) {
        return callGemini(userMessage);
    } else if (preferredProvider == Provider::Groq && groqInitialized) {
        return callGroq(userMessage);
    } else if (geminiInitialized) {
        return callGemini(userMessage);
    } else if (groqInitialized) {
        return callGroq(userMessage);
    }
    return Intent{"", {}, "AI not initialized", 0.0};
}

bool AIAssistant::shouldUseAI(const std::string& message) const {
    if (message.empty() || message[0] == '/') return false;
    if (message.length() < 10) return false;
    return true;
}

void AIAssistant::setPreferredProvider(Provider provider) {
    preferredProvider = provider;
}

std::string AIAssistant::testModel(const std::string& testMessage) {
    auto intent = parseUserIntent(testMessage);
    return "Command: " + intent.command + ", Confidence: " + std::to_string(intent.confidence);
}

Intent AIAssistant::callGemini(const std::string& userMessage) {
    (void)userMessage;
    return Intent{"search", {}, "Stub", 0.5};
}

Intent AIAssistant::callGroq(const std::string& userMessage) {
    (void)userMessage;
    return Intent{"search", {}, "Stub", 0.5};
}

std::string AIAssistant::generatePrompt(const std::string& userMessage) const {
    return "Parse: " + userMessage;
}

Intent AIAssistant::parseResponse(const std::string& response) {
    (void)response;
    return Intent{"unknown", {}, "", 0.0};
}

Intent AIAssistant::parseJsonResponse(const json& j) {
    (void)j;
    return Intent{"unknown", {}, "", 0.0};
}

AIAssistant& getAIAssistant() {
    static AIAssistant globalAIAssistant;
    return globalAIAssistant;
}

} // namespace ChoirBot
