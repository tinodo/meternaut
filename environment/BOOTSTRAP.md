# Bootstrap: the one step that is not a workflow

Every change to Azure goes through the workflow [`deploy-hub.yml`](../.github/workflows/deploy-hub.yml) ([AGENTS.md](../AGENTS.md) rule 18). The workflow signs in to Azure as an identity, and an identity cannot create itself, so a person creates it once. That is this page. It is the only manual step, and nothing here runs until the owner has said yes in plain words in the conversation.

## What the owner approves

**In Azure.** In the subscription that holds the project's resources: two resource groups (one for the identity, one for the project's own resources) and one managed identity with one credential. On the two groups that the workflow works in, these roles:

| Where | Role | What it lets the identity change |
|---|---|---|
| The project's resource group | *Contributor* | Create, change and delete the network, the model account, its private endpoint and the budget in that group, and nothing outside it |
| The same group | *Role Based Access Control Administrator*, limited by a condition | Give a service principal one of eight roles: *Cognitive Services OpenAI User* (so that the gateway's identity can run chat completions on the model account), and, for the usage recording, *Azure Event Hubs Data Sender* (the gateway's identity and the workflow's identity may send to event hubs), *Azure Event Hubs Data Receiver* (the function app's identity may read them), *Storage Blob Data Owner*, *Storage Queue Data Contributor* and *Storage Table Data Contributor* (what the function app's identity needs on its storage account), *Monitoring Metrics Publisher* (its telemetry, and the traces of the Foundry project) and, for the Foundry resource of the agents, *Azure AI User* (named *Foundry User* since the rename: the cases app's identity may create and run agents on the Foundry project; [added on 2026-11-06](#changed-on-2026-11-06-the-foundry-resource-of-the-agents)). Any other role, and any grant to a person or a group, is impossible |
| The gateway's own resource group (the subscription of the existing API Management instance) | A custom role, *Meternaut gateway deployer*, listed below | Add and change objects in the one API Management instance (its APIs, backends, policy fragments, named values, loggers, products and its service-level settings), attach an identity to it, make managed identities in that group, and run deployments in it. It can read the instance's Application Insights and, once the first contract exists, that contract's key, to test the gateway with it. It cannot delete anything: not an object of the instance, not the instance, not an identity |

**In GitHub**, on this repository: five secrets (the identity's client id, the tenant id, the subscription id, and the resource ids of the API Management instance and of its Application Insights; none is a password) and eight variables (the project's resource group, the region, two address ranges, the DNS server, the owner's address twice and the budget). The workflow reads them; none is in the repository.

## What the identity can and cannot do

It can add and change objects in the API Management instance and change its service-level settings, because the one thing it must do to the instance itself, attaching an identity, is a service-level write, and Azure's roles cannot narrow a role to some objects of an instance. What holds it to the Citadel module's objects is the workflow: it runs only the pinned module and [`tools/gateway-prep.py`](../tools/gateway-prep.py), which reads the instance, keeps its system-assigned identity when it adds one, writes only when the instance has not changed since it was read, and writes only in GitHub Actions. It has no right to delete in the instance or in the gateway's group: taking the module's objects out again (`pause`, `remove`) needs delete rights, which the owner grants for that one run, in his own words, and takes away again; they are never a standing right.

It can delete the project's resource group with everything in it, because *Contributor* covers that; the workflow never does, and a budget alert is the only warning. It cannot create other resource groups, change anything else in either subscription, register a resource provider, purge a soft-deleted account, give any role except the eight above to a service principal in the project's group, or touch the network, the firewall or the DNS of the landing zone.

Who can use the credential: any run of the workflow on `main`. The repository is private, and the workflow starts only by hand and only as the owner's account ([`tools/workflow-lint.py`](../tools/workflow-lint.py) fails a change that would make it start any other way). GitHub's Free plan has no required reviewer for a private repository, and the guard cannot tell the owner's click from a run that an agent starts with his token, so the approval is a rule of process and not a technical barrier. The owner has said that he merges and clicks nothing himself: he tells the agent in plain words in the conversation, and the agent merges and starts the run. An agent starts `what-if`, which reads and changes nothing, on its own; `model-side`, `gateway-prepare`, `gateway` and `contract` each need his words (one yes to the whole list is enough).

## Checked first, read-only

- The resource providers that the workflow needs (`Microsoft.CognitiveServices`, `Microsoft.Network`, `Microsoft.Consumption`, `Microsoft.ManagedIdentity`, `Microsoft.Authorization`, `Microsoft.Resources`, `Microsoft.ApiManagement`, `Microsoft.Insights`, and for the usage recording `Microsoft.Web`, `Microsoft.App` (the subnet of a Flex Consumption app is delegated to `Microsoft.App/environments`), `Microsoft.Storage`, `Microsoft.EventHub`, `Microsoft.DocumentDB` and `Microsoft.OperationalInsights`) are registered in both subscriptions. The identity cannot register one; `Microsoft.DocumentDB` was not registered in the project's subscription and was registered by hand on 2026-11-04 (see below); `Microsoft.App` was found registered on 2026-11-04.
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

The owner ordered the usage recording built ("build the whole thing, with the 265 storage ... build it now"), and, the same day, ordered every key out of it. It needs four things that the workflow's identity may not do itself, because they are not changes of the project's resource group: they are done by hand, once, by the person who ordered it, and reported at once. They are narrow and none widens the identity beyond the project's group.

1. **A resource provider.** `Microsoft.DocumentDB` (Cosmos DB) was not registered in the project's subscription. Done on 2026-11-04: `az provider register --namespace Microsoft.DocumentDB`. The same step would be needed for any other provider that the workflow reports as not registered.
2. **More roles that the identity may give.** The condition of the *Role Based Access Control Administrator* assignment on the project's group lists the roles that the identity may give to a service principal. The usage recording gives the gateway's identity and the workflow's identity *Azure Event Hubs Data Sender* (`2b629674-e913-4c01-ae53-ef4638d8f975`) and the function app's identity *Azure Event Hubs Data Receiver* (`a638d3c7-ab3a-418d-83e6-5f17a39d4fde`), *Storage Blob Data Owner* (`b7e6dc6d-f1e8-4753-8033-0f276bb0955b`), *Storage Queue Data Contributor* (`974c5e8b-45b9-4653-ba55-5f855dd0fb88`), *Storage Table Data Contributor* (`0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3`) and *Monitoring Metrics Publisher* (`3913510d-42f4-4e42-8a64-420c390055eb`), each on the one resource that it is for. The condition lists those six besides *Cognitive Services OpenAI User* (the two Event Hubs roles were added earlier on 2026-11-04, the other four later that day, when the Logic App was replaced by the function app: see the changelog). It is replaced as a whole (delete, then create; nothing runs in between):

   ```powershell
   $scope = "/subscriptions/$devSub/resourceGroups/$hubGroup"
   $roles = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd, 2b629674-e913-4c01-ae53-ef4638d8f975, a638d3c7-ab3a-418d-83e6-5f17a39d4fde, b7e6dc6d-f1e8-4753-8033-0f276bb0955b, 974c5e8b-45b9-4653-ba55-5f855dd0fb88, 0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3, 3913510d-42f4-4e42-8a64-420c390055eb'
   $condition = "((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$roles} AND @Request[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'})) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$roles} AND @Resource[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'}))"
   $old = az role assignment list --assignee-object-id $principal --scope $scope --role 'Role Based Access Control Administrator' --query "[0].id" --output tsv
   az role assignment delete --ids $old
   az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal --role 'Role Based Access Control Administrator' --scope $scope --condition $condition --condition-version 2.0
   ```
3. **Two roles for the function app's identity, after the first `recording` run.** The copy jobs read the gateway's Application Insights with the function app's user-assigned identity (`id-meternaut-usage`), which exists only after the run (the workflow's summary prints its object id). The first role is *Monitoring Reader* on that one Application Insights component. The second is needed because the component is workspace-based and its workspace, the central one of the landing zone, is in the mode "Require workspace permissions" (the setting `enableLogAccessUsingOnlyResourcePermissions` is false): with the role on the component alone the query ran and returned nothing (checked: the same query as the owner returned the rows). So a custom role, *Meternaut usage reader*, that reads one table of the workspace (`AppMetrics`, where the metrics of workspace-based Application Insights are kept) is defined on the workspace's resource group and given to the identity on the workspace and nothing else. The table is that of every component that writes to the workspace, not only the gateway's; the owner of the workspace can instead switch it to resource permissions, after which the first role alone suffices:

   ```powershell
   $mgmt = '<subscription id of the central workspace>'; $wsGroup = '<its resource group>'; $ws = '<resource id of the central workspace>'
   az role assignment create --assignee-object-id <object id of the function app's identity> --assignee-principal-type ServicePrincipal --role 'Monitoring Reader' --scope $insights
   # the custom role is made only when it is absent (it was made on 2026-11-04); the definition goes in as text, not as a file
   if (-not (az role definition list --subscription $mgmt --name 'Meternaut usage reader' --query '[0].name' --output tsv)) {
     $role = @{ Name = 'Meternaut usage reader'; IsCustom = $true; Description = 'Reads one table (AppMetrics) of the central workspace, so that the usage copy jobs of Meternaut can read the gateway token metrics. Nothing else.'
       Actions = @('Microsoft.OperationalInsights/workspaces/read', 'Microsoft.OperationalInsights/workspaces/query/read', 'Microsoft.OperationalInsights/workspaces/query/AppMetrics/read')
       NotActions = @(); DataActions = @(); AssignableScopes = @("/subscriptions/$mgmt/resourceGroups/$wsGroup") }
     az role definition create --subscription $mgmt --role-definition ($role | ConvertTo-Json -Depth 5 -Compress)
   }
   az role assignment create --assignee-object-id <object id of the function app's identity> --assignee-principal-type ServicePrincipal --role 'Meternaut usage reader' --scope $ws
   ```

   The custom role exists since 2026-11-04 (made for the first version's Logic App); only the assignment to the new identity is new. The identity is user-assigned, so it survives a new function app and keeps these roles; if it is ever deleted and made again, its object id is new and this step is done again. These two assignments are in other teams' subscriptions, where the workflow's identity has no rights and must not get any: that is why they are a hand step and not an action of the workflow. Done on 2026-11-04, after the first run had made the identity and before the run that published the code.
4. **What the first version left behind is removed.** Seven role assignments belong to the version that this one replaced, and the incremental deployment does not remove them. Four are Azure roles: the three of the old Logic App's identity (the workflow deletes the Logic App, and the identity goes with it, so each shows as "Identity not found": *Monitoring Reader* on the gateway's Application Insights, *Meternaut usage reader* on the workspace, and *Azure Event Hubs Data Receiver* on the Event Hubs namespace), and the namespace-wide *Azure Event Hubs Data Sender* of the gateway's identity, which the template now gives on the two usage hubs only. Three are Cosmos DB data roles of the account: *Data Contributor* of the old Logic App's identity, and *Data Contributor* and *Data Reader* of the workflow's identity, which nothing needs now (the account has no public endpoint, so the runner cannot read it). Done on 2026-11-04, after the first run that published the code, and each deletion reported. The way to find them is one Azure Resource Graph query on the `authorizationresources` table for the principals' object ids, and `az cosmosdb sql role assignment list` for the account's own roles; the way to remove them is `az role assignment delete --ids <id>` and `az cosmosdb sql role assignment delete`. Left on the account afterwards: the one *Data Contributor* of the function app's identity.

One optional repository variable: `RECORDING_READER_IDS`, a comma-separated list of the object ids of the people who may read the usage store in Cosmos DB (a data role of Cosmos DB, not an Azure role). The store has no public endpoint, so a reader also needs a network path to its private endpoint (a machine in the virtual network or one that is connected to it); the Azure portal's Data Explorer does not work from outside. Without the variable nobody but the function app can read it.

## Added on 2026-11-04 for the first cases

The first cases ([proposal](../docs/proposals/02-first-cases.md)) are a second function app that only reads Azure. Its identity, `id-meternaut-cases`, exists after the first run of the action `cases` (the run's summary prints its object id). The workflow's identity has no right outside the project's group and must not get one, so the two things that the cases need there are done by hand, once, on the owner's written word, and reported at once. Nothing in this step gives the workflow's identity a right. The deploy identity's role condition already lists every role that the template gives, so it is not widened again.

1. **Two read roles on the pilot subscription**, for the identity: *Reader* and *Cost Management Reader* (`72fafb9e-0641-4937-9268-a91bfd8191a3`). They read the pilot estate and its cost lines; neither reads a secret or changes anything.

   ```powershell
   az role assignment create --assignee-object-id <object id of id-meternaut-cases> --assignee-principal-type ServicePrincipal --role 'Reader' --scope "/subscriptions/$devSub"
   az role assignment create --assignee-object-id <object id of id-meternaut-cases> --assignee-principal-type ServicePrincipal --role 'Cost Management Reader' --scope "/subscriptions/$devSub"
   ```
2. **One custom role and one assignment in the gateway's subscription.** The gateway always requires the access product's key, so the app reads that key at the start of each run (AGENTS.md rule 23 names this one key). The custom role allows that one read and the read of the subscription, and it is given on the one subscription of the access product, on nothing else:

   ```powershell
   $gw = '<subscription id of the gateway>'; $gwGroup = '<resource group of the gateway>'; $apim = '<name of the gateway instance>'
   # the custom role is made only when it is absent; the definition goes in as text, not as a file
   if (-not (az role definition list --subscription $gw --name 'Meternaut gateway key reader' --query '[0].name' --output tsv)) {
     $role = @{ Name = 'Meternaut gateway key reader'; IsCustom = $true; Description = 'Reads the key of one gateway subscription, so that the first cases of Meternaut can call the models through the gateway. Nothing else.'
       Actions = @('Microsoft.ApiManagement/service/subscriptions/read', 'Microsoft.ApiManagement/service/subscriptions/listSecrets/action')
       NotActions = @(); DataActions = @(); AssignableScopes = @("/subscriptions/$gw/resourceGroups/$gwGroup") }
     az role definition create --subscription $gw --role-definition ($role | ConvertTo-Json -Depth 5 -Compress)
   }
   az role assignment create --assignee-object-id <object id of id-meternaut-cases> --assignee-principal-type ServicePrincipal --role 'Meternaut gateway key reader' --scope "/subscriptions/$gw/resourceGroups/$gwGroup/providers/Microsoft.ApiManagement/service/$apim/subscriptions/meternaut-agents-sub-01"
   ```

   The identity is user-assigned, so it survives a new function app and keeps these roles; if it is ever deleted and made again, its object id is new and this step is done again. The monthly token allowance of the access product (2,000,000) needs no hand step: it is a number in `environment/contract.json`, applied by the action `contract`.

   **Done on 2026-11-05**, on the owner's word ("GO"), each grant reported at once: *Reader* and *Cost Management Reader* for the identity on the pilot subscription; the custom role *Meternaut gateway key reader*, defined for the gateway's resource group; and its assignment on the one subscription of the access product. The last grant was made 2 minutes and 24 seconds before the first run of the Watch read the key. They were read back with `python tools/access-requirements.py check`: all five requirements, R1 to R5, were present, which includes the two roles of the usage recording. The Activity Log of both subscriptions shows one operation by the identity during that run, the key read, and no write.

   **The same steps as a tool.** [`access-requirements.json`](access-requirements.json) lists these grants and the two of the usage recording (R1 to R5), and [`tools/access-requirements.py`](../tools/access-requirements.py) reads it. An earlier version listed one more, the writer's role (W1); it is retired ([below](#changed-on-2026-11-05-meternaut-runs-a-change-as-the-person-who-approves-it)). `check` shows which are present. `grant` is a dry run that prints the exact commands; with `--apply` the person who owns the place makes them with their own sign-in. It never runs in a pipeline. The commands above stay as the record of what was done. [Access and onboarding](../docs/proposals/03-access-and-onboarding.md) says what an installer or a pipeline must do, and why the first grant needs a person.

## Added on 2026-11-05 for the console and the approval loop

The console and the approval loop ([proposal](../docs/proposals/04-the-loop.md)) add an identity to the function app of the first cases: `id-meternaut-console-auth`, which holds no role and only presents a token to Microsoft Entra in place of a client secret. It exists after the first run of the action `cases` that carries the new template (the run's summary prints its object id). The first version of the loop also made `id-meternaut-runner`, an identity that changed Azure; it was retired on the same day ([below](#changed-on-2026-11-05-meternaut-runs-a-change-as-the-person-who-approves-it)). Three things around the console (items 2 to 4 below) are outside the project's group or outside Azure, so the workflow cannot make them and must not get the right to. Each is a hand step, run once by a person who owns the place, with their own sign-in, on the owner's written word, and reported at once. The first two have a tool that reads before it writes, changes nothing without `--apply`, refuses to run in a pipeline and removes nothing.

1. **Retired on 2026-11-05: the writer's custom role and its one assignment. Do not make them.** The app no longer changes Azure with an identity of its own ([below](#changed-on-2026-11-05-meternaut-runs-a-change-as-the-person-who-approves-it) says what runs a change now, and how the role and the assignment are removed where they exist). The role was *Meternaut waste remover*, assigned to `id-meternaut-runner` on the project's group and nowhere else. Its definition is kept here, so that a person can see what the removal takes away:

   ```json
   {
     "Name": "Meternaut waste remover",
     "IsCustom": true,
     "Actions": [
       "Microsoft.Compute/disks/read",
       "Microsoft.Compute/disks/delete",
       "Microsoft.Network/publicIPAddresses/read",
       "Microsoft.Network/publicIPAddresses/delete",
       "Microsoft.Authorization/locks/read"
     ],
     "NotActions": [],
     "DataActions": [],
     "AssignableScopes": ["/subscriptions/<project subscription>/resourceGroups/<project group>"]
   }
   ```
2. **The sign-in of the console: one Microsoft Entra app registration with no secret.** It is made by [`tools/entra-setup.py`](../tools/entra-setup.py): this tenant only, two redirect addresses (the platform's sign-in, and `/arm/return` for the sign-in to Azure Resource Manager that an approval starts), ID tokens on, public client flows off, two delegated permissions (Microsoft Graph `User.Read`, and Azure Service Management `user_impersonation`) with the administrator's consent, an enterprise application that requires assignment, the people who may sign in assigned, and a federated identity credential that trusts `id-meternaut-console-auth`. It holds no client secret and no certificate (rule 23). The tool prints the client id, which goes in the repository variable `CONSOLE_APP_CLIENT_ID`; the action `cases` is run again, and only then does the template switch the platform's sign-in on. The console serves no page without it. A registration that was made before 2026-11-05 lacks the second redirect address and the second permission: [below](#changed-on-2026-11-05-meternaut-runs-a-change-as-the-person-who-approves-it).

   ```powershell
   python tools/entra-setup.py check --tenant-id $tenant --host $host --identity-principal-id <object id of id-meternaut-console-auth> --assign <object id of each person>
   python tools/entra-setup.py apply --tenant-id $tenant --host $host --identity-principal-id <object id of id-meternaut-console-auth> --assign <object id of each person> --apply
   ```
3. **The mailbox that sends the letters, and the one right to send as it.** It is made by [`tools/exchange-setup.py`](../tools/exchange-setup.py): one shared mailbox whose display name ends "(AI)", Exchange's role *Application Mail.Send* for `id-meternaut-cases` limited by a management scope to that one mailbox (no Microsoft Entra permission for mail is given: the two add up, and one for mail would let the identity send as every mailbox), and a read back that includes a proof that the identity may not send as another mailbox. Exchange applies a new assignment to live sends after 30 minutes to two hours. A new Exchange Online organization can also refuse to make the scope until a one-time step has been run, `Enable-OrganizationCustomization`; the tool sends it only when Exchange asks for it (it only un-consolidates stored objects so that custom scopes and roles can be made, and changes no mail flow and no policy), says so, and tries the refused cmdlet again. After that step Exchange can refuse the role assignment itself for about an hour ("You must be assigned a delegating role assignment ..."), until it has applied the right to give the role: the tool says so and stops, and the next run, an hour later, makes it. The role group rows that Exchange shows for a service principal (the default role assignment policy of mailbox users) are not the identity's and are not counted as strays.

   ```powershell
   python tools/exchange-setup.py check --tenant-id $tenant --domain <default domain> --identity-client-id <client id of id-meternaut-cases> --identity-principal-id <object id of id-meternaut-cases> --other-mailbox <an existing other mailbox>
   python tools/exchange-setup.py apply --tenant-id $tenant --domain <default domain> --identity-client-id <client id of id-meternaut-cases> --identity-principal-id <object id of id-meternaut-cases> --other-mailbox <an existing other mailbox> --apply
   ```
4. **Three repository variables**, read by the template and by the workflow's checks (none is a secret): `CONSOLE_APP_CLIENT_ID` (step 2; the same client id is the one that the sign-in to Azure Resource Manager uses, so there is no variable for that), `CONSOLE_PEOPLE` (a JSON list of the people of the console: object id, name, roles, address) and `MAIL_SENDER` (the address of the shared mailbox). The planted waste is made by the action `plant`, which needs no variable.

## Changed on 2026-11-05: the cases app runs on a Basic plan

The cases app moved from the Flex Consumption plan to a Basic plan (B1, Linux, always on), because the Flex front end held requests to the console for 15 to 60 seconds (the [changelog](../CHANGELOG.md) has the measurements). The move needs nothing by hand. The action `cases` does this, in this order, with the deployment identity's existing rights (*Contributor* on the project's group, and its role-assignment right with the condition above):

1. If the cases app still runs on a Flex Consumption plan, it removes the app and then its plan, and waits for the host name to be let go. It touches only the app that the repository names and the plan that the app runs on.
2. If the container `app-package-cases` is still in the usage recording's storage account (the Flex app kept its package there), it removes the *Storage Blob Data Owner* assignment that is made on that container itself, and then the container. The condition lets the identity delete a role that the templates give to a service principal, and no other. Nothing else in the account is touched; the usage recording's own package container stays.
3. If the app is integrated with another subnet than `snet-cases` (the first version used `snet-web`), it takes that integration away, so that the template then makes a new one.
4. It deploys the template, which makes the plan, the subnet `snet-cases` (the last free /27 of the virtual network, delegated to `Microsoft.Web/serverFarms`, with a network security group of its own) and the app under the same name, so the host name, the sign-in's reply address and the links in the letters do not change. **The subnet is made only while it is not there** (the workflow reads that from Azure and passes it as `webSubnetExists`): the landing zone's network manager puts a route table on a new subnet about a minute later, and a template that made the subnet again would take that table away, and with it the subnet's way to the landing zone's DNS ([rule 27](../AGENTS.md); it happened to `snet-web` on 2026-11-05). The app gets `WEBSITES_CONTAINER_START_TIME_LIMIT` = 600 seconds, because a start that has to wait for DNS can outlast the platform's default 230.
5. It publishes the package with a zip deployment to the app's deployment site, with the signed-in identity's own token: basic authentication is off on that site and on the FTP endpoint, and no password exists.
6. It waits (no credential, up to 25 minutes) until the app answers on `/healthz`, signs in again, says whether `snet-pe` and `snet-cases` carry the route table of the landing zone's network manager (the manager puts it on a new subnet 70 seconds to five minutes after the subnet is made, and the app cannot start without it; the app's start limit of 600 seconds lets its first start wait), lists the four functions, and removes `snet-web` when the platform has let go of its link to the plan; if the link is still there it says so, and the next run of `cases` removes the subnet.

No new resource provider is needed (`Microsoft.Web` serves both plans). The baseline template (`model-side`) makes the virtual network only while it is not there (`networkExists`, read from Azure by the workflow), for the same reason (rule 27).

## Changed on 2026-11-05: Meternaut runs a change as the person who approves it

The first version of the loop had one identity that changed Azure, `id-meternaut-runner`, with one custom role in the project's resource group. The owner rejected a standing write right for a tool, so Meternaut now holds no right to change Azure. The function app has two identities: `id-meternaut-cases` reads the estate and stores the records, and `id-meternaut-console-auth` holds no role. When a person approves a plan, the console sends that person to Microsoft Entra to sign in to Azure Resource Manager (the OAuth 2.0 authorization code flow with PKCE, the delegated scope `https://management.azure.com/user_impersonation`, no refresh token). The console redeems the code with the app registration's federated credential (`id-meternaut-console-auth` presents a token for `api://AzureADTokenExchange` as the client assertion: no secret, no certificate) and runs the one change with that person's token. Azure checks that person's own rights, and its Activity Log shows that person as the caller. The 120-second window in which an approval could be cancelled is gone, because it needed a stored token. The template no longer makes `id-meternaut-runner` and no longer has the settings `WRITER_RESOURCE_GROUP`, `WRITER_SUBSCRIPTION_ID`, `WRITER_CLIENT_ID` and `APPROVAL_DELAY_SECONDS`. It gives the app the one resource group and subscription in which the console runs a change (`CHANGE_RESOURCE_GROUP`, `CHANGE_SUBSCRIPTION_ID`) and, once `CONSOLE_APP_CLIENT_ID` is set, the three settings of the sign-in to Azure together: `SIGNIN_TENANT_ID`, `SIGNIN_CLIENT_ID` (that client id) and `OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID` (the client id of `id-meternaut-console-auth`). Until then none of the three is set (the app refuses a part of them), and nobody can approve a change. [The loop](../docs/proposals/04-the-loop.md) and [run as the approver](../docs/proposals/05-run-as-the-approver.md) say why and how.

What the first version made is removed, and one step is new. The workflow does none of it, and its identity must not get a right to (rule 18): each is done by hand, once, by a person who owns the place, with their own sign-in, on the owner's written word, and reported at once.

1. **The writer's role assignment and role definition are removed from the project's group,** the assignment first and then the definition. Where the role was never granted, there is nothing to remove.

   ```powershell
   python tools/access-requirements.py retire --project-subscription $devSub --project-group $hubGroup
   python tools/access-requirements.py retire --project-subscription $devSub --project-group $hubGroup --apply
   ```

   The first command is a dry run: it reads and prints what it would remove. With `--apply` it removes the assignments of the role *Meternaut waste remover* in the project's group (whoever holds them: the assignment of a deleted identity is found too), and then the role definition of that name (its definition is under step 1 of the console and approval loop section above), and only when no assignment of it remains. It reports the identity `id-meternaut-runner` and never deletes it. It removes nothing else. Like `grant`, it never runs in a pipeline: the deployment identity holds no right to remove either.
2. **The identity `id-meternaut-runner` is removed by the workflow.** The template no longer makes it and no longer lists it among the app's identities, the app no longer uses it, and a deployment never removes what a template stops making. After step 1 it holds no right. The action `cases` removes it, by its name, when it is still there, the cases app does not carry it and no role is assigned to it at or around the project's group; any other state stops the run and says why. Nobody has to delete it by hand.
3. **The one new step in Microsoft Entra.** The app registration of the console gets the delegated permission *Azure Service Management* `user_impersonation` (the API of Azure Resource Manager), the administrator's consent for it (so that no approver is asked to consent at the sign-in) and the redirect address `https://<host>/arm/return`. [`tools/entra-setup.py`](../tools/entra-setup.py) makes all three, with the commands of [step 2 of the console and approval loop section](#added-on-2026-11-05-for-the-console-and-the-approval-loop): `check` reads and says what is missing, and `apply` with `--apply` makes only what is missing. It removes nothing and touches nothing else of the registration, with one exception: it switches public client flows off when they are on, because a code that is redeemed with a federated credential gives nothing to anybody else only while the app is a confidential client. The platform's reply address, the permission `User.Read` and the federated credential stay as they are, anything that somebody else added to the redirect addresses or the permissions stays too, and the registration still holds no secret and no certificate. A person who may not consent for the whole tenant still gets the redirect address and the permission made: the tool says so, and prints the address that a tenant administrator opens to give the consent. Until the redirect address and the consent are in place, Microsoft Entra refuses the sign-in that an approval starts, and nothing in Azure changes.

Who may approve is not a grant of Meternaut's. The change is made with the approver's own rights, at the place of the resource: for the planted waste, the right to delete a managed disk and a public IP address in the project's group. A person who does not hold it gets Azure's refusal, and nothing changes.

## Changed on 2026-11-06: the Foundry resource of the agents

Meternaut now finds waste with agents in Microsoft Foundry (Agent Service), and the agents need a place to live. The new action `foundry` makes it. It deploys [`environment/foundry/main.bicep`](foundry/main.bicep) into the project's resource group, with the deployment identity's existing rights (*Contributor* on the group, and its role-assignment right with the condition above), and reads the result back from Azure. What it makes:

- **A second Foundry resource**, `aif-meternaut-agents-<digest>` (kind AIServices, `allowProjectManagement` true, a system-assigned identity), with public network access off and local authentication off. It is reached through one private endpoint into `snet-pe`, copied from the model account's endpoint, and the landing zone's policy registers its name ([rule 19](../AGENTS.md): no private DNS zone, link or zone group is made).
- **One project**, `meternaut`, with a system-assigned identity of its own. The agents live in it. The address that the cases app calls is `https://<resource>.services.ai.azure.com/api/projects/meternaut`, with a Microsoft Entra token for `https://ai.azure.com`.
- **The same two models** as the model account, from [`models.json`](models.json): the same names, versions, deployment type and capacity. The agents use them directly, not through the gateway. That is a temporary exception to [rule 15 (c)](../AGENTS.md): the gateway's API Management instance is on the Developer tier, and the API Management connection that Foundry documents for agents needs Standard v2 or Premium and is in preview.
- **A guardrail**, `meternaut-agents`, based on `Microsoft.DefaultV2`, in the mode Blocking, with the Prompt Shields for user prompt attacks and indirect attacks. The model deployments use it, and the agents inherit it from them.
- **A connection of the project to the Application Insights component `appi-meternaut`** for the agents' traces. It uses the project's managed identity, with *Monitoring Metrics Publisher* on the component. The component takes telemetry only with Microsoft Entra ID, and no key exists anywhere.
- **One role for the cases app**: *Azure AI User* (named *Foundry User* since the rename of the Foundry roles; the id is the same) for `id-meternaut-cases`, on the project and nowhere else. Its data actions let the app create agents and run them in the project, and nothing else here.

**Why a new resource.** The model account `aif-meternaut-<digest>` was made with `allowProjectManagement` false, and Microsoft Learn says that this setting cannot be changed after the account exists (Create a project for Microsoft Foundry). So that account can never hold a project or an agent. It stays as it is and keeps serving the gateway.

**The one hand step: one more role in the condition.** The condition of the deploy identity's *Role Based Access Control Administrator* assignment lists the roles that it may give to a service principal ([above](#added-on-2026-11-04-for-the-usage-recording)). The template gives the cases app *Azure AI User*, which is not in the list, so the action would be refused. *Monitoring Metrics Publisher*, the other role that the template gives, is in the list already. A person who may assign roles in the project's group adds the one id, with their own sign-in, on the owner's written word, and reports it at once. The condition is replaced as a whole (delete, then create; nothing runs in between), so the commands read the current condition first, change nothing but the list of ids, show what changes and ask before they write. They use `$devSub`, `$hubGroup` and `$principal` of the commands at the top of this page:

```powershell
function az { & 'C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe' -IBm azure.cli @args }
$scope = "/subscriptions/$devSub/resourceGroups/$hubGroup"
$foundryUser = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
# 1. Read the assignment and the role ids that its condition lists (the list for a write and the list for a delete must be the same)
$old = az role assignment list --assignee-object-id $principal --scope $scope --role 'Role Based Access Control Administrator' --query '[0]' --output json | ConvertFrom-Json
if (-not $old) { throw 'The deploy identity has no Role Based Access Control Administrator assignment on the project group.' }
$lists = @([regex]::Matches($old.condition, 'GuidEquals\s*\{([^}]*)\}') | ForEach-Object { ($_.Groups[1].Value -split ',\s*' | Sort-Object) -join ',' })
if ($lists.Count -ne 2 -or ($lists | Select-Object -Unique).Count -ne 1) { throw 'The condition is not the one that the templates expect (two lists of the same role ids). Stop and read it.' }
$current = $lists[0] -split ','
if ($current -contains $foundryUser) { throw 'The condition lists the Foundry User role already: nothing to do.' }
# 2. Add the one id, and change nothing else of the condition
$roles = (@($current) + $foundryUser) -join ', '
$condition = "((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$roles} AND @Request[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'})) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$roles} AND @Resource[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'}))"
$shape = { param($c) $c -replace 'GuidEquals\s*\{[^}]*\}', 'GuidEquals {ids}' -replace '\s+', ' ' }
if ((& $shape $old.condition) -ne (& $shape $condition)) { throw 'The condition differs from the templates in more than the role ids. Stop and read it.' }
# 3. Show the difference, then replace
Write-Host "Role ids now:        $($current -join ', ')"
Write-Host "Role ids afterwards: $roles"
Write-Host "Added:               $foundryUser (Azure AI User, named Foundry User since the rename)"
if ((Read-Host 'Replace the condition as shown? Type yes') -ne 'yes') { throw 'Stopped. Nothing was changed.' }
az role assignment delete --ids $old.id
az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal --role 'Role Based Access Control Administrator' --scope $scope --condition $condition --condition-version 2.0
# 4. Read it back
az role assignment list --assignee-object-id $principal --scope $scope --role 'Role Based Access Control Administrator' --query '[0].condition' --output tsv | Select-String $foundryUser
```

**The order.** (1) The hand step above. (2) The action `what-if` (it now shows the Foundry resource too, once the usage recording has made the Application Insights component), and then the action `foundry`. (3) The action `cases`: it passes the project's address to the app only when the project is in Azure, so the app's settings `FOUNDRY_PROJECT_ENDPOINT` and `INVESTIGATE` (on when there is an address, off otherwise) change at that run and not before. On an estate where `cases` has never run, the order is `recording`, `contract`, `cases`, then the hand step, `foundry` and `cases` again: the role goes to `id-meternaut-cases`, which the first run of `cases` makes, and `foundry` refuses to run without it.

**What the action checks, and what it needs.** Before it deploys, `foundry` requires the Application Insights component of the usage recording and the identity `id-meternaut-cases`, and that its parameter file carries that identity's object id: no role is ever given to a placeholder. After the deploy it waits up to 40 minutes for the landing zone's policy to register the private endpoint in the central zone `privatelink.services.ai.azure.com` (the zone of the project address; `privatelink.cognitiveservices.azure.com` and `privatelink.openai.azure.com` are said and not required). If that zone is not registered, the cases app cannot reach the project: the run fails, and the owners of the landing zone are asked for the zone. Nobody creates one. It then reads the resource back from Azure with GET requests only, and fails the run unless public network access is Disabled, local authentication is off, project management is on, the resource and the project have identities, the private endpoint is approved, every model of `models.json` is deployed as it says with the guardrail, the guardrail blocks the three Prompt Shields, and the project's connection to Application Insights is made with an identity. A tenant policy with the effect Modify does not refuse a resource: it rewrites it, so the read-back is the check ([rule 19](../AGENTS.md)). The run's summary prints the project address, and says what the resources hold. It prints no key, because none exists.

**Costs.** The Foundry resource and the project cost nothing while no agent runs. The private endpoint costs a few euros a month, like the others. The two deployments of the models bill by token when the agents run, from the same kind of quota as the model account's (`DataZoneStandard`, 20 thousand tokens a minute each): the two new deployments need that much more quota, which the deploy identity cannot read, so the first run is where a shortage would show. No new resource provider is needed.

**What a person sees in the Foundry portal.** The traces of the agents are in Application Insights. To read them in the Foundry portal a person needs *Log Analytics Reader* on the component (and *Privileged Monitoring Data Reader* where the tables are protected) with their own account. The template gives no person any role.

## After it

The branch that holds this page is merged to `main` (the workflow runs only there, and the credential exists only for `main`; this was done on 2026-11-03, see the changelog), and the workflow is started with the action `what-if`, from the Actions tab (*Hub*, *Run workflow*) or with `gh workflow run deploy-hub.yml --ref main -f action=what-if`. It shows what the next steps would create, and changes nothing. Then, each on the owner's word: `model-side` (the gateway's identity, the network, the model account); `gateway-prepare` (the identity attached to the gateway, the Application Insights logger and, when the usage recording's Event Hubs namespace exists, the two Event Hub loggers: the only changes to the instance itself); a second `what-if`, which shows the exact diff of the Citadel module and is read before anything else; and `gateway` (the module's objects, with its two usage-recording fragments only when both Event Hub loggers exist: see the changelog). Last comes `contract` (the first contract: a product that grants the two inference APIs, with its policy and its one subscription; the run reads the subscription's key from the gateway, tests the gateway with it and keeps it nowhere; with the input `check_limits` it also proves the token limit). The usage recording has two actions of its own: `recording` (removes the key-based Logic App version if it is still there; makes the stores, the identity, the private endpoints and the function app; publishes the code) and, once the two roles in the gateway's and the workspace's subscriptions are given (above), `recording-check` (the copy jobs started once through the control hub, and what they said read back from the function app's telemetry). The Foundry resource of the agents has one action, `foundry` (after the hand step of [its section](#changed-on-2026-11-06-the-foundry-resource-of-the-agents) and before the next `cases`: it makes the resource, its project, the models, the guardrail and the private endpoint, and reads them back from Azure). The first cases have two more: `cases` (after `recording` and `contract`: the second function app with its two identities, its control hub, the longer retention of the traces and the History workbook, and the code published) and, once the three roles above are given, `cases-run` (one Watch started through the control hub, and its History read back from the telemetry). The console and the approval loop have two more: `loop-check` (the console's front door, read from outside with no sign-in: nothing but the health answer may be served, the return address of the Azure sign-in included, and a forged sign-in header must not open anything) and `plant` (makes a disk of Meternaut's own, and with the input `plant_public_ip` an address, in the project's group, tagged as planted waste, so that the loop has something real and harmless to find, to propose and, after a person approves, to delete with that person's own rights). One yes to the whole list lets the agent run them in this order, and stop at the first thing that differs from the list.

## Undoing it

Taking the model side away is meant to be a workflow's job (an action `remove`), and so is taking the module's objects and the contract out of the instance, which needs delete rights that the owner grants for that run only (see above). Neither is built yet: this page said that `remove` would exist before the first `model-side` run, and it did not, so it is the next change, and the changelog records that the promise was not kept. Until then the project's resource group can be deleted by hand, which takes the network, the model account, its private endpoint and the budget with it (the account stays soft-deleted, see below), and the module's objects can be left in the instance, where they do nothing without a caller that holds a contract's key. Taking the identity and the settings away is the other half of the bootstrap, so it is a manual step of the same kind, and it needs the owner's own plain-word yes, given separately from the one that created the identity: delete the role assignments (`az role assignment delete --assignee $principal --scope <each scope>`), the custom role, the two resource groups (with the second, the identity and its credential), and the secrets and variables (`gh secret delete`, `gh variable delete`).

A model account that was deleted is soft-deleted and keeps its name for a while. The workflow restores it by itself on the next `model-side`, so nothing has to be purged.
