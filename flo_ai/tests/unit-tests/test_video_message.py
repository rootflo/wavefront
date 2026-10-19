"""VideoMessageContent: model, frame sampling, per-provider formatting, and
images/videos returned by tools becoming media turns in the conversation."""

import base64
import io
from unittest.mock import AsyncMock, Mock, patch

import pytest

from flo_ai import ImageMessageContent, UserMessage, VideoMessageContent
from flo_ai.agent.agent import Agent
from flo_ai.llm.anthropic_llm import Anthropic
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.llm.gemini_llm import Gemini
from flo_ai.llm.guarded_llm import GuardedLLM
from flo_ai.llm.ollama_llm import OllamaLLM
from flo_ai.llm.openai_llm import OpenAI
from flo_ai.llm.rootflo_llm import RootFloLLM
from flo_ai.tool.base_tool import Tool
from flo_ai.utils import video_frames
from flo_ai.utils.video_frames import sample_video_frames, video_to_bytes

av = pytest.importorskip('av')


def make_video(seconds: int = 2, fps: int = 5, width: int = 64, height: int = 48):
    buf = io.BytesIO()
    with av.open(buf, 'w', format='mp4') as container:
        stream = container.add_stream('mpeg4', rate=fps)
        stream.width, stream.height, stream.pix_fmt = width, height, 'yuv420p'
        for i in range(seconds * fps):
            frame = av.VideoFrame(width, height, 'rgb24')
            plane = frame.planes[0]
            plane.update(bytes([i * 20 % 256]) * plane.buffer_size)
            for packet in stream.encode(frame.reformat(format='yuv420p')):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return buf.getvalue()


@pytest.fixture(scope='module')
def video_bytes():
    return make_video()


def with_frames(llm, n):
    llm.video_max_frames = n
    return llm


def is_png(data: bytes) -> bool:
    return data.startswith(b'\x89PNG')


class TestVideoMessageContent:
    def test_type_and_repr(self):
        video = VideoMessageContent(bytes=b'x' * 1000, mime_type='video/mp4')
        assert video.type == 'video'
        assert video._formatted_cache == {}
        assert 'xxx' not in repr(video)

    def test_user_message_accepts_video(self):
        message = UserMessage(content=VideoMessageContent(url='gs://b/v.mp4'))
        assert message.role == 'user'
        assert message.content.type == 'video'

    def test_video_to_bytes(self):
        assert video_to_bytes(VideoMessageContent(bytes=b'ab')) == b'ab'
        assert video_to_bytes(VideoMessageContent(base64='YWI=')) == b'ab'
        with pytest.raises(ValueError, match='not valid base64'):
            video_to_bytes(VideoMessageContent(base64='%%%'))
        with pytest.raises(ValueError, match='URL-based'):
            video_to_bytes(VideoMessageContent(url='https://x/v.mp4'))
        with pytest.raises(ValueError, match='no bytes'):
            video_to_bytes(VideoMessageContent())


class TestSampleVideoFrames:
    def test_frames_are_spread_over_the_video(self, video_bytes):
        frames = sample_video_frames(video_bytes, 4)
        assert [round(t, 2) for t, _ in frames] == [0.25, 0.75, 1.25, 1.75]
        assert all(is_png(png) for _, png in frames)
        # Distinct source frames, not the first frame repeated.
        assert len({png for _, png in frames}) == 4

    def test_large_frames_are_downscaled(self):
        import pymupdf

        _, png = sample_video_frames(make_video(1, 2, 1600, 900), 1)[0]
        pix = pymupdf.Pixmap(png)
        assert max(pix.width, pix.height) <= video_frames.MAX_FRAME_SIDE

    def test_not_a_video(self):
        with pytest.raises(Exception):
            sample_video_frames(b'not a video', 2)

    def test_past_the_end_targets_do_not_repeat_frames(self, video_bytes):
        # 10 frames, 8 targets: the last target falls after the final frame.
        frames = sample_video_frames(video_bytes, 8)
        assert len({png for _, png in frames}) == len(frames) == 7

    def test_needs_at_least_one_frame(self, video_bytes):
        with pytest.raises(ValueError, match='at least 1'):
            sample_video_frames(video_bytes, 0)


def image_blocks(blocks, key):
    return [b for b in blocks if b.get('type') == key]


class TestFrameSamplingProviders:
    """Providers without native video input get labelled frames as images."""

    async def test_openai_frames_as_image_urls(self, video_bytes):
        llm = with_frames(OpenAI(api_key='k'), 3)
        video = VideoMessageContent(
            base64=base64.b64encode(video_bytes).decode(),
            mime_type='video/mp4',
            file_name='clip.mp4',
        )
        blocks = await llm.format_video_in_message(video)

        texts = [b['text'] for b in image_blocks(blocks, 'text')]
        assert any('clip.mp4' in t for t in texts)
        assert any('3 frames sampled at' in t for t in texts)
        urls = [b['image_url']['url'] for b in image_blocks(blocks, 'image_url')]
        assert len(urls) == 3
        assert all(u.startswith('data:image/png;base64,') for u in urls)
        assert is_png(base64.b64decode(urls[0].split(',', 1)[1]))

    async def test_anthropic_frames_as_image_blocks(self, video_bytes):
        llm = with_frames(Anthropic(api_key='k'), 4)
        blocks = await llm.format_video_in_message(
            VideoMessageContent(bytes=video_bytes, mime_type='video/mp4')
        )
        images = image_blocks(blocks, 'image')
        assert len(images) == 4
        assert images[0]['source']['type'] == 'base64'
        assert images[0]['source']['media_type'] == 'image/png'

    async def test_bedrock_uses_openai_shape(self, video_bytes):
        from flo_ai.llm.aws_bedrock_llm import AWSBedrock

        with patch('flo_ai.llm.aws_bedrock_llm.boto3'):
            llm = with_frames(AWSBedrock(), 2)
        blocks = await llm.format_video_in_message(
            VideoMessageContent(bytes=video_bytes)
        )
        assert len(image_blocks(blocks, 'image_url')) == 2

    async def test_formatting_is_cached_per_llm_class(self, video_bytes):
        video = VideoMessageContent(bytes=video_bytes)
        sample = Mock(wraps=sample_video_frames)
        with patch('flo_ai.llm.base_llm.sample_video_frames', sample):
            first = await OpenAI(api_key='k').format_video_in_message(video)
            second = await OpenAI(api_key='k').format_video_in_message(video)
            await Anthropic(api_key='k').format_video_in_message(video)
        assert first is second
        assert sample.call_count == 2

    async def test_missing_pyav_is_a_clear_error(self, video_bytes, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def no_av(name, *args, **kwargs):
            if name == 'av':
                raise ImportError('no av')
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, '__import__', no_av)
        with pytest.raises(ImportError, match=r'flo-ai\[video\]'):
            await OpenAI(api_key='k').format_video_in_message(
                VideoMessageContent(bytes=video_bytes)
            )


class TestNativeAndDelegatingProviders:
    @patch('flo_ai.llm.gemini_llm.genai.Client')
    async def test_gemini_sends_video_natively(self, _client):
        llm = Gemini(api_key='k')
        part = await llm.format_video_in_message(
            VideoMessageContent(base64='YWI=', mime_type='video/webm')
        )
        assert part.inline_data.data == b'ab'
        assert part.inline_data.mime_type == 'video/webm'

        part = await llm.format_video_in_message(
            VideoMessageContent(url='gs://bucket/v.mp4')
        )
        assert part.file_data.file_uri == 'gs://bucket/v.mp4'
        assert part.file_data.mime_type == 'video/mp4'

        with pytest.raises(ValueError, match='no bytes'):
            await llm.format_video_in_message(VideoMessageContent())

    @patch('flo_ai.llm.gemini_llm.genai.Client')
    async def test_vertex_inherits_native_video(self, _client):
        from flo_ai.llm.vertexai_llm import VertexAI

        assert VertexAI._format_native_video is Gemini._format_native_video

    async def test_ollama_rejects_video(self):
        with pytest.raises(NotImplementedError, match='video'):
            await OllamaLLM().format_video_in_message(VideoMessageContent(bytes=b'x'))

    async def test_guarded_delegates_to_inner(self):
        inner = Mock(spec=BaseLLM)
        inner.format_video_in_message = AsyncMock(return_value=['inner'])
        guarded = GuardedLLM(inner, engine=Mock(), principal=Mock())
        video = VideoMessageContent(bytes=b'x')
        assert await guarded.format_video_in_message(video) == ['inner']
        inner.format_video_in_message.assert_awaited_once_with(video)

    async def test_rootflo_delegates_to_provider(self):
        llm = RootFloLLM(
            base_url='https://example.invalid',
            model_id='68baf67b-ff67-4bb1-a663-bcf08227d012',
        )
        llm._llm = Mock()
        llm._llm.format_video_in_message = AsyncMock(return_value=['provider'])
        assert await llm.format_video_in_message(VideoMessageContent()) == ['provider']


class TestAgentHistory:
    async def test_video_user_message_is_formatted(self, video_bytes):
        llm = with_frames(OpenAI(api_key='k'), 2)
        agent = Agent(name='a', system_prompt='s', llm=llm)
        agent.add_to_history(
            UserMessage(content=VideoMessageContent(bytes=video_bytes))
        )
        history = await agent._get_message_history_impl({})
        content = history[-1]['content']
        assert history[-1]['role'] == 'user'
        assert len(image_blocks(content, 'image_url')) == 2


def agent_with_tool(llm, result):
    async def fetch():
        return result

    tool = Tool(name='fetch', description='fetch a file', function=fetch, parameters={})
    agent = Agent(name='a', system_prompt='s', llm=llm, tools=[tool])
    llm.generate = AsyncMock(return_value={})
    llm.get_function_call = AsyncMock(
        side_effect=[{'name': 'fetch', 'arguments': '{}', 'id': 't1'}, None]
    )
    llm.get_message_content = Mock(return_value='done')
    llm.get_assistant_message_for_tool_call = Mock(return_value=None)
    agent._is_final_answer = AsyncMock(return_value=True)
    return agent


class TestToolMediaResults:
    async def test_image_result_becomes_user_image_turn(self):
        llm = OpenAI(api_key='k')
        image = ImageMessageContent(
            base64='cG5n', mime_type='image/png', file_name='chart.png'
        )
        agent = agent_with_tool(llm, image)

        await agent.run('show me the chart')

        messages = llm.generate.call_args_list[-1].args[0]
        tool_result, media_turn = messages[-2], messages[-1]
        assert 'chart.png' in tool_result['content']
        assert 'cG5n' not in tool_result['content']
        assert media_turn['role'] == 'user'
        assert {
            'type': 'image_url',
            'image_url': {'url': 'data:image/png;base64,cG5n'},
        } in media_turn['content']
        assert any(
            isinstance(m, UserMessage) and m.content is image
            for m in agent.conversation_history
        )

    async def test_video_result_becomes_user_video_turn(self, video_bytes):
        llm = with_frames(OpenAI(api_key='k'), 2)
        video = VideoMessageContent(bytes=video_bytes, mime_type='video/mp4')
        agent = agent_with_tool(llm, video)

        await agent.run('what happens in the clip')

        media_turn = llm.generate.call_args_list[-1].args[0][-1]
        assert media_turn['role'] == 'user'
        assert len(image_blocks(media_turn['content'], 'image_url')) == 2
        assert any(
            isinstance(m, UserMessage) and m.content is video
            for m in agent.conversation_history
        )

    async def test_text_result_stays_a_tool_result(self):
        llm = OpenAI(api_key='k')
        agent = agent_with_tool(llm, '{"content": "id,total"}')

        await agent.run('read the csv')

        messages = llm.generate.call_args_list[-1].args[0]
        assert 'id,total' in messages[-1]['content']
        assert not any(
            isinstance(m, UserMessage) and not isinstance(m.content, str)
            for m in agent.conversation_history
        )
