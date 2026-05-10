# Security Considerations

## Browser profile access

`download_refs.py` launches Microsoft Edge with your **persistent user
profile** (`%LOCALAPPDATA%\Microsoft\Edge\User Data\Default` by default, or
the path in `config.browser.edge_profile_dir`). This profile contains:

- Cookies (including authenticated sessions to any site you've signed into)
- Saved passwords (if you've stored any in Edge)
- Browsing history
- Extensions and their stored data

The script is automated, but the browser it drives is **the same Edge that
holds your daily-driver state**. A bug, a malicious page, or an unexpected
publisher script could in principle interact with that state.

### Recommendation: dedicated Edge profile

Create a separate Edge profile for this tool:

1. Open Edge → click your profile picture (top-right) → "Add profile"
2. Sign into your institutional / library access in the new profile only
3. Find the new profile's path under
   `%LOCALAPPDATA%\Microsoft\Edge\User Data\Profile N`
4. Set `browser.edge_profile_dir` in `config.local.toml` to that directory:

```toml
[browser]
edge_profile_dir = "C:\\Users\\YourName\\AppData\\Local\\Microsoft\\Edge\\User Data\\Profile 1"
```

This way, the worst-case blast radius of any browser-driven exploit is the
data in that one dedicated profile.

## Credentials in config files

`config.local.toml` is in `.gitignore` from the start. **Do not commit it.**

- `crossref.mailto` is public-by-design: Crossref publishes mailto identifiers
  in its query logs and API analytics.
- `zotero.db_path` reveals your local filesystem layout.
- `[institution]` contents may identify your employer / university.

If you fork this repo and accidentally commit `config.local.toml`, treat any
contained values as compromised:

- Rotate any authentication paths the file exposed
- Force-push a commit that removes the file (and consider that the previous
  state may already be cached publicly)

## Reporting a vulnerability

Please **do not** file a public issue for an unpatched security issue.

Open a private security advisory on GitHub
(`Security` tab → `Report a vulnerability`), or contact the repository owner
via the email in their GitHub profile.

For non-critical hardening suggestions (config-handling improvements, sandbox
options, etc.), regular issues / PRs are fine.

## What this tool does NOT do

For clarity:

- It does not store or transmit your credentials.
- It does not bypass paywalls or DRM.
- It does not exfiltrate your browsing history.
- It does not run code from third parties beyond the publisher pages it
  visits as part of normal download flow.

The Playwright dependency does fetch a Chromium binary at install time
(`playwright install msedge` configures it to use your system Edge instead).
That binary comes from `https://playwright.azureedge.net` — review the
Playwright project's distribution if that's a concern in your environment.
