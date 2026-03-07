# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in MACRO, please report it responsibly.

**Email**: yuvraj707sharma@gmail.com

**Please include**:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

**What to expect**:
- Acknowledgment within 48 hours
- Fix within 7 days for critical issues
- Credit in the changelog (unless you prefer anonymity)

## Security Model

MACRO has a built-in security enforcement layer (CWE denylist in `system_prompts.py`) that blocks known vulnerability patterns in generated code:

- **CWE-78**: OS Command Injection — blocks `os.system()`, `subprocess(shell=True)`
- **CWE-89**: SQL Injection — blocks string concatenation in SQL
- **CWE-502**: Deserialization — blocks `pickle.loads()`, `yaml.load()` without SafeLoader
- **CWE-798**: Hardcoded Credentials — blocks embedded API keys
- **CWE-22**: Path Traversal — blocks unsanitized user path input
- **CWE-79**: XSS — blocks unescaped HTML insertion

## API Key Storage

MACRO stores API keys in `~/.contextual-architect/config.json` in plaintext. This is standard for CLI developer tools (similar to `~/.npmrc`, `~/.gitconfig`). The config file is created with user-only permissions.

**Recommendations**:
- Don't commit your config file to version control (it's in `.gitignore`)
- Use environment variables (`GROQ_API_KEY`, etc.) in shared environments
- Rotate keys if you suspect compromise

## Offline Mode

MACRO supports fully offline operation via Ollama. When using Ollama, no code or API keys leave your machine.
