# Customer Support Skills

These English Skills supply role-specific procedures to the planned Python Skill loader. They are operational instructions, while the knowledge collection supplies reference facts. The loader should scan `skills/<name>/SKILL.md`, parse the simple front matter, match `agents` and case-insensitive `keywords`, and inject only matching content into that role's system prompt. A Skill cannot grant tool access or override system-level permissions.

| Skill | Agent | Purpose |
| --- | --- | --- |
| `general_customer_service/SKILL.md` | `general` | Reception, clarification, order questions, complaints, and handoff preparation |
| `technical_support/SKILL.md` | `technical` | Reproducible diagnosis, error codes, API and deployment issues, and escalation |
| `billing_support/SKILL.md` | `billing` | Payment, refund, invoice, subscription, and financial review boundaries |

Each file uses `name`, `description`, comma-separated `keywords`, `agents`, and `enabled` fields in front matter. The planned `/skills` endpoint should show loaded metadata and parse errors; `/skills/reload` should rescan the directory without restarting the service. Escalation is handled by the deterministic Escalation role and its handoff-summary tool.
