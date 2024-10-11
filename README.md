<p align="center">
  <img src="./images/rootflo-logo.png" alt="Rootflo" width="150" />
</p>

<h1 align="center">Composable AI Agentic Workflow</h1>

<p align="center">
Rootflo is an alternative to <b>Langgraph</b>, and  <b>CrewAI</b>. It lets you easily build composable agentic workflows from using simple components to any size, unlocking the full potential of LLMs.
</p>

<p align="center">
  <a href="https://github.com/rootflo/flo-ai/stargazers"><img src="https://img.shields.io/github/stars/rootflo/flo-ai?style=for-the-badge" alt="GitHub stars"></a>
  <a href="https://github.com/rootflo/flo-ai/releases">
    <img src="https://img.shields.io/github/v/release/rootflo/flo-ai?display_name=release&style=for-the-badge" alt="GitHub release (latest)">
  </a>
  <a href="https://github.com/rootflo/flo-ai/graphs/commit-activity"><img alt="GitHub commit activity" src="https://img.shields.io/github/commit-activity/m/rootflo/flo-ai/develop?style=for-the-badge">
  </a>
  <a href="https://github.com/rootflo/flo-ai/blob/develop/LICENSE"><img src="https://img.shields.io/github/license/rootflo/flo-ai?style=for-the-badge" alt="License">
  </a>
  <br/>
</p>

<p align="center">
    <br/>
    <a href="https://flo-ai.rootflo.ai" rel=""><strong>Checkout the docs »</strong></a>
    <br/>
  <br/>
    <a href="https://rootflo.ai">Website</a>
   •
    <a href="https://github.com/rootflo/flo-ai/blob/develop/ROADMAP.md">Roadmap</a>
  </p>

  <hr />

# Flo AI 🌊

> Build production-ready AI agents and teams with minimal code

Flo AI is a Python framework that makes building production-ready AI agents and teams as easy as writing YAML. Think "Kubernetes for AI Agents" - compose complex AI architectures using pre-built components while maintaining the flexibility to create your own.

## ✨ Features

- 🔌 **Truly Composable**: Build complex AI systems by combining smaller, reusable components
- 🏗️ **Production-Ready**: Built-in best practices and optimizations for production deployments
- 📝 **YAML-First**: Define your entire agent architecture in simple YAML
- 🔧 **Flexible**: Use pre-built components or create your own
- 🤝 **Team-Oriented**: Create and manage teams of AI agents working together
- 📚 **RAG Support**: Built-in support for Retrieval-Augmented Generation
- 🔄 **Langchain Compatible**: Works with all your favorite Langchain tools

## 🚀 Quick Start

### Installation

```bash
pip install flo-ai
# or using poetry
poetry add flo-ai
```

### Create Your First AI Team in 30 Seconds

```python
from flo_ai import Flo, FloSession
from langchain_openai import ChatOpenAI

# Define your team in YAML
yaml_config = """
apiVersion: flo/alpha-v1
kind: FloRoutedTeam
name: research-team
team:
    name: ResearchTeam
    router:
        name: TeamLead
        kind: supervisor
    agents:
      - name: Researcher
        role: Research Specialist
        job: Research latest information on given topics
        tools:
          - name: TavilySearchResults
      - name: Writer
        role: Content Creator
        job: Create engaging content from research
"""

# Set up and run
llm = ChatOpenAI(temperature=0)
session = FloSession(llm).register_tool(name="TavilySearchResults", tool=TavilySearchResults())
flo = Flo.build(session, yaml=yaml_config)

# Start streaming results
for response in flo.stream("Write about recent AI developments"):
    print(response)
```

## 📖 Documentation

Visit our [comprehensive documentation](https://flo-ai.rootflo.ai) for:
- Detailed tutorials
- Architecture deep-dives
- API reference
- Best practices
- Advanced examples

## 🌟 Why Flo AI?

### For AI Engineers
- **Faster Development**: Build complex AI systems in minutes, not days
- **Production Focus**: Built-in optimizations and best practices
- **Flexibility**: Use our components or build your own

### For Teams
- **Maintainable**: YAML-first approach makes systems easy to understand and modify
- **Scalable**: From single agents to complex team hierarchies
- **Testable**: Each component can be tested independently

## 🎯 Use Cases

- 🤖 Customer Service Automation
- 📊 Data Analysis Pipelines
- 📝 Content Generation
- 🔍 Research Automation
- 🎯 Task-Specific AI Teams

## 🤝 Contributing

We love your input! Check out our [Contributing Guide](CONTRIBUTING.md) to get started. Ways to contribute:

- 🐛 Report bugs
- 💡 Propose new features
- 📝 Improve documentation
- 🔧 Submit PRs

## 📜 License

Flo AI is [MIT Licensed](LICENSE).

## 🙏 Acknowledgments

Built with ❤️ using:
- [LangChain](https://github.com/hwchase17/langchain)
- [LangGraph](https://github.com/langchain-ai/langgraph)

---

<div align="center">
  <strong>Built with ❤️ by the Rootflo team</strong>
  <br><a href="https://github.com/rootflo/flo-ai/discussions">Community</a> •
  <a href="https://flo-ai.rootflo.ai">Documentation</a>
</div>