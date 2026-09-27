# Security

## Reporting a problem

Please do not open a public issue for a security bug. Use GitHub's
[private vulnerability reporting](https://github.com/PabloTheThinker/hermes-studio/security/advisories/new)
instead. You will get an answer within a few days.

## How Hermes Studio is built to stay safe

- **Local only.** The desk listens on `127.0.0.1` and refuses any other address unless
  `HERMESCLIP_ALLOW_REMOTE=1` is set. To reach it from your other devices, put it behind
  `tailscale serve` (tailnet only). Do not expose it to the public internet: it has no login.
- **Browser attacks.** The desk only answers requests whose `Host` is loopback, a
  `*.ts.net` name, or one you list in `HERMESCLIP_ALLOWED_HOSTS` (this stops DNS rebinding).
  Every write must be `application/json`, and a browser `Origin` must match the host
  (this stops cross-site requests from other tabs). Pages carry a strict Content Security
  Policy, and the desk cannot be framed.
- **Files.** Media is served only from the library, by exact job id and file name. Paths
  that climb out of the library are refused.
- **Commands.** ffmpeg and yt-dlp are run with argument lists, never a shell. Sources are
  passed after `--` so a link can't be read as a flag.
- **Network.** Outbound calls (optional AI naming, oEmbed titles) accept `http(s)` URLs only
  and cap the reply size. Nothing is uploaded and nothing is posted.
- **Supply chain.** CI actions are pinned to commit SHAs. Dependabot watches pip and Actions.
  A secret scan runs on every pull request. `main` is protected: changes land through
  reviewed pull requests with passing checks.
