// A monthly cost budget for the resources of one stage of the build.
//
// A budget only alerts. Azure evaluates it about every 24 hours and does not stop consumption
// (https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets).
// The stops are the hub's token quotas, the kill switch and the review of the stage
// (docs/design/07-safeguards-and-drift.md, section 3).
//
// Resources of the stage carry the tag meternaut-stage with the stage's name. The model tokens
// of a stage are read from the hub's logs, not from this budget (docs/build-plan/04-cost-effort-and-risks.md).

targetScope = 'subscription'

@description('The stage that the budget watches, as named in evaluation/stages.json. Resources of the stage carry the tag meternaut-stage with this value.')
@minLength(1)
param stage string

@description('Name of the budget. One budget for each stage and subscription.')
param budgetName string = 'meternaut-${stage}'

@description('Spending cap of the stage for each month, in the billing currency of the subscription. Taken from evaluation/stages.json after the project owner confirmed it.')
@minValue(1)
param amount int

@description('First day of the month in which the budget starts, as YYYY-MM-DD. It must be the first of a month: the current month, or a later one (the Bicep quickstart says at most three months ahead).')
param startDate string

@description('Date of the stage review, as YYYY-MM-DD. The budget ends here, so a stage that goes on needs a reviewed change.')
param endDate string

@description('People who receive the alerts. At least one is required.')
@minLength(1)
param contactEmails array

@description('Action groups that receive the alerts, as resource ids. Optional.')
param contactGroups array = []

@description('Percent of the cap at which the actual cost raises the warning.')
@minValue(1)
@maxValue(100)
param warnAtPercent int = 80

@description('Percent of the cap at which the forecast cost raises an alert.')
@minValue(1)
@maxValue(1000)
param forecastAtPercent int = 100

resource budget 'Microsoft.Consumption/budgets@2024-08-01' = {
  name: budgetName
  properties: {
    category: 'Cost'
    amount: amount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: startDate
      endDate: endDate
    }
    filter: {
      tags: {
        name: 'meternaut-stage'
        operator: 'In'
        values: [
          stage
        ]
      }
    }
    notifications: {
      warning: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: warnAtPercent
        thresholdType: 'Actual'
        contactEmails: contactEmails
        contactGroups: contactGroups
      }
      cap: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: contactEmails
        contactGroups: contactGroups
      }
      forecast: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: forecastAtPercent
        thresholdType: 'Forecasted'
        contactEmails: contactEmails
        contactGroups: contactGroups
      }
    }
  }
}

output budgetId string = budget.id
