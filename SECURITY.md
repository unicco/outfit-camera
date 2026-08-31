# Security Policy

## Supported Versions

We currently support the following versions with security updates:

| Version | Supported          |
| ------- | ------------------ |
| Latest  | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly:

### How to Report

1. **Do not** create a public GitHub issue for security vulnerabilities
2. Send a detailed report to the maintainers via private communication
3. Include as much information as possible:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Initial Response**: We aim to acknowledge vulnerability reports within 48 hours
- **Investigation**: We will investigate and validate the reported vulnerability
- **Resolution**: If confirmed, we will work on a fix and coordinate disclosure
- **Credit**: We will acknowledge your contribution (unless you prefer to remain anonymous)

### Security Best Practices

When using this project:

- Keep dependencies up to date
- Use environment variables for sensitive configuration
- Follow the principle of least privilege
- Regularly review and rotate API keys and credentials

## Security Features

This project includes:

- Environment variable management via `.env` files (not tracked in git)
- Direct Python execution for consistent security configurations
- Dependency management through Poetry with lock files

Thank you for helping keep this project secure!
