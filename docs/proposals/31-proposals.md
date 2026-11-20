# What a finding proposes: the settings to lower and the other ways to save — a decision record

**Status: decided on 2026-11-20. Built and tested against fakes: no model was called, nothing ran in Azure, and nothing is deployed.** This record is one of three pieces of the same work. It says what the Investigator may state beyond the change that code prices, and what code keeps of it. The family that lowers a setting after a person approved it, and the words of the page, the card and the letter, are the other two, and have their own records.

## What was asked

A finding already states its change in typed form: the action, the bill lines that it would shrink and what remains of them, and code prices it from the bill ([proposal 24](24-priced-findings.md)). What a person read was still a sentence of the AI ("lower the units from 4 to the base capacity") that code could neither check nor act on, with no other way to save named and nothing said of what each way gives up. A person who is asked needs to know what exactly would be set, from what to what, what it saves, what else could be done instead, and what each other way gives up. Meternaut has to find these ways by itself: nothing in an instruction, a tool or a document says how a resource is scaled, which tier or size exists, or what a kind of resource is called ([rule 30](../../AGENTS.md)). The Investigator reads the properties of a resource and the documentation about its type with the tools that exist, and states what it learned as data. Code checks the data.

## What the Investigator may state

Two optional entries of `change`, both data that code compares with what the tools showed in the same run:

- `set`: at most 3 settings, each `{"handle", "property", "from", "to"}`: a number that a tool showed for the resource, under the name that the tool gave it, and a smaller number. This is what a person can be asked to approve.
- `others`: at most 3 other ways to save on the same resource, each `{"title", "gives_up", "in_place", "change"}`. The title is at most 80 characters of plain words. `gives_up` is at most 240 characters on what the way costs in features, limits and availability, as far as the tools and the documentation that was read show it. `in_place` says whether the resource can be altered where it is, or has to be made again. `change` is a change of its own, in the same forms as the main one.

An invented example. The tools showed a resource of the invented kind `microsoft.example/gateways` with the property `capacityUnits` at 4, and its bill line costs 200 dollars a month. The Investigator states the main change `{"action": "reduce", "effects": [{"handle": "r1", "meters": ["m1"], "remains": {"form": "ratio", "on": "capacityUnits", "from": 4, "to": 2}}]}` and beside it `"set": [{"handle": "r1", "property": "capacityUnits", "from": 4, "to": 2}]` and `"others": [{"title": "Use the invented Lite tier", "gives_up": "Fewer units and no zone redundancy, as far as the pages say.", "in_place": false, "change": {"action": "switch", "effects": [...]}}]`. Nothing here is a kind, a property or a tier that an instruction names; the instructions say only what the entries are and how code treats them.

## What code keeps

Every entry is checked on its own. One that fails is dropped by itself, counted by the rule that it failed, and said in the notes of the run in plain words ("finding 2: code dropped 1 of 3 settings (a property that no tool showed: 1) and 1 of 2 other ways (a title that is not plain words: 1)"). The finding is never dropped for a bad entry: it opens its case as it always did.

| A setting is kept only when | |
|---|---|
| The finding proposes a change and its action is `reduce` | Any other proposal or action keeps no setting. |
| The handle is one of the finding's | Another resource, a handle that no tool showed and a handle that is not text are dropped. |
| The property is one that a tool showed for that handle, under that exact name, and the name is a plain one (`pricing.NAME`) | The properties are read from `Toolbox.evidence`, as the tools returned them. |
| Its value is one plain number | A word, a flag and a list (the value is a list when the items of a list under that key differ) are no number, and a setting on them is dropped. |
| `from` is that number | The tools' number, within a millionth. |
| `to` is a number of the same kind, finite, not negative and smaller than `from` | Whole where `from` is whole. Only numbers that go down: a tier, a SKU or a flag is not a setting in this version. |
| The property is not listed twice for the resource, and no more than 3 are kept | The first ones are kept. |
| Where the change states a ratio on the same property of the same resource, `from` and `to` are its numbers | A setting that disagrees with the finding's own change is dropped. |

| Another way is kept only when | |
|---|---|
| The finding covers one resource | The ways of a finding of several resources are dropped and counted: a way is priced for one resource. |
| The title is plain words, at most 80 characters | Letters, digits, spaces and a few marks; no link, markup or amount of money; the same check as the other short phrases of an answer (`roles.clean_text`). |
| Its change has an action that code can read, and neither it nor its title repeats the main change or a way kept before it | An action none, an unknown action or a missing change is dropped, and so is a repeat. |
| No more than 3 are kept | |

A way is priced exactly as the main change is (`pricing.price`, for the finding's resource), from the bill, with the low and the high end of a month. A way that cannot be priced is kept with no figure, and the page says that it is not priced. `gives_up` is cut and cleaned like the other words of the AI, and is kept as the AI's own words that code did not check: a person reads it marked so. A way never becomes a setting: nothing of what it says is executable.

## What lands in the case

The kept entries are the typed facts of the case of each resource, under the key `ways`: `{"set": [{"path", "from", "to"}], "others": [{"title", "givesUp", "action", "inPlace", "lowUsd", "highUsd"}]}`, the shape that `cases/proposals.py` documents and reads back. The shared module first named the key `proposal`, which the facts of a case already use for the word of the finding's proposal (delete, change, investigate) and which other parts read, so the key is `ways`. The facts are kept while a request that was asked with the price is still open and the finding is judged again with no price, as the price itself is; a case that a later answer makes with its own entries keeps those. The case of a group of resources keeps none, because a setting is a number of one resource.

## What the Skeptic sees

The Skeptic is shown the kept settings (the handle, the property as the tool showed it, the value now and after) and the kept ways (title, what each gives up, the action, whether the resource can be altered where it is, and what code priced it at) as typed data beside the model of the saving. One general sentence tells it to judge whether the new value is safe given the evidence rows and whether what the ways give up is right, and to say disagree or unsure when it is not. It can only make a finding weaker ([rule 30](../../AGENTS.md)).

## The instructions

The Investigator is told the shape and general principles, and nothing else: when the change is a smaller number for a property that a tool showed, state it, because only a setting that is stated can be approved and made, with that person's own rights ([rule 29](../../AGENTS.md)), and name nothing that the tools did not show; learn what the smaller options are and how a thing is changed from the properties and from what the documentation was read to say, never only from what it already knows, and name an option only after finding what it must still carry; list every other way that it found, price each through the same forms, and say what each gives up only from what it read, because a price shows neither features nor limits and an average hides a peak; say `in_place` false when the documentation says that a smaller option needs the resource to be made again; and know that a person reads `gives_up` marked as its own words. A test scans the instructions for kinds of resource, measurements and thresholds, and the tests of this piece use invented kinds, properties and values only. The instructions grew from 10,878 to 12,447 characters. The lock of the agents and the red team's copy of the instructions are written again; only the two instruction hashes moved.

## The Study reads the kinds of an open finding first

What the documentation says about a type has to be on record before the Investigator judges a resource of it. The survey of the Study ranked the kinds of resource of the estate by their cost. It now puts first the kinds that a finding which nobody decided is about, and the kinds of a request that waits for an answer, read from the store of the loop with no text of the estate, and then the dearest kinds as before; the cap on the number of kinds is applied after that order. A kind that has a current claim, or a mark that it was studied, still does not wait.

## Text proposed for a rule of AGENTS.md

*The orchestrator numbers it, joins it with the text of the piece that makes the change, and adds it at the merge.*

> **The AI proposes what to change, code checks it, and a person makes it with their own rights** (2026-11-20, the owner, about a request that said "reduce" and nothing else, and a bill that showed what could be saved: "I WANT TO BE ABLE TO DO IT!"). Beside the change that code prices, the Investigator may state the settings that it would lower (a property that a tool showed, the value now and a smaller value) and the other ways to save on the same resource (a title, what each gives up, whether the resource can be altered where it is, and a change of its own that code prices from the bill). Code keeps an entry only when it can compare it with what the tools showed in the same run, drops the others one by one and says so, and no figure is written by an AI (rule 30 (b)); what a way gives up is shown as the AI's own words. A kept setting is data: it is made only by the family that lowers a setting, after a named person approved it, with that person's own token (rule 29), in a resource group that the owner lists in `REAL_CHANGE_SCOPES`, and only while `REAL_CHANGES_ALLOWED` in `families/gates.py` is true; only the owner changes that line, in a pull request that he reads himself. `CHANGE_REQUIRES_PLANTED_TAG` and `CHANGE_SCOPES` stay as they are: every older family is held to what Meternaut planted itself. No instruction, tool, schema or document names how to scale anything, or a kind, a property, a limit or an option of a service (rule 30 (a)).

## What is not proved

- **That the Investigator states `set` and `others` well.** No model was called. A real run has to show whether it names the right property, whether it finds the smaller options in the documentation, whether it prices each way through a form that code accepts, and whether `gives_up` is true.
- **That the documentation of a type is on record before the Investigator judges a resource of it.** The Study runs weekly and reads at most eight kinds by default, so a kind with an open finding may wait a week, and a resource that no earlier run opened a finding for is judged with nothing on record unless the kind was studied for another reason.
- **That the property that a tool named is the one that a write changes.** The tools show a property under the path that the platform lists for the type; the family that makes the change reads the resource live, and says so when it is not a plain value of the resource. No write was tried.
- **That `gives_up` and `in_place` are right.** They are the Investigator's claims, not checked by any code, and the page says so. The Skeptic is told to doubt them.
- **That a setting and the saving agree.** Code checks a setting against a ratio on the same property, and nothing ties it to a stated quantity of a meter, or a way's saving to what a person would see after the change; each saving is the bill's arithmetic on what the AI stated.
- **The page.** The Details table of the request page lists every typed fact, so it lists `ways` as JSON until the words of the page exclude it.
- **What a read of the real estate showed (2026-11-20, read only, property names and numbers only).** In the app's typed form the plans of one service showed `sku.capacity`, `numberOfWorkers` and counts as plain numbers, and a network gateway and an API management instance showed `sku.capacity` (2 and 1). The check kept a setting that lowered `sku.capacity` by one and dropped one that lowered a 0 to 0. No resource of the kind that the owner's example is about exists in the ten subscriptions that this read could see, so the property of that example was not read. A property that ends in `Count` is shown as a number too, and the check cannot tell that no write changes it: the family that makes the change says so.
- **The package.** The sources that the Operator receives grew by 2,354 bytes on an LF copy (the archive from 321,122 to 323,476, the request from 357,501 to 359,855), which leaves 120,145 of the 480,000 free, 145 above the floor of 120,000. A run of the measure varies by about 80 bytes.
