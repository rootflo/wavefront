"""Sample still frames from a video, for models that take images but not video."""

import base64 as _base64
import bisect
import io
from typing import TYPE_CHECKING, List, Tuple

from flo_ai.utils.logger import logger

if TYPE_CHECKING:
    from flo_ai.models.chat_message import VideoMessageContent

# Long side of a sampled frame, in pixels. Frames are sent as images, and a
# full-resolution 4K frame costs far more tokens than it adds.
MAX_FRAME_SIDE = 768


def video_to_bytes(video: 'VideoMessageContent') -> bytes:
    if video.bytes:
        return video.bytes
    if video.base64:
        try:
            return _base64.b64decode(video.base64, validate=True)
        except ValueError as exc:
            raise ValueError(
                f'VideoMessageContent.base64 is not valid base64: {exc}'
            ) from exc
    if video.url:
        raise ValueError(
            'URL-based videos are only supported by providers with native video '
            'input; fetch the video bytes first.'
        )
    raise ValueError('VideoMessageContent has no bytes, base64, or url')


def sample_video_frames(data: bytes, max_frames: int) -> List[Tuple[float, bytes]]:
    """Up to ``max_frames`` PNG frames spread evenly over the video.

    Returns ``(seconds_from_start, png_bytes)`` pairs in time order.
    """
    try:
        import av
    except ImportError as exc:
        raise ImportError(
            "Sending video to this model needs PyAV: pip install 'flo-ai[video]'"
        ) from exc
    import pymupdf

    if max_frames < 1:
        raise ValueError('max_frames must be at least 1')

    with av.open(io.BytesIO(data)) as container:
        if not container.streams.video:
            raise ValueError('Video has no video stream')
        stream = container.streams.video[0]
        time_base = stream.time_base
        start = float(stream.start_time * time_base) if stream.start_time else 0.0
        if stream.duration:
            duration = float(stream.duration * time_base)
        elif container.duration:
            duration = container.duration / av.time_base
        else:
            duration = 0.0

        if duration <= 0:
            # Browser recordings (MediaRecorder WebM) carry no duration or cues,
            # so work out the timeline from the packets and decode once.
            logger.warning(
                'Video has no recorded duration; sampling frames by decoding it once'
            )
            return _sample_without_duration(data, max_frames, pymupdf)

        # Midpoints of equal slices, so a 1-frame sample is the middle of the
        # video rather than its (often black) first frame.
        targets = [duration * (i + 0.5) / max_frames for i in range(max_frames)]
        frames: List[Tuple[float, bytes]] = []
        last_time = None
        for target in targets:
            container.seek(int((start + target) / time_base), stream=stream)
            chosen = None
            for frame in container.decode(stream):
                chosen = frame
                if frame.time is None or frame.time + 1e-6 >= start + target:
                    break
            # Past the last frame, the final frame stands in, unless it was
            # already the previous pick.
            if chosen is None or (
                last_time is not None
                and chosen.time is not None
                and chosen.time <= last_time
            ):
                continue
            last_time = chosen.time
            frames.append((target, _frame_to_png(chosen, pymupdf)))
        if not frames:
            raise ValueError('Could not decode any frames from the video')
        return frames


def _sample_without_duration(
    data: bytes, max_frames: int, pymupdf
) -> List[Tuple[float, bytes]]:
    """Sample a video whose container records no duration, without seeking.

    A first pass reads packet timestamps (no decoding) to get the timeline; a
    second pass decodes once and keeps only the frames that were picked.
    """
    import av

    with av.open(io.BytesIO(data)) as container:
        stream = container.streams.video[0]
        time_base = stream.time_base
        pts_list = sorted(p.pts for p in container.demux(stream) if p.pts is not None)
    if not pts_list:
        raise ValueError('Could not decode any frames from the video')

    times = [float(pts * time_base) for pts in pts_list]
    start = times[0]
    duration = times[-1] - start
    wanted = {}
    for i in range(max_frames):
        target = duration * (i + 0.5) / max_frames
        # The frame nearest the target.
        above = bisect.bisect_left(times, start + target)
        index = min(
            range(max(above - 1, 0), min(above + 1, len(times))),
            key=lambda j: abs(times[j] - start - target),
        )
        wanted.setdefault(pts_list[index], target)

    frames: List[Tuple[float, bytes]] = []
    with av.open(io.BytesIO(data)) as container:
        stream = container.streams.video[0]
        for frame in container.decode(stream):
            if frame.pts in wanted:
                frames.append((wanted[frame.pts], _frame_to_png(frame, pymupdf)))
                if len(frames) == len(wanted):
                    break
    if not frames:
        raise ValueError('Could not decode any frames from the video')
    return frames


def _frame_to_png(frame, pymupdf) -> bytes:
    scale = min(1.0, MAX_FRAME_SIDE / max(frame.width, frame.height))
    width = max(2, int(frame.width * scale)) // 2 * 2
    height = max(2, int(frame.height * scale)) // 2 * 2
    rgb = frame.reformat(width=width, height=height, format='rgb24')
    plane = rgb.planes[0]
    raw = bytes(plane)
    row = width * 3
    if plane.line_size != row:
        raw = b''.join(
            raw[r * plane.line_size : r * plane.line_size + row] for r in range(height)
        )
    return pymupdf.Pixmap(pymupdf.csRGB, width, height, raw, False).tobytes('png')
