# Security policy

Meternaut is a public, open-source project (MIT licence). It reads an Azure estate, proposes savings, and changes something in Azure only after a named person approves it, with that person's own rights ([AGENTS.md](AGENTS.md), rules 23, 26 and 29). It holds no key, no connection string and no secret, in its code or in its settings.

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
- **Workflows are small and pinned.** Every action is pinned to a full commit, and GitHub refuses one that is not; only GitHub's own actions are allowed; the default token of a run is read-only (the two Azure workflows below also ask for an OpenID Connect token, which no run can use while they are disabled and no credential trusts this repository) and a workflow cannot approve a pull request. A run that comes from a fork waits for the maintainer's approval, for every outside contributor, and has no secret: the repository stores none.
- **No workflow reaches Azure.** The repository stores no Azure secret and no variable of an estate, and no federated credential trusts it: the one that was made for the earlier, private repository trusts that repository's immutable ids and not this one's. The workflows that deploy and that check for drift (`deploy-hub.yml` and `drift.yml`) are disabled in the repository's Actions settings, because they print values of an estate into logs that anyone can read; if they were enabled they would still fail at the start, because `azure/login` is not an allowed action, and there would be nothing to print, because no variable is stored. The Hub's steps run on the maintainer's machine, with his own Azure sign-in ([AGENTS.md](AGENTS.md), rule 18). That is why a change to `tools/`, `environment/`, `operator/` or `.github/` is read in full before it is merged, and why the tool that runs the Hub refuses to change Azure until a person has said that the changes in those paths since the commit he last read were read.
- **Dependabot** keeps the pinned libraries, packages and actions current, **code scanning** (CodeQL) reads the workflows, the Python and the JavaScript (GitHub reported the languages of the new repository two and a half hours after the push, and the setup was widened then), and **private vulnerability reporting** is on.

If you find that one of these statements is not true, that is a vulnerability: please report it.
