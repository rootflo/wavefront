# Roadmap

This file provides an overview of the direction this project is heading. The roadmap is organized in steps that focus on a specific theme, for instance, core features, observability, telemetry, etc.

## Core features

Core features improve the library itself to cater wider range of functionalities

| Name | Description | Status | Release version |
|------|-------------|--------|-----------------|
| Full composability | Right now teams can only be combined with teams and agents with agents. We want to extend this to team + agent composibility | In progress | 0.0.4 | 
| Error handling | Ability to handle errors autonomously | In Progress | 0.0.4|
|LLM Extensibilty| Ability to different LLMs across different agents and teams| In Progress | 0.0.4|
|Async Tools| Ability create tools easily within asyncio | In Progress | 0.0.4|
|Output formatter| Ability to templatize output format using pydantic| Yet to start| 0.0.4|
|Auto-Query RAG| Ability to make metadata query within the agentic, which can automatically add metadata while rag query runs, like timestamp or other data|Yet to start|TBD|
|Parellel Router| A router to execute tasks or agents in parallel if the tasks are independent | Yet to start | TBD

## Observability

These features improve logging and debugging abilities while building.

| Name | Description | Status | Release version |
|------|-------------|--------|-----------------|
|Recursion control| Expose parameters like recursion control to limit recursions and policy in case of recursion etc | Yet to start | 0.0.5
|Set up tests| Create a framework for unit-testing flo-ai and its internal functionalities| In progress | TBD

## Community

This is the section where the community can contribute to the roadmap. The items added here will prioritized based on our plans from the rootflo side, but community members are welcome to pick up these features.

| Name | Description | Status |
|------|-------------|--------|


## Notes
The roadmap items are estimates and might change based on rootflo priorities. We will keep this file updated if plans change. 

The community is welcome to suggest changes to the roadmap, through a pull request, by adding features to the community contributions. 

## Released

| Name | Description | Status | Version|
|------|-------------|--------|--------|
|Linear Router|A router lets you build agents or teams that execute linearly or sequentially. The current router supervisor works in a hierarchical way where all the children report to one parent|  ✅ | 0.0.3|
|Reflection| Reflection lets you build a component that can make the AI retrospectively look at the current output and retry or work again on the task at hand|  ✅ | 0.0.3|
|Delegator| Delegator lets you build a component that can help delegate a flo to a particular agent, by some condition|  ✅ | 0.0.3|
|Logging Framework|Better logging framework which can be extended to parent application (with log level control)|  ✅|0.0.3|



