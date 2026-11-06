# Bootstrap: the one step that is not a workflow

Every change to Azure goes through the workflow [`deploy-hub.yml`](../.github/workflows/deploy-hub.yml) ([AGENTS.md](../AGENTS.md) rule 18). The workflow signs in to Azure as an identity, and an identity cannot create itself, so a person creates it once. That is this page. It is the only manual step, and nothing here runs until the owner has said yes in plain words in the conversation.

## What the owner approves

**In Azure.** In the subscription that holds the project's resources: two resource groups (one for the identity, one for the project's own resources) and one managed identity with one credential. On the two groups that the workflow works in, these roles:

| Where | Role | What it lets the identity change |
|---|---|---|
| The project's resource group | *Contributor* | Create, change and delete the network, the model account, its private endpoint and the budget in that group, and nothing outside it |
| The same group | *Role Based Access Control Administrator*, limited by a condition | Give a service principal one of eight roles: *Cognitive Services OpenAI User* (so that the gateway's identity can run chat completions on the model account), and, for the usage recording, *Azure Event Hubs Data Sender* (the gateway's identity sends to the two usage event hubs; the workflow's identity sent to the two control hubs until 2026-11-06 and holds none since [the namespace was made private](#changed-on-2026-11-06-the-event-hubs-namespace-is-private), and since 2026-11-06 the Operator's identity sends to the two control hubs: [its section](#changed-on-2026-11-06-the-operator)), *Azure Event Hubs Data Receiver* (the function app's identity may read them), *Storage Blob Data Owner*, *Storage Queue Data Contributor* and *Storage Table Data Contributor* (what the function app's identity needs on its storage account), *Monitoring Metrics Publisher* (its telemetry, and the traces of the Foundry project) and, for the Foundry resource of the agents, *Azure AI User* (named *Foundry User* since the rename: the cases app's identity may create and run agents on the Foundry project; [added on 2026-11-06](#changed-on-2026-11-06-the-foundry-resource-of-the-agents)). Any other role, and any grant to a person or a group, is impossible |
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
2. **More roles that the identity may give.** The condition of the *Role Based Access Control Administrator* assignment on the project's group lists the roles that the identity may give to a service principal. The usage recording gives the gateway's identity *Azure Event Hubs Data Sender* (`2b629674-e913-4c01-ae53-ef4638d8f975`; it gave it to the workflow's identity too until 2026-11-06, when [that right was retired](#changed-on-2026-11-06-the-event-hubs-namespace-is-private)) and the function app's identity *Azure Event Hubs Data Receiver* (`a638d3c7-ab3a-418d-83e6-5f17a39d4fde`), *Storage Blob Data Owner* (`b7e6dc6d-f1e8-4753-8033-0f276bb0955b`), *Storage Queue Data Contributor* (`974c5e8b-45b9-4653-ba55-5f855dd0fb88`), *Storage Table Data Contributor* (`0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3`) and *Monitoring Metrics Publisher* (`3913510d-42f4-4e42-8a64-420c390055eb`), each on the one resource that it is for. The condition lists those six besides *Cognitive Services OpenAI User* (the two Event Hubs roles were added earlier on 2026-11-04, the other four later that day, when the Logic App was replaced by the function app: see the changelog). It was replaced as a whole (delete, then create; nothing ran in between). A later change of the same condition is one update in place, which cannot leave the identity without its assignment if it fails: see [the Foundry section](#changed-on-2026-11-06-the-foundry-resource-of-the-agents). What was run on 2026-11-04:

   ```powershell
   $scope = "/subscriptions/$devSub/resourceGroups/$hubGroup"
   $roles = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd, 2b629674-e913-4c01-ae53-ef4638d8f975, a638d3c7-ab3a-418d-83e6-5f17a39d4fde, b7e6dc6d-f1e8-4753-8033-0f276bb0955b, 974c5e8b-45b9-4653-ba55-5f855dd0fb88, 0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3, 3913510d-42f4-4e42-8a64-420c390055eb'
   $condition = "((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$roles} AND @Request[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'})) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$roles} AND @Resource[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'}))"
   $old = az role assignment list --assignee-object-id $principal --scope $scope --role 'Role Based Access Control Administrator' --query "[0].id" --output tsv
   az role assignment delete --ids $old
   az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal --role 'Role Based Access Control Administrator' --scope $scope --condition $condition --condition-version 2.0
   ```
3. **Two roles for the function app's identity, after the first `recording` run.** The copy jobs read the gateway's Application Insights with the function app's own system-assigned identity, which is made with the app and exists only after the run (the workflow's summary prints its object id). Until 2026-11-06 the app ran as a user-assigned identity, `id-meternaut-usage`, and the roles below were given to that one ([the move to system-assigned identities](#changed-on-2026-11-06-the-function-apps-move-to-system-assigned-identities-step-two)). The first role is *Monitoring Reader* on that one Application Insights component. The second is needed because the component is workspace-based and its workspace, the central one of the landing zone, is in the mode "Require workspace permissions" (the setting `enableLogAccessUsingOnlyResourcePermissions` is false): with the role on the component alone the query ran and returned nothing (checked: the same query as the owner returned the rows). So a custom role, *Meternaut usage reader*, that reads one table of the workspace (`AppMetrics`, where the metrics of workspace-based Application Insights are kept) is defined on the workspace's resource group and given to the identity on the workspace and nothing else. The table is that of every component that writes to the workspace, not only the gateway's; the owner of the workspace can instead switch it to resource permissions, after which the first role alone suffices:

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

   The custom role exists since 2026-11-04 (made for the first version's Logic App); only the assignment to the new identity is new. The identity is the app's own system-assigned one: it is made with the app and ends with it, so an app that is deleted and made again has a new object id, and this step is done again for it. These two assignments are in other teams' subscriptions, where the workflow's identity has no rights and must not get any: that is why they are a hand step and not an action of the workflow. Done on 2026-11-04 for the user-assigned identity that the app ran as then, after the first run had made the identity and before the run that published the code; for the system-assigned identity they are step one of [the move to system-assigned identities](#changed-on-2026-11-06-the-function-apps-move-to-system-assigned-identities-step-one), made with `tools/access-requirements.py`.
4. **What the first version left behind is removed.** Seven role assignments belong to the version that this one replaced, and the incremental deployment does not remove them. Four are Azure roles: the three of the old Logic App's identity (the workflow deletes the Logic App, and the identity goes with it, so each shows as "Identity not found": *Monitoring Reader* on the gateway's Application Insights, *Meternaut usage reader* on the workspace, and *Azure Event Hubs Data Receiver* on the Event Hubs namespace), and the namespace-wide *Azure Event Hubs Data Sender* of the gateway's identity, which the template now gives on the two usage hubs only. Three are Cosmos DB data roles of the account: *Data Contributor* of the old Logic App's identity, and *Data Contributor* and *Data Reader* of the workflow's identity, which nothing needs now (the account has no public endpoint, so the runner cannot read it). Done on 2026-11-04, after the first run that published the code, and each deletion reported. The way to find them is one Azure Resource Graph query on the `authorizationresources` table for the principals' object ids, and `az cosmosdb sql role assignment list` for the account's own roles; the way to remove them is `az role assignment delete --ids <id>` and `az cosmosdb sql role assignment delete`. Left on the account afterwards: the one *Data Contributor* of the function app's identity.

One optional repository variable: `RECORDING_READER_IDS`, a comma-separated list of the object ids of the people who may read the usage store in Cosmos DB (a data role of Cosmos DB, not an Azure role). The store has no public endpoint, so a reader also needs a network path to its private endpoint (a machine in the virtual network or one that is connected to it); the Azure portal's Data Explorer does not work from outside. Without the variable nobody but the function app can read it.

## Added on 2026-11-04 for the first cases

The first cases ([proposal](../docs/proposals/02-first-cases.md)) are a second function app that only reads Azure. Its identity is the app's own system-assigned one, which exists after the first run of the action `cases` (the run's summary prints its object id). Until 2026-11-06 the app ran as a user-assigned identity, `id-meternaut-cases`, and the commands below were run for that identity and stay as the record of what was done; the system-assigned identity that replaced it gets the same grants with `tools/access-requirements.py` ([the move to system-assigned identities](#changed-on-2026-11-06-the-function-apps-move-to-system-assigned-identities-step-two)). The workflow's identity has no right outside the project's group and must not get one, so the two things that the cases need there are done by hand, once, on the owner's written word, and reported at once. Nothing in this step gives the workflow's identity a right. The deploy identity's role condition already lists every role that the template gives, so it is not widened again.

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

   The identity was user-assigned, so it survived a new function app and kept these roles. The app's own system-assigned identity, which replaced it, does not: it is made with the app, so an app that is deleted and made again has a new object id, and these grants are made again for it. The monthly token allowance of the access product (2,000,000) needs no hand step: it is a number in `environment/contract.json`, applied by the action `contract`. The same grants for the system-assigned identity are made with `tools/access-requirements.py` ([the move to system-assigned identities](#changed-on-2026-11-06-the-function-apps-move-to-system-assigned-identities-step-one)).

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
3. **The mailbox that sends the letters, and the one right to send as it.** It is made by [`tools/exchange-setup.py`](../tools/exchange-setup.py): one shared mailbox whose display name ends "(AI)", Exchange's role *Application Mail.Send* for the identity of the cases app (its own system-assigned identity; `id-meternaut-cases` until 2026-11-06) limited by a management scope to that one mailbox (no Microsoft Entra permission for mail is given: the two add up, and one for mail would let the identity send as every mailbox), and a read back that includes a proof that the identity may not send as another mailbox. Exchange applies a new assignment to live sends after 30 minutes to two hours. A new Exchange Online organization can also refuse to make the scope until a one-time step has been run, `Enable-OrganizationCustomization`; the tool sends it only when Exchange asks for it (it only un-consolidates stored objects so that custom scopes and roles can be made, and changes no mail flow and no policy), says so, and tries the refused cmdlet again. After that step Exchange can refuse the role assignment itself for about an hour ("You must be assigned a delegating role assignment ..."), until it has applied the right to give the role: the tool says so and stops, and the next run, an hour later, makes it. The role group rows that Exchange shows for a service principal (the default role assignment policy of mailbox users) are not the identity's and are not counted as strays.

   ```powershell
   python tools/exchange-setup.py check --tenant-id $tenant --domain <default domain> --identity-client-id <appId of the cases app's service principal> --identity-principal-id <identity.principalId of the cases app> --other-mailbox <an existing other mailbox>
   python tools/exchange-setup.py apply --tenant-id $tenant --domain <default domain> --identity-client-id <appId of the cases app's service principal> --identity-principal-id <identity.principalId of the cases app> --other-mailbox <an existing other mailbox> --apply
   ```

   The identity is the cases app's system-assigned identity. `--identity-principal-id` is `identity.principalId` of the app, which the site shows (`az rest --method get --url "https://management.azure.com<resource id of the app>?api-version=2024-04-01" --query identity.principalId --output tsv`), and `--identity-client-id` is the `appId` of its service principal, which only Microsoft Entra shows: the owner's session reads it with `az ad sp show --id <object id> --query appId --output tsv` (the deployment identity may not read the directory). An app that is deleted and made again has a new identity, with a new object id and a new application id, and this step is done again for it ([the move to system-assigned identities](#changed-on-2026-11-06-the-function-apps-move-to-system-assigned-identities-step-two)).
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

The first version of the loop had one identity that changed Azure, `id-meternaut-runner`, with one custom role in the project's resource group. The owner rejected a standing write right for a tool, so Meternaut now holds no right to change Azure. The function app has two identities: one that reads the estate and stores the records (`id-meternaut-cases` when this was written; since 2026-11-06 the app's own system-assigned identity) and `id-meternaut-console-auth`, which holds no role. When a person approves a plan, the console sends that person to Microsoft Entra to sign in to Azure Resource Manager (the OAuth 2.0 authorization code flow with PKCE, the delegated scope `https://management.azure.com/user_impersonation`, no refresh token). The console redeems the code with the app registration's federated credential (`id-meternaut-console-auth` presents a token for `api://AzureADTokenExchange` as the client assertion: no secret, no certificate) and runs the one change with that person's token. Azure checks that person's own rights, and its Activity Log shows that person as the caller. The 120-second window in which an approval could be cancelled is gone, because it needed a stored token. The template no longer makes `id-meternaut-runner` and no longer has the settings `WRITER_RESOURCE_GROUP`, `WRITER_SUBSCRIPTION_ID`, `WRITER_CLIENT_ID` and `APPROVAL_DELAY_SECONDS`. It gives the app the one resource group and subscription in which the console runs a change (`CHANGE_RESOURCE_GROUP`, `CHANGE_SUBSCRIPTION_ID`) and, once `CONSOLE_APP_CLIENT_ID` is set, the three settings of the sign-in to Azure together: `SIGNIN_TENANT_ID`, `SIGNIN_CLIENT_ID` (that client id) and `OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID` (the client id of `id-meternaut-console-auth`). Until then none of the three is set (the app refuses a part of them), and nobody can approve a change. [The loop](../docs/proposals/04-the-loop.md) and [run as the approver](../docs/proposals/05-run-as-the-approver.md) say why and how.

What the first version made is removed, and one step is new. The workflow does none of it, and its identity must not get a right to (rule 18): each is done by hand, once, by a person who owns the place, with their own sign-in, on the owner's written word, and reported at once.

1. **The writer's role assignment and role definition are removed from the project's group,** the assignment first and then the definition. Where the role was never granted, there is nothing to remove.

   ```powershell
   python tools/access-requirements.py retire --project-subscription $devSub --project-group $hubGroup --only W1
   python tools/access-requirements.py retire --project-subscription $devSub --project-group $hubGroup --only W1 --apply
   ```

   The first command is a dry run: it reads and prints what it would remove. With `--apply` it removes the assignments of the role *Meternaut waste remover* in the project's group (whoever holds them: the assignment of a deleted identity is found too), and then the role definition of that name (its definition is under step 1 of the console and approval loop section above), and only when no assignment of it remains. It reports the identity `id-meternaut-runner` and never deletes it. `--only W1` keeps it to the writer: `retire` without it covers everything that the list retires, which includes (once the list names them) the grants of the user-assigned identities that the two function apps ran as before their system-assigned identities took over (the section on the move to system-assigned identities, below). Those need the names of the apps and the gateway's places as well, and are removed at their own time. Like `grant`, it never runs in a pipeline: the deployment identity holds no right to remove either.
2. **The identity `id-meternaut-runner` is removed by the workflow.** The template no longer makes it and no longer lists it among the app's identities, the app no longer uses it, and a deployment never removes what a template stops making. After step 1 it holds no right. The action `cases` removes it, by its name, when it is still there, the cases app does not carry it and no role is assigned to it at or around the project's group; any other state stops the run and says why. Nobody has to delete it by hand.
3. **The one new step in Microsoft Entra.** The app registration of the console gets the delegated permission *Azure Service Management* `user_impersonation` (the API of Azure Resource Manager), the administrator's consent for it (so that no approver is asked to consent at the sign-in) and the redirect address `https://<host>/arm/return`. [`tools/entra-setup.py`](../tools/entra-setup.py) makes all three, with the commands of [step 2 of the console and approval loop section](#added-on-2026-11-05-for-the-console-and-the-approval-loop): `check` reads and says what is missing, and `apply` with `--apply` makes only what is missing. It removes nothing and touches nothing else of the registration, with one exception: it switches public client flows off when they are on, because a code that is redeemed with a federated credential gives nothing to anybody else only while the app is a confidential client. The platform's reply address, the permission `User.Read` and the federated credential stay as they are, anything that somebody else added to the redirect addresses or the permissions stays too, and the registration still holds no secret and no certificate. A person who may not consent for the whole tenant still gets the redirect address and the permission made: the tool says so, and prints the address that a tenant administrator opens to give the consent. Until the redirect address and the consent are in place, Microsoft Entra refuses the sign-in that an approval starts, and nothing in Azure changes.

Who may approve is not a grant of Meternaut's. The change is made with the approver's own rights, at the place of the resource: for the planted waste, the right to delete a managed disk and a public IP address in the project's group. A person who does not hold it gets Azure's refusal, and nothing changes.

## Changed on 2026-11-06: the Foundry resource of the agents

Meternaut now finds waste with agents in Microsoft Foundry (Agent Service), and the agents need a place to live. The new action `foundry` makes it. It deploys [`environment/foundry/main.bicep`](foundry/main.bicep) into the project's resource group, with the deployment identity's existing rights (*Contributor* on the group, and its role-assignment right with the condition above), and reads the result back from Azure. What it makes:

- **A second Foundry resource**, `aif-meternaut-agents-<digest>` (kind AIServices, `allowProjectManagement` true, a system-assigned identity), with public network access off and local authentication off. It is reached through one private endpoint into `snet-pe`, copied from the model account's endpoint, and the landing zone's policy registers its name ([rule 19](../AGENTS.md): no private DNS zone, link or zone group is made).
- **One project**, `meternaut`, with a system-assigned identity of its own. The agents live in it. The address that the cases app calls is `https://<resource>.services.ai.azure.com/api/projects/meternaut`, with a Microsoft Entra token for `https://ai.azure.com`.
- **The same two models** as the model account, from [`models.json`](models.json): the same names, versions and deployment type, with a capacity of their own, `agentCapacity` (the Investigator's model has 50 thousand tokens a minute here, the Skeptic's 20): an agent that calls tools reads everything said so far again at every step, so one run uses many times the tokens that the gateway's detective does, and the first real runs showed a model with 20 thousand tokens a minute saying "not now" (HTTP 429) in the middle of a run. The client waits and asks again, and a run that is slow ends its tool calls at 70% of its time, but the capacity is what keeps a run from being slow. The agents use the models directly, not through the gateway. That is a temporary exception to [rule 15 (c)](../AGENTS.md): the gateway's API Management instance is on the Developer tier, and the API Management connection that Foundry documents for agents needs Standard v2 or Premium and is in preview.
- **A guardrail**, `meternaut-agents`, based on `Microsoft.DefaultV2`, in the mode Blocking, with the Prompt Shields for user prompt attacks and indirect attacks. The model deployments use it, and the agents inherit it from them.
- **A connection of the project to the Application Insights component `appi-meternaut`** for the agents' traces. It uses the project's managed identity, with *Monitoring Metrics Publisher* on the component. The component takes telemetry only with Microsoft Entra ID, and no key exists anywhere.
- **One role for the cases app**: *Azure AI User* (named *Foundry User* since the rename of the Foundry roles; the id is the same) for the cases app's own system-assigned identity (until 2026-11-06 for the user-assigned `id-meternaut-cases`), on the project and nowhere else. Its data actions let the app create agents and run them in the project, and nothing else here.

**Why a new resource.** The model account `aif-meternaut-<digest>` was made with `allowProjectManagement` false, and Microsoft Learn says that this setting cannot be changed after the account exists (Create a project for Microsoft Foundry). So that account can never hold a project or an agent. It stays as it is and keeps serving the gateway.

**The one hand step: one more role in the condition.** The condition of the deploy identity's *Role Based Access Control Administrator* assignment lists the roles that it may give to a service principal ([above](#added-on-2026-11-04-for-the-usage-recording)). The template gives the cases app *Azure AI User*, which is not in the list, so the action would be refused. *Monitoring Metrics Publisher*, the other role that the template gives, is in the list already. A person who may assign roles in the project's group adds the one id, with their own sign-in, on the owner's written word, and reports it at once.

The condition is changed **in place, with one write**: `az role assignment update` takes the assignment as JSON, changes its condition, and the assignment keeps its id. There is no moment in which the deploy identity has no assignment, so nothing has to be restored when the write fails. The commands read first (there must be exactly one assignment, and its condition must have the shape that the templates write), change nothing but the list of ids, show what changes, and ask before they write. They test the exit code of the update: when it fails, nothing else happens and the assignment is unchanged. After a good update they read the assignment back and fail unless there is exactly one, with the same id, whose two lists of role ids both hold the old ids and the Foundry User role. Nothing is written until the person types `yes`; any other answer is a dry run that changes nothing. They run in PowerShell 7 and in Windows PowerShell 5.1. Paste them as one block, or save them as a `.ps1` file, so that an error stops the rest. They use `$devSub`, `$hubGroup` and `$principal` of the commands at the top of this page:

```powershell
function az { $PSNativeCommandArgumentPassing = 'Legacy'; & 'C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe' -IBm azure.cli @args }
$scope = "/subscriptions/$devSub/resourceGroups/$hubGroup"
$foundryUser = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
$read = "az role assignment list --subscription $devSub --assignee-object-id $principal --scope $scope --role 'Role Based Access Control Administrator' --output json"
function Get-Assignments { param($Query) az role assignment list --subscription $devSub --assignee-object-id $principal --scope $scope --role 'Role Based Access Control Administrator' --query $Query --output json }
# 1. Read the assignment (there must be exactly one) and the role ids that its condition lists (the list for a write and the list for a delete must be the same)
$count = Get-Assignments 'length(@)'
if ($LASTEXITCODE -ne 0) { throw "The assignments could not be read (exit code $LASTEXITCODE). Nothing was changed. Read them: $read" }
if ("$count".Trim() -ne '1') { throw "The deploy identity must have exactly one Role Based Access Control Administrator assignment on the project group, and the list says '$count'. Nothing was changed. Read them: $read" }
$text = Get-Assignments '[0]'
if ($LASTEXITCODE -ne 0) { throw "The assignment could not be read (exit code $LASTEXITCODE). Nothing was changed. Read it: $read" }
$old = $text | ConvertFrom-Json
$lists = @([regex]::Matches($old.condition, 'GuidEquals\s*\{([^}]*)\}') | ForEach-Object { ($_.Groups[1].Value -split ',\s*' | Sort-Object) -join ',' })
if ($lists.Count -ne 2 -or ($lists | Select-Object -Unique).Count -ne 1) { throw 'The condition is not the one that the templates expect (two lists of the same role ids). Stop and read it.' }
$current = $lists[0] -split ','
if ($current -contains $foundryUser) { throw 'The condition lists the Foundry User role already: nothing to do.' }
# 2. Add the one id, and change nothing else of the condition
$roles = (@($current) + $foundryUser) -join ', '
$condition = "((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$roles} AND @Request[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'})) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$roles} AND @Resource[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'}))"
$shape = { param($c) $c -replace 'GuidEquals\s*\{[^}]*\}', 'GuidEquals {ids}' -replace '\s+', ' ' }
if ((& $shape $old.condition) -ne (& $shape $condition)) { throw 'The condition differs from the templates in more than the role ids. Stop and read it.' }
# 3. Show the difference, then change the condition in place: one write, and the assignment keeps its id
Write-Host "Role ids now:        $($current -join ', ')"
Write-Host "Role ids afterwards: $roles"
Write-Host "Added:               $foundryUser (Azure AI User, named Foundry User since the rename)"
if ((Read-Host 'Change the condition as shown? Type yes') -ne 'yes') { throw 'Stopped. Nothing was changed.' }
$old.condition = $condition
$json = $old | ConvertTo-Json -Depth 20 -Compress
# The JSON is an argument of the CLI: every quote of it is doubled, which reaches the CLI unchanged in Windows PowerShell 5.1 and in PowerShell 7 (the Legacy setting in az makes 7.3 and later pass it the same way)
az role assignment update --subscription $devSub --role-assignment ($json -replace '"', '""') --output none
if ($LASTEXITCODE -ne 0) { throw "The update failed (exit code $LASTEXITCODE). It is one write and nothing else was done, so the assignment is unchanged. Read it: $read" }
# 4. Read it back: exactly one assignment, the same one, and both lists hold the old role ids and the Foundry User role
$count = Get-Assignments 'length(@)'
if ($LASTEXITCODE -ne 0) { throw "Read back: the assignments could not be read (exit code $LASTEXITCODE). The update was made; read them: $read" }
if ("$count".Trim() -ne '1') { throw "Read back: the list says '$count' assignments, not one. The update was made; read them: $read" }
$text = Get-Assignments '[0]'
if ($LASTEXITCODE -ne 0) { throw "Read back: the assignment could not be read (exit code $LASTEXITCODE). The update was made; read it: $read" }
$new = $text | ConvertFrom-Json
$after = @([regex]::Matches($new.condition, 'GuidEquals\s*\{([^}]*)\}') | ForEach-Object { ($_.Groups[1].Value -split ',\s*' | Sort-Object) -join ',' })
$meant = ($roles -split ',\s*' | Sort-Object) -join ','
if ($new.id -ne $old.id -or $after.Count -ne 2 -or $after[0] -ne $meant -or $after[1] -ne $meant) { throw "Read back: the assignment is not as meant (the same id, and both lists of role ids hold the old ids and $foundryUser). Its lists are: $($after -join ' | '). Read it: $read" }
Write-Host "Read back: one assignment, with the same id, and both lists hold the old role ids and $foundryUser (Foundry User)."
```

**The order.** (1) The hand step above. (2) The action `what-if` (it now shows the Foundry resource too, once the usage recording has made the Application Insights component), and then the action `foundry`. (3) The action `cases`: it passes the project's address to the app only when the project is in Azure, so the app's settings `FOUNDRY_PROJECT_ENDPOINT` and `INVESTIGATE` (on when there is an address, off otherwise) change at that run and not before. On an estate where `cases` has never run, the order is `recording`, `contract`, `cases`, then the hand step, `foundry` and `cases` again: the role goes to the cases app's own system-assigned identity, which the first run of `cases` makes with the app, and `foundry` refuses to run without it.

**What the action checks, and what it needs.** Before it deploys, `foundry` requires the Application Insights component of the usage recording and the cases app with its own system-assigned identity (the workflow reads the object id from the app), and that its parameter file carries that identity's object id: no role is ever given to a placeholder. After the deploy it waits up to 40 minutes for the landing zone's policy to register the private endpoint in the central zone `privatelink.services.ai.azure.com` (the zone of the project address; `privatelink.cognitiveservices.azure.com` and `privatelink.openai.azure.com` are said and not required). If that zone is not registered, the cases app cannot reach the project: the run fails, and the owners of the landing zone are asked for the zone. Nobody creates one. It then reads the resource back from Azure with GET requests only, and fails the run unless public network access is Disabled, local authentication is off, project management is on, the resource and the project have identities, the project reports an endpoint and it is the address that the cases app is given, the private endpoint is approved, every model of `models.json` is deployed as it says with the guardrail (a list is read to its last page), the guardrail blocks the three Prompt Shields (Jailbreak and Indirect Attack on the user input, Indirect Attack on tool results), and the project's connection to Application Insights is made with an identity. No read waits longer than two minutes: an `az` that does not answer fails the run with a message that names the request, and nothing after it is read. A tenant policy with the effect Modify does not refuse a resource: it rewrites it, so the read-back is the check ([rule 19](../AGENTS.md)). The run's summary prints the project address, and says what the resources hold. It prints no key, because none exists.

**Costs.** The Foundry resource and the project cost nothing while no agent runs. The private endpoint costs a few euros a month, like the others. The two deployments of the models bill by token when the agents run, from the same kind of quota as the model account's (`DataZoneStandard`; `agentCapacity` in `models.json` says how many thousand tokens a minute each has, and the quota of a model counts the deployments of both resources together): the two new deployments need that much more quota, which the deploy identity cannot read, so the first run is where a shortage would show. A capacity is a rate limit and not a charge: nothing is paid for it while no agent runs, and what a run costs is what it reads and writes. No new resource provider is needed.

**What a person sees in the Foundry portal.** The traces of the agents are in Application Insights. To read them in the Foundry portal a person needs *Log Analytics Reader* on the component (and *Privileged Monitoring Data Reader* where the tables are protected) with their own account. The template gives no person any role.

## Changed on 2026-11-06: the function apps move to system-assigned identities, step one

The owner prefers system-assigned managed identities. The two function apps, the cases app (`func-meternaut-cases-<digest>`) and the usage app (`func-meternaut-usage-<digest>`), therefore move from the user-assigned identities `id-meternaut-cases` and `id-meternaut-usage` to an identity of their own each. One user-assigned identity stays: `id-meternaut-console-auth`, which the console's sign-in presents to Microsoft Entra in place of a client secret. Microsoft documents that secretless sign-in of an App Service app only with a user-assigned identity ([Configure Microsoft Entra authentication](https://learn.microsoft.com/azure/app-service/configure-authentication-provider-aad#use-a-managed-identity-instead-of-a-secret)). It holds no role, and that does not change.

An app that loses an identity before the new one has its rights stops working, so the move takes two steps. This section is step one, which is additive. Step two is a separate change: it moves the settings to the new identities and takes the old ones off the apps, and it is made only after the steps below are done and read back. The old identities themselves are removed later, by a person, and not by the workflow: `tools/access-requirements.py retire` finds the grants of an identity by its object id, so it has to run while the identity still exists, and the workflow's identity cannot see the grants outside the project's group that `retire` removes. The order is written down with step two.

**What step one changes.** The actions `recording` and `cases` do it with the deployment identity's existing rights, so nothing new is needed in Azure:

- Each function app gets a system-assigned identity next to its user-assigned ones.
- The cases app's system-assigned identity gets every role that `id-meternaut-cases` holds inside the project's resource group: *Azure Event Hubs Data Receiver* on the control hub, *Storage Blob Data Owner* on the three containers that the Functions hosts of the account share, *Storage Queue Data Contributor* and *Storage Table Data Contributor* on the storage account, and *Monitoring Metrics Publisher* on Application Insights. The usage app's gets what `id-meternaut-usage` holds: *Azure Event Hubs Data Receiver* on the three hubs, *Storage Blob Data Owner*, *Storage Queue Data Contributor* and *Storage Table Data Contributor* on the account, *Monitoring Metrics Publisher*, and the data role *Data Contributor* of the Cosmos DB account. They are the same roles on the same resources, so the condition of the deployment identity's role-assignment right ([above](#added-on-2026-11-04-for-the-usage-recording)) needs no change.
- The action `foundry` gives the cases app's system-assigned identity *Foundry User* on the project as well, once the app has one. The workflow reads its object id from the app (an app that has none yet is "none yet", and no role is given), so the order is `cases`, then `foundry`.
- No setting changes. Both apps keep running on their user-assigned identities: their settings, the deployment storage of the usage app and the console's sign-in are as they were. The summaries of `recording` and `cases` print the object id of each system-assigned identity, and the templates return it (`usageSystemPrincipalId`, `casesSystemPrincipalId`).

A role assignment of a system-assigned identity is named after the app's resource id, because Bicep needs the name when the deployment starts and the identity's object id does not exist until the app does. An app that is deleted and made again gets a new object id, and its old assignments (they show as "Identity not found") have to be removed before the template makes new ones.

**What a person does between the steps** (the owner's session; each is outside the project's resource group or outside Azure, so the workflow's identity has no right to it and must not get one, [rules 18 and 24](../AGENTS.md)):

1. **The same reads outside the group, for the two system-assigned identities.** For the cases app: *Reader* and *Cost Management Reader* on each subscription that the Watch reads, and the custom role *Meternaut gateway key reader* on the one subscription of the gateway's access product (R1 to R3). For the usage app: *Monitoring Reader* on the gateway's Application Insights and the custom role *Meternaut usage reader* on the central workspace (R4 and R5). [`tools/access-requirements.py`](../tools/access-requirements.py) reads each app from the project's group (`--cases-site` and `--usage-site` name them), takes its system-assigned identity, and checks and grants every line for it, next to the user-assigned identity while the app still runs as one. `check` reads what is there, `grant` is a dry run that prints the exact commands, and `grant --apply` makes them with that person's own sign-in:

   ```powershell
   python tools/access-requirements.py check --project-subscription $devSub --project-group $hubGroup --cases-site $casesApp --usage-site $usageApp --gateway $gateway --gateway-insights $insights
   python tools/access-requirements.py grant --project-subscription $devSub --project-group $hubGroup --cases-site $casesApp --usage-site $usageApp --gateway $gateway --gateway-insights $insights
   python tools/access-requirements.py grant --project-subscription $devSub --project-group $hubGroup --cases-site $casesApp --usage-site $usageApp --gateway $gateway --gateway-insights $insights --apply
   ```

   `$casesApp` and `$usageApp` are the names of the two apps in the project's group (`func-meternaut-cases-<digest>` and `func-meternaut-usage-<digest>`), `$gateway` and `$insights` the resource ids of the API Management instance and of its Application Insights component. `--estate` (once for each subscription or management group that the Watch reads; the project's subscription when it is left out), `--workspace`, `--product-subscription` and `--only` are as they were. An app that has no system-assigned identity yet is reported as "cannot yet": run `cases` or `recording` first.
2. **The right to send letters, for the cases app's system-assigned identity.** [`tools/exchange-setup.py`](../tools/exchange-setup.py) makes the role *Application Mail.Send* for it, limited to the one shared mailbox, and proves that it may not send as another mailbox ([step 3 of the console and approval loop section](#added-on-2026-11-05-for-the-console-and-the-approval-loop)). It needs two ids of the identity's service principal. The object id (`--identity-principal-id`) is `identity.principalId` of the app: the summary of the action `cases` prints it, and `az rest --method get --url "https://management.azure.com<resource id of the app>?api-version=2024-04-01" --query identity.principalId --output tsv` reads it. The application (client) id (`--identity-client-id`) is not on the app, and the deployment identity may not read the directory, so the owner's session reads it from Microsoft Entra: `az ad sp show --id <object id> --query appId --output tsv`.

   ```powershell
   python tools/exchange-setup.py check --tenant-id $tenant --domain <default domain> --identity-client-id <appId of the cases app's service principal> --identity-principal-id <identity.principalId of the cases app> --other-mailbox <an existing other mailbox>
   python tools/exchange-setup.py apply --tenant-id $tenant --domain <default domain> --identity-client-id <appId of the cases app's service principal> --identity-principal-id <identity.principalId of the cases app> --other-mailbox <an existing other mailbox> --apply
   ```
3. **Wait, then read back.** An Azure role assignment applies within about ten minutes, and Exchange applies a new assignment to live sends after 30 minutes to two hours. `access-requirements.py check` has to show all five requirements for the system-assigned identities and `exchange-setup.py check` the mailbox right before step two is made.

Step one cannot show that the system-assigned identities work, because the apps do not use them yet. The first runs after step two do (`cases-run` and `recording-check`).

## Changed on 2026-11-06: the function apps move to system-assigned identities, step two

Step one ([above](#changed-on-2026-11-06-the-function-apps-move-to-system-assigned-identities-step-one)) gave each function app a system-assigned identity next to its user-assigned ones, with every role that the old identity holds inside the project's resource group. Step two moves the apps to it. It is made only after the hand steps of step one are done and read back: `tools/access-requirements.py check` shows all five requirements (R1 to R5) present for the two system-assigned identities, and `tools/exchange-setup.py check` shows the mailbox right for the cases app's system-assigned identity. Nothing in step two gives the workflow's identity a right.

**What step two changes.** The actions `recording` and `cases` do it with the deployment identity's existing rights:

- Neither app names a client id any more. `AzureWebJobsStorage__clientId`, `EventHubConnection__clientId` and `AZURE_CLIENT_ID` are gone from the settings of both apps, so the host's connections to storage and Event Hubs, and the code's token requests, use the app's system-assigned identity. `APPLICATIONINSIGHTS_AUTHENTICATION_STRING` is `Authorization=AAD`, without a client id. The code of both apps works whether `AZURE_CLIENT_ID` is set or not, so the order in which code and settings reach an app does not matter.
- The usage app has no user-assigned identity any more (`identity.type` is `SystemAssigned`), and the deployment storage of its Flex Consumption plan signs in with `SystemAssignedIdentity`.
- The cases app keeps one user-assigned identity, `id-meternaut-console-auth`, and the setting `OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID` that names it. It holds no role and stays attached to the app.
- The templates no longer make `id-meternaut-cases` and `id-meternaut-usage`, and no longer give them roles. The roles of the system-assigned identities are the ones that step one made, under the same names, so step two makes no new role assignment on an estate where step one has run. On a new estate the app is made first and its roles after it, because the object id of the identity exists only once the app does, and the first start of the app waits for them.
- The template of the Foundry resource gives *Foundry User* on the project to the cases app's system-assigned identity only. Its parameter `casesSystemPrincipalId` is required and `casesPrincipalId` is gone. The action `foundry` reads the object id from the app and refuses to deploy while the app has no such identity.
- **The workflow does not remove the two old identities, and it does not look for them.** A deployment never removes what a template stops making, so `id-meternaut-cases` and `id-meternaut-usage` stay in the resource group, with the roles that they hold, until a person removes them. The order below is the reason: `tools/access-requirements.py retire` finds the grants of an old identity by the identity's object id, so it has to run while the identity exists, and the workflow's identity cannot see the grants outside the project's group, so it cannot know that they are gone.

**What a person does after step two.** It is the owner's session. Each step is outside the workflow's reach, is done on the owner's written word with the person's own sign-in, and is reported at once. The order matters, and no step is made before the one above it has shown its result. The variables are those of step one and of the commands at the top of this page.

1. **Deploy step two.** Run `recording` and `cases`, and then `foundry`, so that its read back shows the Foundry resource as it is. Each run checks its result: the app answers and lists its functions, and the Foundry resource is read back from Azure.
2. **Show that the apps run as their system-assigned identities.** The tools cannot see which identity an app runs as, so a person checks it with the apps' own answers. Run `recording-check` (the copy jobs start once and what they said is read back from the app's telemetry: they read the gateway's Application Insights and the central workspace with R4 and R5), `cases-run` (one Watch through the control hub, which reads the estate with R1 and R2 and the gateway's key with R3) and `loop-check`. An authorization error in the History or in the telemetry means that a grant is missing for the new identity: stop, and give it with `tools/access-requirements.py grant`. Then read what Azure says about the two apps:

   ```powershell
   az rest --method get --url "https://management.azure.com<resource id of the cases app>?api-version=2024-04-01" --query identity
   az rest --method get --url "https://management.azure.com<resource id of the usage app>?api-version=2024-04-01" --query identity
   az functionapp config appsettings list --subscription $devSub --resource-group $hubGroup --name <name of each app> --query "[?name=='AZURE_CLIENT_ID' || name=='EventHubConnection__clientId' || name=='AzureWebJobsStorage__clientId'].name"
   az monitor activity-log list --subscription $gw --offset 3h --query "[?contains(operationName.value, 'listSecrets')].{caller: caller, time: eventTimestamp}" --output table
   ```

   The cases app shows `SystemAssigned, UserAssigned` with `id-meternaut-console-auth` as its only user-assigned identity, and the usage app shows `SystemAssigned`. The list of settings is empty for both apps. The Activity Log of the gateway's subscription shows the key read of the Watch (`listSecrets` on the access product's subscription) with the cases app's system-assigned identity as the caller, which is its object id or its application id (`az ad sp show --id <object id> --query appId --output tsv`), and not `id-meternaut-cases`.
3. **Read the grants of the system-assigned identities again.** `check` must show all five requirements present for them, and the Exchange tool the mailbox right ([step one](#changed-on-2026-11-06-the-function-apps-move-to-system-assigned-identities-step-one) has the options):

   ```powershell
   python tools/access-requirements.py check --project-subscription $devSub --project-group $hubGroup --cases-site $casesApp --usage-site $usageApp --gateway $gateway --gateway-insights $insights
   python tools/exchange-setup.py check --tenant-id $tenant --domain <default domain> --identity-client-id <appId of the cases app's service principal> --identity-principal-id <identity.principalId of the cases app> --other-mailbox <an existing other mailbox>
   ```
4. **Retire the grants of the old identities that are outside the project's group.** `retire` removes the grants that the file lists as retired: for the two old identities, *Reader* and *Cost Management Reader* on each subscription that the Watch reads, the custom role *Meternaut gateway key reader* on the access product's subscription, *Monitoring Reader* on the gateway's Application Insights, and the custom role *Meternaut usage reader* on the central workspace (W2 to W6). It removes an old identity's assignment only while the grant that replaces it is present for the app's system-assigned identity, which is why it needs the names of the apps, and it never removes a role that the system-assigned identity needs. The first command is a dry run that prints what it would do. The second runs it. Neither deletes an identity:

   ```powershell
   python tools/access-requirements.py retire --project-subscription $devSub --project-group $hubGroup --cases-site $casesApp --usage-site $usageApp --gateway $gateway --gateway-insights $insights
   python tools/access-requirements.py retire --project-subscription $devSub --project-group $hubGroup --cases-site $casesApp --usage-site $usageApp --gateway $gateway --gateway-insights $insights --apply
   ```
5. **Only then remove the two old identities.** Read first what each still holds, and write down its object id: step 6 needs it, and it cannot be read after the identity is gone. What is left after step 4 should be only what the earlier templates made inside the project's group (on the storage account and its three containers, the control hub, Application Insights, the Event Hubs namespace and, for the cases identity, the Foundry project) and, for the usage identity, its data role in the Cosmos DB account. Remove each, so that nothing is left behind as "Identity not found" (the way to remove them is the one of step 4 of [the usage recording section](#added-on-2026-11-04-for-the-usage-recording)). Then delete the identity:

   ```powershell
   $old = az identity show --subscription $devSub --resource-group $hubGroup --name id-meternaut-cases --query principalId --output tsv
   az role assignment list --subscription $devSub --all --assignee $old --query "[].{role: roleDefinitionName, scope: scope, id: id}" --output table
   az role assignment delete --ids <the id of each row>
   az identity delete --subscription $devSub --resource-group $hubGroup --name id-meternaut-cases

   $old = az identity show --subscription $devSub --resource-group $hubGroup --name id-meternaut-usage --query principalId --output tsv
   az role assignment list --subscription $devSub --all --assignee $old --query "[].{role: roleDefinitionName, scope: scope, id: id}" --output table
   az cosmosdb sql role assignment list --subscription $devSub --resource-group $hubGroup --account-name <the Cosmos DB account> --query "[?principalId=='$old'].id" --output tsv
   az role assignment delete --ids <the id of each row>
   az cosmosdb sql role assignment delete --subscription $devSub --resource-group $hubGroup --account-name <the Cosmos DB account> --role-assignment-id <the last part of each id that is listed> --yes
   az identity delete --subscription $devSub --resource-group $hubGroup --name id-meternaut-usage
   ```

   Each `az identity show` fails when the identity is not there: then it was removed already, and there is nothing to do for it.
6. **Remove what the old cases identity held in Exchange.** Exchange keeps the assignment of the role *Application Mail.Send* for `id-meternaut-cases`, with its management scope, and the identity's service principal pointer. [`tools/exchange-setup.py`](../tools/exchange-setup.py) removes nothing, so a person removes both by hand, with their own sign-in as an Exchange administrator, the assignment first, using the object id from step 5:

   ```powershell
   Connect-ExchangeOnline
   Get-ManagementRoleAssignment -RoleAssignee <object id of id-meternaut-cases> | Format-Table Name, Role, CustomResourceScope
   Remove-ManagementRoleAssignment -Identity '<the name of that assignment>'
   Get-ServicePrincipal -Identity <object id of id-meternaut-cases>
   Remove-ServicePrincipal -Identity <object id of id-meternaut-cases>
   ```

   The system-assigned identity's own assignment stays. A read back shows that the old one is gone: `Get-ManagementRoleAssignment -RoleAssignee <object id of id-meternaut-cases>` returns nothing, and `Get-ServicePrincipal -Identity <object id of id-meternaut-cases>` says that there is no such service principal.

**Going back.** Until step 4 has run, the old identities still hold every grant, so going back is reverting this change and running `recording` and `cases` again: the templates of step one put the old identities back on the apps, with their settings. After step 4 their grants outside the group are gone, and going back also means granting those again, with the file as it was before step 4. After step 5 an old identity is made again with a new object id, so every grant of it is made again too.

## Changed on 2026-11-06: the Operator

Once the services of the project are private, the workflow can no longer publish code, start a run, read the telemetry or knock at the console from outside the network ([the decision record](../docs/proposals/07-private-by-default.md)). The Operator does those things from inside: a container group of Azure Container Instances that the workflow makes in a subnet of the project's network, with an identity of its own, lets run one script, reads the log of and deletes. Two new actions: `operator` deploys [`environment/operator/main.bicep`](operator/main.bicep) into the project's resource group, and `operator-probe` runs [`operator/probe.sh`](../operator/probe.sh) once in the Operator and prints what it finds. Two existing actions now use it: `recording-check` and `cases-run` run their check tool ([`tools/recording-check.py`](../tools/recording-check.py), [`tools/cases-check.py`](../tools/cases-check.py)) in the Operator with the generic script [`operator/run-tool.sh`](../operator/run-tool.sh), so that the control event is sent, and the telemetry is read, from inside the network. What `operator` makes, and nothing else:

- **The identity** `id-meternaut-operator`, user-assigned, attached to no app.
- **The subnet** `snet-ops`, delegated to `Microsoft.ContainerInstance/containerGroups`, with the network security group `nsg-meternaut-ops`. It is made once and then left alone ([rule 27](../AGENTS.md)): the landing zone's network manager puts a route table on it some minutes after, a container group gets its way out through that table, and the action waits for it (20 minutes at most; it waits for nothing when the endpoint subnet has no table either).
- **Three roles**, all for that identity. *Reader* on the project's resource group: the probe uses it to read the group, and the check tools use it for their query of the telemetry through Azure Resource Manager (a query of an Application Insights component is `Microsoft.Insights/Components/Query/Read`, and *Reader* includes `*/read`: [Azure permissions for Monitor](https://learn.microsoft.com/azure/role-based-access-control/permissions/monitor#microsoftinsights) and [the built-in roles](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/general#reader), read on 2026-11-06; that this endpoint is authorised by that operation was inferred, and the first `recording-check` showed it on 2026-11-06). *Azure Event Hubs Data Sender* on the control hub `usage-control` (made by the action `recording`) and on `cases-control` (made by the action `cases`), one role on each hub and none on the namespace: the check tools send the one event that starts a copy job or a Watch with it. The roles of the later steps (*Website Contributor* on the two apps, and a role for the data-plane query of the telemetry) come with the step that uses each of them. *Azure Event Hubs Data Sender* is in the condition of the deploy identity's role-assignment right already (the usage recording gives it to the gateway's identity, and gave it to the workflow's identity until the namespace was made private), so the two new roles need no hand step; the roles of the later steps may.

**What the deploy identity's rights already cover.** *Contributor* on the project's group is `*` less a short list of `Microsoft.Authorization` writes and a few other actions ([Learn](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/privileged#contributor), read on 2026-11-06), so it covers `Microsoft.ContainerInstance/containerGroups/*`, the right to join a subnet (`Microsoft.Network/virtualNetworks/subnets/join/action` on `snet-ops`) and the right to assign the identity to a group (`Microsoft.ManagedIdentity/userAssignedIdentities/assign/action` on `id-meternaut-operator`): the network and the identity are both in the project's group. That was read from the role's definition and then shown by a run: the first `operator-probe` is the test, and it passed on 2026-11-06, twice ([the record](../docs/proposals/07-private-by-default.md#what-the-probe-proved-on-2026-11-06)). It does not cover the role assignment of *Reader*, because the condition of its role-assignment right lists eight roles and Reader is not one of them, and it does not cover registering a resource provider. So there are two hand steps, each with a person's own sign-in, on the owner's written word, reported at once. Both were in place when the probe ran on 2026-11-06.

**Hand step 1: a resource provider.** `Microsoft.ContainerInstance` is not in the list of registered providers above, and the identity cannot register one. Read the state first, and register it only when it is not registered:

`az provider show --namespace Microsoft.ContainerInstance --query registrationState --output tsv`, and then `az provider register --namespace Microsoft.ContainerInstance`.

The action `operator-probe` reads the state before it makes anything and stops with the reason when the provider is `NotRegistered` or `Unregistered`.

**Hand step 2: one more role in the condition, *Reader*.** *Reader* (`acdd72a7-3385-48ef-bd42-f606fba81ae7`) is added to the list of the deploy identity's role-assignment right in the same way as the Foundry User role was ([above](#changed-on-2026-11-06-the-foundry-resource-of-the-agents)): one update in place, so that the identity has no moment without its assignment, with the same checks before and after. Nothing is written until the person types `yes`. The action `operator` fails at the role assignment, and changes nothing else, until this is done. The commands use `$devSub`, `$hubGroup` and `$principal` of the commands at the top of this page:

```powershell
function az { $PSNativeCommandArgumentPassing = 'Legacy'; & 'C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe' -IBm azure.cli @args }
$scope = "/subscriptions/$devSub/resourceGroups/$hubGroup"
$reader = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'
$read = "az role assignment list --subscription $devSub --assignee-object-id $principal --scope $scope --role 'Role Based Access Control Administrator' --output json"
function Get-Assignments { param($Query) az role assignment list --subscription $devSub --assignee-object-id $principal --scope $scope --role 'Role Based Access Control Administrator' --query $Query --output json }
# 1. Read the assignment (there must be exactly one) and the role ids that its condition lists (the list for a write and the list for a delete must be the same)
$count = Get-Assignments 'length(@)'
if ($LASTEXITCODE -ne 0) { throw "The assignments could not be read (exit code $LASTEXITCODE). Nothing was changed. Read them: $read" }
if ("$count".Trim() -ne '1') { throw "The deploy identity must have exactly one Role Based Access Control Administrator assignment on the project group, and the list says '$count'. Nothing was changed. Read them: $read" }
$text = Get-Assignments '[0]'
if ($LASTEXITCODE -ne 0) { throw "The assignment could not be read (exit code $LASTEXITCODE). Nothing was changed. Read it: $read" }
$old = $text | ConvertFrom-Json
$lists = @([regex]::Matches($old.condition, 'GuidEquals\s*\{([^}]*)\}') | ForEach-Object { ($_.Groups[1].Value -split ',\s*' | Sort-Object) -join ',' })
if ($lists.Count -ne 2 -or ($lists | Select-Object -Unique).Count -ne 1) { throw 'The condition is not the one that the templates expect (two lists of the same role ids). Stop and read it.' }
$current = $lists[0] -split ','
if ($current -contains $reader) { throw 'The condition lists the Reader role already: nothing to do.' }
# 2. Add the one id, and change nothing else of the condition
$roles = (@($current) + $reader) -join ', '
$condition = "((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$roles} AND @Request[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'})) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$roles} AND @Resource[Microsoft.Authorization/roleAssignments:PrincipalType] ForAnyOfAnyValues:StringEqualsIgnoreCase {'ServicePrincipal'}))"
$shape = { param($c) $c -replace 'GuidEquals\s*\{[^}]*\}', 'GuidEquals {ids}' -replace '\s+', ' ' }
if ((& $shape $old.condition) -ne (& $shape $condition)) { throw 'The condition differs from the templates in more than the role ids. Stop and read it.' }
# 3. Show the difference, then change the condition in place: one write, and the assignment keeps its id
Write-Host "Role ids now:        $($current -join ', ')"
Write-Host "Role ids afterwards: $roles"
Write-Host "Added:               $reader (Reader)"
if ((Read-Host 'Change the condition as shown? Type yes') -ne 'yes') { throw 'Stopped. Nothing was changed.' }
$old.condition = $condition
$json = $old | ConvertTo-Json -Depth 20 -Compress
# The JSON is an argument of the CLI: every quote of it is doubled, which reaches the CLI unchanged in Windows PowerShell 5.1 and in PowerShell 7 (the Legacy setting in az makes 7.3 and later pass it the same way)
az role assignment update --subscription $devSub --role-assignment ($json -replace '"', '""') --output none
if ($LASTEXITCODE -ne 0) { throw "The update failed (exit code $LASTEXITCODE). It is one write and nothing else was done, so the assignment is unchanged. Read it: $read" }
# 4. Read it back: exactly one assignment, the same one, and both lists hold the old role ids and the Reader role
$count = Get-Assignments 'length(@)'
if ($LASTEXITCODE -ne 0) { throw "Read back: the assignments could not be read (exit code $LASTEXITCODE). The update was made; read them: $read" }
if ("$count".Trim() -ne '1') { throw "Read back: the list says '$count' assignments, not one. The update was made; read them: $read" }
$text = Get-Assignments '[0]'
if ($LASTEXITCODE -ne 0) { throw "Read back: the assignment could not be read (exit code $LASTEXITCODE). The update was made; read it: $read" }
$new = $text | ConvertFrom-Json
$after = @([regex]::Matches($new.condition, 'GuidEquals\s*\{([^}]*)\}') | ForEach-Object { ($_.Groups[1].Value -split ',\s*' | Sort-Object) -join ',' })
$meant = ($roles -split ',\s*' | Sort-Object) -join ','
if ($new.id -ne $old.id -or $after.Count -ne 2 -or $after[0] -ne $meant -or $after[1] -ne $meant) { throw "Read back: the assignment is not as meant (the same id, and both lists of role ids hold the old ids and $reader). Its lists are: $($after -join ' | '). Read it: $read" }
Write-Host "Read back: one assignment, with the same id, and both lists hold the old role ids and $reader (Reader)."
```

**The order.** (1) Hand steps 1 and 2. (2) The action `what-if`, which now shows the Operator too once the network and the two control hubs exist, and then `operator`. (3) The action `operator-probe`, which makes a container group, prints what the probe finds into the run's summary, and deletes the group at the end whatever happens. The probe is meant to be run more than once: the subnet is a /27, and a run after a run shows whether the addresses of deleted groups come back in time. (4) The order of the actions on an estate is `recording`, `cases`, `operator`: the template of the Operator only reads the two control hubs, which those two actions make, and the action `operator` stops before it changes anything when a hub is not there.

**What changes for `recording-check` and `cases-run`, and what a person does.** The two actions used to send the control event and read the telemetry from the GitHub-hosted runner with the workflow's own token. They now do both from the Operator, so that the Event Hubs namespace can have public network access switched off (that switch is not changed by this step). It was the next step, and it is done: [the namespace was made private](#changed-on-2026-11-06-the-event-hubs-namespace-is-private) on 2026-11-06. Each action finds the Operator (it stops with the reason, and says to run `operator` first, when the identity or the subnet is missing), lists the app's functions from the runner as before (a read through Azure Resource Manager), makes one container group that runs the check tool with the arguments that the runner used, prints the tool's lines into the run's summary, and deletes the group (a last step deletes any group that a cancelled run left). The tool signs in as the Operator's identity, which holds *Azure Event Hubs Data Sender* on the control hub and *Reader* on the project's group. On an estate where the Operator exists already, as on the real one:

1. Run `operator` again. The template is the same except for the two roles, so the identity, the subnet and the *Reader* role are left as they are, and the two *Azure Event Hubs Data Sender* roles are made. The action stops first, changing nothing, if `usage-control` or `cases-control` is not there (run `recording` and `cases` first).
2. Wait about ten minutes: a new role takes up to that long to apply, and a send before that is answered with 401 or 403 (the log of the run says so, and the summary says what to do).
3. Run `recording-check` and `cases-run`. The telemetry is still read through Azure Resource Manager, with *Reader*, and that stops working when Application Insights gets private-only query access (the record has the next step).

**Done on the real estate on 2026-11-06.** `operator` made both *Azure Event Hubs Data Sender* assignments with no hand step, and `recording-check` and `cases-run` passed through the Operator while the namespace was still public ([what the runs showed](../docs/proposals/07-private-by-default.md#what-the-runs-showed-on-2026-11-06)).

**Costs.** The identity, the subnet and the network security group cost nothing, and neither do the role assignments. A container group costs for the seconds it exists: about 0.9 US cents for a probe of ten minutes at 1 vCPU and 1.5 GB (the price of 2026-11-06 in Sweden Central; [the decision record](../docs/proposals/07-private-by-default.md) has the figures and the two fallbacks that have a standing price, a NAT gateway and a private container registry, which are the owner's to decide if the probe shows that they are needed; it did not). A check lasts as long as the tool waits for the telemetry plus about two minutes to start the group and 20 seconds at the end: at most 25 minutes for `recording-check` (about 2.3 US cents) and 40 for `cases-run` (about 3.6), and usually far less. No new right is given to the deploy identity.

## Changed on 2026-11-06: the Event Hubs namespace is private

The Event Hubs namespace of the usage recording had public network access Enabled, because the gateway sent to it and the deployment workflow sent the control event of the two checks to it from the GitHub-hosted runner. The owner's rule is that no resource of the project has a public endpoint ([the decision record](../docs/proposals/07-private-by-default.md#event-hubs-private-only-deployed-and-proven-on-2026-11-06)), and the Operator sends the control events from inside the network now, so this change made the namespace private-only and took away the right that only made sense while the runner sent to it. **No hand step was needed.** It was deployed through the Hub on 2026-11-06 and every run passed ([what the runs showed](../docs/proposals/07-private-by-default.md#what-the-runs-showed-on-2026-11-06)).

**What changed**, in the templates and the Hub workflow, and nothing by hand:

- [`environment/recording/main.bicep`](recording/main.bicep) sets `publicNetworkAccess: 'Disabled'` on the namespace (local authentication stays off and TLS 1.2 stays). It adds no network rule set and no trusted-service exception: the two function apps and the Operator use the namespace's private endpoint, and nothing else needs a way in.
- The templates of [`recording`](recording/main.bicep) and [`cases`](cases/main.bicep) no longer give the deploy identity *Azure Event Hubs Data Sender* on the control hub (`workflowSendsControl`), and the parameter `workflowPrincipalId` that fed it is gone from both templates and from the parameter builder. The Operator, the gateway and the function apps keep their roles on the hubs.
- A template never deletes an assignment that it no longer declares, so one step in each of the two actions retires the assignment that exists. After its deploy, the action `recording` retires the deploy identity's assignment on the control hub `usage-control`, and the action `cases` the one on `cases-control`. The step reads the deploy identity's assignments at the scope of that hub (`az role assignment list` for that identity), deletes only the one that is *Azure Event Hubs Data Sender*, by its id, reads back that it is gone, and prints what it did. It does nothing when the hub or the assignment is not there (a new estate has neither), and it never touches another assignment: the gateway's, the function apps' and the Operator's roles on the hubs stay.
- The action `recording` also reads the namespace back from Azure after the deploy and fails unless public network access is Disabled, local authentication is off and the private endpoint connection is Approved ([rule 19](../AGENTS.md): a deployment that says Succeeded does not say that the tenant's policies left the resource as the template wrote it).

**Why no hand step.** The condition of the deploy identity's role-assignment right lists *Azure Event Hubs Data Sender* for a write and for a delete of an assignment to a service principal ([the first section of this page](#what-the-owner-approves) and [the usage recording's](#added-on-2026-11-04-for-the-usage-recording): the same condition let the templates give the role), so the identity may delete its own old assignment, which the template made for a service principal. That was read from the condition and the template, and then shown by the runs of 2026-11-06: `recording` and `cases` each deleted the one assignment by its id and read back that it was gone, and Azure refused neither. On another estate, or after a change of the condition: if Azure refuses the delete, the step stops with Azure's message and says what to do, and nothing else has changed. A person then deletes that one assignment with their own sign-in, on the owner's written word ([rule 18](../AGENTS.md)), and runs the action again. Read it first, and delete it by its id and never by a filter (a delete with `--scope` or `--assignee` deletes every assignment that matches). `$devSub` and `$principal` are the ones of the commands at the top of this page, `$principal` being the deploy identity's object id:

```powershell
# 1. Read what the deploy identity holds on the control hub (use the hub that the run named: usage-control or cases-control)
az role assignment list --subscription $devSub --assignee-object-id $principal --scope "<resource id of the control hub>" --fill-principal-name false --query "[].{id:id, role:roleDefinitionId}" --output table
# 2. Only the assignment whose role ends in the id of Azure Event Hubs Data Sender (2b629674-e913-4c01-ae53-ef4638d8f975), by its id
az role assignment delete --ids <id of the assignment>
```

**The order**, on an estate where the namespace is still public:

1. `operator`, when the Operator does not hold *Azure Event Hubs Data Sender* on both control hubs yet, and about ten minutes of waiting for the roles to apply ([the Operator's section](#changed-on-2026-11-06-the-operator)).
2. `recording-check` and `cases-run`, **while the namespace is still public**. They send the control event from the Operator and read the telemetry. Both have to pass first, so that a later failure has one cause.
3. `recording`: it deploys the template that makes the namespace private, reads the namespace back, and retires the deploy identity's right on `usage-control`. Then `cases`: it deploys its template and retires the right on `cases-control`.
4. `recording-check` and `cases-run` again, as the proof. The usage app has been idle, so the control event has to wake it through the private endpoint; on the real estate it did ([the answer](../docs/proposals/07-private-by-default.md#the-usage-app-wakes-from-zero-on-a-private-namespace)).
5. When a policy of the gateway first sends to the two usage hubs, read whether the gateway reaches the namespace ([how](../docs/proposals/07-private-by-default.md#whether-the-gateway-reaches-the-private-namespace)).

**Done on the real estate on 2026-11-06:** steps 1 to 4, and every run passed. Step 5 is still open, because no gateway policy includes the `ai-usage` fragment yet, so nothing sends to the usage hubs.

**Going back.** Revert this change and run `recording` and `cases`: the earlier templates make public access Enabled again and give the deploy identity its role on both control hubs again, and the earlier parameter builder and workflow come back with them. Nothing is restored by hand.

## Changed on 2026-11-06: publishing code from inside the network, phase 1

**No hand step is needed.** [The decision record](../docs/proposals/07-private-by-default.md#publishing-code-to-the-private-apps-phase-1) says why: once the two function apps are private, the workflow can no longer publish their code from the runner, so the Operator will do it, as the deploy identity. This is the first of three phases, and the apps stay public in it. The actions `recording` and `cases` now also make one private endpoint for their function app (about 6.57 euros a month each, the sub-resource `sites`, in `snet-pe`, no DNS zone, link or zone group: the landing zone's policy registers the names) and write `publicNetworkAccess` of the app from a parameter that stays `Enabled`, so the apps stay public. The action `operator-probe` now also asks GitHub for a new OpenID Connect token (audience `api://AzureADTokenExchange`, the one `azure/login` uses; the workflow's `id-token: write` permission is all it needs), gives it to the container as one secure value, signs in there as the deploy identity, builds the usage app's libraries from the lock file, and asks each app's deployment site for the status of a `GET`. Nothing is added to the deploy identity and no credential changes: the first step of the same job, `azure/login`, signs in with a token of the same audience and subject, so the federated credential `github-main` ([above](#the-commands)) accepts it, and the probe of 2026-11-06 showed that it does. If the probe's sign-in line says that it failed, its few words say why (Microsoft Entra's error code is in them), and a person decides, on the owner's word, whether the credential or the workflow changes: nothing is guessed here. The actions `recording` and `cases` also wait, after their deploy and before they publish, until the landing zone's policy has registered each app's endpoint in the central zone (about ten minutes, at most 40 checks a minute apart; `cases` has a step of its own, `recording` waits for the app's endpoint with the five of the services): the first `recording` without that wait failed at the publish, because the app's own name did not resolve yet (the record of the decision says what happened). The order is `recording`, `cases`, and then `operator-probe`.

## After it

The branch that holds this page is merged to `main` (the workflow runs only there, and the credential exists only for `main`; this was done on 2026-11-03, see the changelog), and the workflow is started with the action `what-if`, from the Actions tab (*Hub*, *Run workflow*) or with `gh workflow run deploy-hub.yml --ref main -f action=what-if`. It shows what the next steps would create, and changes nothing. Then, each on the owner's word: `model-side` (the gateway's identity, the network, the model account); `gateway-prepare` (the identity attached to the gateway, the Application Insights logger and, when the usage recording's Event Hubs namespace exists, the two Event Hub loggers: the only changes to the instance itself); a second `what-if`, which shows the exact diff of the Citadel module and is read before anything else; and `gateway` (the module's objects, with its two usage-recording fragments only when both Event Hub loggers exist: see the changelog). Last comes `contract` (the first contract: a product that grants the two inference APIs, with its policy and its one subscription; the run reads the subscription's key from the gateway, tests the gateway with it and keeps it nowhere; with the input `check_limits` it also proves the token limit). The usage recording has two actions of its own: `recording` (removes the key-based Logic App version if it is still there; makes the stores, the private endpoints and the function app with its own system-assigned identity; publishes the code) and, once the two roles in the gateway's and the workspace's subscriptions are given (above), `recording-check` (the copy jobs started once through the control hub, and what they said read back from the function app's telemetry, both from inside the network by the Operator, so it comes after `operator`). The Foundry resource of the agents has one action, `foundry` (after the hand step of [its section](#changed-on-2026-11-06-the-foundry-resource-of-the-agents) and before the next `cases`: it makes the resource, its project, the models, the guardrail and the private endpoint, and reads them back from Azure). The first cases have two more: `cases` (after `recording` and `contract`: the second function app with its own system-assigned identity and the identity of the console's sign-in, its control hub, the longer retention of the traces and the History workbook, and the code published) and, once the three roles above are given, `cases-run` (one Watch started through the control hub, and its History read back from the telemetry, both by the Operator, so it comes after `operator` too). The console and the approval loop have two more: `loop-check` (the console's front door, read from outside with no sign-in: nothing but the health answer may be served, the return address of the Azure sign-in included, and a forged sign-in header must not open anything) and `plant` (makes a disk of Meternaut's own, and with the input `plant_public_ip` an address, in the project's group, tagged as planted waste, so that the loop has something real and harmless to find, to propose and, after a person approves, to delete with that person's own rights). The Operator, which does from inside the network what the workflow cannot do from outside it once the services are private, has two more: `operator` (its identity, the subnet of its container groups and three roles, after the two hand steps of [its section](#changed-on-2026-11-06-the-operator), and after `recording` and `cases`, whose control hubs two of the roles are on) and `operator-probe` (one script run once in a short-lived container group, and what it found printed into the run's summary). The order of those four is `recording`, `cases`, `operator`, and then, about ten minutes after `operator` (a new role takes that long to apply), `recording-check` and `cases-run`. Once both checks have passed through the Operator while the namespace is still public, `recording` makes the Event Hubs namespace private (it reads that back from Azure and retires the deploy identity's right to send to `usage-control`), `cases` retires its right on `cases-control`, and `recording-check` and `cases-run` are run once more as the proof ([the section](#changed-on-2026-11-06-the-event-hubs-namespace-is-private)). On the real estate the Event Hubs steps of this list ran on 2026-11-06 and every run of them passed. Since phase 1 of publishing code from inside the network, the actions `recording` and `cases` also make the two apps' private endpoints and wait until the landing zone's policy has registered them; after that, `operator-probe` is run once more and its lines are read ([the section](#changed-on-2026-11-06-publishing-code-from-inside-the-network-phase-1)). On the real estate the endpoints were made and the probe ran on 2026-11-06, and every check of the probe passed. One yes to the whole list lets the agent run them in this order, and stop at the first thing that differs from the list.

## Undoing it

Taking the model side away is meant to be a workflow's job (an action `remove`), and so is taking the module's objects and the contract out of the instance, which needs delete rights that the owner grants for that run only (see above). Neither is built yet: this page said that `remove` would exist before the first `model-side` run, and it did not, so it is the next change, and the changelog records that the promise was not kept. Until then the project's resource group can be deleted by hand, which takes the network, the model account, its private endpoint and the budget with it (the account stays soft-deleted, see below), and the module's objects can be left in the instance, where they do nothing without a caller that holds a contract's key. Taking the identity and the settings away is the other half of the bootstrap, so it is a manual step of the same kind, and it needs the owner's own plain-word yes, given separately from the one that created the identity: delete the role assignments (`az role assignment delete --assignee $principal --scope <each scope>`), the custom role, the two resource groups (with the second, the identity and its credential), and the secrets and variables (`gh secret delete`, `gh variable delete`).

A model account that was deleted is soft-deleted and keeps its name for a while. The workflow restores it by itself on the next `model-side`, so nothing has to be purged.
