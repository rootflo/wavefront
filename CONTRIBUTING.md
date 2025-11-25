# Contributing to Flo AI

Thank you for your interest in contributing to Flo AI! We welcome contributions from the community and are excited to work with you.

This guide will help you get started with contributing to the Flo AI project. Please read it carefully before making your first contribution.

> **Note**: This contributing guide currently focuses on **Flo AI**, the core agent building and orchestration library. **Wavefront AI** (the enterprise middleware platform) is currently in development and will be open-sourced in the future. When Wavefront AI is released, we will update this guide with additional contribution guidelines for the middleware platform.

---

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Environment Setup](#development-environment-setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Code Style and Standards](#code-style-and-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation Guidelines](#documentation-guidelines)
- [Commit Message Guidelines](#commit-message-guidelines)
- [Pull Request Process](#pull-request-process)
- [Types of Contributions](#types-of-contributions)
- [Questions and Support](#questions-and-support)

---

## 📜 Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to vishnu@rootflo.ai.

---

## 🚀 Getting Started

### Prerequisites

Before you begin, ensure you have:

- **Python 3.10 or higher** (check with `python --version`)
- **Git** installed and configured
- **uv** package manager (recommended) or **pip/poetry**
- **API keys** for LLM providers (for testing):
  - OpenAI API key (optional, for OpenAI tests)
  - Anthropic API key (optional, for Claude tests)
  - Google API key (optional, for Gemini tests)

### Fork and Clone

1. **Fork the repository** on GitHub
2. **Clone your fork**:
   ```bash
   git clone https://github.com/your-username/wavefront.git
   cd wavefront
   ```
3. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/rootflo/wavefront.git
   ```

---

## 🛠️ Development Environment Setup

### Python Environment

We recommend using `uv` for dependency management:

#### For contributing to flo-ai:

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Navigate to flo_ai directory
cd flo_ai

# Sync dependencies (installs all dependencies including dev dependencies)
uv sync

# Activate the virtual environment
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows
```

Alternatively, using pip:

```bash
# Navigate to flo_ai directory
cd flo_ai

# Install in development mode
pip install -e .

# Install development dependencies
pip install -e ".[dev]"
```
For contributing to wavefront:

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Navigate to flo_ai directory
cd wavefront

# Sync dependencies (installs all dependencies including dev dependencies)
uv sync --all-packages

# Activate the virtual environment
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows
```

### Environment Variables

Set up your API keys for testing (create a `.env` file or export them):

[Documentation to be added soon]

### Verify Installation

Test your installation:

```bash
# Run the test suite
pytest tests/unit-tests/

# Run a specific test
pytest tests/unit-tests/test_agent_builder_tools.py
```

## 📁 Project Structure

Understanding the project structure will help you navigate the codebase:

[To be added]

---

## 🔄 Development Workflow

### 1. Create a Branch

Always create a new branch for your work:

```bash
# Update your local main branch
git checkout main
git pull upstream main

# Create a new branch
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
# or
git checkout -b docs/your-documentation-update
```

**Branch naming conventions:**
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `test/` - Test additions or updates
- `chore/` - Maintenance tasks

### 2. Make Your Changes

- Write clean, maintainable code
- Follow the code style guidelines (see below)
- Add tests for new features
- Update documentation as needed
- Keep commits focused and atomic

### 3. Test Your Changes

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit-tests/test_your_file.py

# Run with coverage
pytest --cov=flo_ai --cov-report=html

# Run integration tests (requires API keys)
pytest tests/integration-tests/ -m integration
```

### 4. Commit Your Changes

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```bash
git commit -m "feat: add new feature description"
git commit -m "fix: resolve bug in agent builder"
git commit -m "docs: update contributing guide"
```

**Commit types:**
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, etc.)
- `refactor:` - Code refactoring
- `test:` - Test additions or updates
- `chore:` - Maintenance tasks
- `perf:` - Performance improvements
- `ci:` - CI/CD changes

### 5. Keep Your Branch Updated

Regularly sync with upstream:

```bash
git fetch upstream
git rebase upstream/main
```

### 6. Push and Create Pull Request

```bash
# Push to your fork
git push origin feature/your-feature-name

# Then create a Pull Request on GitHub
```

---

## 💻 Code Style and Standards

### Python Code Style

We use **pre-commit hooks** to ensure code quality. Set it up:

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run on all files (optional, but recommended)
pre-commit run --all-files
```

**Key style guidelines:**

1. **Follow PEP 8** - Python style guide
2. **Type hints** - Use type hints for function signatures:
   ```python
   from typing import Optional, List
   
   async def process_data(
       items: List[str],
       limit: Optional[int] = None
   ) -> dict:
       ...
   ```
3. **Docstrings** - Use Google-style docstrings:
   ```python
   def my_function(param1: str, param2: int) -> bool:
       """Brief description of the function.
       
       Args:
           param1: Description of param1
           param2: Description of param2
           
       Returns:
           Description of return value
           
       Raises:
           ValueError: When something goes wrong
       """
   ```
4. **Async/Await** - Use async/await for I/O operations
5. **Error Handling** - Use appropriate exception types and provide clear error messages

## 🧪 Testing Guidelines

### Writing Tests

1. **Test Coverage** - Aim for high test coverage, especially for new features
2. **Test Organization**:
   - Unit tests in `tests/unit-tests/`
   - Integration tests in `tests/integration-tests/`
   - Mark integration tests with `@pytest.mark.integration`

3. **Test Naming**:
   ```python
   def test_function_name_with_condition_returns_expected():
       """Test that function_name returns expected when condition is met."""
   ```

4. **Async Tests**:
   ```python
   import pytest
   
   @pytest.mark.asyncio
   async def test_async_function():
       result = await my_async_function()
       assert result == expected
   ```

5. **Fixtures** - Use pytest fixtures for common setup:
   ```python
   @pytest.fixture
   def sample_agent():
       return AgentBuilder().with_name('test').build()
   ```

### Running Tests

```bash
# Run all unit tests
pytest tests/unit-tests/

# Run specific test file
pytest tests/unit-tests/test_agent_builder.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=flo_ai --cov-report=term-missing

# Run only integration tests (requires API keys)
pytest tests/integration-tests/ -m integration

# Skip integration tests
pytest -m "not integration"
```

### Test Requirements

- All tests must pass before submitting a PR
- New features should include tests
- Bug fixes should include regression tests
- Integration tests are optional but encouraged for LLM integrations

---

## 📚 Documentation Guidelines

### Code Documentation

- **Docstrings** - All public functions, classes, and methods should have docstrings
- **Type hints** - Use type hints for better IDE support and documentation
- **Comments** - Add comments for complex logic, but prefer self-documenting code

### Documentation Updates

When adding new features, update:

1. **README.md** - If the feature is user-facing
2. **API Documentation** - If adding new APIs
3. **Examples** - Add examples in `flo_ai/examples/` if applicable
4. **Docstrings** - Update docstrings for any changed functions

### Documentation Format

- Use Markdown for documentation files
- Use MDX for the documentation site
- Include code examples where helpful
- Keep documentation up-to-date with code changes

---

## 📝 Commit Message Guidelines

We follow [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Examples:**

```
feat(arium): add parallel router support

Add support for executing independent agents in parallel
to improve workflow performance.

Closes #123
```

```
fix(builder): resolve memory leak in agent builder

Fix memory leak that occurred when building multiple agents
in a single session.

Fixes #456
```

```
docs(readme): update installation instructions

Update installation instructions to include uv package manager
as the recommended option.
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `style` - Formatting, missing semicolons, etc.
- `refactor` - Code refactoring
- `test` - Adding or updating tests
- `chore` - Maintenance tasks
- `perf` - Performance improvements

---

## 🔀 Pull Request Process

### Before Submitting

1. ✅ **Tests pass** - All tests should pass locally
2. ✅ **Code formatted** - Run pre-commit hooks or format manually
3. ✅ **Documentation updated** - Update relevant documentation
4. ✅ **Branch is up-to-date** - Rebase on latest main branch
5. ✅ **No merge conflicts** - Resolve any conflicts

### PR Checklist

When creating a PR, ensure:

- [ ] Clear description of changes
- [ ] Reference to related issues (if any)
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] Code follows style guidelines
- [ ] All tests pass
- [ ] No breaking changes (or clearly documented)

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
Describe how you tested your changes

## Checklist
- [ ] Code follows style guidelines
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] All tests pass

## Related Issues
Closes #123
```

### Review Process

1. **Automated Checks** - CI will run tests and linting
2. **Code Review** - Maintainers will review your PR
3. **Feedback** - Address any feedback or requested changes
4. **Approval** - Once approved, your PR will be merged

**Tips for faster reviews:**
- Keep PRs focused and small
- Respond to feedback promptly
- Be open to suggestions
- Test thoroughly before submitting

---

## 🎯 Types of Contributions

We welcome various types of contributions:

### 🐛 Bug Reports

1. Check if the bug has already been reported
2. Use the bug report template
3. Include:
   - Clear description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details
   - Error messages/logs

### 💡 Feature Requests

1. Check if the feature has been requested
2. Use the feature request template
3. Include:
   - Clear description
   - Use case and motivation
   - Proposed implementation (if you have ideas)
   - Alternatives considered

### 📝 Code Contributions

- **New Features** - Implement features from the roadmap or your own ideas
- **Bug Fixes** - Fix reported bugs
- **Performance Improvements** - Optimize existing code
- **Refactoring** - Improve code structure without changing functionality
- **Tests** - Add or improve test coverage

### 📚 Documentation

- **Tutorials** - Write tutorials for common use cases
- **Examples** - Add example code
- **API Documentation** - Improve API documentation
- **Translation** - Translate documentation (if applicable)

### 🎨 Design

- **UI/UX Improvements** - Improve Studio interface
- **Icons/Graphics** - Design icons or graphics
- **Documentation Design** - Improve documentation layout

### 🤝 Community

- **Answer Questions** - Help others in discussions
- **Review PRs** - Review and test others' contributions
- **Share Use Cases** - Share how you're using Flo AI

---

## ❓ Questions and Support

### Getting Help

- **GitHub Discussions** - For questions and discussions
- **GitHub Issues** - For bug reports and feature requests
- **Email** - vishnu@rootflo.ai for direct contact

### Resources

- **Documentation** - [https://flo-ai.rootflo.ai](https://flo-ai.rootflo.ai)
- **README** - Check the main [README.md](README.md) and [flo_ai/README.md](flo_ai/README.md)
- **Roadmap** - See [ROADMAP.md](ROADMAP.md) for planned features
- **Examples** - Check `flo_ai/examples/` for code examples

### Before Asking

1. **Search** - Check if your question has been answered
2. **Read Documentation** - Review relevant documentation
3. **Check Examples** - Look at example code
4. **Reproduce** - Try to reproduce the issue yourself

---

## 🎉 Recognition

Contributors will be recognized in:

- **README.md** - Contributor list (for significant contributions)
- **Release Notes** - Credit for contributions in releases
- **Documentation** - Attribution for documentation contributions

---

## 📄 License

By contributing, you agree that your contributions will be licensed under the same license as the project (MIT License for Flo AI).

---

## 🙏 Thank You!

Thank you for taking the time to contribute to Flo AI! Your contributions help make this project better for everyone.

**Happy Contributing! 🚀**

---

**Questions?** Feel free to open an issue or reach out to vishnu@rootflo.ai
