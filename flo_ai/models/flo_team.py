from flo_ai.models.flo_member import FloMember
from flo_ai.state.flo_session import FloSession


class FloTeam:
    def __init__(
        self, session: FloSession, name: str, members: list[FloMember]
    ) -> None:
        self.name = name
        self.members = members
        self.session = session

    class Builder:
        def __init__(
            self, session: FloSession, name: str, members: list[FloMember]
        ) -> None:
            self.name = name
            self.session = session
            self.members = members
            self.member_names = list(map(lambda x: x.name, self.members))

        def build(self):
            return FloTeam(name=self.name, session=self.session, members=self.members)
