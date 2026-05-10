---
name: New publisher request
about: Add support for a publisher not currently covered
title: "[publisher: ] "
labels: new-publisher
---

## Publisher

- Name: (e.g. Cambridge University Press)
- DOI prefix: (e.g. `10.1017`)
- Sample article DOI:
- Sample article URL:

## Access

- [ ] I have institutional access to this publisher
- [ ] Articles are open-access only
- [ ] I'm requesting on behalf of someone with access

## PDF download path

If you've inspected the publisher's article page, paste the CSS selector for
the PDF download link, OR the URL pattern for the direct-PDF route.

Example formats:

```
PDF selector: a.pdf-download-link
or: a[data-track-action="download pdf"]

Direct URL pattern: https://example.com/articles/{doi}/pdf
```

## SI / Supplementary

- [ ] Supplementary downloads needed
- [ ] Supplementary URLs follow a predictable pattern (describe below)

```
SI URL pattern (if known):
```

## Strategy hints

Which existing publisher does this one most resemble (Wiley-style PDFDirect,
Elsevier-style viewer, generic article-page scraping)? Initial guess is
useful even if uncertain.

## Anything special

- JS-driven navigation that breaks generic fallbacks
- Cloudflare / Radware / other challenge pages
- Unusual SSO requirements
- Rate limits or odd quotas

## Willing to test

- [ ] Yes, I can test against a sample PR locally with my institutional access
- [ ] No, I'm just requesting — please ping someone else for verification
