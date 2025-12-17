# 🐱 OtakuNeko - Your Personal Anime AI Assistant

OtakuNeko is an intelligent, conversational AI assistant designed for anime enthusiasts. It connects to your Bangumi account to understand your viewing history and preferences, offering personalized recommendations, in-depth analysis of your viewing habits, and much more.

![Demo Screenshot](https://your-image-host.com/demo.png) <!-- It's highly recommended to add a screenshot of your app here -->

## ✨ Features

*   **Conversational AI Chat**: Engage in natural conversations about anime. The AI has access to your watch list for context-aware responses.
*   **Personalized Recommendations**: Get anime recommendations based on your tastes, specified genres, or mood. The agent can suggest new shows or remind you of items in your backlog.
*   **Anime Profile Generation**: Generate a detailed "二次元成分鉴定" (Anime DNA Analysis) report, complete with shareable summary images.
*   **Annual Viewing Reports**: Create a beautiful, shareable summary of your anime viewing history for the past year.
*   **Bangumi Integration**: Seamlessly syncs your anime collection from Bangumi (bgm.tv) to keep your data up-to-date.
*   **Multi-Provider AI Support**: Supports both the default DeepSeek AI and any custom OpenAI-compatible API endpoint (like OpenAI, Moonshot, Groq, etc.).
*   **Enhanced Reliability**: Implements circuit breaker pattern to prevent cascading failures when external services are unavailable.
*   **Improved Performance**: Utilizes caching mechanisms to reduce redundant computations and network requests.
*   **Robust Error Handling**: Gracefully handles network issues and API failures with clear user feedback.

## 🚀 Getting Started

Follow these steps to get OtakuNeko running on your local machine.

### Prerequisites

*   Python 3.8+
*   An API Key from an AI provider (e.g., [DeepSeek](https://platform.deepseek.com/), [OpenAI](https://platform.openai.com/))
*   Your Bangumi username and access token

### Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/ShowayLiao/OtakuNeko.git
    cd OtakuNeko
    ```

2.  **Set up your environment variables:**
    *   Rename the `.env.example` file to `.env`.
    *   Open the `.env` file and fill in your API keys and Bangumi credentials.

    ```bash
    # Example .env file for DeepSeek (default)
    DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxx"
    BGM_USERNAME="YourBangumiUsername"
    BGM_ACCESS_TOKEN="YourBangumiAccessToken"
    
    # Example .env file for OpenAI (alternative)
    CUSTOM_API_KEY="sk-xxxxxxxxxxxxxxxx"
    CUSTOM_API_BASE_URL="https://api.openai.com/v1"
    CUSTOM_MODEL_CHAT="gpt-3.5-turbo"
    CUSTOM_MODEL_REASONER="gpt-4-turbo"
    BGM_USERNAME="YourBangumiUsername"
    BGM_ACCESS_TOKEN="YourBangumiAccessToken"
    ```

3.  **Run the setup script:**
    This script will create a Python virtual environment and install all the necessary dependencies.

    *   **On macOS / Linux:**
        ```bash
        chmod +x Setup.sh
        ./Setup.sh
        ```
    *   **On Windows:**
        ```bat
        Setup.bat
        ```

### Running the Application

Once the setup is complete, you can start the application.

*   **On macOS / Linux:**
    ```bash
    ./Run.sh
    ```
*   **On Windows:**
    ```bat
    Run.bat
    ```

The application will open in your web browser at `http://localhost:8501`.

### First Steps

1.  **Configure AI Provider**: On first run, select your preferred AI provider from the dropdown in the sidebar.
2.  **Sync Your Data**: In the sidebar, click the **"🔄 一键全量更新"** button to fetch your anime collection from Bangumi. This is a required first step.
3.  **Start Chatting**: Use the chat input to ask for recommendations, generate your profile, or simply chat about anime!

## 🛠️ Advanced Configuration

### Multiple AI Providers

OtakuNeko supports multiple AI providers simultaneously. You can configure both DeepSeek and a custom provider, then switch between them at runtime using the provider selector in the sidebar.

### Circuit Breaker Settings

The application implements a circuit breaker pattern to handle network failures gracefully. If the Bangumi API becomes unavailable, the circuit breaker will temporarily stop making requests and display clear error messages to users.

### Caching

The application uses caching to improve performance:
- Dataset caching (5-minute TTL)
- Memory caching for user data
- Search result caching for vector operations

## 📚 Documentation

For detailed information about the improvements and changes made to OtakuNeko, please refer to the following documentation files:
- [Key Improvements Summary](../IMPROVEMENTS_SUMMARY.md)
- [Change Log](../CHANGELOG.md)
- [Circuit Breaker Implementation](../CIRCUIT_BREAKER_DOCS.md)
- [Multi-Provider AI Support](../MULTI_PROVIDER_AI.md)
- [Deployment Guide](../DEPLOYMENT_GUIDE.md)

## 🤝 Contributing

Pull Requests are welcome! For major changes, please open an issue first to discuss what you would like to change. Please make sure to update tests as appropriate.

## 📄 License

MIT