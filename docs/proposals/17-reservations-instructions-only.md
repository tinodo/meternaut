# Reservations: instructions only, no purchase tool — a decision record

**Status: decided by the owner on 2026-11-09.** Meternaut does not buy reservations. It can show a platform recommendation as advice that changes nothing in Azure, and this page says how a person buys one. A purchase tool is not built.

## The owner's words

"You do NOT have to build RI purchases. I have no means to test it, and you can just provide instructions. FOR NOW. Perhaps my customers want it later, but for now; just provide instructions."

## What Meternaut does and does not do

- The tool `commitments` of the Investigator reads the platform's purchase recommendations for reservations and for savings plans, with the role R2 ([access](03-access-and-onboarding.md), [the toolbox](12-investigation-toolbox.md)). A finding about a commitment becomes a plan of the family `advise`: the answer is recorded and nothing changes in Azure ([the families](14-families-of-change.md)).
- No family, tool or role of Meternaut buys, exchanges, refunds or rescopes a reservation.
- The use of a reservation that exists is not read: that needs a billing role or a role on the reservation, which no role of Meternaut holds ([access](03-access-and-onboarding.md)).

## How a person buys a reservation

Read on 2026-11-09 on Microsoft Learn (the pages are listed at the end).

**Before**

1. **Clean up first.** Delete what is idle and resize what is too big, then commit: a discount lowers the rate and does not remove waste. Learn's own order is: right-size, exchange or trade in what is underused, buy new reservations for stable workloads, and only then add savings plans.
2. **Read the recommendation.** Azure Advisor shows single-subscription scope only, priced for three years where that term is sold. For a resource group or a shared scope, open Reservations, Add, pick the product and read the Recommended tab. The Consumption *Reservation Recommendations* API gives the same numbers. They come from the hourly usage of the last 7, 30 and 60 days, and the quantity that saves most is the one that is shown, so buy as close to it as you can. Resources that are shut down regularly get no recommendation, and there is none for the management group scope.
3. **Reservation or savings plan.** A workload that runs all the time, at one size and in one region, suits a reservation. A workload that changes or spreads over regions suits a savings plan. Do not buy both at once: allow at least three days for the recommendations to update.

**Buying**

4. **Role.** The built-in Owner or Reservation Purchaser role on the billing subscription (an Enterprise Agreement, Microsoft Customer Agreement or pay-as-you-go subscription). A custom role that copies them does not work. A billing administrator of an agreement needs one of these roles on at least one subscription too. An Enterprise Agreement administrator or a billing profile owner can switch off the *Reserved Instances* policy, so that people with only a role cannot buy.
5. **In the portal.** Reservations, Add, the product, then the scope (a resource group, a subscription, shared across the billing context, or a management group), the region and size, a term of one or three years, the quantity and how it is paid (all up front, or monthly for the same total), and then review and purchase. Some services have no reservation discount, for example serverless databases.
6. **By API.** `PUT https://management.azure.com/providers/Microsoft.Capacity/reservationOrders/<GUID>` with the sku, the billing scope, the term, the quantity and the applied scope type ([Learn's sample](https://learn.microsoft.com/azure/cost-management-billing/reservations/reservation-apis) uses api-version 2019-04-01; take the version of the *Reservation Order - Purchase* page). The Azure CLI has `az reservations reservation-order calculate` to price an order first.

**After**

7. **Look at the use after a week.** Rescoping is free and does not change the term, so widen the scope to shared when the use is low. Keep instance size flexibility on for virtual machines. Owners and billing contacts get notices of the purchase, the end of the term and a change of scope.
8. **Treat it as a one-way door.** A refund counts against 50,000 US dollars of cancelled commitment in a rolling 12 months for a billing profile or an enrollment. There is no early termination fee today and Learn says that one of 12 percent may come. Compute reservations can be exchanged "until further notice"; a reservation bought after 1 February 2027 for a service that savings plans cover cannot be exchanged, and one bought before keeps one last exchange.

## If a customer asks for a purchase tool later

A sketch, not a design; none of it is built.

- A new family, with the person's own sign-in as for every change ([run as the approver](05-run-as-the-approver.md)). The approver needs the built-in Owner or Reservation Purchaser role on the billing subscription, and Meternaut would hold none.
- The plan would carry the product, region, size, quantity, term, scope, payment and the price that the calculation returned, and the digest would bind them to the approval, as it does for the other families ([the families](14-families-of-change.md)).
- A purchase cannot be tested without spending money, and a refund is capped, so a test would need a budget that the owner sets. That is why the owner declined it for now.

## Sources, read on 2026-11-09

All under https://learn.microsoft.com/azure/cost-management-billing/: `reservations/prepare-buy-reservation`, `reservations/view-reservations`, `reservations/exchange-and-refund-azure-reservations`, `reservations/reserved-instance-purchase-recommendations`, `reservations/determine-reservation-purchase`, `reservations/reservation-apis` and `savings-plan/decide-between-savings-plan-reservation`.
