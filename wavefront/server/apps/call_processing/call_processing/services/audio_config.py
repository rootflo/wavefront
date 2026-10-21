"""Audio sample-rate helpers shared by the telephony and browser (WebRTC) paths.

Telephony streams (Twilio / Exotel / Smartflo, mu-law) are 8 kHz. Browser
WebRTC audio is wideband, so STT/TTS and the pipeline run at 16 kHz.
"""

from copy import deepcopy
from typing import Any, Dict, Optional

TELEPHONY_SAMPLE_RATE = 8000
WEBRTC_PROVIDER = 'webrtc'


def with_sample_rate(
    service_config: Dict[str, Any], sample_rate: Optional[int]
) -> Dict[str, Any]:
    """Return a copy of an STT/TTS config with ``parameters.sample_rate`` forced.

    ``None`` leaves the config untouched (telephony keeps its factory defaults).
    The override wins over any ``sample_rate`` an agent stored in its STT/TTS
    parameters, which are tuned for 8 kHz telephony.
    """
    if sample_rate is None:
        return service_config
    forced = deepcopy(service_config)
    parameters = dict(forced.get('parameters') or {})
    parameters['sample_rate'] = sample_rate
    forced['parameters'] = parameters
    return forced


def service_sample_rate(provider: str, pipeline_rate: int) -> Optional[int]:
    """Rate to force onto STT/TTS services, or None to keep telephony defaults."""
    return pipeline_rate if provider == WEBRTC_PROVIDER else None
