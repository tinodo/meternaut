// The cost anomaly alert of a subscription: Cost Management emails the recipients when it detects
// an unusual change in the cost of a resource group.
// https://learn.microsoft.com/azure/cost-management-billing/understand/analyze-unexpected-charges#create-an-anomaly-alert
//
// What to know before deploying (all from that page):
// - The portal only shows the rule when the view id names ms:DailyAnomalyByResourceGroup, so the
//   view id is not a parameter.
// - Creating the rule needs the Cost Management Contributor role or the permission
//   Microsoft.CostManagement/scheduledActions/write. The alert is sent on the creator's access at the
//   time of sending, so the identity that deploys it must keep the Reader role (or
//   Microsoft.CostManagement/scheduledActions/read): a pipeline's service principal, not a person.
// - One subscription holds at most five anomaly alert rules, and the public cloud only offers them.
// The shape follows the scheduled-action module of the FinOps toolkit (MIT licence):
// https://github.com/microsoft/finops-toolkit/tree/dev/src/bicep-registry/scheduled-action

targetScope = 'subscription'

@description('Name of the alert rule in the resource id.')
param alertName string = 'meternaut-anomaly'

@description('People who receive the alert e-mails. At least one is required.')
@minLength(1)
param emailRecipients array

@description('The person or team that receives unsubscribe requests and is named in the e-mails.')
param notificationEmail string

@description('First moment the alert runs, as a UTC time such as 2026-12-01T00:00:00Z.')
param startDate string

@description('Last moment the alert runs, as a UTC time such as 2027-12-01T00:00:00Z. The rule expires here, so renewing it is a reviewed change.')
param endDate string

@description('Subject of the e-mail, at most 70 characters.')
@maxLength(70)
param emailSubject string = 'Cost anomaly detected'

resource anomalyAlert 'Microsoft.CostManagement/scheduledActions@2025-03-01' = {
  name: alertName
  kind: 'InsightAlert'
  scope: subscription()
  properties: {
    displayName: alertName
    scope: ''
    viewId: '${subscription().id}/providers/Microsoft.CostManagement/views/ms:DailyAnomalyByResourceGroup'
    notificationEmail: notificationEmail
    status: 'Enabled'
    notification: {
      subject: emailSubject
      to: emailRecipients
      language: 'en'
      regionalFormat: 'en-us'
    }
    schedule: {
      frequency: 'Daily'
      startDate: startDate
      endDate: endDate
    }
  }
}

output anomalyAlertId string = anomalyAlert.id
