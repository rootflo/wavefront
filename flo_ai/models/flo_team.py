from flo_ai.models.flo_member import FloMember
from flo_ai.state.flo_session import FloSession
from flo_ai.helpers.utils import randomize_name


class FloTeam():
    def __init__(self,
                  session: FloSession,
                  name: str,
                  members: list[FloMember]) -> None:
        self.name = name
        self.session = session
        self.members = members

    class Builder:
        def __init__(self, 
                    session: FloSession,
                    name: str,
                    members: list[FloMember]) -> None:
            self.name = randomize_name(name)
            self.session = session
            self.members = members
            self.member_names= list(map(lambda x: x.name, self.members))
            
        def build(self):
            return FloTeam(
                name = self.name,
                session=self.session, 
                members=self.members
            )