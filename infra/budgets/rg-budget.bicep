// A monthly cost budget for one resource group.
//
// For a resource group that the solution made for itself inside a subscription that it does not own, such as the
// resource group of the first environment. The budget covers every resource in the group, so the group should hold
// nothing but what the solution made.
//
// A budget only alerts. Azure evaluates it about every 24 hours and does not stop consumption
// (https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets).
// What stops spending is a token quota on the gateway's contracts and, in the end, deleting the group.
//
// It lives in the resource group, so deleting the group deletes it. It has no end date unless one is given.

targetScope = 'resourceGroup'

@description('Name of the budget. One budget for each resource group.')
@minLength(1)
param budgetName string

@description('Spending cap for each month, in the billing currency of the subscription.')
@minValue(1)
param amount int

@description('First day of the month in which the budget starts, as YYYY-MM-DD: the current month or a later one.')
param startDate string = utcNow('yyyy-MM-01')

@description('Last day of the budget, as YYYY-MM-DD. Leave empty to let the budget run until the resource group is deleted.')
param endDate string = ''

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
      endDate: empty(endDate) ? null : endDate
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
