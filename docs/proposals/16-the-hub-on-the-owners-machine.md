# The Hub on the owner's machine — a decision record (superseded)

**Status: ordered by the owner on 2026-11-08; superseded on 2026-11-11.** For three days every deploy ran from his machine, with his own `az` session, by a tool of this repository that ran the steps of the Hub workflow. On 2026-11-11 the owner ordered the tool deleted ("I TOLD YOU TO USE GITHUB AGAIN"), and the Hub is the GitHub workflow again ([rule 18](../../AGENTS.md)). This record stays so that the reasons and what was learned are not lost.

## Why it was made

The owner's GitHub Actions quota was used up (about 1,280 minutes in four days, 75 percent of them in the Hub), and the Hub workflow was the only way a change reached Azure. He chose to deploy from his machine rather than wait ("B"), and ordered the building moved there too ([rule 35](../../AGENTS.md)).

## What it was

A command-line tool that read `deploy-hub.yml` and ran its steps on the owner's machine, one run at a time, with his own Azure CLI session, so that Azure decided what a run could do and recorded him as the caller. It showed a dry run and a what-if first, needed the owner's plain words and a flag for a change of Azure, and left a record of each run in the git-ignored `local/` folder.

## The guards

The five tools that change Azure (`az-deploy.py create`, `retire-old.py`, `cases-move.py`, `aigateway-prep.py` and `operator-run.py`) took a proof file that only a run of the tool made, instead of `GITHUB_ACTIONS=true`, which any process can set. When the repository was made public ([proposal 18](18-making-the-repository-public.md)) the tool also refused to run until a person said, with a flag and a commit, that every change outside the documents since the commit he last read was read. A review found a way round that gate in each of three versions, and the fourth closed them; it stayed a tripwire and not a lock, because the tool and its helper ran before any gate could look at them.

## Why it was deleted

- The reason was gone. The runs of a public repository cost no minutes, and the owner made the repository public for that.
- It was the one place where repository code ran with the owner's own sign-in, on his machine. Its guards could stop an accident, not a change that nobody read.
- Its first lines said that every change to Azure is made from the owner's machine, and that was no longer true.

## What replaced it

The workflow `deploy-hub.yml`, as in [rule 18](../../AGENTS.md), **run in this repository, directly, in the GitHub environment `hub`** (built on 2026-11-11, not yet run). The owner rejected a plan of the same day, in which a small private deploy repository of his would call the workflow, because a private repository costs Actions minutes again and a public one does not; he ordered the mechanism of his other project instead: a protected `main` and a deploy from GitHub Actions, with OpenID Connect and no stored credential. The environment takes a deployment from `main` alone, every identifier of the estate is a secret of it (the log of a public repository is public, and GitHub masks a secret and not a variable), and the federated credential trusts the subject of the environment and nothing else ([the steps](../../environment/BOOTSTRAP.md)). The five tools accept a real GitHub runner again (`tools/hubguard.py`, four variables: a tripwire and not a lock), and the workflow starts by hand only, as the owner's account, on `main`. `drift.yml` stays disabled in the Actions settings. The owner's yes is to the environment with its branch rule and its secrets, the credential for its subject, the allowed action `azure/login` and a first run of `what-if`. The records of the runs from 2026-11-08 to 2026-11-11 stay in the owner's git-ignored `local/records/` folder.
