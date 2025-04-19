from typing import Optional
from flo_ai.state.flo_session import FloSession
from flo_ai.router.flo_supervisor import FloSupervisor
from flo_ai.router.flo_llm_router import FloLLMRouter
from flo_ai.router.flo_linear import FloLinear
from flo_ai.yaml.config import TeamConfig
from flo_ai.models.flo_team import FloTeam
from flo_ai.router.flo_router import FloRouter
from flo_ai.router.flo_agent_router import FloAgentRouter
from flo_ai.error.flo_exception import FloException
from flo_ai.constants.common_constants import DOCUMENTATION_ROUTER_ANCHOR


class FloRouterFactory:
    @staticmethod
    def create(
        session: FloSession,
        router_kind: str,
        team_config: TeamConfig,
        flo_team: FloTeam,
    ) -> FloRouter:
        if router_kind == 'supervisor':
            router_model = FloRouterFactory.__resolve_model(
                session, team_config.router.model
            )
            return FloSupervisor.Builder(
                session,
                team_config.name,
                flo_team,
                llm=router_model,
                model_nick_name=team_config.router.model,
            ).build()
        elif router_kind == 'linear':
            return FloLinear.Builder(session, team_config.name, flo_team).build()
        elif router_kind == 'llm':
            router_model = FloRouterFactory.__resolve_model(
                session, team_config.router.model
            )
            return FloLLMRouter.Builder(
                session,
                team_config.router.name,
                flo_team,
                llm=router_model,
                model_nick_name=team_config.router.model,
            ).build()
        elif router_kind == 'agent':
            return FloAgentRouter.Builder(
                session,
                team_config.name,
                flo_agent=flo_team,
            ).build()
        else:
            raise Exception(f"""Unknown router type: {router_kind}. 
                            The supported types are supervisor, linear and llm. 
                            Check the documentation @ {DOCUMENTATION_ROUTER_ANCHOR}""")

    @staticmethod
    def __resolve_model(session: FloSession, model_name: Optional[str] = None):
        if model_name is None:
            return session.llm
        if model_name not in session.models:
            raise FloException(
                f"""Model not found: {model_name}.
                The model you would like to use should be registered to the session using session.register_model api, 
                and the same model name should be used here instead of `{model_name}`"""
            )
        return session.models[model_name]
