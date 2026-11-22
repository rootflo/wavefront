import { VoiceProviderKind } from '@app/hooks';
import { AudioLines, LucideIcon, Volume2 } from 'lucide-react';

type KindInfo = {
  /** Short label, e.g. "STT". */
  label: string;
  /** Spelled-out name, e.g. "Speech-to-Text". */
  title: string;
  icon: LucideIcon;
  defaultProvider: string;
  namePlaceholder: string;
};

export const VOICE_PROVIDER_KINDS: Record<VoiceProviderKind, KindInfo> = {
  stt: {
    label: 'STT',
    title: 'Speech-to-Text',
    icon: AudioLines,
    defaultProvider: 'deepgram',
    namePlaceholder: 'e.g., Deepgram Production',
  },
  tts: {
    label: 'TTS',
    title: 'Text-to-Speech',
    icon: Volume2,
    defaultProvider: 'elevenlabs',
    namePlaceholder: 'e.g., ElevenLabs Production',
  },
};
