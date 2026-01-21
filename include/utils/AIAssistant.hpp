#pragma once

#include <string>
#include <optional>
#include <nlohmann/json.hpp>

namespace ChoirBot {

using json = nlohmann::json;

/**
 * AI intent parsing result
 */
struct Intent {
    std::string command;           // Extracted command (e.g., "date", "search")
    json parameters;               // Extracted parameters
    std::string responseText;      // Optional conversational response
    double confidence;             // 0.0 to 1.0
    
    bool isValid() const { return confidence > 0.7; }
};

/**
 * AI Assistant for natural language processing
 * Uses Google Gemini or Groq as fallback
 */
class AIAssistant {
public:
    enum class Provider {
        Gemini,
        Groq,
        Both
    };
    
    AIAssistant();
    ~AIAssistant();
    
    // Initialize AI providers
    bool initializeGemini();
    bool initializeGroq();
    
    // Parse user intent from natural language
    Intent parseUserIntent(const std::string& userMessage);
    
    // Check if message should use AI
    bool shouldUseAI(const std::string& message) const;
    
    // Provider management
    void setPreferredProvider(Provider provider);
    Provider getPreferredProvider() const { return preferredProvider; }
    
    // Test AI model
    std::string testModel(const std::string& testMessage);
    
private:
    Provider preferredProvider;
    bool geminiInitialized;
    bool groqInitialized;
    
    std::string geminiApiKey;
    std::string groqApiKey;
    
    // API calls
    Intent callGemini(const std::string& userMessage);
    Intent callGroq(const std::string& userMessage);
    
    // Prompt generation
    std::string generatePrompt(const std::string& userMessage) const;
    
    // Response parsing
    Intent parseResponse(const std::string& response);
    Intent parseJsonResponse(const json& j);
};

/**
 * Get global AI assistant instance
 */
AIAssistant& getAIAssistant();

} // namespace ChoirBot
