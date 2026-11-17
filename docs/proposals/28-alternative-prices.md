# Alternative prices: what a switch to another tier or size would cost, from Azure's public price list — a decision record

**Status: decided on 2026-11-17. The tool that shows the prices is built, tested against fakes, and read once against the real public price list (counts and numbers only, below). The form of a change that uses these prices is not built: [proposal 24](24-priced-findings.md) leaves a seam for it and refuses it. Not deployed.**

## What was asked

Many of the best savings are a switch to another tier, size or SKU of the same service. The Investigator can see from its measurements that something is bigger than its use needs, but the bill holds only what is paid now, so it could not price the alternative, and a saving that nobody can price is not one that a person can decide on. An independent read of a real estate priced such switches from Azure's public price list. Meternaut has to do the same, for any service, with code doing the arithmetic and no model writing an amount ([rules 26 (d) and 30](../../AGENTS.md)).

## The tool: `price_alternatives`

| Part | What it does |
|---|---|
| Input | `meter`: the handle of a meter of one resource, as `cost_meters` showed it (`m3`). `within`: `product` (the default) or `service`. `offset`, to read a long table page by page. The meter of a whole type has no region, so it is not offered |
| What leaves the app | One GET of the price list, with no token. The address holds four typed words: the service and the product of the meter, as the bill gives them (its category and its subcategory), the region of the resource, and the currency (US dollars). Each word passes the check that `cost_meters` applies to the words of a meter, and a word that fails makes no call. No name, tag, id, group or amount of the estate is in it |
| What comes back | A table of pay-as-you-go prices in dollars: a price handle (`p1`, `p2`, ...) that stands for the line in this run only, the SKU and the meter, the price of one unit, the region (or `global`), and `steps` when the price changes with the quantity; the product is given once when it is the same for every row. Only the lines in the unit of measure of the meter are listed (`other_units` counts the others), the lowest price first. A text of the list that is not a short word of the platform is shown as `other`, as a word of a meter is |
| The line of the meter itself | `current`: the line whose product, meter and unit are the words of the meter on the bill, with `retail` (its list price), `paid` (what the bill paid for one unit over the window: the cost divided by the quantity) and `rate_ratio` (paid divided by retail). `match` says `found`, `none` or `several`. The ratio is kept in the register of the run (`Toolbox.rates`) for the code that will price a switch, so that a rate that is not the list price (a negotiated or a reserved one) is carried over to any other line, and the figure does not pretend that the estate pays list prices |
| What it does not say | Nothing about which line is better, and no list of what to look at. It shows prices. The Investigator decides, and says what the alternative must still do |

**The product of the meter, by default.** A page of the list holds 1,000 lines and about 600 KB, and one service has more than 7,000 pay-as-you-go lines in one region, so a read of a whole service is slow, and the list answered HTTP 429 to a burst of reads from one machine. The product of the meter is a few dozen lines at most, one page, and it is where the next size of the same series is. `within service` reads every product of the service, up to five pages (5,000 lines), and says `complete: false` when it did not read the whole list.

**The lines that hold everywhere, too.** The list names the region of a price that holds in every region `Global`. The dearest meter of the top service of a real bill is such a price, so a read of the region of the resource alone found a line for 4 of the 11 meters of that service, and not for the dearest. The address asks for the region and for `Global`, and the line of the region wins when there are both. A resource in the region `global` is asked for `Global`.

**What counts as the line of the meter.** The product, the meter and the unit of the line are those of the bill: the category of a meter on the bill is the service of the list, its subcategory the product, its name the meter, and its unit the unit. The words must be equal. When several lines have them, the line of the region is the one; when the lines that are left disagree on the price the match is `several` and there is no line and no rate (the SKUs of one meter share its price, and that is not a disagreement). A line whose price has several steps is shown with `steps` and has no rate, because what the bill paid for one unit mixes the steps. A price that the list gives twice with two values is left out, and so is a line that is not a pay-as-you-go price in dollars (a reservation, a dev/test price, a savings plan, another currency).

**Limits of a read.** At most five pages and 6,000 prices for one read, 30 seconds, and 20,000 prices held by a run. A list is read once for a service, a region and a product in a run, whether it worked or not. A read that fails (the call, an answer that is not the list, a next page somewhere else, a limit) answers `unavailable` with the platform's error code word and never its text, a note says so, and the rest of the investigation goes on.

## Which client, which call

The Watch's own client reads it, with the Watch's list of calls, which gets one more exact entry: `GET https://prices.azure.com/api/retail/prices` (`http.PRICE_CALL`). It is the entry that the Study's list already held ([proposal 15](15-learning.md)), defined once and used by both lists. The list sees an address without its query, so it pins the method, the host and the path, and nothing else of the host: no write, no other path, no other port. The query is made by `cases/prices.py` from checked words only, and a test pins it. The call carries no token (a test checks the headers), so no role is needed: the call is on no line of [`environment/access-requirements.json`](../../environment/access-requirements.json), the test of that file names it as a call that needs none, and the drift check probes that the list lets the GET through and refuses a POST and another path. The list writes the address of the next page with the port 443; the app follows it only on the same host and path, asks again without the port, and refuses any other.

## What a real read showed (2026-11-17, read only, counts and numbers only)

The real tool ran, with its real client and the real list, over the words of 23 meters that the real bill showed (the dearest meters of four services of the top spend: 5, 2, 6 and 10 meters). The bill was read with a person's own read-only sign-in, and no name or id of it is kept.

- **Every meter found its line:** `match` was `found` for 23 of 23, in the region of the resource or, for some, as a `Global` line.
- **The rate ratio:** 1 for 17 meters, within 0.01 of 1 for 2, above 1 for 3 (1.087, 1.1025, 1.2485: why is not examined) and not worked out for 1, a price with steps. The estate mostly pays list prices.
- **Alternatives of the same unit exist:** the product of the meter listed from 1 to 52 lines in its unit (a median of 23), and for 22 of the 23 meters there was at least one other line; the whole top service had 24 lines in 6 products (17 distinct prices).
- **Paging:** the read of a product was one page, a service of 1,672 prices came in two pages (about 1 MB, 0.9 seconds), and one of more than 5,000 lines stopped at the cap of five pages (3 MB, 5.7 seconds), said `complete: false` and still found the line of the meter.
- **A fault that only the real list could show:** it writes the address of the next page with `:443`, which the first version refused; fakes now write it too.
- **The list throttles:** HTTP 429 came after a burst of reads from one machine, and none came when the reads were 5 to 6 seconds apart. The page does not say what the limit is.

Facts about the list are from [the Azure Retail Prices REST API overview](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices), read on 2026-11-17 (the page is dated 2026-01-06): no sign-in is needed; the filter fields include `serviceName`, `productName`, `armRegionName` and `priceType`, and their values are case sensitive; at most 1,000 lines come back for a call, with the link to the next page; the types of price are `Consumption`, `Reservation` and `DevTestConsumption`; the list holds prices in US dollars, and this version holds the Commercial cloud only. The version `2023-01-01-preview` that the app asks for is the one the page names.

## Access at each level (rule 12)

The list is public, so the tool needs no access of its own at any level. What it needs is a meter handle, which comes from the bill that the Watch reads with the Cost Management Reader role (R2): a Watch that cannot read the bill has no meter and the tool answers `unknown-handle`. A bill in another currency has no meter handle either, because `cost_meters` shows dollars only. An agreement with negotiated or reserved rates is what `rate_ratio` is for: it is worked out from the cost lines that the Watch can read, and a person who sees the figure sees that it rests on the rate that the bill shows.

## What is not proved

- **That the app's network reaches the host.** The Study reads the same host with its own client and the network requirements name it ([`tools/cases-check.py`](../../tools/cases-check.py)); whether the function app's subnet reaches it is for the platform team, and nothing here ran from the app. A failed read is `unavailable` and the investigation goes on.
- **That the words of the bill match the list for every service.** They did for 23 of 23 meters of four services. A meter whose words differ has no line and no rate. Marketplace products, other agreements' meter words and a meter renamed inside the window were not looked at.
- **Why three rates are above 1.** A resource in another region than its row, a price that changed inside the window, or usage that the list prices in steps could each do it. The ratio is one number for the whole window.
- **That an alternative does the same work.** The tool shows prices and nothing else. Features, limits and the use are judged by the Investigator from its measurements and from what the Study read, by the second AI and by a person.
- **That the Investigator uses the tool well.** No model was called for this change.
- **The limit of the list.** It is not documented; the tool reads once for a list, and takes a refusal for `unavailable`.
- **What it leaves out.** Reservation, dev/test and savings plan prices (a commitment is a change of its own: [proposal 17](17-reservations-instructions-only.md)), other currencies, and the Government clouds.
- **What the tests pin.** Mutation-checked one at a time: the global lines, each cap, the price given twice, a price with no first step, the match by region and by price, the host of the next page, that no token is sent, the currency and the kind of price, the length of a text, the check of the words of the address, the region `global`, the unit filter, the rate for a price with steps, the check of the words shown, the read once, the region that is not a word, the scope of a read, the register of rates, the bound on what a run holds, the code word of a failure and the meter of a whole type.

## What it costs

No new resource, role or call that needs an identity. The definition of the Investigator grows by 997 characters for the description of the tool and 356 for two sentences of the instructions, which every step of an investigation reads again; that is the one cost in tokens. The room that the change takes in the upload package of the function app is in [the changelog](../../CHANGELOG.md).
