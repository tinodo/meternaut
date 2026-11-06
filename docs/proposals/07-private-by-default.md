# Private by default: an Operator inside the network — a decision record

**Status: proposed on 2026-11-06, after the owner found public network access on the Event Hubs namespace, both function apps, Application Insights and the workspace, and asked that all of it be switched off. The identity, the subnet, the tool that runs one container group and the first script (the probe) are in the repository. None of it has run on the real estate, and nothing is private yet. A statement that was inferred and not read in a source is marked (inferred).** This page records one decision: no resource of Meternaut has a public endpoint, and what the deployment workflow can then no longer do from outside the network is done by a short-lived container inside it, the Operator. It builds on [the first environment](01-first-environment.md), [the first cases](02-first-cases.md), [the loop](04-the-loop.md) and [run as the approver](05-run-as-the-approver.md).

## The rule and the state

The rule, from the owner on 2026-11-06, extends [rule 23](../../AGENTS.md): no PaaS resource of the project has a public endpoint (public network access Disabled, private endpoints only), and no key exists anywhere (managed identities and OpenID Connect only: no shared access signature, no storage key, no personal access token, no publish profile).

| Resource | Public network access today | Private endpoint | Source |
|---|---|---|---|
| Model account | Disabled | yes | [`environment/main.bicep`](../../environment/main.bicep) |
| Foundry resource of the agents | Disabled | yes | [`environment/foundry/main.bicep`](../../environment/foundry/main.bicep) |
| Storage account | Disabled | blob, queue and table | [`environment/recording/main.bicep`](../../environment/recording/main.bicep) |
| Cosmos DB account | Disabled | yes | the same |
| Event Hubs namespace | **Enabled**: the gateway sends to it and the workflow sends the control event | yes, which both apps use | the same |
| Usage function app (Flex Consumption) | **Enabled** | none | the same |
| Cases function app (Basic plan; it also serves the console, behind the platform's sign-in) | **Enabled** | none | [`environment/cases/main.bicep`](../../environment/cases/main.bicep) |
| Application Insights component and its workspace | **Enabled** for ingestion and for queries (the templates set neither) | none | the same, and the [changelog](../../CHANGELOG.md) |

## What private access breaks

Once the four services above are private, these stop working from the GitHub-hosted runner, which is outside the network. Azure Resource Manager, the control plane, stays reachable, so everything that is a deployment or a read of a resource's own properties keeps working.

| What | Today | Why it stops |
|---|---|---|
| Publishing code | The runner posts the package to the app's deployment site (Kudu) | That site is reached through the app's private endpoint, with a DNS record of its own next to the app's ([App Service private endpoints](https://learn.microsoft.com/azure/app-service/overview-private-endpoint)). With public access off there is no other way in |
| Starting a run | The runner sends one event to the control hub | A namespace with public access Disabled takes data-plane traffic only through its private endpoints (inferred from what the setting means) |
| Reading telemetry | The runner queries the component for the History and for the copy jobs' results | "Queries sent through the Resource Manager API can't use Azure Monitor private links. These queries can only gain access if the target resource allows queries from public networks", and blocking public queries blocks every client outside the private link scope ([Azure Monitor private link design](https://learn.microsoft.com/azure/azure-monitor/fundamentals/private-link-design#control-network-access-to-ampls-resources)) |
| Checking the console's access | `tools/console-check.py door` asks the console from outside and expects a sign-in or a refusal | A request from outside no longer reaches the sign-in: the platform refuses it earlier (inferred), so the check would pass without testing what it was written to test |
| The agents' traces | The Foundry project sends them to the component with the project's identity | Foundry's own page lists public addresses that traces and evaluations need on the Application Insights side ([network isolation for Foundry](https://learn.microsoft.com/azure/foundry/how-to/configure-private-link), firewall allowlisting). The project is a Basic agent setup, which runs in Microsoft's network and not in ours (inferred), so a component whose ingestion is Disabled cannot take them |
| People using the console | A person opens the console's public address and signs in | A private console is reached only from a network that has a path to its private endpoint. Whether the approvers have one is not known to this record (inferred); it is a decision for the owner below |

## The options

The research of 2026-11-06 looked for a way to keep every one of the four actions working without a public endpoint, without a key and without a machine that runs between two runs.

| Option | Keyless | Why it does not do, or what it needs |
|---|---|---|
| Keep public access and restrict it by address | yes | Breaks the rule: the endpoint stays public. The runner's addresses are GitHub's, a large and changing set (inferred) |
| An ARM deployment of the app's `onedeploy` extension with a `packageUri` | no, for a private blob | The platform downloads the package from the URL. A private blob needs a shared access signature, which rule 23 forbids. A public URL needs none: that is route (b) below |
| `WEBSITE_RUN_FROM_PACKAGE` from a blob, with a managed identity | yes | Not supported on Flex Consumption. On the Basic plan it could work (inferred), but somebody has to write the blob, and the storage account is private: the same problem one step earlier |
| The ARM `hostruntime` proxy | yes | Not documented, so nothing is built on it |
| An ARM `deploymentScripts` resource | no | It mounts a storage account with the account key |
| GitHub-hosted runners inside the virtual network | yes | Azure private networking needs larger runners, and the page is written for organizations ([GitHub docs](https://docs.github.com/en/organizations/managing-organization-settings/about-azure-private-networking-for-github-hosted-runners-in-your-organization)); the plan needed is Team or Enterprise (from the research, not re-read). The repository belongs to a person |
| A self-hosted runner inside the virtual network | no | Registering it takes a GitHub credential, and the machine runs and costs money between two runs |
| **The Operator: a container group in a delegated subnet** | yes: its own managed identity | What follows. It is the only option that meets the rule, needs no standing compute and no organization. It is not proven here: the probe is what proves it |

## The Operator

**What it is.** A container group of Azure Container Instances that the workflow makes through Azure Resource Manager when a step needs the inside of the network. One script runs in it. The workflow reads its log through Azure Resource Manager and deletes the group. [`tools/operator-run.py`](../../tools/operator-run.py) does all four, and it deletes the group in every case: after an error, after a timeout (exit code 124) and after an interrupt (130). The group runs in the subnet `snet-ops`, which is delegated to container groups and gives it no public address, as the user-assigned identity `id-meternaut-operator`. The template is [`environment/operator/main.bicep`](../../environment/operator/main.bicep); the Hub actions are `operator` (make the identity and the subnet) and `operator-probe` (the first run).

**How a script gets in.** The script and any files travel in the request as one secret volume at `/mnt/op`. The volume is kept in memory in the container and is read-only ([Learn](https://learn.microsoft.com/azure/container-instances/container-instances-volume-secret)). A value that must not be seen is passed as a secure environment variable. The tool takes every such value out of everything it prints, including what Azure and the container say, and the request body is written to a file that only the tool's user can read and is removed at the end.

**The image** is `mcr.microsoft.com/azure-cli`, pinned by digest. On 2026-11-06 the tags `2.92.0`, `latest` and `azurelinux3.0` were the same manifest list (Azure CLI 2.92.0 on Azure Linux 3.0). Container Instances runs amd64 images only ([Learn](https://learn.microsoft.com/azure/container-instances/container-instances-resource-and-quota-limits)), so the workflow names the digest of the linux/amd64 manifest, which two requests to MCR with `curl` give and no container tool is needed. The pinned reference is `mcr.microsoft.com/azure-cli@sha256:67afdcb4f3efce0b33aadba0b8a72402b6f071741400fd75cc5cb8a1d7bf1d98`. To read it again: a HEAD request to `https://mcr.microsoft.com/v2/azure-cli/manifests/<tag>` with the header `Accept: application/vnd.docker.distribution.manifest.list.v2+json` gives the digest of the manifest list in `Docker-Content-Digest`, and a GET of the same address lists the manifests, of which the one with architecture `amd64` and operating system `linux` is the one to pin. A tag can move and a digest cannot, so the pin is changed by a person, on purpose, with the same two requests. The layers of that image, listed from MCR without running it, hold bash, curl, getent, python 3.12 and jq. They hold no awk, so nothing in the probe uses one.

**The log.** A running container keeps up to 4 MB of log, a stopped one only 16 KB or 1,000 lines ([Learn](https://learn.microsoft.com/azure/container-instances/container-instances-resource-and-quota-limits)). So a script prints little (the probe at most 120 short lines, about 12 KB), the tool reads the log every few seconds while the container runs and once more at the end, prints each line once, prints the group's events when the container never started (an image that cannot be pulled is the likely cause), and says when the last read is as long as the limit. The workflow also puts the log into the run's summary.

**Facts about container groups in a virtual network** that shape the design ([Learn](https://learn.microsoft.com/azure/container-instances/container-instances-virtual-network-concepts), [Learn](https://learn.microsoft.com/azure/container-instances/container-instances-vnet)):

- The subnet holds container groups only. Learn says that a subnet smaller than /24 is known to run out of addresses, because the platform releases the address of a deleted group slowly, and it names /28 as one of the sizes. A /24 does not fit a small virtual network, so the subnet is the largest the network can spare, a /27 (27 usable addresses), and the probe is run several times in a row to see whether that is enough.
- A group does not take the DNS servers of the virtual network. The tool gives it the landing zone's, which is what lets the name of a private endpoint resolve to its private address.
- Learn says, on two pages, that a NAT gateway is the only supported way out for a container group in a virtual network. The landing zone sends the traffic of a subnet through its firewall with a route table, and the same site documents a container group behind Azure Firewall ([Learn](https://learn.microsoft.com/azure/container-instances/container-instances-egress-ip-address), not re-read). Whether the landing zone's route works for a container group is the first thing the probe finds out: the image is pulled through it.
- A Linux container in a virtual network can get a token of its managed identity. Learn says that only Windows containers in a virtual network cannot ([Learn](https://learn.microsoft.com/azure/container-instances/container-instances-managed-identity)).
- The landing zone's network manager puts a route table on the new subnet some minutes after the subnet is made. The template makes the subnet once and leaves it alone ([rule 27](../../AGENTS.md)), and the action `operator` waits until the table is there.

**Identity and roles.** The identity is user-assigned, which is an exception to the owner's preference for system-assigned identities ([changelog](../../CHANGELOG.md), 2026-11-06); the console's sign-in identity is the other one. A system-assigned identity belongs to one container group, and a group exists for the minutes of one run, so every run would make a new identity whose roles have to be assigned and applied before the container can use them, and the changelog gives up to ten minutes for a role to apply. A user-assigned identity is made once, holds its roles, and is attached to each group (inferred: that the roles of a system-assigned identity of a container group cannot be given in advance). It is attached to no app. Each role below goes on one resource and is added with the step that uses it. Each also has to be added, by a person, to the condition of the deploy identity's role-assignment right ([bootstrap](../../environment/BOOTSTRAP.md)); until then the deploy of that role is refused and nothing else changes.

| Role | Where | What the Operator does with it | Added with |
|---|---|---|---|
| Reader | The project's resource group | Shows that it signs in and can read; later, reads the state of resources | This change |
| Website Contributor | Each of the two function apps | Publishes code with its own token to the private deployment site | The publish step |
| The built-in reader role of the workspace | The workspace | Runs queries through the Azure Monitor private link, for the History and the copy jobs' results | The read step |
| Azure Event Hubs Data Sender | The control hub only | Sends the control event that starts a run | The run step |

**What the Hub actions will do with it.** An action that only deploys or reads a resource's own properties does not change. These change:

| Hub action | Through the Operator |
|---|---|
| `recording`, `cases` | Gets the package (the routes below), posts it to the private deployment site with its identity's token, and reports the result |
| `recording-check`, `cases-run` | Sends the control event with the Event Hubs REST API and a token of its identity, then queries the telemetry for the answer and prints a few lines of it |
| `loop-check`, and the check at the end of `cases` | Makes the same requests as `tools/console-check.py door` from inside the network, with that tool sent in the secret volume |

**Rule 29.** [Rule 29](../../AGENTS.md) says that no identity of Meternaut holds a role that writes in Azure. Website Contributor writes. The Operator is the deployment workflow's arm inside the network, not a part of the product: the workflow's identity already holds Contributor on the group and can do all of it; the Operator's identity is attached to no app, is used only by a group that the workflow makes, and has the role on the two apps and nowhere else. Whether that is inside rule 29, or the role is given just before a run and taken away after it, is the owner's to say (decisions below).

## What it costs

Container Instances bills the vCPU and the memory of a group for the seconds it exists. The Retail Prices API on 2026-11-06 gives, for Sweden Central and a Linux group, 0.0466 US dollars for a vCPU-hour and 0.00511 for a gigabyte-hour. A group of 1 vCPU and 1.5 GB costs about 0.054 US dollars an hour, so a probe of 10 minutes costs about 0.9 US cents, and 30 such runs a month about 27 cents. The identity, the subnet and its network security group cost nothing. The private endpoints that the later steps add (one for each app and one for the Azure Monitor private link scope) cost a few dollars a month each. Two fallbacks have a standing price, and the probe says whether either is needed:

- A NAT gateway, if the landing zone's route does not work for a container group: 0.045 US dollars an hour, about 33 a month, plus a Standard public IP address at 0.005 an hour, about 3.65, so about 37 a month.
- A private container registry, if MCR cannot be reached from the subnet: Azure Container Registry Premium, which private links need, is 1.67 US dollars a day, about 50 a month, which is the owner's line.

## What the probe checks

[`operator/probe.sh`](../../operator/probe.sh) runs in the container and prints one `ok:` or `FAIL:` line for each check: at most 120 short lines, never a token or a secret, always ending in `probe-done`, and always exiting 0, because the facts are the product. That the image is pulled at all is the first answer, and the tool's events show it when it is not.

| Check | What it shows | What it decides |
|---|---|---|
| The container starts | MCR is reachable from the subnet, and the landing zone's route lets a container group out | Whether the Operator can work at all, and whether a NAT gateway or a private registry is needed |
| `az login --identity`, `az group show` | The identity signs in inside a group in a network, and its Reader role works | Everything else |
| The resolvers, and the names that are passed in | The DNS servers the group got, and whether a private endpoint's name gives a private address | Whether private endpoints can be used from the Operator |
| `management.azure.com`, `login.microsoftonline.com` | The Operator's own calls | Whether it can sign in and call Azure |
| `api.github.com`, `codeload.github.com` | The GitHub API and the repository archive at a commit | Route (a) from the repository |
| `api.github.com` and the host of the workflow artifacts | The download of an artifact that the job uploaded | Route (a) from an artifact |
| `github.com`, the release-asset hosts | A release asset with a public address | Route (b) |
| `pypi.org`, `files.pythonhosted.org` | Installing a package inside the container | Building inside the container |
| `api.applicationinsights.io`, `api.loganalytics.io` | The query endpoints that the read step will use | Whether the telemetry can be read from inside after the private link exists |
| A file of a stated size in the secret volume | How many bytes the request body and the volume carry | Route (c) |

**How the answers choose the package route.** The usage app's package is tens of megabytes (the Azure SDK wheels), so it cannot ride in the request. The cases app's package is about 200 KB of source and one wheel.

- **(a) The job's own token.** The workflow hands the container its token for the run as a secure value, and the container downloads the package that the job built and uploaded as an artifact, or the repository archive at the commit. The token expires when the job ends, and on a GitHub-hosted runner at the latest after 6 hours ([GitHub docs](https://docs.github.com/en/actions/concepts/security/github_token)). It would need `actions: read` next to `contents: read`. If the API and the artifact host answer, this is the route, and nothing needs to be built in the container. If only the archive host answers, the container would have to build the package itself, which needs the two package hosts and Python 3.13 (the image has 3.12, so the build would have to target 3.13 wheels: inferred): possible, and clumsy.
- **(b) A public repository and a release asset** at a public address. It needs no token, and it also allows the `onedeploy` extension to take that address as its `packageUri`, so that even the publish step would need no Operator (inferred: whether the platform follows the redirect of a release asset is not documented). It needs the owner's decision on visibility, rule 1.
- **(c) A package inside the request**, as a file of the secret volume, for the cases app only. It works if the size check passes with room above the package (base64 adds a third), and it does not help the usage app.
- **None of them**: if no GitHub host and no size is enough, the usage app has no route until the platform team of the landing zone allows one host, or the owner chooses a private registry.

## Decisions for the owner

**A public repository** (rule 1). Needed only for route (b). Cost: none. The way back: none in practice, because published content can be copied. Recommendation: do not decide now. Run the probe first; route (a) needs no change of visibility.

**The job's token inside the container** (rule 23). It is not a key that anyone keeps: it exists for one job. It is a bearer token, though, and whoever holds it can read the whole private repository until the job ends. Whether that counts as "an identity of the run" under rule 23 is the owner's to say (inferred reading of the rule). Way out: route (b) or (c). Recommendation: allow it for the packages of the two apps and nothing else, if the probe shows that route (a) is the only one.

**The Operator's Website Contributor** (rule 29), as above. Recommendation: standing, on the two apps only. The Operator can be used only by a group that the deploy identity makes, and that identity can already do everything the role allows, so a standing role adds no right that the workflow does not hold. Counter-disclosure: it is a standing right to write that a person who may assign that identity could use. The alternative, given just before a run and taken away after it, needs the same entry in the condition and a wait for the role to take effect (inferred).

**The console for people.** A private console cannot be opened from the public internet. The approvers need a path into the landing zone's network (a VPN, ExpressRoute, or a machine inside), or a public front end such as Azure Front Door with Private Link in front of it, which is a public endpoint again and costs a standing price. Until the owner says which, the cases app stays public and everything else goes private first.

**The agents' traces.** Foundry's Basic agent setup cannot send traces to a component whose ingestion is Disabled. Three ways:

| Way | What it gives | What it costs |
|---|---|---|
| No traces from Foundry | The agents run; the History is unchanged | Nothing. The agents' own steps stay in the History that the app writes |
| A separate component for the traces, ingestion public, Microsoft Entra ID only | The traces | One public ingestion point that holds the agents' traces and not the History, and takes no key. A few cents a month. Taken away by removing the connection |
| The Standard agent setup, with a delegated subnet | Traces and agent state inside the network | It needs a Cosmos DB account, a storage account and an AI Search service of the project's own. AI Search Basic alone is 0.101 US dollars an hour, about 74 a month, so the whole is above the owner's line |

Recommendation: no traces from Foundry while the component is private, and a separate component only if the owner wants the traces and accepts one public ingestion point.

**A NAT gateway or a private registry**, if the probe shows that either is needed. Both are named with their prices above. Recommendation: the NAT gateway first, because it costs less and the registry also needs an image import.

## The order of the work

1. **The identity switch**, in its own change, first. Both steps are merged: both apps run as their system-assigned identities and the grants of the user-assigned ones are retired in the code ([changelog](../../CHANGELOG.md), 2026-11-06). What is left is a person's: deploy it, read it back, and remove the old identities. The roles and the private endpoints below are given to identities, and changing an identity after that repeats them (inferred).
2. **The Operator and the probe** (this change). A person registers the resource provider `Microsoft.ContainerInstance` in the project's subscription if it is not registered, and adds Reader to the deploy identity's condition ([bootstrap](../../environment/BOOTSTRAP.md)). Then the Hub actions `operator`, and `operator-probe` several times in a row. The answers decide the package route, the egress and the subnet size. Nothing is private yet.
3. **Event Hubs private.** First check that the gateway's loggers still reach the namespace: the gateway's API Management instance is in a network (inferred from the gateway tool's notes), and whether that network has a path to the namespace's private endpoint is not known. The control event then goes through the Operator, with Azure Event Hubs Data Sender on the control hub.
4. **The two apps private**, one private endpoint each, with the central zone for App Service sites registered by the landing zone's policy for both records (the app's and the deployment site's: not read in the landing zone; a fact to check, and the workflow waits for it as it does for the other endpoints). Publishing and the access check go through the Operator. The console stays public until the decision about people is taken.
5. **Application Insights and the workspace private**, through an Azure Monitor private link scope with one private endpoint. The central zones `privatelink.monitor.azure.com`, `privatelink.oms.opinsights.azure.com`, `privatelink.ods.opinsights.azure.com`, `privatelink.agentsvc.azure-automation.net` and `privatelink.blob.core.windows.net` exist in the hub (the owner's finding), and the built-in policy "Configure Azure Monitor Private Link Scope to use private DNS zones" (`437914ee-c176-4fff-8986-7e05eb971365`, part of the Azure landing zone reference's DNS initiative) has to be assigned in the landing zone: a fact to check, not to assume. The scope starts in Open access mode and moves to Private Only after every resource is in it ([Learn](https://learn.microsoft.com/azure/azure-monitor/fundamentals/private-link-design)). Telemetry is read through the Operator, and the Foundry decision above comes first.

## Not checked

- Whether Container Instances in a virtual network is available in the project's region, and whether a landing-zone policy denies or changes a container group. The first deploy shows both.
- Whether the route table that the landing zone's network manager puts on the subnet lets a container group out. The probe's first line says.
- Whether a /27 is large enough. The probe is repeated; the failure is "subnet full".
- Whether the secret volume holds a file of the size that the cases package needs. Learn states no limit; the size check measures one.
- Whether `az login --identity` works as written inside a group in a network on Linux. Learn documents it; nobody here has seen it.
- That `az container create --file` sends the file as the body of the request. Read from the tool's own compiled code, not run.

## Sources

Read on 2026-11-06: [Azure Container Instances, virtual network scenarios](https://learn.microsoft.com/azure/container-instances/container-instances-virtual-network-concepts), [deploy a container group to a virtual network](https://learn.microsoft.com/azure/container-instances/container-instances-vnet), [NAT gateway for a container group](https://learn.microsoft.com/azure/container-instances/container-instances-nat-gateway), [managed identity in a container group](https://learn.microsoft.com/azure/container-instances/container-instances-managed-identity), [secret volumes](https://learn.microsoft.com/azure/container-instances/container-instances-volume-secret), [resource and quota limits](https://learn.microsoft.com/azure/container-instances/container-instances-resource-and-quota-limits), [the container group template reference](https://learn.microsoft.com/azure/templates/microsoft.containerinstance/containergroups), [Azure Monitor private link design](https://learn.microsoft.com/azure/azure-monitor/fundamentals/private-link-design), [network isolation for Foundry](https://learn.microsoft.com/azure/foundry/how-to/configure-private-link), [App Service private endpoints](https://learn.microsoft.com/azure/app-service/overview-private-endpoint), [GITHUB_TOKEN](https://docs.github.com/en/actions/concepts/security/github_token), [GitHub's communication requirements for runners](https://docs.github.com/en/actions/reference/runners/self-hosted-runners), [Azure private networking for GitHub-hosted runners](https://docs.github.com/en/organizations/managing-organization-settings/about-azure-private-networking-for-github-hosted-runners-in-your-organization), the Azure Retail Prices API, the manifests and layers of `mcr.microsoft.com/azure-cli`, and the built-in role list ([Reader](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/general), [Website Contributor](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/web-and-mobile)).

From the research of the same day and not read again: the statements about `onedeploy` with a `packageUri` ([Azure Functions infrastructure as code](https://learn.microsoft.com/azure/azure-functions/functions-infrastructure-as-code#deployment-sources)), `WEBSITE_RUN_FROM_PACKAGE` on Flex Consumption, `deploymentScripts`, the plan that Azure private networking for runners needs, and the registration of a self-hosted runner.
