# Round 2 · Reviewer B1 — Azure billing fact-check, part 1 (raw report)

> **Status: RAW — verbatim as returned.** Agent type `cloud-solution-architect`, read-only, 2026-10-31. Brief: fact-check against current Microsoft documentation every Azure billing claim in the 34-case gallery (`03-estate-and-investigation.md` §14), the Cost Grammar and commercial-layer table (`02-learning-azure.md` §2 and §9) and the Azure statements in the north star (v4 revision, commit `cbd6756`). The orchestrator's spot-checks are appended at the end; the disposition is in [disposition.md](disposition.md).

---

# R2-B1: Azure billing fact-check, part 1 (read-only; no files changed)

**Summary** (79 claims checked; n/a means the row has no Azure-specific claim)
1. **Confirmed: 47.**
2. **Partly: 13**: B1-11, 12, 28, 30, 41, 44, 45, 47, 51, 57, 61, 67, 72.
3. **Wrong: 4**: B1-06, 26, 69, 73.
4. **Outdated: 0.** I found no retired service and no preview stated as GA. The Linux Consumption 2028 and AI Search serverless-preview statements are hedged correctly.
5. **Overgeneralised: 8**: B1-10, 13, 14, 20, 37, 38, 49, 76.
6. **Unverifiable: 0 whole claims** (unverified sub-claims are in the last section). **n/a: 7**: B1-16, 17, 18, 32, 33, 34, 77.

**Conventions**
- F3 = `<repo>\docs\03-estate-and-investigation.md`. Gallery rows r1–r34 are B1-01 to B1-34.
- F2 = `<repo>\docs\02-learning-azure.md`.
- F1 = `<repo>\docs\01-north-star.md`.
- S1–S54 are the pages I fetched; the full URLs are in the source key at the end.
- I checked every quote by machine against the fetched page text. Apostrophes may be typographic in the originals.
- OV = already verified by the orchestrator, so I checked wording only.
- T# = see "Top 10 corrections".
- The repo names few services. Each verdict applies to the Azure service the description most plausibly means.

## A. F3 §14 gallery (B1-01 to B1-34)

| ID | Claim | Verdict | Evidence and fix |
|---|---|---|---|
| B1-01 | r1 "A fleet of Windows VMs runs at the licence-inclusive rate" | Confirmed | S26 "active Software Assurance or qualifying subscription licenses." |
| B1-02 | r2 "would free a reservation benefit that simply moves to another VM" | Confirmed | S28 "automatically applies to another matching resource in the specified scope"; S1 "less expensive (based on retail rates)" |
| B1-03 | r3 "A savings plan bought in January sits 30% unused through every August lull" | Confirmed (premise; figures hypothetical) | S30 "Unused commitment for an hour expires and doesn't roll over." |
| B1-04 | r4 "A reservation for an instance family the platform team is migrating away from in Q3" | Confirmed (premise) | S28 "You can't carry forward unused reserved hours." Exchange limits: OV |
| B1-05 | r5 "its database did not — every request now crosses regions" | Confirmed | S3 "Between regions within Europe $0.02 per GB" |
| B1-06 | r6 "Backups replicated to three regions when the recovery plan names one" | **Wrong** | S22 "continue to use the default geo-redundant storage (GRS)"; S23 "restore Azure VMs in a secondary region, which is an Azure paired region". Native options reach one paired region, not three. Fix: T2 |
| B1-07 | r7 "peaking at 8% of its capacity ever since" | Confirmed (8% hypothetical) | S21 "You can purchase 1, 2, 4, 8 or 16 messaging units for each Service Bus Premium namespace." |
| B1-08 | r8 "A GPU pool kept warm between training runs that are two weeks apart" | Confirmed | S10: deallocated is "Not billed"; stopped-but-allocated is billed |
| B1-09 | r9 "A data-engineering cluster with no auto-termination, still attached on Sunday" | Confirmed (mechanism) | S24 "specify an inactivity period in minutes after which you want the compute resource to terminate." Default value UNVERIFIED |
| B1-10 | r10 "Versioning, soft delete and snapshots compounding on a very large analytics container" | **Overgeneralised** | S12 "Storage accounts with a hierarchical namespace enabled for use with Azure Data Lake Storage aren't currently supported." Fix: T5 |
| B1-11 | r11 "A container registry holding images from thousands of CI builds that nobody can pull" | Partly | S16 "A retention policy for untagged manifests is currently a preview feature of container registries with the Premium pricing plan." Fix: "…that nobody can pull; the built-in retention policy covers untagged manifests only (a Premium preview feature), so tagged CI images need their own clean-up." |
| B1-12 | r12 "Private endpoints whose target services were deleted months ago" | Partly | S6 "should be deleted for cleanup". An hourly endpoint meter is documented (S5). That a disconnected endpoint keeps billing is inferred, not stated. Fix: "Private endpoints (billed per hour while they exist) whose target services were deleted months ago" |
| B1-13 | r13 "Managed disks and public IPs from deleted VMs" | **Overgeneralised** | S11 "will continue to incur charges as applicable." That applies to detached resources only. Fix: "Managed disks and public IPs left behind by deleted VMs (delete behaviour is set per resource: CLI-created VMs detach the OS disk by default, while the portal offers Delete with VM)" |
| B1-14 | r14 "A default that switched on zone redundancy in the dev copy of a production template" | **Overgeneralised** | S51 "there's an extra cost for your SQL managed instance and for zone-redundant backups."; S52 "you can enable it at no extra cost" (Premium and Business Critical); S53 "Your App Service plan must have a minimum of two instances for zone redundancy." Fix: T10 |
| B1-15 | r15 "Geo-replication enabled on a registry for a region with no consumers" | Confirmed | S14 "Storage is billed per geo-replica"; S15 "per replicated region" |
| B1-16 | r16 "A database tier chosen for one premium feature that nobody uses" | n/a | No Azure claim |
| B1-17 | r17 "A plan tier chosen just above its free allowance" | n/a | Generic. Example allowance scope: S20 "per month per subscription" |
| B1-18 | r18 "A service in preview pricing goes to paid on 1 March; nine of fourteen estates use it" | n/a (hypothetical) | Optional real analogue: S32 "Billing for the Serverless Developer tier began on September 13, 2026." |
| B1-19 | r19 "Function apps on Linux Consumption: the plan retires in 2028" | Confirmed | Date OV. S19 "Flex Consumption is a Linux-based Azure Functions hosting plan". Optional precision: "retires on 30 September 2028" |
| B1-20 | r20 "A job that starts and stops hundreds of times a day, each start paying a started-hour minimum" | **Overgeneralised** | S8 "A partial hour is billed as a full hour." (firewall) versus S17 "on a per-second basis" (Container Apps). The quantum is per meter. Fix: T10 |
| B1-21 | r21 "Private connectivity that added a per-GB processing meter nobody modelled" | Confirmed | S5 "Data Transfer pricing still applies to data transfer."; meter "Outbound Data Processed" |
| B1-22 | r22 "A retry loop in an AI agent that quadruples token spend after a prompt change" | Confirmed (pay-as-you-go premise) | S50 "Inference: Per 1,000 tokens (input and output) when the model is called." The same page puts provisioned throughput outside standard-deployment costs. Optional: add "on pay-as-you-go deployments" |
| B1-23 | r23 "A model swapped for a larger one in a configuration change" | Confirmed | S50, same page |
| B1-24 | r24 "A monthly spending limit that, once reached, takes an agent offline for the rest of the month" | Confirmed (shorthand) | S35 "This limit applies to active flow only". The limit is in AAUs and always-on billing continues. Optional: "A monthly AAU limit that … while the always-on charge continues" |
| B1-25 | r25 "Agents created for a trial and forgotten, billing always-on since creation" | Confirmed | S35 "Always-on billing continues from agent creation until the agent is deleted"; row "Stop agent Stops Still billed". Optional: add "stopping is not enough; only deleting stops it" |
| B1-26 | r26 "Cross-zone chatter between a chatty service pair that autoscaling spread across zones" | **Wrong** | S2 "Azure doesn't charge for data transfer between availability zones in the same region, whether you use private or public IP addressing." Fix: T1 |
| B1-27 | r27 "A consumption commitment tracking 11% short at year-end, while eligible spend sits outside the billing account" | Confirmed | OV (MACC is tracked on the billing account); wording faithful |
| B1-28 | r28 "Two similar marketplace purchases — only one counts toward the commitment" | Partly | S27 "purchases made directly on Microsoft Marketplace via credit card do not contribute to your MACC." Eligibility is the offer's "Azure benefit eligible" badge plus how it is bought and paid. Fix: add "(eligibility depends on the offer's Azure benefit eligible badge and on how it is bought and paid for)" |
| B1-29 | r29 "A quarter of the bill is untagged" | Confirmed | S54 "Tags are widely used to group costs to align with different business units, engineering environments". A native lever exists: tag inheritance |
| B1-30 | r30 "Production-priced licences in a non-production subscription that qualifies for dev/test rates" | Partly | S37 "The offer enables active Visual Studio subscribers to run development and testing workloads on Azure at special Dev/Test rates."; S38 "don't carry a financially backed SLA". Fix: T6 |
| B1-31 | r31 "The same SKU at a lower list price in a neighbouring region" | Confirmed | S43 "Use the API to explore prices for Azure services against different regions and different SKUs." |
| B1-32 | r32 "A seven-year retention policy on a dataset whose legal requirement is ninety days" | n/a | Policy example |
| B1-33 | r33 "Cost per order fell 18% while the bill rose 9%" | n/a | Arithmetic example |
| B1-34 | r34 "A cache that lets the database drop two tiers" | n/a | Design example |

## B. F2, F3 and F1 claims (B1-35 to B1-79)

| ID | Claim | Verdict | Evidence and fix |
|---|---|---|---|
| B1-35 | F2 §2 grammar, Capacity: "a *floor*: some services bill a minimum even at zero" | Confirmed | S18 "The minimum for every Premium plan is at least one instance." |
| B1-36 | F2 Consumption: "an *idle rate* that is not zero" | Confirmed | S17 "When a revision is scaled to zero replicas, no resource consumption charges are incurred." |
| B1-37 | F2 Multiplier: "adding one to each of two dimensions quadruples the bill" | **Overgeneralised** | S33 "R × P = SU". True only for 1×1 → 2×2; from 2×2 to 3×3 it is 2.25×. Fix: T7 |
| B1-38 | F2 Tier/step: "a tier you can never leave" | **Overgeneralised** | S49 "You can't scale from a higher pricing tier to a lower pricing tier." That is service-specific. Fix: "a tier that some services will not let you step back down from" |
| B1-39 | F2 Commitment: "right-size the next term, re-scope, exchange where allowed" | Confirmed | S39 refund cap "can't exceed USD 50,000 in a 12-month rolling window"; "All pre-purchase plans" are listed among the non-exchangeable reservations. Exchange policy: OV |
| B1-40 | F2 Coupling: "private connectivity, diagnostics and replication traffic" | Confirmed | S14 "cross-region data transfer charges still apply when ACR replicates pushed content to other geo-replicas"; S5. Diagnostics not sourced |
| B1-41 | F2 Allowance: "allowances are often per subscription, per month, per region" | Partly | S20 "monthly free grant of 250,000 executions and 100,000 GB-s of resource consumption per month per subscription". No region-scoped allowance found. Fix: "allowances are often per subscription and per month — check each service's scope" |
| B1-42 | F2 Rate and benefit: "discount structures differ by agreement" | Confirmed | S39 "a CSP customer can't exchange, cancel, renew, or refund a reservation themself" |
| B1-43 | F2 §2 decodes: "always keeps at least one instance warm" | Confirmed | S18 |
| B1-44 | F2 decodes: "today the documented path is Flex Consumption, because Linux Consumption retires in September 2028" | Partly | Date OV. S19 "Flex Consumption is a Linux-based Azure Functions hosting plan", so Windows apps cannot take this path. Fix: T9 |
| B1-45 | F2 decodes: "bills an *idle* rate when a minimum replica count is above zero" | Partly | S17 "Idle usage charges don't apply to serverless GPU apps." Fix: "bills an *idle* rate on the Consumption plan when a minimum replica count is above zero (serverless GPU apps excepted)" |
| B1-46 | F2 decodes: "set the minimum to zero where latency allows" | Confirmed | S17 |
| B1-47 | F2 decodes: "billed by replicas × partitions (a serverless preview bills consumption instead, and the two cannot be converted)" | Partly | S32 "The Serverless Developer tier doesn't support migration to or from other pricing tiers"; "provided without a service-level agreement and isn't recommended for production workloads." The multiplication is confirmed by S33. Fix: T9 |
| B1-48 | F2 decodes: "A file-transfer option on storage that bills hourly while enabled" | Confirmed | S13 "Enabling SFTP has an hourly cost." |
| B1-49 | F2 decodes: "Object versioning plus soft delete plus snapshots on the same data" | **Overgeneralised** | S12, as B1-10. Fix: T5 |
| B1-50 | F2 decodes: "A managed firewall: billed while it is allocated — deallocating it stops the billing" | Confirmed (OV; wording faithful) | S7 "When stopping and starting the firewall, billing stops and starts accordingly." and "the private IP address might change". Optional: add the IP caveat |
| B1-51 | F2 decodes: "A NAT gateway: documented hourly and data-processing charges, and no stopped state — only removal stops them" | Partly | S9 "NAT gateways incur hourly charges and data processing costs." No Learn page documents a stop operation; only a Q&A answer says so. Fix: "A NAT gateway: documented hourly and data-processing charges; no stop operation is documented, so removal is the lever" |
| B1-52 | F2 decodes: "own units *layered* on top of the compute underneath" | Confirmed | S25 "virtual machines (VMs) provisioned in clusters and Databricks Units (DBUs)" |
| B1-53 | F2 decodes: "A capacity that can be paused, where pausing stops compute but storage keeps billing" | Confirmed | S41 "You won't be charged for compute resources while the database is paused. However, you will continue to be charged for storage." (Synapse); S42 "storage costs remain billed to Capacity1" (Fabric) |
| B1-54 | F2 laws: "A per-hour meter usually starts at provisioning, not at first use." | Confirmed | S8 "A fixed hourly fee will be charged per a firewall deployment regardless of scale." |
| B1-55 | F2 laws: "Billing granularity differs by meter — per second, prorated, or per started hour" | Confirmed | S17 "on a per-second basis"; S8 "A partial hour is billed as a full hour." |
| B1-56 | F2 laws: "A thing that is stopped but not released often keeps its most expensive meter." | Confirmed | S10 "Some Azure resources, such as Disks and Networking continue to incur charges."; stopped-but-allocated VMs stay billed |
| B1-57 | F2 laws: "Retention policies compound: each protective feature added to the same data multiplies its stock." | Partly | S12 "you are billed for unique blocks of data across that blob, its versions, and any snapshots it might have". Fix: "Retention policies compound: each protective feature keeps changed or deleted data for its own period, so the stock grows with churn × the longest retention, not once per feature." |
| B1-58 | F2 §3: "unauthenticated, all meters, by region and SKU"; "prices in a base currency" | Confirmed | S43 "an unauthenticated experience to get retail rates for all Azure services"; "Example calls filtered for compute with currency in euro" (USD by default; a currencyCode parameter converts) |
| B1-59 | F2 §3: "(including the open FOCUS dataset where the agreement and scope support it)" | Confirmed | S44 "using the open-source FinOps Open Cost and Usage Specification" |
| B1-60 | F2 §3: "property changes are queryable for 14 days, platform metrics are kept for about 93 days" | Confirmed | S46 "View the last 14 days of resource configuration changes to see which properties changed and when."; S47 "Platform and custom metrics are stored for 93 days with the following exceptions" |
| B1-61 | F3 §1: "Azure itself retains property changes for just 14 days and platform metrics for about 93" | Partly | S48 "Azure retains activity log events for 90 days and then deletes them." Fix: T8 |
| B1-62 | F2 §6: "4 AAUs per agent-hour, from the moment an agent is created until it is deleted" | Confirmed | S35 "Always-on billing continues from agent creation until the agent is deleted" (OV); the "Stop agent" row stays "Still billed" |
| B1-63 | F2 §6: "the page notes new customers can evaluate with the always-on charge waived" | Confirmed | S35 "New customers can evaluate SRE Agent that waives the always-on cost." |
| B1-64 | F2 §6: "about 3.8 AAUs on one model and about 1.3 on another" | Confirmed | S35 quick-question row: ~3.8 (Claude Opus 4.6) and ~1.3 (GPT 5.3 Codex) |
| B1-65 | F2 §6: "covers active flow only; at the limit the agent becomes unavailable until next month, and always-on charges continue" | Confirmed (faithful) | S35 "This limit applies to active flow only". The same page's portal label says "combined always-on and active flow allocation", so tie the wording to the billing page |
| B1-66 | F2 §9 Agreement type: "who can see the price sheet, how export and data latency differ, who may exchange or refund" | Confirmed | S40 "Depending on the policies set for your organization by the Enterprise Admin, only certain"; S34 "typically available in Cost Management within 8-24 hours" (pay-as-you-go up to 72); S39 CSP quote (B1-42) |
| B1-67 | F2 §9 Price level: "list → contracted → effective (after commitments); the pricing currency and the billing currency" | Partly | S36 "represents the actual rate that you end up paying per unit". PricingCurrency and ExchangeRatePricingToBilling are listed as MCA fields. Fix: "…; on MCA, a pricing currency and a billing currency" |
| B1-68 | F2 §9 Commitments: "hourly benefits (reservations, savings plans; an unused hour does not roll over), pooled prepurchases, and agreement-level consumption commitments" | Confirmed | S29 "can't be rolled over to another hour."; S28 "You can't carry forward unused reserved hours." Learn's term for prepurchases is "pre-purchase plans" (S39) |
| B1-69 | F2 §9 Rate levers: "licence benefits, dev/test pricing, spot capacity, capacity reservations, credits and free grants" | **Wrong** (capacity reservations) | S31 "Reserved Instances provide a billing discount only and don't guarantee capacity."; capacity reservations are "priced at the same rate as the underlying VM size". Fix: T3 |
| B1-70 | F2 §9: "and the order in which they stack" | Confirmed | S29 "Because reservation benefits are more restrictive than savings plan benefits" (reservations apply first) |
| B1-71 | F2 §9 Price mechanics: "graduated tiers, free allowances, billing quantum, currency conversion, tax" | Confirmed (general) | Consistent with S3, S20, S8 and S36; not individually quoted |
| B1-72 | F2 §9 Non-resource charges: "marketplace and SaaS purchases, support plans" | Partly | Marketplace: S27. Support plans UNVERIFIED (not fetched) |
| B1-73 | F2 §9 Network paths: "egress, cross-region, inter-zone and private-connectivity processing" | **Wrong** (inter-zone) | S2 quote (see B1-26). Fix: T1 |
| B1-74 | F2 §9 Views: "actual versus amortised cost" | Confirmed | S45 "Reservations – Source data is from amortized usage and charges." |
| B1-75 | F1 line 136: "own documentation says its VM savings are computed at retail rates and ignore existing commitment coverage" | Confirmed | S1 "less expensive (based on retail rates)"; "The recommendations don't take into account the presence of Reserved Instances (RI) / Savings plan purchases." |
| B1-76 | F1 worked investigation: "traffic that crosses regions is billed, traffic inside a region is not" | **Overgeneralised** | S2 (zones are free); S4 "Ingress and egress traffic is charged at both ends of the peered networks."; S5 processing meters; S3 inter-region rates vary by geography. Fix: T4 |
| B1-77 | F1: "about €2,300 a month" | n/a (illustrative) | At S3's intra-Europe rate (USD 0.02/GB) that implies about 115 TB a month of cross-region traffic. Fine if flagged illustrative |
| B1-78 | F1: "the bill itself lags by hours to days" | Confirmed | S34 "typically available in Cost Management within 8-24 hours"; pay-as-you-go "it could take up to 72 hours" |
| B1-79 | F3 §11: "storage in the second region, replication traffic between regions, a higher-priced SKU that the feature requires" | Confirmed | S14 "Storage is billed per geo-replica"; S15 geo-replication is Premium-only and priced "per replicated region" |

## Top 10 corrections by embarrassment risk (paste-ready)

**T1. Inter-zone traffic is not charged (B1-26, B1-73; Wrong).** S2 says Azure doesn't charge for data transfer between availability zones in the same region.
- Where: F3 §14 r26 and F2 §9 "Network paths".
- Replace r26 with: "Chatty traffic between a service pair that a redesign put in two peered virtual networks". Keep the "why" cell as written.
- Replace §9 with: "egress, cross-region, peering and private-connectivity processing — priced by *path*, not by resource".

**T2. Backups in "three regions" (B1-06; Wrong).** Where: F3 §14 r6. Replace with: "Backups left on geo-redundant storage (a second, paired region) when the recovery plan names only one region".

**T3. Capacity reservations are not a rate lever (B1-69; Wrong).** Where: F2 §9 "Rate levers" and "Commitments".
- Rate levers become: "licence benefits, dev/test pricing, spot capacity, credits and free grants — and the order in which they stack".
- Add to Commitments: "capacity reservations (a capacity guarantee priced like the underlying VM, not a discount; they can be combined with reserved instances for term discounts)".

**T4. "Traffic inside a region is not" billed (B1-76).** Where: F1 "A worked investigation", first blockquote paragraph. Replace with: "traffic that leaves a region is billed per GB (the rate depends on geography), traffic between availability zones in a region is not, and traffic inside a region can still be billed where it crosses a VNet peering, a private endpoint, a NAT gateway or a firewall".

**T5. Versioning and snapshots on analytics storage (B1-10, B1-49).** Versioning is unsupported on hierarchical-namespace accounts (S12).
- F3 r10 becomes: "Versioning, soft delete and snapshots compounding on a very large flat-namespace blob container (versioning is not supported on hierarchical-namespace accounts, so check the account type first)".
- F2 decode becomes: "Object versioning plus soft delete plus snapshots on the same data (versioning is unsupported on hierarchical-namespace accounts)".

**T6. Dev/test eligibility (B1-30).** Where: F3 r30. Replace with: "Non-production workloads at production rates because the subscription is not on a Dev/Test offer, although the team holds active Visual Studio subscriptions (Dev/Test rates need an EA or MCA Dev/Test subscription, carry no financially backed SLA, and the EA offer is not available in Azure Government)". Evidence: S37, S38 and S34's offer table, which lists an MCA "Microsoft Azure Plan for Dev/Test". S37 also states the Government limit.

**T7. Multiplier arithmetic (B1-37).** Where: F2 §2 grammar, Multiplier cell. Replace with: "doubling both dimensions quadruples the bill (1 × 1 → 2 × 2); from 2 × 2, adding one to each gives about 2.25×".

**T8. Retention window (B1-61).** Where: F3 §1. Replace with: "Azure keeps resource property changes in Resource Graph for 14 days and platform metrics for about 93 days; the Activity Log keeps control-plane events for 90 days." Who-changed-what evidence outlives the property diff.

**T9. SKU-scoped statements stated as universal (B1-44, B1-47).** Where: F2 decodes.
- Flex: "today the documented path for Linux apps is Flex Consumption (Linux-only), because Linux Consumption retires on 30 September 2028".
- AI Search: "billed by replicas × partitions (a serverless preview bills consumption instead; its Developer tier has no SLA and cannot be migrated to or from other tiers)".

**T10. Zone redundancy cost and hour quantum are per service (B1-14, B1-20).** Where: F3 r14 and r20.
- r14: "A default that switched on zone redundancy in the dev copy of a production template — an uplift on some services (SQL Managed Instance, the extra instances an App Service plan needs) and free on others (SQL Database Premium and Business Critical)".
- r20: "A job that deploys and deallocates a firewall (or stops and starts a SQL Managed Instance) hundreds of times a day, each start paying a started-hour minimum".

## Claims I could not verify and why

- **NAT gateway "no stopped state" (B1-51).** No Learn page documents a stop operation or says removal is the only lever. Only a Microsoft Q&A answer says so, and I treated that as non-authoritative.
- **Databricks default auto-termination (B1-09).** The page I fetched states no default.
- **VM compute billing granularity.** I found no current authoritative statement.
  - The Linux VM pricing FAQ still says "We charge for the number of full minutes your virtual machine is running" (legacy text).
  - A Q&A thread (an MVP answer; a second MVP says no official page exists) alleges a 5-minute minimum from 1 June 2025. I could not confirm it.
  - Do not state VM granularity as fact. The repo's generic law (B1-55) is safe.
- **Region-scoped free allowances (B1-41), diagnostics as a coupling meter (B1-40), and the price-mechanics list (B1-71).** I found no source in this pass.
- **Support plans as a non-resource charge, and spot VMs as a rate lever (B1-72, B1-69).** I did not fetch these.
- **A disconnected private endpoint still billing (B1-12).** Inferred from the hourly meter; Learn does not say so.
- **Azure Hybrid Benefit being applied per resource rather than automatically (B1-01).** I found no statement either way.
- **Azure SRE Agent GA or preview status.** The overview page does not say, and the repo does not claim GA. The billing page also labels the limit two ways (B1-65).
- **Hypothetical figures** (8%, 30%, 11%, 18%/9%, "1 March", €2,300) are unverifiable by design.
- **The exam bank** (`<repo>\docs\research\exam-bank-cost-traps.md`, 109 KB) was only grepped. Its rows TRAP-BAK-005, TRAP-STOR-004 and TRAP-COMMIT-006 already carry hedges that the gallery rows lack.
- **Enterprise Agreement to MCA transition status.** Not checked.

## Source key (all fetched)

S1 https://learn.microsoft.com/en-us/azure/advisor/advisor-cost-recommendations
S2 https://learn.microsoft.com/en-us/azure/reliability/availability-zones-overview
S3 https://azure.microsoft.com/en-us/pricing/details/bandwidth/
S4 https://azure.microsoft.com/en-us/pricing/details/virtual-network/
S5 https://azure.microsoft.com/en-us/pricing/details/private-link/
S6 https://learn.microsoft.com/en-us/azure/private-link/manage-private-endpoint
S7 https://learn.microsoft.com/en-us/azure/firewall/firewall-faq
S8 https://azure.microsoft.com/en-us/pricing/details/azure-firewall/
S9 https://learn.microsoft.com/en-us/cloud-computing/finops/best-practices/networking
S10 https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing
S11 https://learn.microsoft.com/en-us/azure/virtual-machines/delete
S12 https://learn.microsoft.com/en-us/azure/storage/blobs/versioning-overview
S13 https://learn.microsoft.com/en-us/azure/storage/blobs/secure-file-transfer-protocol-support
S14 https://learn.microsoft.com/en-us/azure/container-registry/container-registry-geo-replication
S15 https://azure.microsoft.com/en-us/pricing/details/container-registry/
S16 https://learn.microsoft.com/en-us/azure/container-registry/container-registry-retention-policy
S17 https://learn.microsoft.com/en-us/azure/container-apps/billing
S18 https://learn.microsoft.com/en-us/azure/azure-functions/functions-premium-plan
S19 https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-plan
S20 https://azure.microsoft.com/en-us/pricing/details/functions/
S21 https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-premium-messaging
S22 https://learn.microsoft.com/en-us/azure/backup/backup-create-recovery-services-vault
S23 https://learn.microsoft.com/en-us/azure/backup/backup-azure-recovery-services-vault-overview
S24 https://learn.microsoft.com/en-us/azure/databricks/compute/configure
S25 https://azure.microsoft.com/en-us/pricing/details/databricks/
S26 https://learn.microsoft.com/en-us/windows-server/get-started/azure-hybrid-benefit
S27 https://learn.microsoft.com/en-us/marketplace/azure-consumption-commitment-benefit
S28 https://learn.microsoft.com/en-us/azure/cost-management-billing/reservations/reservation-discount-application
S29 https://learn.microsoft.com/en-us/azure/cost-management-billing/savings-plan/discount-application
S30 https://learn.microsoft.com/en-us/azure/cost-management-billing/savings-plan/savings-plan-compute-overview
S31 https://learn.microsoft.com/en-us/azure/virtual-machines/capacity-reservation-overview
S32 https://learn.microsoft.com/en-us/azure/search/search-sku-manage-costs
S33 https://learn.microsoft.com/en-us/azure/search/search-capacity-planning
S34 https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data
S35 https://learn.microsoft.com/en-us/azure/sre-agent/billing
S36 https://learn.microsoft.com/en-us/azure/cost-management-billing/automate/understand-usage-details-fields
S37 https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/direct-ea-administration
S38 https://learn.microsoft.com/en-us/azure/devtest/offer/how-to-manage-reliability-performance
S39 https://learn.microsoft.com/en-us/azure/cost-management-billing/reservations/exchange-and-refund-azure-reservations
S40 https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/ea-pricing
S41 https://learn.microsoft.com/en-us/azure/synapse-analytics/sql-data-warehouse/pause-and-resume-compute-portal
S42 https://learn.microsoft.com/en-us/fabric/onelake/onelake-capacity-consumption
S43 https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices
S44 https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-export-acm-data
S45 https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/quick-acm-cost-analysis
S46 https://learn.microsoft.com/en-us/azure/governance/resource-graph/overview
S47 https://learn.microsoft.com/en-us/azure/azure-monitor/metrics/data-platform-metrics
S48 https://learn.microsoft.com/en-us/azure/azure-monitor/platform/activity-log
S49 https://learn.microsoft.com/en-us/azure/azure-cache-for-redis/cache-how-to-scale
S50 https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/manage-costs
S51 https://learn.microsoft.com/en-us/azure/reliability/reliability-sql-managed-instance
S52 https://learn.microsoft.com/en-us/azure/azure-sql/database/high-availability-sla-local-zone-redundancy
S53 https://learn.microsoft.com/en-us/azure/reliability/reliability-app-service
S54 https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/enable-tag-inheritance

---

## Orchestrator spot-checks (2026-10-31)

Not all 79 rows were re-verified by the orchestrator. The four rows rated **Wrong** and the corrections with the highest embarrassment risk were re-read on the source page; the rest rely on the reviewer's machine-checked quotes and were treated as correct unless a wording change made them riskier.

- **B1-26 / B1-73 (inter-zone traffic) — confirmed.** `learn.microsoft.com/en-us/azure/reliability/availability-zones-overview`: "Azure doesn't charge for data transfer between availability zones in the same region, whether you use private or public IP addressing." Both the gallery row and the §9 "network paths" entry were wrong.
- **B1-10 / B1-49 (versioning) — confirmed.** `learn.microsoft.com/en-us/azure/storage/blobs/versioning-overview`: "Not supported on hierarchical namespace (Azure Data Lake Storage) accounts".
- **B1-69 (capacity reservations as a rate lever) — confirmed.** `learn.microsoft.com/en-us/azure/virtual-machines/capacity-reservation-overview`: "Reserved Instances provide a billing discount only and don't guarantee capacity" and "Capacity reservations are priced at the same rate as the underlying VM size."
- **B1-06 (backups in three regions) — consistent.** `learn.microsoft.com/en-us/azure/backup/backup-azure-recovery-services-vault-overview`: Cross Region Restore restores "in a secondary region, which is an Azure paired region" — one paired region, not three.
- **B1-37 (multiplier arithmetic) — confirmed.** `learn.microsoft.com/en-us/azure/search/search-capacity-planning`: "R × P = SU"; doubling both dimensions from 1 × 1 quadruples the units, but from 2 × 2 adding one to each gives 9/4 = 2.25 times.
- **Not re-fetched:** B1-30 (dev/test eligibility) — the paste-ready fix was shortened to claims that do not depend on offer details; B1-14, B1-20, B1-38, B1-41, B1-45, B1-57, B1-61, B1-67 were applied as worded but with the hedge "service-specific" rather than the full detail.
- **Reviewer's own limits are kept:** the NAT gateway "no stopped state" claim and VM compute billing granularity are UNVERIFIED, so the docs no longer state either as fact.