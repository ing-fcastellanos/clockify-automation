# Security policy

## Supported versions

`jira-clockify-sync` follows [Semantic Versioning](https://semver.org/). Only
the latest released version on PyPI receives security fixes.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security problems.**

Use GitHub's private vulnerability reporting:

1. Go to the [Security advisories page](https://github.com/ing-fcastellanos/clockify-automation/security/advisories/new).
2. Click **Report a vulnerability**.
3. Describe the issue, the affected version(s), and a reproducer if you have
   one. Redact any tokens, credentials, or workspace IDs.

If you can't use GitHub for any reason, email
[ing.fcastellanos@gmail.com](mailto:ing.fcastellanos@gmail.com) with the same
information and "SECURITY" in the subject.

## What to expect

- Acknowledgement within **5 business days**.
- A first assessment (confirmed / not reproducible / out of scope) within
  **14 days**.
- For confirmed issues: a fix and a coordinated release. You will be credited
  in the release notes unless you ask to remain anonymous.

## Out of scope

- Vulnerabilities in JIRA Cloud, Clockify, or any third-party service the tool
  talks to. Report those to the upstream provider.
- Misconfiguration of `.env` (leaked tokens, world-readable files) — that is a
  responsibility of the user's environment, not of this package.
- Issues that require an attacker to already have write access to the user's
  shell, filesystem, or PyPI account.
