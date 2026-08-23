# ADR-004 - Classification rules bundled inside the package

Decision:
Default classification rules live in `src/linux_state/rules/` and are shipped
as package data. User-defined rule directories are loaded *before* the bundled
defaults, giving them higher priority (first match wins).

Reason:
A single canonical location avoids duplicate rule files between the repository
root and the installed package. Bundling makes the CLI work out of the box on
any distribution; the user-override directory satisfies the requirement that
user rules always beat default rules (AGENTS §34) without ever being modified
by the tool.

Consequence:
The `rules/` top-level directory from SPEC §29 is realized inside the package
instead of at the repository root.

Status:
Accepted
