# Bootstrap: the one step that is not a workflow

Every change to Azure goes through the workflow [`deploy-hub.yml`](../.github/workflows/deploy-hub.yml) ([AGENTS.md](../AGENTS.md) rule 18). The workflow signs in to Azure as an identity, and an identity cannot create itself, so a person creates it once. That is this page. It is the only manual step, and nothing here runs until the owner has said yes in plain words in the conversation.

## What the owner approves

**In Azure**, in the subscription of the landing zone that holds the project's resources:

| What | Why |
|---|---|
| A resource group for the identity | Kept apart from the hub's group, so that removing the hub can never remove the identity |
| A resource group for the hub | The only place where the workflow builds anything |
| One managed identity, in the first group | The identity the workflow signs in as. It has no password and no secret |
| One credential on that identity | It lets a run of the workflow on the `main` branch of this repository sign in as the identity, and nothing else: not another branch, not a pull request, not another repository |
| Role *Contributor* on the hub's group | To create the network, the model account and its private endpoint, and to delete them again |
| Role *Role Based Access Control Administrator* on the hub's group, limited by a condition | To give the API Management instance's identity the one role that lets it call the model (*Cognitive Services OpenAI User*). The condition allows that one role and only for a service principal: any other role, and any grant to a person or a group, is impossible |
| Role *API Management Service Contributor* on the existing API Management instance | To add and remove the objects whose names start with `meternaut-` (listed in the [README](README.md#what-is-added-to-the-api-management-instance)) |

**In GitHub**, on this repository: four secrets (the identity's client id, the tenant id, the subscription id and the resource id of the API Management instance; no one of them is a password) and nine variables (the group name, the region, two address ranges, the DNS server, the owner's address twice, the budget and the name of the instance's Application Insights logger). The workflow reads them; none is in the repository.

## What the identity can and cannot do

It can create, change and delete resources in the hub's group, and it can add and remove `meternaut-` objects on the API Management instance. It can also delete the hub's resource group itself with everything in it, because *Contributor* covers that; the workflow never does, and a budget alert is the only warning. It cannot create other resource groups, change anything else in the subscription, register a resource provider, purge a soft-deleted account, or assign any role except *Cognitive Services OpenAI User*, to a service principal, inside the hub's group.

Two limits to know:

- *API Management Service Contributor* cannot be narrowed to the `meternaut-` objects: the role covers the whole instance, so the identity could change or read anything on it. What holds it to the `meternaut-` objects is [`tools/apim-sync.py`](../tools/apim-sync.py), which refuses any other path and refuses to write outside GitHub Actions, and the plan the workflow prints before it writes.
- *Contributor* covers every resource type in the group. The group is dedicated, and a budget alerts on its cost.

Who can use the credential: any run of the workflow on `main`. The repository is private, the workflow starts only by hand and only for the owner ([`tools/workflow-lint.py`](../tools/workflow-lint.py) fails a change that would make it start any other way), and the owner merges to `main`. GitHub's Free plan has no required reviewer for a private repository, so the approval is the owner's own click on *Run workflow*. An agent may start `what-if`, which reads and changes nothing; only the owner starts `deploy`, `pause` and `remove`.

## Checked first, read-only

- The resource providers that the workflow needs (`Microsoft.CognitiveServices`, `Microsoft.Network`, `Microsoft.Consumption`, `Microsoft.ManagedIdentity`, `Microsoft.Authorization`, `Microsoft.Resources`) are registered in the subscription. The identity cannot register one.
- The address range chosen for the network overlaps no virtual network, VPN client pool or on-premises range that the signed-in account can see in the tenant. The landing zone's network manager peers and routes the new network by itself.
- The API Management instance has a system-assigned identity. The workflow does not change the instance itself, so it stops with a message if the identity is missing.
- The model `gpt-6-luna` has quota in the region: the Data Zone Standard limit is 100 and none is used. The identity cannot read quota, so the first deployment is where a shortage would show.

## The commands

Run once, by the person who approved it, signed in to Azure and to GitHub as himself. Nothing here is written into the repository: fill in the values at the top. The Azure CLI is called through its own Python because the `az.cmd` wrapper on Windows mangles the parentheses of the condition.

```powershell
$sub    = '<subscription id of the landing-zone subscription>'
$apim   = '<resource id of the existing API Management instance>'
$logger = '<name of that instance''s Application Insights logger>'
$owner  = '<the owner''s mail address>'
$vnet   = '<a free /27 inside 10.0.0.0/8 for the network>'
$subnet = '<the first /28 of it, for the endpoint>'
$dns    = '<the landing zone''s DNS server>'
$region = 'swedencentral'
$repo   = 'tinodo/meternaut'
$idRg   = 'meternaut-dev-bootstrap-sc-rg'
$hubRg  = 'meternaut-dev-hub-sc-rg'
$uami   = 'meternaut-dev-deploy-sc-uami'
function az { & 'C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe' -IBm azure.cli @args }

az account set --subscription $sub

# 1. The two resource groups
az group create --name $idRg  --location $region --tags workload=meternaut component=identity owner=$owner
az group create --name $hubRg --location $region --tags workload=meternaut component=hub owner=$owner

# 2. The identity
az identity create --resource-group $idRg --name $uami --location $region --tags workload=meternaut
$principal = az identity show --resource-group $idRg --name $uami --query principalId --output tsv
$client    = az identity show --resource-group $idRg --name $uami --query clientId --output tsv

# 3. The credential: a run of the workflow on the main branch of this repository
az identity federated-credential create --resource-group $idRg --identity-name $uami --name github-main `
  --issuer https://token.actions.githubusercontent.com --subject "repo:${repo}:ref:refs/heads/main" --audiences api://AzureADTokenExchange

# 4. The rights
$scope = "/subscriptions/$sub/resourceGroups/$hubRg"
az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal --role 'Contributor' --scope $scope
$condition = @'
((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {5e0bd9bd-7b93-4f28-af87-19fc36ad61bd} AND @Request[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'})) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {5e0bd9bd-7b93-4f28-af87-19fc36ad61bd} AND @Resource[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'}))
'@
az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal --role 'Role Based Access Control Administrator' --scope $scope --condition $condition --condition-version 2.0
az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal --role 'API Management Service Contributor' --scope $apim

# 5. The repository's settings
$tenant = az account show --query tenantId --output tsv
gh secret set AZURE_CLIENT_ID       --repo $repo --body $client
gh secret set AZURE_TENANT_ID       --repo $repo --body $tenant
gh secret set AZURE_SUBSCRIPTION_ID --repo $repo --body $sub
gh secret set HUB_APIM_RESOURCE_ID  --repo $repo --body $apim
gh variable set HUB_RESOURCE_GROUP   --repo $repo --body $hubRg
gh variable set HUB_LOCATION         --repo $repo --body $region
gh variable set HUB_VNET_PREFIX      --repo $repo --body $vnet
gh variable set HUB_PE_SUBNET_PREFIX --repo $repo --body $subnet
gh variable set HUB_DNS_SERVERS      --repo $repo --body $dns
gh variable set HUB_OWNER            --repo $repo --body $owner
gh variable set HUB_ALERT_EMAILS     --repo $repo --body $owner
gh variable set HUB_BUDGET_AMOUNT    --repo $repo --body 20
gh variable set HUB_APIM_LOGGER      --repo $repo --body $logger
```

The DNS server is the landing zone's own: a virtual network that does not use it cannot resolve the central private DNS zones. Read the result back before the first run: `az role assignment list --assignee $principal --all --output table` shows three assignments, `gh secret list --repo $repo` four secrets and `gh variable list --repo $repo` nine variables. The budget's start date is not a setting: the workflow reads it from the budget once it exists.

## After it

Merge the branch that holds this page to `main`, then start the workflow from the Actions tab: *Hub*, *Run workflow*, action `what-if`. It shows what a deploy would create in Azure and in the API Management instance, and changes nothing. A `deploy` follows when the owner has read it, and the first one is run with `check_limits` ticked.

## Undoing it

Taking the hub away is the workflow's job: start it with action `remove` (or `pause` to keep everything but the private endpoint). That needs no manual step.

Taking the identity and the settings away is the other half of the bootstrap, so it is a manual step of the same kind, and it needs the owner's own plain-word yes, given separately from the one that created the identity. Run `remove` first; then, as the person who was asked:

```powershell
az role assignment delete --assignee $principal --scope $apim
az group delete --name $hubRg --yes
az group delete --name $idRg --yes
```

The first line removes the identity's rights on the instance, which deleting the identity would otherwise leave behind as an orphan; the next two delete the two resource groups, and with the second the identity and its credential. Delete the secrets and variables with `gh secret delete` and `gh variable delete`.

A model account that `remove` or the group deletion took away is soft-deleted and keeps its name for a while. The workflow restores it by itself on the next `deploy`, so nothing has to be purged. Purging frees the name for another use at once; it needs a right on the subscription that the identity does not have, so it is another manual step that waits for its own yes: `az cognitiveservices account purge --location $region --resource-group $hubRg --name <account>`.
