"""One request from the answer of the Investigator to the change and the words about it, on the three pieces together: what the Investigator proposes, the family that lowers a count and the words of the pages.

Everything here is invented: the kinds `microsoft.example/bastionhosts` (a number of scale units under `properties`) and `microsoft.example/workerpools` (a capacity at the root, `sku.capacity`), their
names, the groups and the ids. Nothing is made up of the app: what is reused is the fake Azure and the world of test_families_setting (`Real`, `RealArm`, `lead_of`, the brief, the card and the person of
its tests), the harness and the fake toolbox of test_investigate (`Harness`, `FakeToolbox`, `finding`), the readers of the pages of test_words and the console of the web tests (`console_of`). The two
added here are one fake Azure that knows the two kinds (`Arm`) and the readers of what a person reads.

The line of the owner (`REAL_CHANGES_ALLOWED`) is never edited: a test leaves it as it is, or turns it on in memory for the time of the test only, with a list of real groups that is made in memory too.
"""
import json
import unittest
from dataclasses import replace
from unittest import mock
from urllib.parse import urlsplit

import familysupport as fs
import test_families_setting as tfs
from familysupport import OID
from test_families_briefs import console_of
from test_families_setting import API, REAL_GROUP, REAL_SUB, Real, RealArm
from test_investigate import FakeFoundry, FakeToolbox, Harness, answer, entry, finding, key_of, meter_line, metrics, resource
from test_words import Rendered, _letter, blocks_of_card, blocks_of_html, problems

from cases import brief as brief_mod
from cases import letters, pricing, proposals, upkeep
from cases.families import gates, words
from cases.runner import execute

HOST, POOL = "microsoft.example/bastionhosts", "microsoft.example/workerpools"
BASE_ID = f"/subscriptions/{REAL_SUB}/resourceGroups/{REAL_GROUP}/providers/Microsoft.Example"
KINDS = ("bastionHosts", "workerPools")
TOKEN = "second-person-token"
OLD_STOCK = ("Meternaut makes no change for this kind of finding yet", "Consider reducing", "Traffic that you cannot see from here may depend on it.", "reducing the resource",
             "That is the AI's own proposal, and Meternaut did not check it.")


def host(units: int = 4, name: str = "bastion-one") -> dict:
    """A resource of the first invented kind as Azure shows it: the number of scale units under `properties`, a retention in days, what Azure fills in itself, and a list with a child in it."""
    return {"id": f"{BASE_ID}/bastionHosts/{name}", "name": name, "type": "Microsoft.Example/bastionHosts", "etag": 'W/"11111111-2222-3333-4444-555555555555"', "location": "swedencentral",
            "tags": {"team": "blue"}, "sku": {"name": "Standard"}, "systemData": {"createdBy": "somebody"},
            "properties": {"scaleUnits": units, "provisioningState": "Succeeded", "dnsName": "bst-one.example.test", "retentionDays": 30, "enableTunneling": False,
                           "ipConfigurations": [{"name": "ip1", "id": f"{BASE_ID}/bastionHosts/{name}/ipConfigurations/ip1", "etag": 'W/"22222222-2222-3333-4444-555555555555"',
                                                 "properties": {"provisioningState": "Succeeded", "subnet": {"id": f"{BASE_ID}/virtualNetworks/net/subnets/s1"}}}]}}


def pool(capacity: int = 3, name: str = "pool-one") -> dict:
    """A resource of the second invented kind: its number is at the root of the resource, `sku.capacity`."""
    return {"id": f"{BASE_ID}/workerPools/{name}", "name": name, "type": "Microsoft.Example/workerPools", "etag": 'W/"33333333-2222-3333-4444-555555555555"', "location": "swedencentral", "tags": {},
            "sku": {"name": "S2", "capacity": capacity}, "systemData": {"createdBy": "somebody"}, "properties": {"provisioningState": "Succeeded", "workerSize": "Medium"}}


class Arm(RealArm):
    """The fake Azure of test_families_setting with two more invented kinds: the provider lists them, and a PUT of either is carried out later, as a PUT of the first kind is there."""

    def __init__(self) -> None:
        super().__init__()
        self.totals["MetricA"] = [0.0, 0.0, 0.0]

    def answer(self, method: str, key: str, body):
        found = super().answer(method, key, body)
        if key == f"/subscriptions/{REAL_SUB}/providers/microsoft.example" and found[0] == 200:
            listing = json.loads(found[2])
            listing["resourceTypes"] += [{"resourceType": kind, "apiVersions": self.versions} for kind in KINDS]
            return 200, found[1], json.dumps(listing).encode()
        return found

    def write(self, method: str, key: str, body):
        if method != "PUT" or not any(f"/microsoft.example/{kind.lower()}/" in key for kind in KINDS):
            return super().write(method, key, body)
        sent = self.headers[-1].get("If-Match")
        current = self.etag_header or self.resources.get(key, {}).get("etag")
        if sent is not None and (key not in self.resources or str(sent).removeprefix("W/").strip('"') != str(current).removeprefix("W/").strip('"')):
            return 412, {}, b'{"error":{"code":"PreconditionFailed","message":"the etag does not match"}}'
        self.puts.append((key, urlsplit(self.url).query, body))
        old = self.resources[key]
        stated = {"id": old["id"], "name": old["name"], "type": old["type"], "systemData": old["systemData"], "etag": 'W/"new"', **body}
        stated["properties"] = {**body["properties"], "provisioningState": "Updating"}
        self.resources[key] = stated
        self.effects[key] = fs.Effect(self.reads_before_effect, self.settled)
        return self.started(201)


# What the Investigator answers: a reduction of the scale units, with the setting that it proposes and two other ways (a free tier, whose saving rests on a share that it assumes, and a removal that
# names a charge that no meter of the run has, so that code cannot price it).
SET = {"handle": "r1", "property": "scaleUnits", "from": 4, "to": 2}
FREE = {"title": "Use the free tier", "gives_up": "It is shared and carries no promise of uptime.", "in_place": False,
        "change": {"action": "switch", "effects": [{"handle": "r1", "meters": ["m1"], "remains": {"form": "assumed", "low": 0.05, "high": 0.2}}], "how": "Make it again on the free tier."}}
GONE = {"title": "Remove it", "gives_up": "Everything that connects through it stops.", "in_place": True,
        "change": {"action": "remove", "effects": [{"handle": "r1", "meters": ["m9"], "remains": {"form": "none"}}], "how": "Delete it."}}


def reduction(setting: dict = SET, on: str = "scaleUnits", start: int = 4, to: int = 2, others=(FREE, GONE)) -> dict:
    return {"action": "reduce", "effects": [{"handle": "r1", "meters": ["m1"], "remains": {"form": "ratio", "on": on, "from": start, "to": to}}], "how": "Lower the number.", "set": [setting],
            "others": list(others)}


def investigated(shown: dict, kind: str = HOST, name: str = "bastion-one", change: dict | None = None):
    """The investigation of one resource of an invented kind (a bill line of 201.60 a month, nobody connected): the typed answer goes through the fake toolbox, the check and the pricing, and the case
    that the run made is returned with the notes of the run."""
    one = resource(1, resource_id=shown["id"], resource_type=kind, name=name, resource_group=REAL_GROUP, cost_usd_30d=201.6)
    evidence = {"r1": {**metrics(MetricA=0), "properties": {key: value for key, value in shown["properties"].items() if isinstance(value, (int, float, str))}}}
    if "capacity" in shown.get("sku", {}):
        evidence["r1"]["properties"]["sku.capacity"] = shown["sku"]["capacity"]
    box = FakeToolbox([one], evidence, meters={"m1": meter_line("r1", 201.6)})
    said = finding(handles=["r1"], basis="oversized", proposal="change", evidence=[entry("r1", "MetricA", 0)], change=change or reduction())
    h = Harness(FakeFoundry(answer(said)), box, with_store=True)
    h.go()
    return h.store.case_get(key_of(box.handles["r1"])), h.notes


def world_of(shown: dict, case, kind: str = HOST):
    """The world of the family around one resource and the case that the investigation made of it, as the owner's resource in a real group: the lead of the case, in the store of the world."""
    arm = Arm()
    world = Real(arm=arm)
    arm.add(shown)
    case = replace(case, subscription_id=REAL_SUB, resource_group=REAL_GROUP, resource_id=shown["id"], resource_type=kind)
    world.store.case_put(case)
    lead = tfs.lead_of(shown, case.facts, resource_type=kind, cost_usd_30d=case.cost_usd_30d)
    return world, lead, case


def surfaces(world, plan) -> dict[str, Rendered]:
    """The page, the Teams card and the letter of the request of a plan, as a person reads them."""
    case = world.store.case_get(plan.case_id)
    page = Rendered("page", "page", blocks_of_html(console_of(world, plan, case).get(f"/ok/{plan.plan_id}").text))
    return {"page": page, "card": Rendered("card", "card", blocks_of_card(tfs.card_of(tfs.shown(world, plan)))),
            "letter": _letter("letter", letters.approval_letter(plan, case, tfs.PERSON, tfs.BASE, tfs.NOW, tfs.CONTACTS))}


def read(shown: Rendered) -> str:
    """What a person reads: everything but the Details, the navigation and the quotes of an AI."""
    return " ".join(block.text for block in shown.blocks if not block.details and block.region != "nav" and block.kind != "quote")


def cells(shown: Rendered) -> list[str]:
    return [block.text for block in shown.blocks if block.kind == "cell" and not block.details]


class FromTheAnswerToTheChange(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case, cls.notes = investigated(host())

    def test_the_answer_becomes_a_case_that_holds_the_priced_change_and_the_ways_under_the_key_of_the_ways(self):
        facts = self.case.facts
        self.assertEqual(facts["proposal"], "change", "the word of the finding's own proposal is where it was")
        self.assertEqual(proposals.KEY, "ways")
        ways = facts[proposals.KEY]
        self.assertEqual(ways["set"], [{"path": "scaleUnits", "from": 4, "to": 2}])
        self.assertEqual([(way["title"], "lowUsd" in way, way.get("estimate", False)) for way in ways["others"]], [("Use the free tier", True, True), ("Remove it", False, False)])
        priced = pricing.saved(facts)
        self.assertEqual((round(priced.low, 2), round(priced.bill, 2), priced.level), (100.8, 201.6, "Scenario"))
        self.assertEqual([note for note in self.notes if "dropped" in note], [])

    def test_with_the_line_as_it_is_the_request_asks_and_says_why_meternaut_cannot_make_the_change(self):
        self.assertIs(gates.REAL_CHANGES_ALLOWED, False, "the line of the owner is as it was written: this test turns nothing on")
        world, lead, case = world_of(host(), self.case)
        plan = world.approvals.plan_for(case, lead, (OID,))
        self.assertEqual((plan.family, plan.preconditions[proposals.CANNOT_KEY]), ("advise", "switch-off"))
        shown = surfaces(world, plan)
        for surface, one in shown.items():
            with self.subTest(surface):
                text = read(one)
                self.assertIn("Scale down the bastion host bastion-one: scale units from 4 to 2", text if surface == "letter" else " ".join(b.text for b in one.blocks))
                self.assertIn("You are asked whether to scale down the bastion host by lowering scale units from 4 to 2.", text)
                self.assertIn("Meternaut cannot make this change itself. The owner has not yet allowed Meternaut to change real resources. Your answer is recorded with your name.", text)
                self.assertIn("The AI named 2 other ways to save on this bastion host.", text)
                for stock in OLD_STOCK:
                    self.assertNotIn(stock, text)
                self.assertEqual([], problems(replace(one, name=f"the line off, {surface}")))
        page = read(shown["page"])
        self.assertIn("Of them, 1 is the AI's estimate and 1 is not priced.", page)
        self.assertIn("The page shows them: 1 the AI's estimate and 1 not priced.", read(shown["card"]))
        self.assertIn("The page shows them: 1 the AI's estimate and 1 not priced.", read(shown["letter"]))
        listed = [block.text for block in shown["page"].blocks if block.details and block.kind == "cell"]
        self.assertIn("proposal", listed, "the word of the finding's own proposal (change) is a typed fact, listed in the Details where it was")
        self.assertNotIn(proposals.KEY, listed, "and the ways, which the page says in its own words, are not")
        saves = cells(shown["page"])
        self.assertEqual(saves[saves.index("Saves a month") + 3::3][:2], ["about $161 to $192, the AI's estimate", "Not priced"], "an estimate says so in its cell")
        self.assertIn("A saving that is the AI's estimate rests on a share of the cost that the AI assumed, and Meternaut did not check that share.", page)
        self.assertNotIn("capacity units", page, "the words of the kind are those of its own property")
        table = cells(shown["page"])
        start = table.index("Saved, a month") + 1
        for name, now, after, saved in (table[start + n:start + n + 4] for n in (0, 4)):
            self.assertEqual((now, after, saved), ("$202", "$101", "$101"), name)
            self.assertEqual(int(now[1:]) - int(after[1:]), int(saved[1:]), "what is paid now less what is paid after is what is saved, as it is printed")
        self.assertEqual([name for name, *_ in (table[start + n:start + n + 4] for n in (0, 4))], ["Charges it would shrink", "The whole bastion host"])

    def test_with_the_line_on_for_the_time_of_the_test_the_request_is_the_change_and_one_write_is_made_with_the_approvers_own_token(self):
        with mock.patch.object(gates, "REAL_CHANGES_ALLOWED", True):
            world, lead, case = world_of(host(), self.case)
            plan = world.approvals.plan_for(case, lead, (OID,))
            self.assertEqual(plan.family, "change-setting")
            said = words.words_of(plan.family, plan, HOST, "bastion-one", REAL_GROUP)
            asked = surfaces(world, plan)
            for surface, one in asked.items():
                with self.subTest(surface):
                    text = read(one)
                    self.assertIn("Scale down the bastion host bastion-one: scale units from 4 to 2", " ".join(b.text for b in one.blocks))
                    self.assertIn(f"You are asked whether to let Meternaut scale down the bastion host bastion-one in resource group {REAL_GROUP} by lowering scale units from 4 to 2.", text)
                    self.assertIn("At the rate of the last 7 days this bastion host costs about $202 a month for what the change would shrink.", text, "the figure says what it rests on, as the request that asked did")
                    self.assertIn("The page shows them: 1 the AI's estimate and 1 not priced." if surface != "page" else "Of them, 1 is the AI's estimate and 1 is not priced.", text)
                    self.assertIn(brief_mod.plain_sentences(said.undo if surface == "page" else said.short_undo, 200 if surface != "page" else 1000), text)
                    for stock in OLD_STOCK + ("Meternaut cannot make this change itself",):
                        self.assertNotIn(stock, text)
                    self.assertEqual([], problems(replace(one, name=f"the line on, {surface}")))
            terms = [(block.text, block.kind) for block in asked["page"].blocks if block.kind in ("term", "value") and not block.details]
            self.assertEqual([text for text, kind in terms if kind == "term"], ["What changes", "Who does it", "Checked again", "What could go wrong", "Undo"])
            self.assertEqual([text for text, kind in terms if kind == "value"][0], said.change)
            self.assertIn(said.rechecked, [text for text, kind in terms])
            self.assertIn(said.risk, [text for text, kind in terms])
            self.assertIn(said.undo, [text for text, kind in terms])
            read_before = json.loads(json.dumps(world.arm.get(host()["id"])))
            world.approve(plan)
            done = execute(world.services(plan, TOKEN), world.store.action_get(plan.plan_id), approved_digest=plan.digest)
            self.assertEqual((done.kind, done.action.state), ("ran", "done"), done.action.result)
            (key, query, body), = world.arm.puts
            self.assertEqual((key, query), (host()["id"].lower(), f"api-version={API}"))
            expected = json.loads(json.dumps(read_before))
            for name in ("id", "name", "type", "systemData", "etag"):
                expected.pop(name)
            expected["properties"].pop("provisioningState")
            expected["properties"]["scaleUnits"] = 2
            expected["properties"]["ipConfigurations"][0].pop("etag")
            expected["properties"]["ipConfigurations"][0]["properties"].pop("provisioningState")
            self.assertEqual(body, expected, "the resource as it was read, with the one number lowered and nothing else touched")
            self.assertEqual(world.arm.writes_of("PUT"), [f"https://management.azure.com{host()['id']}?api-version={API}"], "one write, to the exact address of the resource and the version that was chosen")
            self.assertEqual({method for method, _ in world.arm.writes()}, {"PUT"})
            puts = [headers for (method, _), headers in zip(world.arm.calls, world.arm.headers) if method == "PUT"]
            self.assertEqual([(h.get("If-Match"), h["Authorization"]) for h in puts], [(read_before["etag"], f"Bearer {TOKEN}")], "the etag of the reading, and the token of the person who approved")
            methods = [method for method, _ in world.arm.calls]
            self.assertIn("GET", methods[len(methods) - 1 - methods[::-1].index("PUT") + 1:], "the resource is read again after the write")
            self.assertEqual(world.arm.get(host()["id"])["properties"]["scaleUnits"], 2)
            finished = world.store.plan_get(plan.plan_id)
            outcome = tfs.shown(world, finished, done.action).outcome
            self.assertEqual((outcome.title, outcome.result), ("Done", "Done"))
            self.assertTrue(any("Azure shows the bastion host with scale units at 2, and its last operation worked." in line for line in outcome.lines), outcome.lines)

    def test_the_confirm_step_is_said_on_the_page_and_on_the_card_with_the_nouns_and_the_numbers_of_the_request(self):
        with mock.patch.object(gates, "REAL_CHANGES_ALLOWED", True):
            world, lead, case = world_of(host(), self.case)
            plan = world.approvals.plan_for(case, lead, (OID,))
            console = console_of(world, plan, case)
            form = console.get(f"/ok/{plan.plan_id}").form(f"/ok/{plan.plan_id}", has_button="Approve")
            reply = console.submit(form, "Approve", confirm=False, note="Go on")
            self.assertEqual(reply.status, 200, "approving asks once more before anything is signed in")
            self.assertTrue(reply.headings(1)[0].startswith("Confirm: Scale down the bastion host bastion-one: scale units from 4 to 2"), reply.headings(1))
            self.assertIn("This changes a real resource. Nothing is changed until you confirm here.", reply.main.text())
            self.assertIn("Meternaut does not know what a lower number takes away from what uses the bastion host.", reply.main.find("div", class_="notice warning").text())
            self.assertEqual((console.delegate.begins, world.store.decisions_of_plan(plan.plan_id)), ([], []), "nothing is recorded and no sign-in starts at the first press")
            card = tfs.card_of(tfs.shown(world, plan))
            texts = {item["id"]: item["text"] for item in tfs.by_id(card).values() if isinstance(item, dict) and "text" in item}
            self.assertEqual(texts["sure-text"], f"This changes a real resource: the bastion host bastion-one in resource group {REAL_GROUP}. Nothing is changed until you press Yes.")

    def test_a_change_that_azure_also_changed_something_else_for_is_done_with_a_difference_on_the_page_the_card_and_the_letter(self):
        with mock.patch.object(gates, "REAL_CHANGES_ALLOWED", True):
            world, lead, case = world_of(host(), self.case)
            world.arm.also = {"retentionDays": 99}
            plan = world.approvals.plan_for(case, lead, (OID,))
            world.approve(plan)
            done = execute(world.services(plan, TOKEN), world.store.action_get(plan.plan_id), approved_digest=plan.digest)
            self.assertEqual((done.kind, done.action.state), ("ran", "done"))
            kept = world.store.plan_get(plan.plan_id)
            b = tfs.shown(world, kept, done.action)
            self.assertEqual((b.outcome.title, b.outcome.result), ("Done, with a difference", "Done, with a difference"))
            said = "Azure shows the bastion host with scale units at 2, and its last operation worked. Azure also changed: properties.retentionDays."
            self.assertIn(said, b.outcome.lines)
            self.assertEqual(sum("Azure also changed" in line for line in b.outcome.lines), 1, "said once")
            self.assertNotIn("scale units at 2.", b.outcome.lines, "what Azure shows is said once, in the sentence of the result, and not again as a fragment")
            page = console_of(world, kept, case).get(f"/ok/{plan.plan_id}").text
            self.assertIn("Done, with a difference", page)
            self.assertIn("Azure also changed: properties.retentionDays.", page)
            letter = letters.done_letter(kept, done.action, case, tfs.PERSON, tfs.BASE, tfs.NOW, tfs.CONTACTS)
            self.assertEqual(letter.subject, "[Meternaut] " + letters.DIFFERENT_SUBJECT)
            self.assertIn(said, letter.text)
            self.assertNotIn("scale units at 2.", letter.text.splitlines(), "and not as a line of its own in the letter")
            self.assertEqual(sum("Azure also changed" in line for line in letter.text.splitlines()), 1)

    def test_every_place_that_shows_the_title_shows_the_same_one_for_the_change_the_advice_with_a_setting_and_the_advice_with_none(self):
        title = "Scale down the bastion host bastion-one: scale units from 4 to 2"
        bare = reduction(others=())
        del bare["set"]
        none, _ = investigated(host(), change=bare)
        self.assertEqual(none.facts.get(proposals.KEY, {}).get("set"), None, "the AI named no setting")
        kinds = {"the change that Meternaut makes": (self.case, True), "advice with a setting": (self.case, False), "advice with no setting": (none, False)}
        for kind, (case, on) in kinds.items():
            with self.subTest(kind), mock.patch.object(gates, "REAL_CHANGES_ALLOWED", on):
                world, lead, mine = world_of(host(), case)
                plan = world.approvals.plan_for(mine, lead, (OID,))
                self.assertEqual(plan.family, "change-setting" if on else "advise")
                for surface, one in surfaces(world, plan).items():
                    heads = [block.text for block in one.blocks if block.text.startswith("Scale down the") and block.kind in ("heading", "label") and not block.details]
                    self.assertEqual(heads, [title], f"{surface}: one title, and the place is on the line under it")
                sent = {"escalation letter": letters.escalation_letter(plan, mine, tfs.PERSON, tfs.BASE, tfs.NOW, tfs.CONTACTS, source="owners"),
                        "escalation digest": letters.escalation_digest_letter(tfs.PERSON, tfs.BASE, tfs.NOW, [(plan, mine, "owners")], tfs.CONTACTS),
                        "weekly letter": letters.escalation_weekly_letter(tfs.PERSON, tfs.BASE, tfs.NOW, [(plan, mine)], tfs.CONTACTS),
                        "digest": letters.digest_letter(tfs.PERSON, tfs.BASE, tfs.NOW, [(plan, mine)], tfs.CONTACTS)}
                for name, letter in sent.items():
                    self.assertIn(title, letter.text, name)
                    self.assertNotRegex(letter.text, r"bastion-one in (resource )?group \S+: scale units", name)
                rows = [link.text() for link in console_of(world, plan, mine).get("/").main.find_all("a") if link.attrs.get("href") == f"/ok/{plan.plan_id}"]
                self.assertEqual([row.removeprefix("Review and decide: ").removeprefix("Review: ") for row in rows], [title], "the Decisions page")

    def test_the_request_that_asked_is_taken_back_once_with_its_words_and_the_new_request_is_named_on_its_page_and_in_the_history(self):
        world, lead, case = world_of(host(), self.case)
        old = world.approvals.plan_for(case, lead, (OID,))
        self.assertEqual((old.family, old.preconditions[proposals.CANNOT_KEY]), ("advise", "switch-off"), "the line is as it is: the request asks")
        lines = []
        history = mock.Mock(emit=lambda kind, **fields: lines.append((kind, fields)))
        extras = mock.Mock(approvals=world.approvals, approvers=lambda: (OID,))
        with mock.patch.object(gates, "REAL_CHANGES_ALLOWED", True):
            said = upkeep.upgrade(extras, history)
            later = upkeep.upgrade(extras, history)
        self.assertEqual(len(said), 1)
        self.assertIn("taken back, because Meternaut can make the change itself now", said[0])
        self.assertEqual((later, len(lines)), ([], 1), "said once: the next Watch finds nothing to say")
        taken = world.store.plan_get(old.plan_id)
        (new,) = [plan for plan in world.store.plans_open() if plan.state == "open"]
        self.assertEqual((taken.state, taken.preconditions["takenBack"], new.family), ("expired", "upgraded", "change-setting"))
        case = world.store.case_get(old.case_id)
        console = console_of(world, new, case)
        console.store.plan_put(taken)
        page = console.get(f"/ok/{old.plan_id}")
        text = page.main.text()
        self.assertIn(brief_mod.TAKEN_BACK["upgraded"], text)
        self.assertIn("Nothing was changed in Azure.", text)
        (pointer,) = [a for a in page.main.find_all("a") if a.attrs.get("href") == f"/ok/{new.plan_id}"]
        self.assertEqual(pointer.text(), "Scale down the bastion host bastion-one: scale units from 4 to 2", "the same title as the request that it replaces")
        feed = console.get("/history").main.text()
        self.assertIn("Scale down the bastion host bastion-one: scale units from 4 to 2", feed)
        self.assertIn(brief_mod.TAKEN_BACK["upgraded"], feed, "a request that a change took the place of is a line of its own and says why")
        self.assertNotIn("request to look at a finding", feed)

    def test_a_change_that_does_not_hold_any_more_is_taken_back_as_changed_and_the_page_and_the_history_say_so_and_name_the_request_that_asks_instead(self):
        with mock.patch.object(gates, "REAL_CHANGES_ALLOWED", True):
            world, lead, case = world_of(host(), self.case)
            old = world.approvals.plan_for(case, lead, (OID,))
            self.assertEqual(old.family, "change-setting")
            world.arm.get(host()["id"])["properties"]["scaleUnits"] = 3
            (taken, new, _), = world.approvals.upgrade((OID,))
        self.assertEqual((taken.plan_id, taken.preconditions["takenBack"], new.family, new.preconditions[proposals.CANNOT_KEY]), (old.plan_id, "changed", "advise", "mismatch"))
        console = console_of(world, new, world.store.case_get(old.case_id))
        console.store.plan_put(world.store.plan_get(old.plan_id))
        page = console.get(f"/ok/{old.plan_id}").main
        self.assertIn(brief_mod.TAKEN_BACK["changed"], page.text())
        (pointer,) = [a for a in page.find_all("a") if a.attrs.get("href") == f"/ok/{new.plan_id}"]
        self.assertEqual(pointer.text(), "Scale down the bastion host bastion-one: scale units from 4 to 2", "the request that asks instead has the title of the one that was taken back")
        feed = console.get("/history").main.text()
        self.assertIn(brief_mod.TAKEN_BACK["changed"], feed)
        self.assertNotIn("request to look at a finding", feed, "a change that was taken back is a line of its own")
        asks = read(Rendered("page", "page", blocks_of_html(console.get(f"/ok/{new.plan_id}").text)))
        self.assertIn(f"Meternaut cannot make this change itself. {proposals.CANNOT['mismatch']} Your answer is recorded with your name.", asks)

    def test_a_setting_that_is_no_count_is_dropped_with_its_reason_in_the_notes_and_the_request_still_asks_and_says_what_is_true(self):
        change = reduction({"handle": "r1", "property": "retentionDays", "from": 30, "to": 7}, on="retentionDays", start=30, to=7, others=())
        case, notes = investigated(host(), change=change)
        self.assertEqual([note for note in notes if "dropped" in note], ["finding 1: code dropped 1 of 1 setting (a property that is not a count or a size: 1)"])
        self.assertNotIn("set", case.facts.get(proposals.KEY, {}), "nothing is kept of the setting")
        world, lead, case = world_of(host(), case)
        plan = world.approvals.plan_for(case, lead, (OID,))
        self.assertEqual(plan.family, "advise", "the finding is still asked about")
        for surface, one in surfaces(world, plan).items():
            with self.subTest(surface):
                text = read(one)
                self.assertIn("Scale down the bastion host bastion-one: retention days from 30 to 7", " ".join(block.text for block in one.blocks))
                self.assertIn("Meternaut only lowers a count of units, and retention days is not one, so it has nothing to change here. Your answer is recorded with your name.", text)
                self.assertNotIn("did not name a setting", text, "the AI did name one: code dropped it")
                self.assertEqual([], problems(replace(one, name=f"a setting that is no count, {surface}")))

    def test_a_number_at_the_root_of_a_resource_of_another_kind_is_lowered_there_and_the_words_follow_the_kind(self):
        shown = pool()
        change = reduction({"handle": "r1", "property": "sku.capacity", "from": 3, "to": 2}, on="sku.capacity", start=3, to=2, others=())
        case, notes = investigated(shown, kind=POOL, name="pool-one", change=change)
        self.assertEqual(case.facts[proposals.KEY], {"set": [{"path": "sku.capacity", "from": 3, "to": 2}]}, notes)
        with mock.patch.object(gates, "REAL_CHANGES_ALLOWED", True):
            world, lead, case = world_of(shown, case, POOL)
            plan = world.approvals.plan_for(case, lead, (OID,))
            self.assertEqual(plan.family, "change-setting")
            self.assertEqual(plan.title, f"Scale down the worker pool pool-one in resource group {REAL_GROUP}: sku capacity from 3 to 2")
            for surface, one in surfaces(world, plan).items():
                with self.subTest(surface):
                    self.assertIn("You are asked whether to let Meternaut scale down the worker pool pool-one in resource group", read(one))
                    self.assertIn("by lowering sku capacity from 3 to 2.", read(one))
            read_before = json.loads(json.dumps(world.arm.get(shown["id"])))
            world.approve(plan)
            done = execute(world.services(plan, TOKEN), world.store.action_get(plan.plan_id), approved_digest=plan.digest)
            self.assertEqual((done.kind, done.action.state), ("ran", "done"), done.action.result)
            (key, query, body), = world.arm.puts
            self.assertEqual((key, query), (shown["id"].lower(), f"api-version={API}"))
            self.assertEqual(body["sku"], {"name": "S2", "capacity": 2}, "the number is lowered where it is, at the root")
            self.assertEqual(body["properties"], {key: value for key, value in read_before["properties"].items() if key != "provisioningState"}, "and nothing under properties moves")
            self.assertEqual(world.arm.get(shown["id"])["sku"]["capacity"], 2)
