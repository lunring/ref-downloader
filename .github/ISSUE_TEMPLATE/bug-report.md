---
name: Bug report
about: Something doesn't download or fails unexpectedly
title: "[BUG] "
labels: bug
---

## Environment

- OS: (e.g. Windows 11 24H2)
- Edge version: (Edge → Settings → About Microsoft Edge)
- Python version: `python --version`
- Project version / commit: (`git log -1 --oneline` or release tag)

## What happened

Run command:

```
python run_ref_downloader.py <DOI> ...
```

## Expected behavior

What did you expect to happen?

## Actual behavior

What happened instead? Paste the relevant console output.

## Reference details

- Parent DOI:
- Failing reference DOI / index:
- Publisher (per `download_report.csv`):
- Status from report (e.g. `manual_pending (auth_redirect)`):

## Logs

Paste the LAST 30 lines of
`<output_dir>/runs/<timestamp>-round-03/events.jsonl` that mention the
failing ref. **Redact any institution-specific URLs** before posting.

```jsonl
(events.jsonl excerpt here)
```

## What you've already tried

- [ ] Closed all `msedge.exe` processes before retrying
- [ ] Verified the failing DOI resolves at `https://doi.org/<DOI>`
- [ ] Checked `config.local.toml` for typos in `[institution]` section
- [ ] Other: ___

## Additional context

Anything else that might help — institutional VPN status, recent publisher
site changes, etc.
