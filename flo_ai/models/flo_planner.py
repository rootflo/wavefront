from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from flo_ai.models.flo_executable import ExecutableFlo
from flo_ai.state.flo_state import TeamFloAgentStateWithPlan
from langchain_core.pydantic_v1 import BaseModel, Field
from typing import Union
from langgraph.graph.graph import CompiledGraph
from flo_ai.models.flo_routed_team import FloRoutedTeam
from langgraph.graph import StateGraph
from flo_ai.state.flo_session import FloSession
from flo_ai.helpers.utils import randomize_name


class Response(BaseModel):
    """Response to user."""
    response: str

class Plan(BaseModel):
    """Plan to follow in future"""

    steps: list[str] = Field(
        description="different steps to follow, should be in sorted order"
    )

class Act(BaseModel):
    """Action to perform."""
    action: Union[Response, Plan] = Field(
        description="Action to perform. If you want to respond to user, use Response. "
        "If you need to further use tools to get the answer, use Plan."
    )

class FloPlanner(ExecutableFlo):
    def __init__(self, name: str, graph: CompiledGraph) -> None:
        super().__init__(name, graph)

    def draw(self, xray=True):
        return self.graph.get_graph(xray=xray).draw_mermaid_png()
    
    def stream(self, work, config = None):
        return self.graph.stream({
             "input": work
        }, config)
    
    def invoke(self, work):
        return self.graph.invoke({
             "input": work
        })

class FloPlannerBuilder:

    def __init__(self, 
                 session: FloSession,
                 name: str,
                 team: FloRoutedTeam,
                 planner_prompt: Union[ChatPromptTemplate, None] = None,
                 replanner_prompt: Union[ChatPromptTemplate, None] = None,
                 llm: Union[BaseLanguageModel, None] = None) -> None:
        self.planner_name = randomize_name(name)
        self.re_planner_name = randomize_name("{}-{}".format("replan", name))
        self.session = session
        self.llm = llm if llm is not None else session.llm
        self.team = team
        planner_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """For the given objective, come up with a simple step by step plan. \
        This plan should involve individual tasks, that if executed correctly will yield the correct answer. Do not add any superfluous steps. \
        The result of the final step should be the final answer. Make sure that each step has all the information needed - do not skip steps.""",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        ) if planner_prompt is None else planner_prompt
        self.planner =  planner_prompt | self.llm.with_structured_output(Plan)

        self.replanner_prompt = ChatPromptTemplate.from_template(
                """For the given objective, come up with a simple step by step plan. \
            This plan should involve individual tasks, that if executed correctly will yield the correct answer. Do not add any superfluous steps. \
            The result of the final step should be the final answer. Make sure that each step has all the information needed - do not skip steps.

            Your objective was this:
            {input}

            Your original plan was this:
            {plan}

            You have currently done the follow steps:
            {past_steps}

            Update your plan accordingly. If no more steps are needed and you can return to the user, then do that. 
            Otherwise if there are still steps to complete, fill out the plan. Only add steps to the plan that still NEED to be done. 
            Do not return previously done steps as part of the plan."""
        ) if replanner_prompt is None else replanner_prompt
        self.replanner =  self.replanner_prompt | self.llm.with_structured_output(Act)

    def execute_step(self, state: TeamFloAgentStateWithPlan):
        plan = state["plan"]
        plan_str = "\n".join(f"{i+1}. {step}" for i, step in enumerate(plan))
        task = plan[0]
        task_formatted = f"""For the following plan:
            {plan_str}\n\nYou are tasked with executing step {1}, {task}."""
        agent_response = self.team.invoke(task_formatted)
        return {
            "past_steps": (task, agent_response["messages"][-1].content),
        }

    def plan_step(self, state: TeamFloAgentStateWithPlan):
        plan =  self.planner.invoke({"messages": [("user", state["input"])]})
        if self.session is not None:
            self.session.append(self.planner_name)
        return {"plan": plan.steps}
    
    def replan_step(self, state: TeamFloAgentStateWithPlan):
        output = self.replanner.invoke(state)
        if self.session is not None:
            self.session.append(self.re_planner_name)
        if isinstance(output.action, Response):
            return { "response": output.action.response }
        else:
            return { "plan": output.action.steps }
        
    def should_end(self, state: TeamFloAgentStateWithPlan):
        if "response" in state and state["response"]:
            return "__end__"
        else:
            return self.team.name

    def build(self):
        workflow = StateGraph(TeamFloAgentStateWithPlan)

        # Add the plan node
        workflow.add_node(self.planner_name, self.plan_step)

        # Add the execution step
        workflow.add_node(self.team.name, self.execute_step)

        # Add a replan node
        workflow.add_node(self.re_planner_name, self.replan_step)

        workflow.set_entry_point(self.planner_name)

        # From plan we go to agent
        workflow.add_edge(self.planner_name, self.team.name)

        # From agent, we replan
        workflow.add_edge(self.team.name, self.re_planner_name)

        workflow.add_conditional_edges(
            self.re_planner_name,
            # Next, we pass in the function that will determine which node is called next.
            self.should_end,
        )

        # Finally, we compile it!
        # This compiles it into a LangChain Runnable,
        # meaning you can use it as you would any other runnable
        return FloPlanner(self.planner_name, workflow.compile())