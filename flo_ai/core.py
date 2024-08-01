from flo_ai.yaml.flo_team_builder import to_supervised_team
from flo_ai.builders.yaml_builder import build_supervised_team, FloRoutedTeamConfig
from typing import (
    Any,
    Iterator,
    Union
)
from flo_ai.state.flo_session import FloSession
from flo_ai.models.flo_executable import ExecutableFlo

class Flo:

    def __init__(self,
                 session: FloSession,
                 config: FloRoutedTeamConfig) -> None:
        self.config = config
        self.runnable: ExecutableFlo = build_supervised_team(session, config)

    def stream(self, query, config = None) -> Iterator[Union[dict[str, Any], Any]]:
        return self.runnable.stream(query, config)
    
    def invoke(self, query, config = None) -> Iterator[Union[dict[str, Any], Any]]:
        return self.runnable.invoke(query, config)
    
    @staticmethod
    def build(session: FloSession, yaml: str):
        return Flo(session, to_supervised_team(yaml))

    def draw(self, xray=True):
        return self.runnable.draw(xray)
    
    def draw_to_file(self, filename: str, xray=True):
        from PIL import Image as PILImage
        import io
        byte_image = self.runnable.draw(xray)
        with io.BytesIO(byte_image) as image_io:
            image = PILImage.open(image_io)
            image.save(filename)

        