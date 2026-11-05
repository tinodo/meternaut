import ast
import dataclasses
import datetime as dt
import random
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

import support  # noqa: F401  (puts the app on the path)
from cases import letters
from cases.letters import AI_LINE, DARK, LIGHT, MAX_LISTED, Letter
from cases.models import ActionRecord, CaseRecord, PlanRecord, RunRecord
from cases.people import Person

NOW = dt.datetime(2026, 11, 5, 10, 18, 0, tzinfo=dt.timezone.utc)
BASE = "https://meternaut.example"
OID = "11111111-1111-1111-1111-111111111111"
PERSON = Person(OID, "Maya", ("approver", "owner"), "maya@example.com")
OUTSIDER = Person("22222222-2222-2222-2222-222222222222", "Noor", ("ops",), "noor@example.com")
NAME = "disk-zq7-name"
GROUP = "rg-zq7-group"
HOSTILE = "\"><script>alert(1)</script><img src=x onerror=alert(2)> & 'quote' \u202e\x00\nnew line"
HOSTILE_ONE_LINE = "\"><script>alert(1)</script><img src=x onerror=alert(2)> & 'quote' new line"
ALLOWED_TAGS = {"html", "head", "meta", "title", "style", "body", "table", "tr", "td", "th", "h1", "h2", "h3", "p", "ul", "li", "a"}
LINK_PATHS = re.compile(r"^https://meternaut\.example/(ok/[A-Za-z0-9_-]{1,64}|history|me/decisions|me/settings)$")


def make_plan(**changes) -> PlanRecord:
    values = dict(
        plan_id="p1a2b3c4d5", case_id="c1", family="delete-disk", resource_id=f"/subscriptions/s/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/{NAME}",
        resource_name=NAME, resource_group=GROUP, subscription_id="s", code="7F3K92QD", title=f"Delete an unattached managed disk in resource group {GROUP}",
        what_changes=f"The writer deletes the disk named {NAME}. It changes nothing else.", saving_usd_month=41.2, waiting_costs_usd_day=1.37,
        could_go_wrong="If something still uses the disk, that use stops.", undo="A deleted disk cannot be restored.",
        evidence_level="Observed now: the disk is unattached. Not measured yet: the saving.", approvers=(OID,), created_at="2026-11-05T09:00:00Z",
        expires_at="2026-11-08T09:30:00Z")
    values.update(changes)
    return PlanRecord(**values)


def make_case(**changes) -> CaseRecord:
    values = dict(case_id="c1", resource_id="r1", resource_name=NAME, resource_type="microsoft.compute/disks", resource_group=GROUP, subscription_id="s",
                  detector="orphan-managed-disk", run_id="run1", status="awaiting_ok", saving_usd_month=41.2, cost_usd_30d=41.2,
                  models={"detective": "model-d", "skeptic": "model-s"})
    values.update(changes)
    return CaseRecord(**values)


def make_action(**changes) -> ActionRecord:
    values = dict(plan_id="p1a2b3c4d5", case_id="c1", family="delete-disk", resource_id="r1", state="done", queued_at="2026-11-05T09:00:00Z",
                  finished_at="2026-11-05T09:05:00Z", result="Deleted the disk.", verification={"gone": True, "costAfterUsd": None, "note": "Azure no longer lists it."})
    values.update(changes)
    return ActionRecord(**values)


def make_run(**changes) -> RunRecord:
    values = dict(run_id="a", trigger="timer", started_at="2026-11-02T06:00:00Z", leads=5, cases=3, proposed=1, needs_human=1, dropped=1, errors=0)
    values.update(changes)
    return RunRecord(**values)


def everything(person: Person = PERSON, **overrides) -> dict[str, Letter]:
    plan, case = overrides.get("plan", make_plan()), overrides.get("case", make_case())
    return {
        "first contact": letters.first_contact_letter(person, BASE, NOW),
        "approval": letters.approval_letter(plan, case, person, BASE, NOW),
        "digest": letters.digest_letter(person, BASE, NOW, overrides.get("runs", [make_run()]),
                                        overrides.get("cases", [make_case(status="proposed"), make_case(case_id="c2", status="needs_human", guards=("locked",))]),
                                        overrides.get("plans", [plan])),
        "done": letters.done_letter(plan, overrides.get("action", make_action()), case, person, BASE, NOW),
    }


class Parsed(HTMLParser):
    """The tags, the attributes and the visible text of a letter's HTML."""

    def __init__(self, source: str) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attributes: list[tuple[str, str, str | None]] = []
        self.text: list[str] = []
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes += [(tag, name, value) for name, value in attrs]

    def handle_data(self, data):
        self.text.append(data)

    def visible(self) -> str:
        return " ".join(self.text)


def luminance(color: str) -> float:
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def hrefs(letter: Letter) -> list[str]:
    return re.findall(r'href="([^"]*)"', letter.html)


class WhatEveryLetterHas(unittest.TestCase):
    def test_the_subject_starts_with_the_name_says_the_point_and_holds_no_resource_name_and_no_amount(self):
        plan, case = make_plan(), make_case()
        for kind, letter in everything(plan=plan, case=case).items():
            with self.subTest(letter=kind):
                self.assertTrue(letter.subject.startswith("[Meternaut] "), letter.subject)
                self.assertNotIn("\n", letter.subject)
                self.assertLessEqual(len(letter.subject), 90)
                for word in (NAME, GROUP, plan.code, "USD", "$", "?", "disk"):
                    self.assertNotIn(word, letter.subject)

    def test_the_subjects_say_the_point(self):
        found = {kind: letter.subject for kind, letter in everything().items()}
        self.assertEqual(found["first contact"], "[Meternaut] An AI assistant for Azure costs will write to you")
        self.assertEqual(found["approval"], "[Meternaut] A change to Azure waits for your OK")
        self.assertEqual(found["digest"], "[Meternaut] Summary: 1 change waits for your OK")
        self.assertEqual(found["done"], "[Meternaut] A change to Azure has run")

    def test_every_letter_says_that_an_ai_wrote_it_which_roles_took_part_and_that_a_person_approves_every_change(self):
        for kind, letter in everything().items():
            with self.subTest(letter=kind):
                for text in (letter.text, Parsed(letter.html).visible()):
                    self.assertIn(AI_LINE, text)
                    self.assertIn("The Detective judges", text)
                    self.assertIn("The Skeptic argues against", text)
                    self.assertIn("computed by code, not by a model", text)
                    self.assertIn("A person approves every change, on a page, after signing in.", text)
                self.assertIn("Replies to this letter are not read, and nothing is approved by e-mail.", letter.text)
                self.assertIn("To reach a person, ask whoever put you on my list of people.", letter.text)

    def test_the_wording_has_no_question_no_urgency_no_countdown_and_never_says_that_something_was_saved(self):
        for kind, letter in everything().items():
            with self.subTest(letter=kind):
                lower = letter.text.lower()
                self.assertNotIn("?", letter.text)
                self.assertNotIn("saved", lower)
                self.assertNotIn("\u2013", letter.text)
                self.assertNotIn("\u2014", letter.text)
                self.assertTrue(letter.text.isascii(), "plain letters are plain ASCII")
                self.assertIsNone(re.search(r"\b(urgent|urgently|immediately|hurry|asap|last chance|act now|deadline|running out)\b", lower))
                self.assertIsNone(re.search(r"\b(in|within|after|only) \d+ (seconds?|minutes?|hours?|days?)( left)?\b", lower))

    def test_the_html_is_self_contained_and_holds_only_what_a_letter_needs(self):
        for kind, letter in everything().items():
            with self.subTest(letter=kind):
                page = letter.html
                self.assertTrue(page.startswith("<!DOCTYPE html>"))
                self.assertIn('<html lang="en">', page)
                self.assertIn('<meta charset="utf-8">', page)
                self.assertIn('<meta name="color-scheme" content="light dark">', page)
                self.assertIn("<title>" + letter.subject + "</title>", page)
                self.assertIn("prefers-color-scheme: dark", page)
                for word in ("<script", "<img", "<link", "<iframe", "<object", "<embed", "<form", "<input", "<button", "<svg", "<video", "<audio", "<base",
                             "@import", "url(", " src=", "javascript:", "srcset"):
                    self.assertNotIn(word, page.lower())
                parsed = Parsed(page)
                self.assertLessEqual(set(parsed.tags), ALLOWED_TAGS)
                self.assertEqual(parsed.tags.count("h1"), 1)
                self.assertGreaterEqual(parsed.tags.count("h2"), 3)
                self.assertFalse([a for a in parsed.attributes if a[1].startswith("on")])
                for tag, name, value in parsed.attributes:
                    if tag == "a":
                        self.assertIn(name, {"class", "href", "style"})

    def test_every_address_in_a_letter_is_a_link_of_the_console_with_a_fixed_path_and_at_most_an_opaque_id(self):
        for kind, letter in everything().items():
            with self.subTest(letter=kind):
                self.assertTrue(hrefs(letter))
                for address in hrefs(letter) + re.findall(r"https?://\S+", letter.text):
                    self.assertRegex(address, LINK_PATHS)
                self.assertEqual(sorted(re.findall(r"https?://[^\s\"<>]+", letter.html)), sorted(hrefs(letter)), "an address appears only as a link")
                for name in (NAME, GROUP, "7F3K92QD", "41", "USD"):
                    for address in hrefs(letter):
                        self.assertNotIn(name, address)

    def test_the_output_is_the_same_every_time_and_does_not_depend_on_the_order_of_the_input(self):
        plans = [make_plan(plan_id=f"p{n}", code=f"CODE000{n}", expires_at=f"2026-11-0{5 + n}T09:00:00Z") for n in range(1, 4)]
        cases = [make_case(case_id=f"c{n}", resource_name=f"res-{n}", status="proposed", saving_usd_month=float(n)) for n in range(1, 5)]
        runs = [make_run(run_id=f"r{n}", started_at=f"2026-11-0{n}T06:00:00Z") for n in range(1, 4)]
        first = letters.digest_letter(PERSON, BASE, NOW, runs, cases, plans)
        for attempt in range(5):
            order = lambda items: random.Random(attempt).sample(items, len(items))  # noqa: E731
            self.assertEqual(letters.digest_letter(PERSON, BASE, NOW, order(runs), order(cases), order(plans)), first)
        self.assertEqual(everything(), everything())

    def test_a_time_without_a_time_zone_is_read_as_utc_and_a_zone_is_converted(self):
        naive = NOW.replace(tzinfo=None)
        zoned = NOW.astimezone(dt.timezone(dt.timedelta(hours=-5)))
        self.assertEqual(letters.first_contact_letter(PERSON, BASE, naive), letters.first_contact_letter(PERSON, BASE, NOW))
        self.assertEqual(letters.first_contact_letter(PERSON, BASE, zoned), letters.first_contact_letter(PERSON, BASE, NOW))
        self.assertIn("Written on Thursday 5 November 2026, 10:18 UTC.", letters.first_contact_letter(PERSON, BASE, zoned).text)

    def test_a_letter_cannot_be_changed_after_it_is_made(self):
        letter = letters.first_contact_letter(PERSON, BASE, NOW)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            letter.subject = "[Meternaut] other"  # type: ignore[misc]

    def test_the_html_and_the_text_hold_the_same_words(self):
        for kind, letter in everything().items():
            with self.subTest(letter=kind):
                visible = " ".join(Parsed(letter.html).visible().split())
                checked = 0
                for line in letter.text.splitlines():
                    if line and not set(line) <= set("=-~") and not line.startswith("- ") and "https://" not in line and ": " not in line:
                        self.assertIn(line, visible)
                        checked += 1
                self.assertGreater(checked, 5)


class TheContrast(unittest.TestCase):
    def test_every_text_colour_meets_wcag_aa_on_the_colour_it_sits_on_in_the_light_and_in_the_dark_palette(self):
        for name, palette in (("light", LIGHT), ("dark", DARK)):
            for text, ground in (("text", "background"), ("muted", "background"), ("link", "background"), ("text", "head")):
                with self.subTest(palette=name, text=text, ground=ground):
                    self.assertGreaterEqual(contrast(palette[text], palette[ground]), 4.5)

    def test_the_inline_colours_are_the_light_palette_and_the_dark_one_is_in_the_media_query(self):
        page = letters.first_contact_letter(PERSON, BASE, NOW).html
        style, body = page.split("</style>")[0], page.split("</style>")[1]
        used = set(re.findall(r"(?<![-a-z])(?:color|background-color):(#[0-9a-f]{6})", body))
        self.assertTrue(used)
        self.assertLessEqual(used, set(LIGHT.values()))
        for color in (DARK["background"], DARK["text"], DARK["muted"], DARK["link"], DARK["head"], DARK["rule"]):
            self.assertIn(color, style)


class FirstContact(unittest.TestCase):
    def setUp(self):
        self.letter = letters.first_contact_letter(PERSON, BASE, NOW)

    def test_it_says_who_writes_why_this_person_what_happens_today_and_what_does_not(self):
        text = self.letter.text
        for sentence in ("I am Meternaut, an AI assistant", "with the roles: approver, owner", "A person who is not on the list receives nothing from me.",
                         "I find leads", "Two AI roles judge each lead. The Detective proposes what to do. The Skeptic argues against it.",
                         "No model writes the plan.", "The writer is the only part of Meternaut that can change Azure.",
                         "removes only the resource that an approved plan names", "I make no change without a person's OK on a page.",
                         "I approve nothing by e-mail.", "I do not ask for sign-in details or a code by e-mail.", "My letters have no images.",
                         "I do not keep the text of a letter."):
            self.assertIn(sentence, text)

    def test_it_has_one_link_to_the_settings_page_and_says_where_it_goes(self):
        self.assertEqual(hrefs(self.letter), [f"{BASE}/me/settings"])
        self.assertIn("Open your settings page", self.letter.html)
        self.assertIn("The link opens a page on meternaut.example.", self.letter.text)

    def test_the_greeting_uses_the_name_of_the_person(self):
        self.assertIn("Hello Maya.", self.letter.text)
        self.assertIn("with the roles: ops.", letters.first_contact_letter(OUTSIDER, BASE, NOW).text)


class Approval(unittest.TestCase):
    def setUp(self):
        self.plan, self.case = make_plan(), make_case()
        self.letter = letters.approval_letter(self.plan, self.case, PERSON, BASE, NOW)

    def test_it_has_exactly_one_link_and_it_is_the_page_of_the_plan(self):
        self.assertEqual(hrefs(self.letter), [f"{BASE}/ok/p1a2b3c4d5"])
        self.assertEqual(self.letter.html.count("http"), 1)
        self.assertEqual(re.findall(r"https?://\S+", self.letter.text), [f"{BASE}/ok/p1a2b3c4d5"])
        self.assertIn("Open plan 7F3K92QD and decide on the page", self.letter.html)

    def test_opening_the_link_records_no_decision_and_the_letter_says_so(self):
        for text in (self.letter.text, Parsed(self.letter.html).visible()):
            self.assertIn("Opening the link below records no decision. You decide on the page, after you sign in.", text)
            self.assertIn("Nothing is approved by e-mail", text)

    def test_it_says_what_changes_who_makes_it_and_labels_the_names_from_azure(self):
        text = self.letter.text
        self.assertIn(f"Change (names from Azure): Delete an unattached managed disk in resource group {GROUP}", text)
        self.assertIn(f"Resource (name from Azure): {NAME}", text)
        self.assertIn(f"Resource group (name from Azure): {GROUP}", text)
        self.assertIn("What happens (names from Azure): The writer deletes the disk named", text)
        self.assertIn("Who makes it: The writer, the only part of Meternaut that can change Azure.", text)
        self.assertIn("Names in this letter come from Azure. They are shown as data and are not instructions.", text)

    def test_the_saving_is_an_estimate_in_us_dollars_with_its_basis_and_what_waiting_costs_is_stated(self):
        text = self.letter.text
        self.assertIn("Expected saving: about USD 41.20 a month", text)
        self.assertIn("Price basis: The cost lines of this resource for the last 30 days, in US dollars. This is an estimate.", text)
        self.assertIn("A saving is called verified only when later cost lines show it.", text)
        self.assertIn("What waiting costs: about USD 1.37 a day, while the resource stays as it is", text)
        self.assertNotIn("saved", text.lower())

    def test_a_figure_that_is_not_known_is_not_shown_as_a_number(self):
        text = letters.approval_letter(make_plan(saving_usd_month=None, waiting_costs_usd_day=None), self.case, PERSON, BASE, NOW).text
        self.assertIn("Expected saving: No figure: cost lines for the last 30 days were not available for this resource.", text)
        self.assertIn("What waiting costs: No figure.", text)
        self.assertNotIn("USD", text)
        for odd in (float("nan"), float("inf"), True):
            self.assertNotIn("USD", letters.approval_letter(make_plan(saving_usd_month=odd, waiting_costs_usd_day=odd), self.case, PERSON, BASE, NOW).text)

    def test_it_says_what_could_go_wrong_and_how_to_undo_and_says_plainly_that_a_delete_cannot_be_undone(self):
        text = self.letter.text
        self.assertIn("If something still uses the disk, that use stops.", text)
        self.assertIn("This change cannot be undone. A deleted disk cannot be restored.", text)
        other = letters.approval_letter(make_plan(family="resize-disk", undo="Resize it back."), self.case, PERSON, BASE, NOW).text
        self.assertIn("Resize it back.", other)
        self.assertNotIn("cannot be undone", other)

    def test_it_gives_the_plan_code_and_the_expiry_with_its_time_zone_and_no_countdown(self):
        self.assertIn("Plan code: 7F3K92QD", self.letter.text)
        self.assertIn("Expires: Sunday 8 November 2026, 09:30 UTC", self.letter.text)
        self.assertNotRegex(self.letter.text, r"\b\d+ (hours?|days?) (left|remaining)\b")

    def test_the_models_that_took_part_are_named_when_the_case_says_which(self):
        self.assertIn("For this case the Detective ran on model-d and the Skeptic ran on model-s.", self.letter.text)
        bare = letters.approval_letter(self.plan, make_case(models={}), PERSON, BASE, NOW).text
        self.assertNotIn("For this case", bare)
        half = letters.approval_letter(self.plan, make_case(models={"detective": "model-d", "skeptic": None}), PERSON, BASE, NOW).text
        self.assertIn("For this case the Detective ran on model-d.", half)

    def test_it_says_why_the_person_got_it(self):
        self.assertIn("Why you got this: you are listed as an approver of this plan.", self.letter.text)
        other = letters.approval_letter(self.plan, self.case, OUTSIDER, BASE, NOW).text
        self.assertIn("Why you got this: you are on the list of people who receive letters from Meternaut.", other)
        upper = letters.approval_letter(make_plan(approvers=(OID.upper(),)), self.case, PERSON, BASE, NOW).text
        self.assertIn("you are listed as an approver of this plan", upper)

    def test_a_plan_that_is_no_longer_open_is_not_presented_as_waiting(self):
        for state, words in (("approved", "approved and waiting to start"), ("consumed", "closed because it ran"), ("declined", "declined"),
                             ("expired", "expired"), ("withdrawn", "withdrawn"), ("failed", "closed because the change failed")):
            with self.subTest(state=state):
                text = letters.approval_letter(make_plan(state=state), self.case, PERSON, BASE, NOW).text
                self.assertIn(f"State: This request is {words}. Nothing can be approved from it.", text)
                self.assertNotIn("Nothing has changed yet.", text)
                self.assertNotIn("Expires:", text)

    def test_an_open_plan_past_its_time_says_so(self):
        late = NOW + dt.timedelta(days=4)
        text = letters.approval_letter(self.plan, self.case, PERSON, BASE, late).text
        self.assertIn("Expired: Sunday 8 November 2026, 09:30 UTC. Nothing can be approved now.", text)
        self.assertNotIn("Nothing has changed yet.", text)
        self.assertEqual(len(re.findall(r"https?://\S+", text)), 1)

    def test_a_time_that_cannot_be_read_is_shown_as_data(self):
        text = letters.approval_letter(make_plan(expires_at="soon"), self.case, PERSON, BASE, NOW).text
        self.assertIn("Expires: soon", text)

    def test_the_plan_id_in_the_link_must_be_an_opaque_id(self):
        for bad in ("", "a b", "a/b", "a?x=1", "x" * 65, "../x", 'a"b', "caf\u00e9", "abc\n", NAME + "/" + GROUP):
            with self.subTest(plan_id=bad):
                with self.assertRaises(ValueError):
                    letters.approval_letter(make_plan(plan_id=bad), self.case, PERSON, BASE, NOW)
        for good in ("abc", "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6", "plan_1-2", "x" * 64):
            self.assertIn(f"/ok/{good}", letters.approval_letter(make_plan(plan_id=good), self.case, PERSON, BASE, NOW).html)

    def test_long_texts_are_cut(self):
        text = letters.approval_letter(make_plan(what_changes="w" * 5000, title="t" * 5000), self.case, PERSON, BASE, NOW).text
        self.assertIn("w" * 697 + "...", text)
        self.assertNotIn("w" * 698, text)
        self.assertIn("t" * 237 + "...", text)


class Digest(unittest.TestCase):
    def plans(self):
        return [make_plan(plan_id="p2", code="CODE0002", title="Second change", expires_at="2026-11-09T09:00:00Z"),
                make_plan(plan_id="p1", code="CODE0001", title="First change", expires_at="2026-11-07T09:00:00Z", saving_usd_month=None),
                make_plan(plan_id="p3", code="CODE0003", title="Approved change", state="approved"),
                make_plan(plan_id="p4", code="CODE0004", title="Declined change", state="declined"),
                make_plan(plan_id="p5", code="CODE0005", title="Late change", expires_at="2026-11-05T10:00:00Z")]

    def test_it_lists_the_plans_that_wait_with_one_link_each_in_the_order_of_their_expiry_and_a_link_to_the_history(self):
        letter = letters.digest_letter(PERSON, BASE, NOW, [make_run()], [], self.plans())
        self.assertEqual(hrefs(letter), [f"{BASE}/ok/p1", f"{BASE}/ok/p2", f"{BASE}/history"])
        self.assertEqual(re.findall(r"https?://\S+", letter.text), [f"{BASE}/ok/p1", f"{BASE}/ok/p2", f"{BASE}/history"])
        text = letter.text
        self.assertIn("Change (names from Azure): First change", text)
        self.assertIn("Change (names from Azure): Second change", text)
        self.assertLess(text.index("Plan CODE0001"), text.index("Plan CODE0002"))
        for hidden in ("Approved change", "Declined change", "Late change", "CODE0003", "CODE0004", "CODE0005"):
            self.assertNotIn(hidden, text)
        self.assertIn("Expected saving: No figure", text)
        self.assertIn("Expected saving: about USD 41.20 a month (an estimate)", text)
        self.assertIn("Open plan CODE0001 and decide on the page", letter.html)

    def test_the_subject_counts_what_waits_and_never_an_amount(self):
        subjects = {n: letters.digest_letter(PERSON, BASE, NOW, [], [], [make_plan(plan_id=f"p{k}") for k in range(n)]).subject for n in (0, 1, 2, 12)}
        self.assertEqual(subjects[0], "[Meternaut] Summary: nothing waits for your OK")
        self.assertEqual(subjects[1], "[Meternaut] Summary: 1 change waits for your OK")
        self.assertEqual(subjects[2], "[Meternaut] Summary: 2 changes wait for your OK")
        self.assertEqual(subjects[12], "[Meternaut] Summary: 12 changes wait for your OK")
        for subject in subjects.values():
            self.assertNotIn("USD", subject)

    def test_when_nothing_waits_it_says_so_and_still_links_to_the_history(self):
        letter = letters.digest_letter(PERSON, BASE, NOW, [], [], [])
        self.assertIn("Nothing waits for your OK.", letter.text)
        self.assertIn("No run was recorded for this summary.", letter.text)
        self.assertIn("No resource is proposed.", letter.text)
        self.assertIn("No case needs a person.", letter.text)
        self.assertEqual(hrefs(letter), [f"{BASE}/history"])

    def test_it_adds_up_what_ran(self):
        runs = [make_run(run_id="a", started_at="2026-11-02T06:00:00Z", leads=5, cases=3, proposed=1, needs_human=1, dropped=1, errors=0),
                make_run(run_id="b", started_at="2026-11-04T06:00:00Z", ok=False, leads=2, cases=2, proposed=0, needs_human=1, dropped=0, errors=1)]
        text = letters.digest_letter(PERSON, BASE, NOW, runs, [], []).text
        for line in ("Runs: 2, from Monday 2 November 2026, 06:00 UTC to Wednesday 4 November 2026, 06:00 UTC", "Runs that finished well: 1", "Runs that failed: 1",
                     "Leads found: 7", "Cases judged: 5", "Proposed: 1", "Need a person: 2", "Dropped: 1", "Errors: 1"):
            self.assertIn(line, text)

    def test_it_lists_what_is_proposed_and_what_needs_a_person_with_the_names_labelled(self):
        cases = [make_case(case_id="c1", resource_name="proposed-1", status="proposed", saving_usd_month=12.5),
                 make_case(case_id="c2", resource_name="held-1", status="needs_human", guards=("locked", "too-new"), saving_usd_month=None, detector="stopped-vm"),
                 make_case(case_id="c3", resource_name="waiting-1", status="awaiting_ok"), make_case(case_id="c4", resource_name="gone-1", status="dropped")]
        text = letters.digest_letter(PERSON, BASE, NOW, [], cases, []).text
        proposed, needs = text.split("What I propose")[1].split("What needs a person")[0], text.split("What needs a person")[1]
        self.assertIn("Resource (name from Azure): proposed-1", proposed)
        self.assertIn("What it is: a managed disk that is not attached", proposed)
        self.assertIn("Estimated saving: about USD 12.50 a month", proposed)
        self.assertIn("A proposal is not a plan", proposed)
        self.assertIn("Resource (name from Azure): held-1", needs)
        self.assertIn("What it is: a virtual machine that is stopped", needs)
        self.assertIn("Checks that held it back: locked, too-new", needs)
        for other in ("waiting-1", "gone-1"):
            self.assertNotIn(other, text)

    def test_a_kind_without_words_falls_back_to_the_type_of_the_resource(self):
        case = make_case(status="proposed", detector="new-detector", resource_type="microsoft.example/things")
        self.assertIn("What it is: a resource of type microsoft.example/things", letters.digest_letter(PERSON, BASE, NOW, [], [case], []).text)

    def test_a_long_list_is_cut_and_the_rest_is_left_to_the_history_page(self):
        plans = [make_plan(plan_id=f"p{n:02d}", code=f"C{n:02d}", expires_at=f"2026-11-{6 + n // 10:02d}T0{n % 10}:00:00Z") for n in range(MAX_LISTED + 3)]
        cases = [make_case(case_id=f"c{n:02d}", resource_name=f"res-{n:02d}", status="proposed") for n in range(MAX_LISTED + 2)]
        letter = letters.digest_letter(PERSON, BASE, NOW, [], cases, plans)
        self.assertEqual(len(hrefs(letter)), MAX_LISTED + 1)
        self.assertIn("3 more plans wait. They are on the history page.", letter.text)
        self.assertIn("2 more are on the history page.", letter.text)
        self.assertEqual(letter.text.count("Resource (name from Azure): res-"), MAX_LISTED)
        self.assertEqual(letter.subject, f"[Meternaut] Summary: {MAX_LISTED + 3} changes wait for your OK")

    def test_the_proposals_come_in_the_order_of_their_estimated_saving(self):
        cases = [make_case(case_id="c1", resource_name="small", status="proposed", saving_usd_month=1.0),
                 make_case(case_id="c2", resource_name="large", status="proposed", saving_usd_month=90.0),
                 make_case(case_id="c3", resource_name="none", status="proposed", saving_usd_month=None)]
        text = letters.digest_letter(PERSON, BASE, NOW, [], cases, []).text
        self.assertLess(text.index("large"), text.index("small"))
        self.assertLess(text.index("small"), text.index("none"))

    def test_it_says_why_the_person_got_it_and_names_the_page_host(self):
        text = letters.digest_letter(PERSON, BASE, NOW, [], [], []).text
        self.assertIn("with the roles: approver, owner.", text)
        self.assertIn("The links open pages on meternaut.example.", text)

    def test_a_plan_id_that_is_not_opaque_is_refused_here_too(self):
        with self.assertRaises(ValueError):
            letters.digest_letter(PERSON, BASE, NOW, [], [], [make_plan(plan_id="a/b")])
        self.assertTrue(letters.digest_letter(PERSON, BASE, NOW, [], [], [make_plan(plan_id="a/b", state="declined")]).subject)


class Done(unittest.TestCase):
    def test_a_change_that_ran_says_what_ran_the_result_that_it_cannot_be_undone_and_that_cost_lines_confirm_later(self):
        letter = letters.done_letter(make_plan(), make_action(), make_case(), PERSON, BASE, NOW)
        self.assertEqual(letter.subject, "[Meternaut] A change to Azure has run")
        text = letter.text
        for line in (f"Change (names from Azure): Delete an unattached managed disk in resource group {GROUP}", f"Resource (name from Azure): {NAME}", "Plan code: 7F3K92QD", "State: done",
                     "Finished: Thursday 5 November 2026, 09:05 UTC", "Result: Deleted the disk.", "Check afterwards: Azure no longer lists the resource.",
                     "Note of the check: Azure no longer lists it.", "This change cannot be undone. A deleted disk cannot be restored.",
                     "Cost lines arrive after the change. When they do, I compare them with the estimate of about USD 41.20 a month and record the result. "
                     "Until then the saving is an estimate and is not confirmed."):
            self.assertIn(line, text)
        self.assertEqual(hrefs(letter), [f"{BASE}/me/decisions"])
        self.assertEqual(re.findall(r"https?://\S+", text), [f"{BASE}/me/decisions"])
        self.assertNotIn("saved", text.lower())

    def test_the_state_decides_the_subject_and_the_words(self):
        cases = {"done": "A change to Azure has run", "verified": "A change to Azure has run", "failed": "A change to Azure did not run",
                 "unknown": "The result of a change to Azure is not known", "running": "The state of a change to Azure", "queued": "The state of a change to Azure"}
        for state, point in cases.items():
            with self.subTest(state=state):
                letter = letters.done_letter(make_plan(), make_action(state=state), make_case(), PERSON, BASE, NOW)
                self.assertEqual(letter.subject, f"[Meternaut] {point}")

    def test_a_change_that_did_not_complete_does_not_claim_that_it_ran(self):
        for state in ("failed", "unknown", "running"):
            with self.subTest(state=state):
                text = letters.done_letter(make_plan(), make_action(state=state, error="The disk is locked."), make_case(), PERSON, BASE, NOW).text
                self.assertIn("Error: The disk is locked.", text)
                self.assertNotIn("cannot be undone", text)
                self.assertNotIn("Cost lines arrive", text)
                self.assertIn("Look at the resource in Azure before anything else is done with it.", text)
        self.assertIn("was tried and did not complete", letters.done_letter(make_plan(), make_action(state="failed"), make_case(), PERSON, BASE, NOW).text)
        self.assertIn("its result is not known", letters.done_letter(make_plan(), make_action(state="unknown"), make_case(), PERSON, BASE, NOW).text)

    def test_the_check_afterwards_is_told_as_it_is(self):
        still = letters.done_letter(make_plan(), make_action(verification={"gone": False, "costAfterUsd": 3.5, "note": ""}), make_case(), PERSON, BASE, NOW).text
        self.assertIn("Check afterwards: Azure still lists the resource.", still)
        self.assertIn("Cost lines after the change: USD 3.50", still)
        self.assertNotIn("Note of the check", still)
        none = letters.done_letter(make_plan(), make_action(verification={}, result="", finished_at=None), make_case(), PERSON, BASE, NOW).text
        self.assertNotIn("Check afterwards", none)
        self.assertIn("Result: No result text was recorded.", none)
        self.assertIn("Finished: not finished", none)

    def test_a_result_without_a_figure_for_the_saving_does_not_invent_one(self):
        text = letters.done_letter(make_plan(saving_usd_month=None), make_action(), make_case(), PERSON, BASE, NOW).text
        self.assertIn("I compare them with the estimate and record the result.", text)
        self.assertNotIn("USD", text)


class WhatComesFromAzureIsData(unittest.TestCase):
    def hostile(self) -> dict[str, Letter]:
        plan = make_plan(title=HOSTILE, resource_name=HOSTILE, resource_group=HOSTILE, what_changes=HOSTILE, could_go_wrong=HOSTILE, undo=HOSTILE,
                         evidence_level=HOSTILE, code=HOSTILE)
        case = make_case(resource_name=HOSTILE, resource_group=HOSTILE, resource_type=HOSTILE, models={"detective": HOSTILE, "skeptic": HOSTILE}, guards=(HOSTILE,),
                         detector="unknown-detector", status="proposed")
        action = make_action(result=HOSTILE, error=HOSTILE, verification={"gone": True, "note": HOSTILE, "costAfterUsd": 1.0}, state="failed")
        person = Person(OID, HOSTILE, (HOSTILE,), "maya@example.com")
        digest_cases = [case, dataclasses.replace(case, case_id="c2", status="needs_human")]
        return {
            "first contact": letters.first_contact_letter(person, BASE, NOW),
            "approval": letters.approval_letter(plan, case, person, BASE, NOW),
            "digest": letters.digest_letter(person, BASE, NOW, [make_run()], digest_cases, [plan]),
            "done": letters.done_letter(plan, action, case, person, BASE, NOW),
        }

    def test_a_hostile_value_adds_no_tag_no_attribute_and_no_script_and_shows_as_text(self):
        for kind, letter in self.hostile().items():
            with self.subTest(letter=kind):
                parsed = Parsed(letter.html)
                self.assertLessEqual(set(parsed.tags), ALLOWED_TAGS)
                self.assertNotIn("script", parsed.tags)
                self.assertNotIn("img", parsed.tags)
                self.assertFalse([a for a in parsed.attributes if a[1].startswith("on")])
                self.assertNotIn("<script", letter.html.lower())
                self.assertNotIn("<img", letter.html.lower())
                self.assertNotIn(HOSTILE, letter.html)
                self.assertEqual(parsed.tags.count("a"), len(hrefs(letter)))
                for address in hrefs(letter):
                    self.assertRegex(address, LINK_PATHS)
                if kind != "first contact":
                    self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", letter.html)
                    self.assertIn("&quot;&gt;&lt;script&gt;", letter.html)
                    self.assertIn("&#x27;quote&#x27;", letter.html)

    def test_what_a_name_holds_is_cut_down_to_one_line_without_control_or_direction_characters(self):
        for kind in ("approval", "done", "digest"):
            letter = self.hostile()[kind]
            with self.subTest(letter=kind):
                self.assertNotIn("\u202e", letter.text + letter.html)
                self.assertNotIn("\x00", letter.text + letter.html)
                self.assertIn(HOSTILE_ONE_LINE[:120].rstrip(), letter.text)
        self.assertNotIn("\u202e", self.hostile()["first contact"].text)

    def test_the_subject_never_holds_what_came_from_azure_or_from_a_person(self):
        for kind, letter in self.hostile().items():
            with self.subTest(letter=kind):
                for piece in ("<", ">", '"', "script", "quote", "\u202e", "\x00"):
                    self.assertNotIn(piece, letter.subject)

    def test_the_address_of_the_console_must_be_an_address_and_nothing_more(self):
        for bad in ("", "host", "ftp://host", "http://host.example", "https://host/a b", "https://host/..", "https://host/a/../b", "https://host?x=1",
                    "https://host#x", "javascript:alert(1)", 'https://host"><script>', "https://user@host", "https://host.example\n/x"):
            with self.subTest(base=bad):
                with self.assertRaises(ValueError):
                    letters.first_contact_letter(PERSON, bad, NOW)
        for good, link in (("https://host.example", "https://host.example/me/settings"), ("https://host.example/", "https://host.example/me/settings"),
                           (" https://host.example/api\n", "https://host.example/api/me/settings"),
                           ("https://host.example:8443/api", "https://host.example:8443/api/me/settings"), ("http://localhost:7071", "http://localhost:7071/me/settings"),
                           ("http://127.0.0.1:7071/api", "http://127.0.0.1:7071/api/me/settings")):
            with self.subTest(base=good):
                self.assertEqual(hrefs(letters.first_contact_letter(PERSON, good, NOW)), [link])


class WhatTheModuleIs(unittest.TestCase):
    source = (Path(support.APP_ROOT) / "cases" / "letters.py").read_text(encoding="utf-8")

    def test_it_imports_only_the_standard_library_and_the_records(self):
        allowed = {"__future__", "datetime", "html", "math", "re", "unicodedata", "dataclasses", "urllib"}
        for node in ast.walk(ast.parse(self.source)):
            if isinstance(node, ast.Import):
                self.assertLessEqual({a.name.split(".")[0] for a in node.names}, allowed)
            elif isinstance(node, ast.ImportFrom):
                self.assertTrue(node.level == 1 and node.module in ("models", "people") or node.level == 0 and node.module.split(".")[0] in allowed, node.module)

    def test_it_reads_no_clock_and_does_no_input_or_output(self):
        for pattern in (r"\.(now|utcnow|today)\(", r"\bimport time\b", r"\btime\.(time|sleep|monotonic)\(", r"\bopen\(", r"\bprint\(", r"\bos\.", r"\bsys\.", r"\burlopen",
                        r"\bsocket", r"\blogging"):
            self.assertIsNone(re.search(pattern, self.source), pattern)


if __name__ == "__main__":
    unittest.main()
