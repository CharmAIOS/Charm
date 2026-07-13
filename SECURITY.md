# Security Policy

## Supported Versions

Charm is preparing its first formal open-source release process. Until the version support policy is finalized, security fixes target the latest maintained branch and the latest published package version.

## Reporting a Vulnerability

Please do not report security vulnerabilities through public GitHub issues.

To report a vulnerability, contact the Charm team privately:

- Email: <team@charmos.io>
- Discord: use a private message with a maintainer if email is unavailable

Include:

- A description of the issue.
- Affected package, service, or repository.
- Reproduction steps or proof of concept.
- Expected impact.
- Any known mitigations.

## Response Expectations

Initial response target: 3 business days.

After triage, the team will coordinate:

- severity,
- remediation plan,
- disclosure timing,
- release or deploy plan,
- credit, if applicable.

## Scope

Security-sensitive areas include:

- authentication and authorization,
- billing and wallet flows,
- secret handling,
- OAuth integrations,
- runner sandboxing,
- deployment workflows,
- package publishing,
- database policies and migrations.
