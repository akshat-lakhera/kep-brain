# Security policy

## Reporting a vulnerability

Report vulnerabilities privately through GitHub: open the repository's Security tab and choose "Report a vulnerability" (private vulnerability reporting). Please do not open a public issue for a security problem.

Include the affected route or component, the steps to reproduce, and the impact you observed. The maintainer will acknowledge the report and follow up in the same thread.

## Scope

- The API (`apps/api`), the MCP server, the web app (`apps/web`) and the deployment files in `deploy/`.
- Secrets belong in `.env`, which is not tracked. If you find a committed credential, report it the same way.

## Supported versions

Only the `main` branch is maintained.
