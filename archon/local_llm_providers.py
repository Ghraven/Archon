from enum import Enum

class LocalLLMProvider(Enum):
    OLLAMA = "Ollama"
    LMSTUDIO = "LMStudio"
    # Add more providers as needed