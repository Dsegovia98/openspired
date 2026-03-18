# GLOBAL RULES — {{PRODUCT_NAME}}
## Scope: Universal | Maintained by: Product Owner

> These rules apply to ALL agents in every pipeline run.
> Edit this file to reflect your product's non-negotiable conventions.

---

## Platform
- **Primary platform:** {{PLATFORM}}  (e.g. Web Desktop, Mobile, API-only)
- **No development for:** {{EXCLUDED_PLATFORMS}}

## User Roles
{{ROLES_DESCRIPTION}}
<!-- Example:
- **BASIC:** View-only access. Cannot create or edit.
- **FULL:** Full access. Can create, edit, and configure.
-->

## Output Format
- All tickets are bilingual: English first, then Spanish.
- Plain text only — no Jira markup tags ({panel}, {color}, etc.).
- Separator between languages: `════════════════════════════════ ESPAÑOL ════════════════════════════════`
- Max 6 acceptance criteria per block.
- Max 3 critical flows per ticket.

## Domain Conventions
{{DOMAIN_CONVENTIONS}}
<!-- Add any product-specific rules agents must always follow. Examples:
- Empty states must include an actionable CTA.
- Audit logs only for transactional actions (create, edit, delete).
- Never reference external communication tools other than {{COMMUNICATION_TOOL}}.
-->
