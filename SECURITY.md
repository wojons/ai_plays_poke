# Security Policy

## Supported Versions

The latest version of AI Plays Pokémon is supported with security updates.

## Reporting a Vulnerability

To report a security vulnerability, please open an issue on the project's GitHub repository or contact the maintainers directly.

**Please do not disclose security vulnerabilities publicly until they have been addressed.**

## Security Model

This project runs Pokémon ROMs via PyBoy emulation. The following security considerations apply:

- **ROM files:** ROM files are read-only game data. Only load ROMs from trusted sources.
- **API keys:** DeepSeek API keys are stored in environment variables only — never committed to the repository.
- **Dependencies:** Dependencies are pinned and periodically audited via `pip-audit`.
- **Subprocess isolation:** PyBoy runs as a subprocess with limited system access.

## Best Practices for Contributors

- Never commit API keys, tokens, or credentials
- Use environment variables for all secrets
- Keep dependencies up to date
- Review code for injection vulnerabilities in prompt construction
- Test with `gitleaks` before committing
