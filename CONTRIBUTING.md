# Contributing to PTP-01X

Thank you for your interest in contributing to PTP-01X! This document provides guidelines and instructions for contributing.

## Getting Started

### Prerequisites
- Python 3.10+
- Git
- An OpenAI API key (for full AI functionality)
- A Pokemon ROM file (for testing)

### Development Setup
```bash
# 1. Fork the repository on GitHub

# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/ai_plays_poke.git
cd ai_plays_poke

# 3. Create a virtual environment
python3 -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 4. Install dependencies
pip install -r requirements.txt

# 5. Install development dependencies
pip install -r requirements-dev.txt

# 6. Create your feature branch
git checkout -b feature/your-feature-name
```

## Development Workflow

### Code Style
- **Formatting:** Use Black with default settings (line length 88)
- **Type Hints:** All functions must have type hints
- **Imports:** Sort imports using isort
- **Naming:** Follow PEP 8 conventions (snake_case for functions/variables, PascalCase for classes)

```bash
# Format your code before committing
black src/ tests/

# Check formatting without making changes
black --check src/ tests/
```

### Testing
```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_schemas.py -v

# Run tests in parallel
pytest tests/ -n auto -v
```

**Test Requirements:**
- All new features must include tests
- Tests should follow the pattern: `test_feature_behavior_expectedOutcome`
- Use pytest fixtures for common setup
- Mark integration tests with `@pytest.mark.integration`

### Type Checking
```bash
# Run mypy type checker
mypy src/ --ignore-missing-imports --strict
```

### Linting
```bash
# Run flake8
flake8 src/ tests/ --max-line-length=88 --extend-ignore=E203,W503
```

### Commit Messages
Follow conventional commit format:
- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code refactoring
- `test:` Adding tests
- `chore:` Maintenance tasks

Example:
```
feat(battle): Add type effectiveness checking

- Calculate move effectiveness based on type chart
- Prioritize super-effective moves in battle AI
- Add unit tests for type calculation

Fixes #123
```

## Project Structure

```
├── src/
│   ├── core/           # Core AI systems (emulator, vision, AI client)
│   ├── db/             # Database operations
│   ├── schemas/        # Command and data schemas
│   └── cli/            # Command-line interface
├── tests/
│   ├── conftest.py     # Pytest fixtures
│   └── test_*.py       # Test files
├── specs/              # Technical specifications
├── prompts/            # LLM prompts
├── memory-bank/        # Architecture documentation
└── config/             # Configuration files
```

## Adding New Features

### 1. Plan Your Changes
- Review relevant specifications in `specs/ptp_01x_detailed/`
- Check existing implementations for patterns
- Update memory bank if adding significant features

### 2. Implement
- Follow code style guidelines
- Add type hints
- Include error handling
- Write docstrings for public functions

### 3. Test
- Write unit tests for new functionality
- Ensure existing tests still pass
- Test edge cases

### 4. Document
- Update README.md if adding user-facing features
- Add code comments for complex logic
- Update specifications if behavior changed

## Key Design Patterns

### State Machine
The project uses a hierarchical state machine for game state detection. When adding new states:
1. Define the state in `src/schemas/`
2. Add detection logic in the vision pipeline
3. Add handling in the appropriate handler

### Memory Architecture
Three-tier memory system:
- **Observer:** Long-term persistence (saved to disk)
- **Strategist:** Session-long learning (in-memory, session-scoped)
- **Tactician:** Immediate context (tick-to-tick)

### GOAP Planning
Goal-Oriented Action Planning for decision making. When adding new goals:
1. Define goal in schemas
2. Add to GOAP planner
3. Define preconditions and effects

## Issue Tracking

### Bug Reports
Include:
- Clear description of the bug
- Steps to reproduce
- Expected behavior vs actual behavior
- Environment details (OS, Python version, ROM version)
- Error messages and tracebacks

### Feature Requests
Include:
- Clear description of the feature
- Use case and motivation
- Suggested implementation approach
- Any relevant references or examples

## Questions?

- Check existing documentation in `memory-bank/`
- Review technical specifications in `specs/`
- Search existing GitHub issues
- Open a new issue for discussion

## Code of Conduct

Be respectful and constructive. We're all here to build something amazing together.

---

*Last Updated: December 31, 2025*