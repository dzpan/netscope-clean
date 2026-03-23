# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in NetScope, please report it responsibly.

**Email:** security@netscope.dev

Please include:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge your report within 48 hours and aim to provide a fix or mitigation within 7 days for critical issues.

## Scope

The following are in scope for security reports:

- Authentication bypass or token leakage
- SSH credential exposure (stored credentials, logs, API responses)
- Command injection via playbook execution or VLAN change engine
- Unauthorized access to device configurations or audit logs
- API endpoints accessible without proper authentication

The following are **out of scope**:

- Vulnerabilities in upstream dependencies (report these to the relevant project)
- Issues requiring physical access to the server
- Social engineering attacks

## Supported Versions

Security fixes are applied to the latest release on `main`. We do not backport fixes to older versions.
