# parlant-pipecat

**Build intelligent voice agents on [Parlant](https://github.com/emcie-co/parlant) using [Pipecat](https://github.com/pipecat-ai/pipecat)**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

Parlant-Pipecat is a seamless integration that combines Parlant's powerful conversational AI capabilities with Pipecat's flexible voice pipeline framework. Build production-ready voice agents with natural conversations, advanced turn-taking, and enterprise-grade reliability.

---

## ✨ Key Features

- **Drop-in Replacement**: `ParlantService` replaces any LLM service in your Pipecat pipeline - no context aggregator needed
- **Natural Conversations**: Leverage Parlant's stateful conversation management for coherent, context-aware interactions
- **Typing Indicators & Filler Phrases**: Keep conversations engaging with audio feedback during processing
- **Production Ready**: Built on enterprise-tested components with full async support

---

## 🚀 Quick Start

### Prerequisites

Ensure you have a **Parlant server running** on `http://localhost:8800` (or configure a custom URL). Visit the [Parlant documentation](https://parlant.io) to get started with Parlant.

### Installation

**For production use:**

```bash
pip install parlant-pipecat
```

**For development or running examples:**

1. **Clone this repository**:

   ```bash
   git clone https://github.com/emcie-co/parlant-pipecat.git
   cd parlant-pipecat
   ```

2. **Install with Poetry**:

   ```bash
   poetry install
   ```

3. **Set up environment variables**:
   Create a `.env` file with your service credentials:
   ```bash
   CARTESIA_API_KEY=your_cartesia_api_key
   # Add other service keys as needed
   ```

### Running the Example

Run the live agent example with office ambience:

```bash
poetry run python examples/live_agent_with_office_ambience.py
```

This example demonstrates a fully-featured voice agent with:

- Real-time speech-to-text (Cartesia STT)
- Parlant conversational AI
- Text-to-speech output (Cartesia TTS)
- Background office ambience mixing
- Smart turn detection and VAD

> **💡 Pro Tip**: Configure your Parlant agent with `VoiceOptimizedPerceivedPerformancePolicy` for the best voice experience. This policy optimizes response timing and reduces perceived latency in voice conversations.

---

## 🏗️ Integration Guide

### Basic Pipeline Setup

`ParlantService` integrates seamlessly into your Pipecat pipeline. Here's the basic structure:

```python
from parlant.contrib.pipecat import ParlantService
from pipecat.pipeline.pipeline import Pipeline

# Initialize Parlant service
parlant = ParlantService()

# Build your pipeline
pipeline = Pipeline([
    transport.input(),
    rtvi,
    stt,                  # Your STT service
    parlant,              # Replaces LLM service - no context aggregator needed!
    tts,                  # Your TTS service
    transport.output(),
])
```

**Key Differences from Standard LLM Pipelines**:

-  `ParlantService` goes where you'd typically use an `LLMService`
-  **No context aggregator required** - Parlant manages conversation state internally
-  Works with any Pipecat-compatible STT/TTS services

### Full Example

See [`examples/live_agent_with_office_ambience.py`](examples/live_agent_with_office_ambience.py) for a complete implementation including:

- WebRTC transport configuration
- VAD (Voice Activity Detection) setup
- Turn analyzer integration
- Audio mixing for background ambience
- RTVI processor integration

---

## ⚙️ Configuration

### `ParlantService` Parameters

#### `parlant_config: ParlantConfig`

Configure connection to your Parlant server:

```python
from parlant.contrib.pipecat import ParlantConfig, ParlantService

config = ParlantConfig(
    agent_id="your-agent-id",           # Optional: ID of Parlant agent (defaults to first agent)
    customer_id_provider=async_fn,      # Optional: Async function returning customer ID
    url="http://localhost:8800",        # Parlant server URL
    client=custom_client,               # Optional: Pre-configured AsyncParlantClient
)

parlant = ParlantService(parlant_config=config)
```

**`ParlantConfig` Fields**:

- **`agent_id`** (`str | None`): The ID of the Parlant agent to use. If not provided, defaults to the first available agent.
- **`customer_id_provider`** (`Callable[[], Awaitable[str | None]] | None`): Async function that returns the customer ID for session tracking. If not provided, uses Parlant's guest customer.
- **`url`** (`str`): Base URL of your Parlant server. Default: `"http://localhost:8800"`
- **`client`** (`AsyncParlantClient | None`): Pre-configured Parlant client. If provided, `url` is ignored.

#### `agent_greeting: str | None`

Initial message the agent speaks when a session starts:

```python
parlant = ParlantService(
    agent_greeting="Hello! I'm here to help. What can I do for you?"
)
```

Set to `None` to disable the greeting. Default: `"Hi, I'm an AI assistant. Please bear with me as I may take a few seconds to process your speech. How can I help you today?"`

#### `filler_phrase_provider: Callable`

Customize what the agent says during longer processing delays:

```python
async def custom_filler_provider(
    params: FillerPhraseProviderParams
) -> str:
    return "Thinking about that..."

parlant = ParlantService(
    filler_phrase_provider=custom_filler_provider
)
```

The provider receives `FillerPhraseProviderParams` with context about the session, agent, customer, and recent messages. Return `None` to skip filler phrases.

Default phrases include: _"Just a sec."_, _"One moment please."_, etc.

#### `typing_track_config: TypingTrackConfig`

Configure typing sound effects played during processing:

```python
from parlant.contrib.pipecat import TypingTrackConfig

typing_config = TypingTrackConfig(
    use_typing_track=True,                      # Enable/disable typing sounds
    typing_track_filename="/path/to/sound.wav", # Custom sound file (mono WAV)
    typing_track_sample_rate=16000,             # Sample rate in Hz
)

parlant = ParlantService(typing_track_config=typing_config)
```

**`TypingTrackConfig` Fields**:

- **`use_typing_track`** (`bool`): Enable typing sound effects. Default: `True`
- **`typing_track_filename`** (`str`): Path to typing sound WAV file (must be mono/1-channel). Default: included `typing.wav`
- **`typing_track_sample_rate`** (`int`): Sample rate of the typing track. Default: `16000`

---

## 🤝 Contributing

We welcome contributions! Whether it's:

- 🐛 Bug reports and fixes
- 💡 Feature requests and implementations
- 📚 Documentation improvements
- 🧪 Test coverage enhancements
- 💬 Examples and use cases

**Getting Started**:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Please ensure your code follows the existing style and includes appropriate tests.

---

## 📄 License

This project is licensed under the **Apache License 2.0** - see the [LICENSE](LICENSE) file for details.

---

## 🔗 Links

- **Parlant**: [github.com/emcie-co/parlant](https://github.com/emcie-co/parlant)
- **Pipecat**: [github.com/pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat)
- **Documentation**: [parlant.io](https://parlant.io)

---

**Built with ❤️ by the Parlant team**
