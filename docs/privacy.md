# Privacy and data handling

Phase 0 stores one owner password hash, opaque session-token hashes, CSRF-token hashes, and service data in local PostgreSQL/Redis volumes. Raw owner passwords and session tokens are not persisted. Browser cookies are HTTPOnly, SameSite=Lax, and Secure when enabled for HTTPS.

The setup token, CSRF signing secret, database password, and optional OmniRoute key belong only in the ignored local `.env` file or the deployment's protected secret store. Do not commit them or include them in screenshots, support bundles, or shared logs. Request validation errors omit submitted input; unhandled errors log a request ID without request bodies.

Phase 0 does not ingest source content or send prompts to an AI provider. Configure OmniRoute only when a later phase implements a reviewed model call and data-egress policy. Connector source permissions, retention, deletion, and backup encryption will be documented with the phases that add those behaviors.
