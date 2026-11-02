# infra/

Infrastructure as code for Meternaut, in Bicep. The platform team owns this folder ([design 09](../docs/design/09-delivery-and-operations.md#1-the-repository)).

**Nothing here has been deployed.** A deployment waits for the project owner to confirm the estate, the named owner, the spending cap and the review date of the stage it belongs to ([AGENTS.md](../AGENTS.md) rule 15). CI only compiles the templates.

| Path | What it creates | Scope |
|---|---|---|
| [`budgets/stage-budget.bicep`](budgets/stage-budget.bicep) | A monthly budget for the resources that carry the tag `meternaut-stage` with one stage's name, with an alert at a warning level, one at the cap and one on the forecast. It ends on the review date of the stage | A subscription |
| [`budgets/anomaly-alert.bicep`](budgets/anomaly-alert.bicep) | The cost anomaly alert of a subscription | A subscription |

The proposed numbers for each stage are in [`evaluation/stages.json`](../evaluation/stages.json).

## What a budget does and does not do

A budget alerts and does nothing more. Azure evaluates budgets about every 24 hours and does not stop consumption ([Learn](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets)). The stops are the hub's token quotas, the kill switch, and the review of the stage ([design 07](../docs/design/07-safeguards-and-drift.md#3-stopping-the-system)). The model tokens of a stage are billed to the hub, so they are read from the hub's logs and are not part of these budgets.

## Roles to deploy

- **Budget:** the Owner role can create, change and delete budgets of a subscription; Contributor and Cost Management Contributor can create, change and delete their own and can change the amount of a budget that someone else made ([Learn](https://learn.microsoft.com/azure/cost-management-billing/costs/quick-create-budget-bicep)).
- **Anomaly alert:** the Cost Management Contributor role or the permission `Microsoft.CostManagement/scheduledActions/write`. Azure sends the alert on the creator's access at the time of sending, so the identity that creates it must keep the Reader role (or `Microsoft.CostManagement/scheduledActions/read`): use the deployment pipeline's service principal, not a person. A subscription holds at most five anomaly alert rules, and only the public cloud offers them ([Learn](https://learn.microsoft.com/azure/cost-management-billing/understand/analyze-unexpected-charges#create-an-anomaly-alert)).

Both templates take their dates as parameters. A budget starts on the first of a month; the anomaly alert needs a UTC start and end time. Each stops at its end date, so keeping it going is a reviewed change.

## Check without deploying

From the repository root:

```text
az bicep build --file infra/budgets/stage-budget.bicep --stdout
az bicep build --file infra/budgets/anomaly-alert.bicep --stdout
az bicep lint --file infra/budgets/stage-budget.bicep
```

Neither command signs in or reads a subscription.
