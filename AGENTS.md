# Secret-file boundaries

- Do not read, modify, delete, rename, copy, hash, back up, or print `.env` or `.env.*` files. `.env.example` is the only exception and must contain placeholders, never real credentials.
- Do not inspect secrets through environment dumps, process environments, Python configuration objects, browser requests, debugging, or other indirect paths.
- Do not run the application, paid integration checks, or application imports that load private dotenv configuration without the user's explicit authorization for that operation. Use isolated dummy configuration for tests.
- Put proposed configuration changes in `.env.example` and let the user update private settings manually.
- Respect `.codex/hooks.json` and its policy. Never disable, modify, work around, or bypass a blocked operation, including through scripts, aliases, obfuscated paths, another tool, or another agent.
- If the user wants to change the protection, provide a concrete proposed change for the user to review and apply. Hook trust and activation belong to the user.
- These instructions and local hooks do not constitute OS isolation. Never claim that secret access is technically impossible under unrestricted same-user filesystem permissions.
