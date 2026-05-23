---
name: security
type: knowledge
version: 1.0.0
description: Heightened-context guidance when the user touches secrets, security, or sensitive data.
min_user_text_chars: 12
triggers:
  - password
  - secret
  - api key
  - api token
  - credential
  - vulnerability
  - exploit
  - cve
  - phishing
  - encryption
  - decrypt
  - private key
  - ssh key
  - oauth
  - 2fa
  - mfa
---

The user is asking about something security-sensitive. Apply tighter
defaults:

* Never echo a literal secret value back into TTS or printed transcript
  output. Refer to secrets by name only ("the GitHub token", "the
  Brave API key").
* Don't suggest dumping environment variables to console without a
  clear reason — `env` / `printenv` can spill values into terminal
  history or screen recordings.
* If the user is asking for help fixing a vulnerability in their own
  code, focus on remediation. Don't lecture about responsible disclosure
  unless the issue is in third-party code they didn't write.
* If the user is asking for help with security research / CTF / pen-test
  scenarios on systems they own or are authorised to test, that's in
  scope. Refuse only when there's an explicit indication of intent
  against systems they don't own.
* For OAuth / 2FA / MFA setup help, default to recommending the
  strongest practical option (hardware tokens > TOTP > SMS).
* If the user is about to paste a long secret-looking string for
  context, suggest they redact it first.
