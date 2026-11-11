# Security policy

Meternaut is a public, open-source project (MIT licence). It reads an Azure estate, proposes savings, and changes something in Azure only after a named person approves it, with that person's own rights ([AGENTS.md](AGENTS.md), rules 23, 26 and 29). It holds no key, no connection string and no credential, in its code or in its settings: the one environment of its settings, `hub`, holds identifiers of the maintainer's estate as secrets, so that GitHub masks them in logs that anyone can read.

## Reporting a vulnerability

Please do not open a public issue for a vulnerability. Use GitHub's private vulnerability reporting: the **Report a vulnerability** button under the *Security* tab of this repository. Say what you found, how to reproduce it, and what you think it allows. This is a small project with one maintainer: expect an answer in days, and a fix as fast as the change can be tested.

What counts as a vulnerability here:

- a way to make Meternaut change something in Azure without the approval of the person whom the change is for, or to make a change that was not approved;
- a way to read or send data that the system should not, to skip one of its guards (the switches, the budgets, the checks of an agent's answers), or to impersonate a person or an identity;
- a secret, a key or an identifier of a real estate in this repository or in its history;
- a weakness in a workflow, a template or a tool that a pull request from a fork, or a stranger, could use.

## What the repository does to stay safe

- **Nothing secret is committed.** `tools/tests/test_public_hygiene.py` fails a private key, a token, a storage or Service Bus key, a signed address, a long JWT, a work e-mail address, an expletive and any identifier of the maintainer's own estate (kept there only as hashes); the maintainer's own checkout holds two more lists, outside the repository, for the rest. GitHub secret scanning with push protection is on. Records that name an estate stay on the maintainer's machine ([AGENTS.md](AGENTS.md), rule 17).
- **`main` is protected, for everybody.** No deletion and no force push; a change comes by pull request, and the check `checks` of the workflow of the same name has to pass. The tags (the editions of the documents) cannot be moved or deleted.
- **Workflows are small and pinned.** Every action is pinned to a full commit, and GitHub refuses one that is not; only GitHub's own actions and one more, `azure/login`, are allowed; the default token of a run is read-only (the Hub asks for an OpenID Connect token as well, see below) and a workflow cannot approve a pull request. A run that comes from a fork waits for the maintainer's approval, for every outside contributor, and has no secret: the repository's own settings hold none, and the secrets of the environment `hub` reach only a job that is bound to it, which takes a deployment from `main` alone.
- **One workflow reaches Azure, and only from `main`.** The Hub (`deploy-hub.yml`) signs in with OpenID Connect and no stored credential, as a managed identity whose federated credential trusts one subject only: a job that is bound to the GitHub environment `hub` of this repository. The environment accepts a deployment from `main` alone, the workflow starts only by hand and only as the maintainer's account, and `main` is protected (above), so no pull request, fork, branch or tag can get a token. The environment's secrets are identifiers of the estate and no credential; they are secrets so that GitHub masks them in the logs, which anyone can read, and the workflow publishes no output of the job and masks what it reads from Azure. The federated credential that was made for the earlier, private repository trusts that repository's immutable ids and not this one's. The drift workflow (`drift.yml`) stays disabled in the repository's Actions settings ([AGENTS.md](AGENTS.md), rule 18). That is why a change to `tools/`, `environment/`, `operator/`, `.github/`, the tests or `AGENTS.md` is read in full before it is merged: what is on `main` is what runs with the deploy identity.
- **Dependabot** keeps the pinned libraries, packages and actions current, **code scanning** (CodeQL) reads the workflows, the Python and the JavaScript (GitHub reported the languages of the new repository two and a half hours after the push, and the setup was widened then), and **private vulnerability reporting** is on.

If you find that one of these statements is not true, that is a vulnerability: please report it.
