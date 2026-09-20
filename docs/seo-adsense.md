# SEO, custom domain, and AdSense

The application includes the technical primitives needed for search indexing
and optional advertising. These features do not guarantee rankings or AdSense
approval.

## Included SEO surfaces

- `robots.txt` permits crawling and advertises the canonical sitemap.
- API and generated documentation responses send `X-Robots-Tag: noindex,
  nofollow`. They are not blocked in `robots.txt`, so crawlers can see and obey
  that directive instead of retaining URL-only index entries.
- `sitemap.xml` includes the homepage, policy pages, About page, and current
  crawlable event pages.
- `/events/{event_id}` renders fight-card facts without requiring JavaScript.
- Event pages include canonical URLs, Open Graph/Twitter metadata, and
  `SportsEvent` structured data.
- Shared pick URLs use fragments, so personal selections do not create duplicate
  indexed URLs or enter origin logs.
- The homepage includes explanatory editorial content instead of presenting
  only controls and third-party data.
- Optional Google Search Console and Bing Webmaster Tools verification tags are
  server-rendered when configured.
- Optional IndexNow ownership verification and bulk submission support are
  available for Bing and other participating engines.

## Custom domain

1. Deploy the service to Cloud Run using [`cloud-run.md`](cloud-run.md).
2. Choose a domain controlled by the deployment operator.
3. Map the domain using Cloud Run domain mapping, a Google HTTPS load balancer,
   or Cloudflare in front of the Cloud Run service.
4. Configure the required DNS records and wait for TLS issuance.
5. Set `PUBLIC_BASE_URL` to the final HTTPS origin without a trailing slash.
6. Redeploy and verify:

   ```bash
   curl -fsS https://picks.example.com/robots.txt
   curl -fsS https://picks.example.com/sitemap.xml
   ```

7. Add the domain to Google Search Console and Bing Webmaster Tools. DNS
   verification is preferred because it covers the whole domain. If DNS access
   is unavailable, set `GOOGLE_SITE_VERIFICATION` and/or
   `BING_SITE_VERIFICATION` to render their HTML verification tags.
8. Submit `https://picks.example.com/sitemap.xml` in both webmaster consoles.
9. Pick one canonical host (`www` or apex) and redirect the other host to it at
   the DNS proxy or load-balancer layer.

Do not configure `PUBLIC_BASE_URL` to a temporary preview URL once the custom
domain is public, or canonical links and sitemap entries will disagree.

## Google Search Console

- Submit the root sitemap and monitor Page Indexing, Core Web Vitals, HTTPS,
  manual actions, and structured-data reports.
- Use URL Inspection for a small number of important pages after launch or a
  migration. Do not automate repeated inspection or submission requests.
- Keep sitemap URLs canonical, absolute, indexable, and successful. The
  application intentionally omits `priority`, `changefreq`, and speculative
  `lastmod` values because Google ignores or distrusts inaccurate signals.
- Validate event markup with Google's Rich Results Test. Structured data must
  continue to match visible page content.
- Do not use Google's Indexing API for these pages. Google limits that API to
  `JobPosting` pages and livestream `BroadcastEvent` pages embedded in
  `VideoObject`.

## Bing Webmaster Tools and IndexNow

After Bing ownership verification and sitemap submission, IndexNow can notify
participating search engines about changed URLs. Generate a random 8-128
character key containing only letters, numbers, and dashes, then configure:

```bash
gh variable set INDEXNOW_KEY \
  --repo cascadiacollections/mma-api-service \
  --body "replace-with-random-key"
```

The deployed service will expose `https://picks.example.com/<key>.txt` with the
key as its only content. To submit the current canonical sitemap URLs:

```bash
PUBLIC_BASE_URL=https://picks.example.com \
INDEXNOW_KEY=replace-with-random-key \
just indexnow
```

The repository also includes a manually dispatched **Submit IndexNow URLs**
workflow. Use it after material page additions, updates, or removals; do not
schedule repeated unchanged submissions. An HTTP success means the URLs were
received, not that indexing is guaranteed. Review Bing's URL Inspection and
IndexNow reports for the final result.

## AdSense

Advertising is off by default. The application loads no Google advertising
resources unless `ADSENSE_PUBLISHER_ID` is configured.

Before enabling ads:

1. Serve the site from its stable custom domain.
2. Ensure the About, Terms, Privacy, and Data Policy pages accurately describe
   the deployed service.
3. Publish sufficient original, useful content. A functional tool with thin or
   primarily third-party content may still be rejected as low-value inventory.
4. Apply for AdSense and complete domain verification.
5. Configure a Google-certified consent management platform where required,
   including the EEA, UK, and Switzerland.
6. Review Google's publisher, invalid-traffic, placement, and restricted-content
   policies.
7. Never click live ads or encourage users to click them.

Once the domain is approved, set:

```bash
gh variable set ADSENSE_PUBLISHER_ID \
  --repo cascadiacollections/mma-api-service \
  --body "ca-pub-0000000000000000"

# Optional when using a manual responsive ad unit; omit for Auto ads.
gh variable set ADSENSE_SLOT_ID \
  --repo cascadiacollections/mma-api-service \
  --body "0000000000"
```

Redeployment enables the AdSense loader and publishes an `ads.txt` record:

```text
google.com, pub-0000000000000000, DIRECT, f08c47fec0942fa0
```

Verify the production response:

```bash
curl -fsS https://picks.example.com/ads.txt
```

If consent, privacy, licensing, or content requirements are not complete, leave
the AdSense variables unset.

## Monitoring

- Review Search Console indexing and structured-data reports.
- Review Bing Webmaster Tools crawl, sitemap, URL Inspection, and IndexNow
  reports.
- Monitor Core Web Vitals before and after enabling advertisements.
- Watch AdSense policy notifications and invalid-traffic reports.
- Keep event pages useful without ads and avoid layouts that cause accidental
  clicks.
- Re-submit the sitemap after major URL changes; ordinary event additions are
  discovered from the dynamic sitemap.
