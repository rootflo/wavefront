"""Provider names as stored on LLM, STT and TTS configs.

``str`` enums, so a stored config string compares and hashes equal to its member.
"""

from enum import Enum


class LLMProvider(str, Enum):
    OPENAI = 'openai'
    AZURE_OPENAI = 'azure_openai'
    GEMINI = 'gemini'
    GROQ = 'groq'


class STTProvider(str, Enum):
    DEEPGRAM = 'deepgram'
    SARVAM = 'sarvam'
    ELEVENLABS = 'elevenlabs'
    AZURE = 'azure'
    ASSEMBLYAI = 'assemblyai'
    WHISPER = 'whisper'


class TTSProvider(str, Enum):
    ELEVENLABS = 'elevenlabs'
    DEEPGRAM = 'deepgram'
    CARTESIA = 'cartesia'
    SARVAM = 'sarvam'
    AZURE = 'azure'
