# Roadmap

This file provides an overview of the direction this project is heading. The roadmap is organized in steps that focus on a specific theme, for instance, core features, observability, telemetry, etc.

## Core features

Core features improve the library itself to cater wider range of functionalities

| Name | Description | Status | Release version |
|------|-------------|--------|-----------------|
|Resume work| Functionality that lets agents resume from where they stopped|Yet to start|0.0.7 |
|To Yaml| Explore the ability to convert code build agents into Yaml| Yet to start| TBD |
|Web server| First step towards creating a publishable service to which agents can be saved and re-used| Yet to start| 0.0.5 |
|Web app| A webapp where agents can be accessed like chat bot/slack| TBD |
|Model routing| Explore the possibility to use a model router within the agents, instead of specifying every agent models | TBD |
|Parellel Router| A router to execute tasks or agents in parallel if the tasks are independent | Yet to start | TBD

## Observability

These features improve logging and debugging abilities while building.

| Name | Description | Status | Release version |
|------|-------------|--------|-----------------|
|Recursion control| Expose parameters like recursion control to limit recursions and policy in case of recursion etc | Yet to start | TBD
| Token count | Expose the total tokens used by an agent execution directly through session| Yet to start | TBD

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
| Full composability | Right now teams can only be combined with teams and agents with agents. We want to extend this to team + agent composibility | ✅ | 0.0.4 | 
| Error handling | Ability to handle errors autonomously | ✅  | 0.0.4|
|LLM Extensibilty| Ability to different LLMs across different agents and teams| ✅  | 0.0.4|
|Async Tools| Ability create tools easily within asyncio | ✅  | 0.0.4|
|Observer| Observer framework for raising agent decision events and other important events | ✅  | 0.0.4|
|Set up tests| Create a framework for unit-testing flo-ai and its internal functionalities| ✅  | 0.0.4 |
|Linear Router|A router lets you build agents or teams that execute linearly or sequentially. The current router supervisor works in a hierarchical way where all the children report to one parent|  ✅ | 0.0.3|
|Reflection| Reflection lets you build a component that can make the AI retrospectively look at the current output and retry or work again on the task at hand|  ✅ | 0.0.3|
|Delegator| Delegator lets you build a component that can help delegate a flo to a particular agent, by some condition|  ✅ | 0.0.3|
|Logging Framework|Better logging framework which can be extended to parent application (with log level control)|  ✅|0.0.3|
|Output formatter| Ability to templatize output format using pydantic| ✅| 0.0.5 |



