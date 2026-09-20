# Operator privacy plan

This plan describes how to operate MMA Pick'em under a public brand while
limiting unnecessary disclosure of its creator's personal identity. It is a
privacy and implementation checklist, not legal advice. Requirements vary by
jurisdiction, business structure, users served, and monetization model.

## Objective

Use lawful separation rather than false information:

- The public sees a brand or legal entity and role-based contact details.
- GitHub, the registrar, cloud provider, payment processors, tax authorities,
  and courts receive verified identity where required.
- Public website and package metadata do not unnecessarily expose an
  individual's name, address, or personal email address.

Public pseudonymity is achievable. Complete legal anonymity is not.

## Establish the operating entity

1. Form an LLC, corporation, or other suitable entity after
   jurisdiction-specific review.
2. Obtain the entity's tax identifier, bank account, domain, registered agent,
   legitimate mailing address, and role-based email addresses.
3. Review whether the selected jurisdiction publicly identifies members,
   managers, directors, or organizers.
4. Execute a written assignment transferring the existing source, artwork,
   domain rights, and related intellectual property to the entity.

Do not replace the current copyright owner with an entity until ownership has
actually been assigned. Never provide fabricated identity or address
information to government agencies, financial institutions, registrars,
hosting providers, advertising networks, or legal claimants.

## Privatize and separate GitHub operations

Review forks, releases, packages, and downstream copies before changing
visibility:

```bash
gh repo edit cascadiacollections/mma-api-service \
  --visibility private \
  --accept-visibility-change-consequences
```

Then:

- Keep the repository in a neutral organization controlled by the entity.
- Keep organization membership private where GitHub permits it.
- Restrict repository visibility changes to organization owners.
- Use a role-based domain email or GitHub noreply address for future commits.
- Make associated GHCR packages private.
- Remove or restrict public releases, Actions artifacts, and documentation
  sites that expose source or personal metadata.
- Review deploy keys, GitHub Apps, Actions secrets, and organization access.

Privatization does not erase existing clones, caches, detached public forks,
downloaded packages, or other copies. Previously distributed MIT-licensed
versions remain licensed. Rewriting commit authors can reduce exposure in the
current repository but cannot reliably remove identity from previous copies.

## Remove public identity disclosures

After the entity owns the project, replace personal metadata with the entity or
brand in:

- `LICENSE`
- `pyproject.toml` author metadata
- FastAPI contact metadata in `app/main.py`
- OCI image labels in `Dockerfile`
- Website GitHub and Source navigation links
- Public API documentation
- README and deployment documentation
- Package, image, social-preview, and release metadata

Use role-based contacts such as:

```text
Brand Name LLC
legal@example.com
privacy@example.com
support@example.com
```

If the repository becomes private, remove public Source/GitHub links or point
them to a separate public project-information page.

## Protect domain and infrastructure records

- Register the domain through the entity.
- Enable the registrar's privacy or proxy service.
- Inspect the resulting public record through ICANN RDAP.
- Use role-based registrar, DNS, TLS, and abuse contacts.
- Use organization-owned GitHub and Google Cloud resources.
- Ensure Cloud Run billing, Search Console, DNS, and monitoring access belong
  to the entity rather than depending on a personal account.
- Review certificate-transparency records before creating personally named
  subdomains.

Registrar privacy limits ordinary public lookup but does not hide information
from the registrar, registry, lawful requesters, or dispute proceedings.

## Update public legal notices

Where applicable, identify the entity as the website operator, contracting
party, copyright owner, data controller, advertising publisher, and contact
for legal or privacy requests.

Update the Terms, Privacy, Data Policy, and About pages with accurate entity
and role-based contact information. Infrastructure logs can contain IP
addresses, user agents, timestamps, paths, statuses, and latency even without
accounts. EU and UK rules may require the identity and contact details of the
data controller; a valid entity can generally be identified instead of an
individual operator.

## Treat monetization as an identity boundary

Before enabling AdSense:

- Create the advertising and payments profile under the entity.
- Expect Google to verify the real payee, tax, address, banking, and identity
  information.
- Review Google seller-information visibility.
- Understand that public `ads.txt` exposes the publisher ID.
- Understand that `sellers.json` may expose the payments-profile entity or
  individual name, domain, and publisher ID.
- Use an approved consent management platform where required.

Search Console and Bing verification tokens do not normally identify the
operator publicly, but account ownership remains visible to those providers.

## Avoid unnecessary public legal records

Copyright exists automatically in the United States. Registration is optional
but can provide important enforcement benefits, and registration records are
public. Obtain advice before registering a pseudonymous work or choosing the
claimant and public address.

The U.S. Copyright Office's DMCA designated-agent directory is public. The
current application does not accept user uploads, comments, or other hosted
user content, so registration may not presently be necessary. If user content
is added, consider a qualified third-party designated-agent service.

## Recommended implementation order

1. Obtain advice about entity jurisdiction, public records, privacy, and the
   intended operating regions.
2. Form the entity and establish its registered agent, address, domain, and
   role-based email accounts.
3. Assign the existing intellectual property to the entity.
4. Transfer or recreate GitHub, domain, cloud, and advertising resources under
   entity control.
5. Audit existing public forks, releases, images, caches, and package metadata.
6. Make the repository and GHCR packages private.
7. Replace personal identity references throughout the application and
   deployment metadata.
8. Update public legal documents to identify the entity accurately.
9. Validate RDAP, site metadata, API documentation, image labels, `ads.txt`,
   and `sellers.json` exposure.
10. Enable advertising only after legal, privacy, data-licensing, consent, and
    seller-transparency reviews are complete.

## References

- [GitHub repository visibility](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility)
- [GitHub organization membership visibility](https://docs.github.com/en/organizations/managing-membership-in-your-organization/publicizing-or-hiding-organization-membership)
- [ICANN RDAP](https://www.icann.org/rdap/)
- [Google AdSense seller information](https://support.google.com/adsense/answer/9889911)
- [Google AdSense ads.txt guide](https://support.google.com/adsense/answer/12171612)
- [U.S. Copyright Office public records](https://www.copyright.gov/public-records/)
- [U.S. Copyright Office DMCA directory](https://www.copyright.gov/dmca-directory/)
