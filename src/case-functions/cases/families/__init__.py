"""The families of change (AGENTS.md rule 26 (a)).

A family is one kind of change with its own plan text, its own re-check right before it acts, its own call to Azure, its own check afterwards and its own test. This package imports nothing when
it is imported: the modules in it are loaded one by one by whoever needs them, so that the decision brief can read `words` (what a person reads of a family, which holds no way to reach Azure)
without loading the rest.

- `registry`: the list of the families, and the choice of the families that a finding may lead to.
- `base`: what a family is (the interface that the approval loop and the runner know) and what every family shares.
- `gates`: the two gates of every change (the resource groups of `CHANGE_SCOPES`, and the tag and the list of what Meternaut planted), and the owner-only switch.
- `calls`: every call that a family makes to Azure Resource Manager, in one place (the one module of the package that names a method that writes).
- `azure`, `lro`: the calls with a token, and how a change that Azure carries out later is followed.
- `digest`: the digest of a plan, which the approver's sign-in carries and the runner checks before it acts.
- `words`: what a person reads of each family (the decision brief's fields).
- `delete`, `disk`, `public_ip`, `vm`, `idle`, `machine`: the families themselves.

The table of the families, with their calls, their re-checks, their undo and their risk, is in docs/proposals/14-families-of-change.md. A change is made only on a resource inside the
`CHANGE_SCOPES` that carries the planted tag and is on the planted list (gates), and only with the approver's own token.
"""
