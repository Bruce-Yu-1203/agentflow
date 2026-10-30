# Demo Knowledge Base

`demo_knowledge.json` contains six English sample documents for local development: refunds, order status, account security, technical troubleshooting, membership points, and delivery. The content mirrors the intended customer-support scenarios and includes stable `document_id` values for safe reimport.

The file is a JSON array of `{ "document_id", "title", "content" }` objects. It can be submitted to the planned `POST /knowledge/upload` endpoint as a `.json` file, or its array can be wrapped as `{ "documents": [...] }` for `POST /knowledge/add` once the Python API is implemented.

Seed these documents only in development and only when the knowledge collection is empty. They are fictional policies and operational examples. Production knowledge must be replaced by approved, current policy text and connected business records; a retrieved sample document must never be presented as proof that a particular order, payment, or account action occurred.
