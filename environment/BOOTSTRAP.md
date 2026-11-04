# Bootstrap: the one step that is not a workflow

Every change to Azure goes through the workflow [`deploy-hub.yml`](../.github/workflows/deploy-hub.yml) ([AGENTS.md](../AGENTS.md) rule 18). The workflow signs in to Azure as an identity, and an identity cannot create itself, so a person creates it once. That is this page. It is the only manual step, and nothing here runs until the owner has said yes in plain words in the conversation.

## What the owner approves

**In Azure.** In the subscription that holds the project's resources: two resource groups (one for the identity, one for the project's own resources) and one managed identity with one credential. On the two groups that the workflow works in, these roles:

| Where | Role | What it lets the identity change |
|---|---|---|
| The project's resource group | *Contributor* | Create, change and delete the network, the model account, its private endpoint and the budget in that group, and nothing outside it |
| The same group | *Role Based Access Control Administrator*, limited by a condition | Give a service principal one of three roles: *Cognitive Services OpenAI User* (so that the gateway's identity can run chat completions on the model account), and, for the usage recording, *Azure Event Hubs Data Sender* (the gateway's identity may send to the two event hubs) and *Azure Event Hubs Data Receiver* (the Logic App may read them). Any other role, and any grant to a person or a group, is impossible |
| The gateway's own resource group (the subscription of the existing API Management instance) | A custom role, *Meternaut gateway deployer*, listed below | Add and change objects in the one API Management instance (its APIs, backends, policy fragments, named values, loggers, products and its service-level settings), attach an identity to it, make managed identities in that group, and run deployments in it. It can read the instance's Application Insights and, once the first contract exists, that contract's key, to test the gateway with it. It cannot delete anything: not an object of the instance, not the instance, not an identity |

**In GitHub**, on this repository: five secrets (the identity's client id, the tenant id, the subscription id, and the resource ids of the API Management instance and of its Application Insights; none is a password) and eight variables (the project's resource group, the region, two address ranges, the DNS server, the owner's address twice and the budget). The workflow reads them; none is in the repository.

## What the identity can and cannot do

It can add and change objects in the API Management instance and change its service-level settings, because the one thing it must do to the instance itself, attaching an identity, is a service-level write, and Azure's roles cannot narrow a role to some objects of an instance. What holds it to the Citadel module's objects is the workflow: it runs only the pinned module and [`tools/gateway-prep.py`](../tools/gateway-prep.py), which reads the instance, keeps its system-assigned identity when it adds one, writes only when the instance has not changed since it was read, and writes only in GitHub Actions. It has no right to delete in the instance or in the gateway's group: taking the module's objects out again (`pause`, `remove`) needs delete rights, which the owner grants for that one run, in his own words, and takes away again; they are never a standing right.

It can delete the project's resource group with everything in it, because *Contributor* covers that; the workflow never does, and a budget alert is the only warning. It cannot create other resource groups, change anything else in either subscription, register a resource provider, purge a soft-deleted account, give any role except the three above to a service principal in the project's group, or touch the network, the firewall or the DNS of the landing zone.

Who can use the credential: any run of the workflow on `main`. The repository is private, and the workflow starts only by hand and only as the owner's account ([`tools/workflow-lint.py`](../tools/workflow-lint.py) fails a change that would make it start any other way). GitHub's Free plan has no required reviewer for a private repository, and the guard cannot tell the owner's click from a run that an agent starts with his token, so the approval is a rule of process and not a technical barrier. The owner has said that he merges and clicks nothing himself: he tells the agent in plain words in the conversation, and the agent merges and starts the run. An agent starts `what-if`, which reads and changes nothing, on its own; `model-side`, `gateway-prepare`, `gateway` and `contract` each need his words (one yes to the whole list is enough).

## Checked first, read-only

- The resource providers that the workflow needs (`Microsoft.CognitiveServices`, `Microsoft.Network`, `Microsoft.Consumption`, `Microsoft.ManagedIdentity`, `Microsoft.Authorization`, `Microsoft.Resources`, `Microsoft.ApiManagement`, `Microsoft.Insights`, and for the usage recording `Microsoft.Web`, `Microsoft.Storage`, `Microsoft.EventHub`, `Microsoft.DocumentDB` and `Microsoft.OperationalInsights`) are registered in both subscriptions. The identity cannot register one; `Microsoft.DocumentDB` was not registered in the project's subscription and was registered by hand on 2026-11-04 (see below).
- The address range chosen for the network overlaps no virtual network, VPN client pool or on-premises range that the signed-in account can see in the tenant. The landing zone's policy joins a new virtual network to the network manager's group, which peers and routes it by itself.
- The API Management instance is in the state `Succeeded`, and has an Application Insights logger whose component the workflow can read.
- The models in [`environment/models.json`](models.json) have quota in the region for the deployment type chosen. The identity cannot read quota, so the first deployment is where a shortage would show.
- No soft-deleted key vault, account or workspace holds a name that the workflow would use.

## The custom role

```json
{
  "Name": "Meternaut gateway deployer",
  "IsCustom": true,
  "Description": "Lets the Meternaut deployment identity add and change Citadel's objects in one API Management instance and make a managed identity in its resource group. It cannot delete anything.",
  "Actions": [
    "Microsoft.ApiManagement/service/read",
    "Microsoft.ApiManagement/service/write",
    "Microsoft.ApiManagement/service/*/read",
    "Microsoft.ApiManagement/service/*/write",
    "Microsoft.ApiManagement/service/subscriptions/listSecrets/action",
    "Microsoft.ManagedIdentity/userAssignedIdentities/read",
    "Microsoft.ManagedIdentity/userAssignedIdentities/write",
    "Microsoft.ManagedIdentity/userAssignedIdentities/assign/action",
    "Microsoft.Resources/deployments/*",
    "Microsoft.Resources/subscriptions/resourceGroups/read",
    "Microsoft.Insights/components/read",
    "Microsoft.Authorization/roleAssignments/read",
    "Microsoft.Authorization/roleDefinitions/read"
  ],
  "NotActions": [],
  "AssignableScopes": [
    "/subscriptions/<gateway subscription id>/resourceGroups/<gateway resource group>"
  ]
}
```

The one action that reads a secret, `Microsoft.ApiManagement/service/subscriptions/listSecrets/action`, is there so that the workflow can read the key of the contract it makes and test the gateway with it. That key lets a caller use the contract's models within the contract's token limits, and nothing else.

If the first `gateway` run is refused with a message about `Microsoft.Network/virtualNetworks/subnets/join/action` (a service in a virtual network may need it on its subnet to be updated), the answer is to add that one action, on that one subnet, as a separate approved step: not to widen this role.

## The commands

Run once, by the person who approved it, signed in to Azure and to GitHub as himself. Nothing here is written into the repository: fill in the values at the top. The Azure CLI is called through its own Python because the `az.cmd` wrapper on Windows mangles the parentheses of the condition.

```powershell
$devSub    = '<id of the subscription that holds the project''s resources>'
$gwSub     = '<subscription id of the API Management instance>'
$gwGroup   = '<resource group of the API Management instance>'
$apim      = '<resource id of the API Management instance>'
$insights  = '<resource id of the Application Insights component that the instance logs to>'
$owner     = '<the owner''s mail address>'
$vnet      = '<a free /24 inside 10.0.0.0/8 for the network>'
$subnet    = '<the first /27 of it, for the endpoint>'
$dns       = '<the landing zone''s DNS server>'
$region    = 'swedencentral'
$repo      = 'tinodo/meternaut'
$idGroup   = 'meternaut-bootstrap-sc-rg'
$hubGroup  = 'meternaut-sc-rg'
$uami      = 'meternaut-deploy-sc-uami'
function az { & 'C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe' -IBm azure.cli @args }

# 1. The two resource groups
az group create --subscription $devSub --name $idGroup  --location $region --tags workload=meternaut component=identity owner=$owner
az group create --subscription $devSub --name $hubGroup --location $region --tags workload=meternaut component=project owner=$owner

# 2. The identity
az identity create --subscription $devSub --resource-group $idGroup --name $uami --location $region --tags workload=meternaut
$principal = az identity show --subscription $devSub --resource-group $idGroup --name $uami --query principalId --output tsv
$client    = az identity show --subscription $devSub --resource-group $idGroup --name $uami --query clientId --output tsv

# 3. The credential: a run of the workflow on the main branch of this repository. GitHub names the repository in the
#    subject by its owner's and its own numeric id too (repo:<owner>@<id>/<repository>@<id>); the repository's own setting
#    gives that prefix. The plain form repo:<owner>/<repository> does not match: Azure answers AADSTS700213.
$prefix = (gh api "repos/$repo/actions/oidc/customization/sub" | ConvertFrom-Json).sub_claim_prefix
az identity federated-credential create --subscription $devSub --resource-group $idGroup --identity-name $uami --name github-main `
  --issuer https://token.actions.githubusercontent.com --subject "${prefix}:ref:refs/heads/main" --audiences api://AzureADTokenExchange

# 4. The rights on the project's group
$scope = "/subscriptions/$devSub/resourceGroups/$hubGroup"
az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal --role 'Contributor' --scope $scope
$condition = @'
((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {5e0bd9bd-7b93-4f28-af87-19fc36ad61bd} AND @Request[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'})) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {5e0bd9bd-7b93-4f28-af87-19fc36ad61bd} AND @Resource[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'}))
'@
az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal --role 'Role Based Access Control Administrator' --scope $scope --condition $condition --condition-version 2.0

# 5. The custom role on the gateway's group (the JSON above, saved with the gateway's group in AssignableScopes)
az role definition create --role-definition '<the JSON above, with the gateway subscription and group filled in>'
az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal --role 'Meternaut gateway deployer' --scope "/subscriptions/$gwSub/resourceGroups/$gwGroup"

# 6. The repository's settings
$tenant = az account show --subscription $devSub --query tenantId --output tsv
gh secret set AZURE_CLIENT_ID          --repo $repo --body $client
gh secret set AZURE_TENANT_ID          --repo $repo --body $tenant
gh secret set AZURE_SUBSCRIPTION_ID    --repo $repo --body $devSub
gh secret set GATEWAY_RESOURCE_ID      --repo $repo --body $apim
gh secret set GATEWAY_APPINSIGHTS_ID   --repo $repo --body $insights
gh variable set ENV_RESOURCE_GROUP     --repo $repo --body $hubGroup
gh variable set ENV_LOCATION           --repo $repo --body $region
gh variable set ENV_VNET_PREFIX        --repo $repo --body $vnet
gh variable set ENV_PE_SUBNET_PREFIX   --repo $repo --body $subnet
gh variable set ENV_DNS_SERVERS        --repo $repo --body $dns
gh variable set ENV_OWNER              --repo $repo --body $owner
gh variable set ENV_ALERT_EMAILS       --repo $repo --body $owner
gh variable set ENV_BUDGET_AMOUNT      --repo $repo --body 25
```

Read the result back before the first run: `az role assignment list --assignee $principal --all --output table` shows three assignments, `gh secret list --repo $repo` five secrets and `gh variable list --repo $repo` eight variables. The budget's start date is not a setting: the workflow reads it from the budget once it exists.

## Added on 2026-11-04 for the usage recording

The owner ordered the usage recording built ("build the whole thing, with the 265 storage ... build it now"). It needs three things that the workflow's identity may not do itself, because they are not changes of the project's resource group: they are done by hand, once, by the person who ordered it, and reported at once. They are narrow and none widens the identity beyond the project's group.

1. **A resource provider.** `Microsoft.DocumentDB` (Cosmos DB) was not registered in the project's subscription. Done on 2026-11-04: `az provider register --namespace Microsoft.DocumentDB`. The same step would be needed for any other provider that the workflow reports as not registered.
2. **Two more roles that the identity may give.** The condition of the *Role Based Access Control Administrator* assignment on the project's group lists the roles that the identity may give to a service principal. The usage recording gives the gateway's identity *Azure Event Hubs Data Sender* (`2b629674-e913-4c01-ae53-ef4638d8f975`) on the Event Hubs namespace and the Logic App's identity *Azure Event Hubs Data Receiver* (`a638d3c7-ab3a-418d-83e6-5f17a39d4fde`) on the same namespace. The condition now lists those two besides *Cognitive Services OpenAI User*. It is replaced as a whole (delete, then create; nothing runs in between):

   ```powershell
   $scope = "/subscriptions/$devSub/resourceGroups/$hubGroup"
   $roles = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd, 2b629674-e913-4c01-ae53-ef4638d8f975, a638d3c7-ab3a-418d-83e6-5f17a39d4fde'
   $condition = "((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$roles} AND @Request[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'})) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$roles} AND @Resource[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'}))"
   $old = az role assignment list --assignee-object-id $principal --scope $scope --role 'Role Based Access Control Administrator' --query "[0].id" --output tsv
   az role assignment delete --ids $old
   az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal --role 'Role Based Access Control Administrator' --scope $scope --condition $condition --condition-version 2.0
   ```
3. **One role in the gateway's subscription, after the first `recording` run.** The copy job reads the gateway's Application Insights with the Logic App's own identity, which exists only after the run. That identity gets *Monitoring Reader* on that one Application Insights component and nothing else (the workflow's summary prints its object id):

   ```powershell
   az role assignment create --assignee-object-id <object id of the Logic App's identity> --assignee-principal-type ServicePrincipal --role 'Monitoring Reader' --scope $insights
   ```

   If the Logic App is ever made again, its identity is new, and this step is done again.

One optional repository variable: `RECORDING_READER_IDS`, a comma-separated list of the object ids of the people who may read the usage store in Cosmos DB's Data Explorer (a data role of Cosmos DB, not an Azure role). Without it nobody but the workflow's identity and the Logic App can read it.

## After it

The branch that holds this page is merged to `main` (the workflow runs only there, and the credential exists only for `main`; this was done on 2026-11-03, see the changelog), and the workflow is started with the action `what-if`, from the Actions tab (*Hub*, *Run workflow*) or with `gh workflow run deploy-hub.yml --ref main -f action=what-if`. It shows what the next steps would create, and changes nothing. Then, each on the owner's word: `model-side` (the gateway's identity, the network, the model account); `gateway-prepare` (the identity attached to the gateway, and the Application Insights logger: the only changes to the instance itself); a second `what-if`, which shows the exact diff of the Citadel module and is read before anything else; and `gateway` (the module's objects, without its two usage-recording fragments: see the changelog). Last comes `contract` (the first contract: a product that grants the two inference APIs, with its policy and its one subscription; the run reads the subscription's key from the gateway, tests the gateway with it and keeps it nowhere; with the input `check_limits` it also proves the token limit). The usage recording has two actions of its own: `recording` (the stores and the Logic App, with its workflows published) and, once the role in the gateway's subscription is given (above), `recording-check` (the copy job started once, and what it wrote read back). One yes to the whole list lets the agent run them in this order, and stop at the first thing that differs from the list.

## Undoing it

Taking the model side away is meant to be a workflow's job (an action `remove`), and so is taking the module's objects and the contract out of the instance, which needs delete rights that the owner grants for that run only (see above). Neither is built yet: this page said that `remove` would exist before the first `model-side` run, and it did not, so it is the next change, and the changelog records that the promise was not kept. Until then the project's resource group can be deleted by hand, which takes the network, the model account, its private endpoint and the budget with it (the account stays soft-deleted, see below), and the module's objects can be left in the instance, where they do nothing without a caller that holds a contract's key. Taking the identity and the settings away is the other half of the bootstrap, so it is a manual step of the same kind, and it needs the owner's own plain-word yes, given separately from the one that created the identity: delete the role assignments (`az role assignment delete --assignee $principal --scope <each scope>`), the custom role, the two resource groups (with the second, the identity and its credential), and the secrets and variables (`gh secret delete`, `gh variable delete`).

A model account that was deleted is soft-deleted and keeps its name for a while. The workflow restores it by itself on the next `model-side`, so nothing has to be purged.
