# EXTRACT.md — what came from Science40 / research-4.0

Source branch: `research-4.0` (repo S40-2026beta).  
Target: this package (`identity-core` / MonoIdentity).

## Taken (algorithms rewritten into clean modules)

| S40 source | Symbols / idea | Landed in |
|---|---|---|
| `routes/auth.py` | register → inactive + verify email; confirm; login; logout; forgot/reset anti-enum | `service.py` |
| `routes/models.py` `User` | `set_password` / `check_password` (Werkzeug) | `passwords.py` |
| `routes/models.py` `User` | confirmation/reset token idea | `tokens.py` + `email_tokens` table (not User columns) |
| `routes/models.py` `LoginLog` | slim audit row | `models.LoginLog` |
| `routes/google_oauth.py` (r4.0) | upsert order: `google_id` → email → create; active immediately | `service.upsert_oauth` + `oauth_google.py` |
| `routes/twitter_oauth.py` (r4.0 + dna PKCE) | no-email → complete profile; OAuth2 PKCE transport | `oauth_twitter.py` + `complete_profile` |
| `helpers/rate_limiter.py` | 5/min style limits | `rate_limit.py` (+ Flask routes) |
| `services/auth_security_service.py` | fail count → lockout | `IdentityService._register_failure` |
| `services/email_service.py` | raw send idea only | `mailer.py` (no EmailTemplate ORM) |

## Deliberately omitted

- `routes/twofa.py`, TOTP / backup codes
- `helpers/permissions.py`, `Role` / `Permission` / seed_permissions
- Organization / Project membership & invites
- ELIXIR / LS Login, ORCID, LinkedIn OAuth
- Scientist / counselor / VC registration flows
- Claim protocol
- Hardcoded admin email bypass lists
- Metronic / S40 HTML templates
- `twitter_oauth_new.py` / `twitter_oauth_old.py`
- Platform lock, audit_trail, gamification / UserInvite side-effects
- Hardcoded OAuth client secrets from research-4.0 (env-only here)

## Behaviour changes vs S40

| Topic | S40 | identity-core |
|---|---|---|
| Password min length | register 6 / reset 8 | **8 everywhere** |
| Tokens storage | columns on `User` | `email_tokens` table |
| OAuth without email | placeholder emails (dna) or pending session | `profile_complete=False`, nullable email |
| Auth bypass | admin emails | **none** |
| Primary API | Flask routes | **`service.py`**; Flask optional |
| User PK | integer | UUID string |
| `role_id` / `user_type` | present | **removed** |
