# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest  | ✅        |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you discover a security vulnerability in Openspired, please report it responsibly:

1. Open a [GitHub Security Advisory](https://github.com/Dsegovia98/openspired/security/advisories/new)
2. Or email the maintainers directly (see profile)

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You will receive a response within 48 hours. We appreciate responsible disclosure.

## Security Best Practices for Users

- **Never commit your `.env` file** — it contains your API keys
- **Your `workspace/` is private** — it contains product context; add it to `.gitignore`
- API keys are read from `.env` only — they are never logged or transmitted elsewhere
- The pipeline makes API calls only to the AI provider you configure (Anthropic, Google, or OpenAI)
