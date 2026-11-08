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
from cases.letters import DARK, LIGHT, MAX_LISTED, Letter
from cases.models import ActionRecord, CaseRecord, PlanRecord, RunRecord
from cases.people import Person

NOW = dt.datetime(2026, 11, 5, 10, 18, 0, tzinfo=dt.timezone.utc)
BASE = "https://meternaut.example"
OID = "11111111-1111-1111-1111-111111111111"
PERSON = Person(OID, "Maya", ("approver", "owner"), "maya@example.com")
OUTSIDER = Person("22222222-2222-2222-2222-222222222222", "Noor", ("ops",), "noor@example.com")
CONTACTS = ("Maya (maya@example.com)", "Ops (ops@example.com)")
# Every name below is invented (AGENTS.md rule 17): a letter is checked with the data of a disk that nobody uses.
NAME = "disk-zq7-name"
GROUP = "rg-zq7-group"
HOSTILE = "\"><script>alert(1)</script><img src=x onerror=alert(2)> & 'quote' \u202e\x00\nnew line"
HOSTILE_ONE_LINE = "\"><script>alert(1)</script><img src=x onerror=alert(2)> & 'quote' new line"
ALLOWED_TAGS = {"html", "head", "meta", "title", "style", "body", "table", "tr", "td", "th", "h1", "p", "ul", "li", "a"}
LINK_PATHS = re.compile(r"^https://meternaut\.example/(ok/[A-Za-z0-9_-]{1,64})?$")
# The most words that a letter may have (what a person reads in about a minute), counted in what the letter shows.
MOST_WORDS = {"first contact": 110, "approval": 135, "digest": 150, "done": 95}


def make_plan(**changes) -> PlanRecord:
    values = dict(
        plan_id="p1a2b3c4d5", case_id="c1", family="delete-disk", resource_id=f"/subscriptions/s/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/{NAME}",
        resource_name=NAME, resource_group=GROUP, subscription_id="s", code="7F3K92QD", title=f"Delete an unattached managed disk in resource group {GROUP}",
        what_changes=f"When you approve and sign in to Azure, Meternaut deletes the disk named {NAME} with your own permissions. It changes nothing else.",
        saving_usd_month=41.2, waiting_costs_usd_day=1.37,
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
                  finished_at="2026-11-05T09:05:00Z", result="Deleted. Azure no longer lists the resource.",
                  verification={"gone": True, "checkedAt": "2026-11-05T09:05:00Z"})
    values.update(changes)
    return ActionRecord(**values)


def make_run(**changes) -> RunRecord:
    values = dict(run_id="a", trigger="timer", started_at="2026-11-02T06:00:00Z", leads=5, cases=3, proposed=1, needs_human=1, dropped=1, errors=0)
    values.update(changes)
    return RunRecord(**values)


def waiting(count: int) -> list[tuple[PlanRecord, CaseRecord]]:
    """`count` open requests, each for its own disk, the larger saving for the higher number."""
    return [(make_plan(plan_id=f"p{n}", case_id=f"c{n}", code=f"CODE000{n}", resource_name=f"disk-{n}", saving_usd_month=float(n * 10), waiting_costs_usd_day=None),
             make_case(case_id=f"c{n}", resource_name=f"disk-{n}", status="proposed", saving_usd_month=float(n * 10))) for n in range(1, count + 1)]


def everything(person: Person = PERSON, contacts=(), **overrides) -> dict[str, Letter]:
    plan, case = overrides.get("plan", make_plan()), overrides.get("case", make_case())
    return {
        "first contact": letters.first_contact_letter(person, BASE, NOW, contacts, plan.plan_id),
        "approval": letters.approval_letter(plan, case, person, BASE, NOW, contacts),
        "digest": letters.digest_letter(person, BASE, NOW, overrides.get("waiting", waiting(2)), contacts),
        "done": letters.done_letter(plan, overrides.get("action", make_action()), case, person, BASE, NOW, contacts),
    }


class Parsed(HTMLParser):
    """The tags, the attributes and the visible text of a letter's HTML (not its title and not its style sheet)."""

    def __init__(self, source: str) -> None:
        super().__init__()
        self.source_html = source
        self.tags: list[str] = []
        self.attributes: list[tuple[str, str, str | None]] = []
        self.text: list[str] = []
        self.hidden = 0
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes += [(tag, name, value) for name, value in attrs]
        self.hidden += tag in ("style", "title")

    def handle_endtag(self, tag):
        self.hidden -= tag in ("style", "title")

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)

    def visible(self) -> str:
        return " ".join(self.text)

    def paragraphs(self) -> list[str]:
        return [" ".join(part.split()) for part in re.findall(r"<p [^>]*>(.*?)</p>", self.source_html, re.S)]


def luminance(color: str) -> float:
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def hrefs(letter: Letter) -> list[str]:
    return re.findall(r'href="([^"]*)"', letter.html)


def word_count(letter: Letter) -> int:
    return len(Parsed(letter.html).visible().split())


def words_of(text: str) -> list[str]:
    """The words of a text, without the marks that only the plain copy has (the rule under a heading, the dash of a list, the colon after a label, the address)."""
    return sorted(word.strip(":") for word in text.split() if word != "-" and not set(word) <= set("=") and not word.startswith("https://"))


class WhatEveryLetterHas(unittest.TestCase):
    def test_the_subject_starts_with_the_name_says_the_point_and_holds_no_resource_name_and_no_amount(self):
        plan, case = make_plan(), make_case()
        for kind, letter in everything(plan=plan, case=case).items():
            with self.subTest(letter=kind):
                self.assertTrue(letter.subject.startswith("[Meternaut] "), letter.subject)
                self.assertNotIn("\n", letter.subject)
                self.assertLessEqual(len(letter.subject), 90)
                for word in (NAME, GROUP, plan.code, "USD", "US dollars", "$", "?", "disk", "41"):
                    self.assertNotIn(word, letter.subject)

    def test_the_subjects_say_the_point(self):
        found = {kind: letter.subject for kind, letter in everything().items()}
        self.assertEqual(found["first contact"], "[Meternaut] An AI assistant for Azure costs will write to you")
        self.assertEqual(found["approval"], "[Meternaut] A change to Azure waits for your OK")
        self.assertEqual(found["digest"], "[Meternaut] 2 decisions wait for you")
        self.assertEqual(found["done"], "[Meternaut] A change to Azure has run")

    def test_the_subject_is_the_same_whatever_the_data_says(self):
        benign = {kind: letter.subject for kind, letter in everything(action=make_action(state="failed")).items()}
        hostile = WhatComesFromAzureIsData.hostile()
        for kind, subject in benign.items():
            with self.subTest(letter=kind):
                self.assertEqual(hostile[kind].subject, subject)

    def test_every_letter_ends_in_one_footer_line_that_says_who_wrote_it_why_the_person_got_it_and_whom_to_talk_to(self):
        for kind, letter in everything(contacts=CONTACTS).items():
            with self.subTest(letter=kind):
                footers = [line for line in letter.text.splitlines() if line.startswith("Written by an AI")]
                self.assertEqual(len(footers), 1)
                self.assertEqual(letter.text.rstrip().splitlines()[-1], footers[0], "the footer is the last line")
                for words in ("a person approves every change.", "You got this because", "Talk to a person: Ops (ops@example.com)."):
                    self.assertIn(words, footers[0])
                self.assertEqual(sum(1 for p in Parsed(letter.html).paragraphs() if p.startswith("Written by an AI")), 1)
                self.assertIn(footers[0], " ".join(Parsed(letter.html).visible().split()))
                self.assertNotIn("mailto:", letter.html.lower(), "the person to talk to is plain text")

    def test_the_person_to_talk_to_is_one_person_other_than_the_reader_when_there_is_one(self):
        for person, expected in ((PERSON, "Ops (ops@example.com)"), (OUTSIDER, "Maya (maya@example.com)")):
            with self.subTest(person=person.name):
                self.assertIn(f"Talk to a person: {expected}.", letters.first_contact_letter(person, BASE, NOW, CONTACTS).text)
        alone = letters.first_contact_letter(PERSON, BASE, NOW, ("Maya (maya@example.com)",))
        self.assertIn("Talk to a person: Maya (maya@example.com).", alone.text)
        nobody = letters.first_contact_letter(PERSON, BASE, NOW)
        self.assertIn("Talk to a person: whoever put you on my list of people.", nobody.text)

    def test_a_letter_names_the_models_that_took_part_in_the_case_when_the_case_says_which(self):
        for kind in ("approval", "done"):
            self.assertIn("Written by an AI (models: model-d, model-s); a person approves every change.", everything()[kind].text)
        self.assertIn("Written by an AI; a person approves every change.", everything(case=make_case(models={}))["approval"].text)

    def test_the_ceremony_of_the_old_letters_is_gone(self):
        for kind, letter in everything().items():
            with self.subTest(letter=kind):
                for gone in ("The Detective judges", "The Skeptic argues against", "computed by code, not by a model", "Replies to this letter are not read",
                             "nothing is approved by e-mail", "Written on", "Opening this link", "Open the history"):
                    self.assertNotIn(gone, letter.text)

    def test_the_wording_has_no_question_no_urgency_no_countdown_and_never_says_that_something_was_saved(self):
        for kind, letter in everything(contacts=CONTACTS).items():
            with self.subTest(letter=kind):
                lower = letter.text.lower()
                self.assertNotIn("?", letter.text)
                self.assertNotIn("saved", lower)
                self.assertNotIn("\u2013", letter.text)
                self.assertNotIn("\u2014", letter.text)
                self.assertTrue(letter.text.isascii(), "plain letters are plain ASCII")
                self.assertIsNone(re.search(r"\b(urgent|urgently|immediately|hurry|asap|last chance|act now|deadline|running out|countdown)\b", lower))
                self.assertIsNone(re.search(r"\b\d+ (seconds?|minutes?|hours?|days?) (left|remaining|to go)\b|\b(expires|expiring) in\b", lower))
                self.assertNotIn("!", letter.text)

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
                self.assertEqual(parsed.tags.count("h1"), 1, "one real heading: the point of the letter")
                self.assertFalse([a for a in parsed.attributes if a[1].startswith("on")])
                for tag, name, value in parsed.attributes:
                    if tag == "a":
                        self.assertIn(name, {"class", "href", "style"})

    def test_a_letter_has_one_link_and_it_is_the_page_of_its_request_or_the_start_page(self):
        for kind, letter in everything().items():
            with self.subTest(letter=kind):
                self.assertEqual(len(hrefs(letter)), 1)
                self.assertEqual(Parsed(letter.html).tags.count("a"), 1)
                self.assertRegex(hrefs(letter)[0], LINK_PATHS)
                self.assertEqual(re.findall(r"https?://\S+", letter.text), hrefs(letter), "the address is in the text, once")
                self.assertEqual(sorted(re.findall(r"https?://[^\s\"<>]+", letter.html)), hrefs(letter), "an address appears only as the link")
                for name in (NAME, GROUP, "7F3K92QD", "41", "USD"):
                    self.assertNotIn(name, hrefs(letter)[0])
        found = everything()
        self.assertEqual(hrefs(found["first contact"]), [f"{BASE}/ok/p1a2b3c4d5"])
        self.assertEqual(hrefs(found["approval"]), [f"{BASE}/ok/p1a2b3c4d5"])
        self.assertEqual(hrefs(found["done"]), [f"{BASE}/ok/p1a2b3c4d5"])
        self.assertEqual(hrefs(found["digest"]), [f"{BASE}/"])

    def test_each_letter_is_short_enough_to_read_in_a_minute(self):
        for kind, letter in everything(contacts=CONTACTS).items():
            with self.subTest(letter=kind):
                self.assertLessEqual(word_count(letter), MOST_WORDS[kind])
        five = letters.digest_letter(PERSON, BASE, NOW, waiting(MAX_LISTED + 3), CONTACTS)
        assert five is not None
        self.assertLessEqual(word_count(five), MOST_WORDS["digest"])

    def test_the_output_is_the_same_every_time_and_does_not_depend_on_the_order_of_the_input(self):
        many = waiting(5)
        first = letters.digest_letter(PERSON, BASE, NOW, many)
        for attempt in range(5):
            self.assertEqual(letters.digest_letter(PERSON, BASE, NOW, random.Random(attempt).sample(many, len(many))), first)
        self.assertEqual(everything(), everything())

    def test_a_time_without_a_time_zone_is_read_as_utc_and_a_zone_is_converted(self):
        naive = NOW.replace(tzinfo=None)
        zoned = NOW.astimezone(dt.timezone(dt.timedelta(hours=-5)))
        plan, case = make_plan(), make_case()
        for moment in (naive, zoned):
            self.assertEqual(letters.approval_letter(plan, case, PERSON, BASE, moment), letters.approval_letter(plan, case, PERSON, BASE, NOW))
            self.assertEqual(letters.digest_letter(PERSON, BASE, moment, waiting(2)), letters.digest_letter(PERSON, BASE, NOW, waiting(2)))
        late = dt.datetime(2026, 11, 8, 9, 45, 0, tzinfo=dt.timezone.utc)
        self.assertIsNone(letters.digest_letter(PERSON, BASE, late, [(plan, case)]), "after its time a request does not wait")
        self.assertIsNone(letters.digest_letter(PERSON, BASE, late.astimezone(dt.timezone(dt.timedelta(hours=-5))), [(plan, case)]))

    def test_a_letter_cannot_be_changed_after_it_is_made(self):
        letter = letters.first_contact_letter(PERSON, BASE, NOW)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            letter.subject = "[Meternaut] other"  # type: ignore[misc]

    def test_the_html_and_the_text_hold_the_same_words(self):
        for kind, letter in everything(contacts=CONTACTS).items():
            with self.subTest(letter=kind):
                self.assertEqual(words_of(Parsed(letter.html).visible()), words_of(letter.text))


class TheContrast(unittest.TestCase):
    def test_every_text_colour_meets_wcag_aa_on_the_colour_it_sits_on_in_the_light_and_in_the_dark_palette(self):
        for name, palette in (("light", LIGHT), ("dark", DARK)):
            for text, ground in (("text", "background"), ("muted", "background"), ("link", "background"), ("text", "head"), ("button_text", "button")):
                with self.subTest(palette=name, text=text, ground=ground):
                    self.assertGreaterEqual(contrast(palette[text], palette[ground]), 4.5)

    def test_the_inline_colours_are_the_light_palette_and_the_dark_one_is_in_the_media_query(self):
        page = everything()["approval"].html
        style, body = page.split("</style>")[0], page.split("</style>")[1]
        used = set(re.findall(r"(?<![-a-z])(?:color|background-color):(#[0-9a-f]{6})", body))
        self.assertTrue(used)
        self.assertLessEqual(used, set(LIGHT.values()))
        for color in (DARK["background"], DARK["text"], DARK["muted"], DARK["link"], DARK["head"], DARK["rule"], DARK["button"], DARK["button_text"]):
            self.assertIn(color, style)

    def test_the_button_is_a_link_with_its_own_colours_and_a_text_that_says_where_it_goes(self):
        for kind, letter in everything().items():
            with self.subTest(letter=kind):
                button = re.search(r'<a class="mn-button" href="[^"]+" style="([^"]+)">([^<]+)</a>', letter.html)
                assert button is not None
                self.assertIn(f"background-color:{LIGHT['button']}", button.group(1))
                self.assertIn(f"color:{LIGHT['button_text']}", button.group(1))
                self.assertGreaterEqual(len(button.group(2).split()), 1)
        self.assertEqual(re.search(r'class="mn-button"[^>]*>([^<]+)<', everything()["approval"].html).group(1), "Decide")


class FirstContact(unittest.TestCase):
    def setUp(self):
        self.letter = letters.first_contact_letter(PERSON, BASE, NOW, CONTACTS, "p1a2b3c4d5")

    def test_it_is_three_sentences_before_the_button(self):
        body = [p for p in Parsed(self.letter.html).paragraphs() if not p.startswith("Written by an AI") and "mn-button" not in p]
        sentences = [s for p in body for s in re.split(r"(?<=[.])\s+", p) if s]
        self.assertEqual(len(sentences), 3, sentences)

    def test_it_says_who_writes_what_for_what_it_does_not_do_and_where_to_pause_or_stop_the_letters(self):
        text = self.letter.text
        self.assertIn("I am Meternaut, an AI that looks for Azure resources that cost money and are not used", text)
        self.assertIn("I change nothing myself: you decide on a web page, and a change runs with your own Azure rights.", text)
        self.assertIn("You can pause or stop my letters under Settings on that page.", text)
        self.assertIn("with the roles: approver, owner", text)

    def test_its_one_link_is_the_first_request_or_the_start_page(self):
        self.assertEqual(hrefs(self.letter), [f"{BASE}/ok/p1a2b3c4d5"])
        self.assertIn("See the first decision", self.letter.html)
        bare = letters.first_contact_letter(PERSON, BASE, NOW)
        self.assertEqual(hrefs(bare), [f"{BASE}/"])
        self.assertIn("Open the web page", bare.html)

    def test_the_greeting_uses_the_name_of_the_person(self):
        self.assertIn("Hello Maya, ", self.letter.text)
        self.assertIn("Hello Noor, ", letters.first_contact_letter(OUTSIDER, BASE, NOW).text)

    def test_the_plan_id_in_the_link_must_be_an_opaque_id(self):
        for bad in ("../x", "a b", "x" * 65, "p?x=1", "p/../q", "p\n1"):
            with self.subTest(plan_id=bad):
                with self.assertRaises(ValueError):
                    letters.first_contact_letter(PERSON, BASE, NOW, (), bad)


class Approval(unittest.TestCase):
    def letter(self, **changes) -> Letter:
        return letters.approval_letter(changes.pop("plan", make_plan()), changes.pop("case", make_case()), changes.pop("person", PERSON), BASE, NOW, changes.pop("contacts", CONTACTS))

    def test_it_answers_the_eight_questions_in_the_words_of_the_brief(self):
        text = self.letter().text
        self.assertIn("Delete the unattached disk disk-zq7-name in group rg-zq7-group", text)  # what am I asked to decide
        self.assertIn("Expected saving: about 41.20 US dollars a month. How sure: high.", text)  # what do I get; how sure
        self.assertIn("Cost, last 30 days: 41.20 US dollars", text)  # on what evidence
        self.assertIn("State: Not attached to any virtual machine", text)
        self.assertIn("Owner: Meternaut has not looked up who owns this resource yet.", text)  # whose is it
        self.assertIn("If you approve: Deletes the disk disk-zq7-name in resource group rg-zq7-group. Nothing else changes. "
                      "It runs with your own permissions, after you sign in to Azure.", text)  # what happens, who does it, with whose rights
        self.assertIn("Undo: This cannot be undone.", text)
        self.assertIn("Risk, medium: If something still uses the disk, that use stops, and the data on it is lost for good.", text)
        self.assertIn("Decide: https://meternaut.example/ok/p1a2b3c4d5", text)  # what are my choices: the page

    def test_the_owner_is_said_in_the_words_of_the_facts_that_code_read(self):
        case = make_case(owner={"tagOwner": "alice@example.com", "tagName": "owner", "createdBy": "bob@example.com", "createdAt": "2026-03-01T08:00:00Z", "lookedUp": True})
        self.assertIn("Owner: Tag owner: alice@example.com. Created by bob@example.com on 2026-03-01.", self.letter(case=case).text)
        self.assertIn("Owner: No owner is recorded on the resource.", self.letter(case=make_case(owner={"lookedUp": True})).text)

    def test_opening_the_link_records_nothing_and_the_letter_has_no_button_that_decides(self):
        letter = self.letter()
        self.assertNotIn("<form", letter.html)
        self.assertEqual(hrefs(letter), [f"{BASE}/ok/p1a2b3c4d5"])
        self.assertNotIn("approve=", letter.html)

    def test_the_saving_is_an_estimate_with_its_level_in_us_dollars_and_a_scenario_says_what_it_rests_on(self):
        self.assertIn("Expected saving: about 41.20 US dollars a month.", self.letter().text)
        advisor = self.letter(case=make_case(detector="advisor-cost")).text
        self.assertIn("Scenario saving: about 41.20 US dollars a month (Azure Advisor's own estimate: no cost line of this resource backs it).", advisor)
        self.assertNotIn("$", self.letter().text)

    def test_a_figure_that_is_not_known_is_not_shown_as_a_number(self):
        letter = self.letter(plan=make_plan(saving_usd_month=None, waiting_costs_usd_day=None), case=make_case(saving_usd_month=None, cost_usd_30d=None))
        self.assertIn("No figure: no cost line of the last 30 days was read for this resource. How sure: high.", letter.text)
        self.assertNotIn("a month", letter.text)

    def test_it_says_plainly_that_a_delete_cannot_be_undone_and_what_could_go_wrong(self):
        self.assertIn("Undo: This cannot be undone.", self.letter().text)
        self.assertIn("Risk, medium:", self.letter().text)

    def test_the_plan_code_and_the_time_it_ends_are_for_the_page_and_not_for_the_letter(self):
        letter = self.letter()
        for left_out in ("7F3K92QD", "2026-11-08", "expires", "Expires"):
            self.assertNotIn(left_out, letter.text)

    def test_the_models_that_took_part_are_named_in_the_footer(self):
        self.assertIn("Written by an AI (models: model-d, model-s); a person approves every change.", self.letter().text)
        investigated = self.letter(case=make_case(detector="investigation", models={"investigator": "model-i", "skeptic": "model-s"}))
        self.assertIn("models: model-i, model-s", investigated.text)

    def test_it_says_why_the_person_got_it(self):
        self.assertIn("You got this because you are named as an approver of this request.", self.letter().text)
        self.assertIn("You got this because you are on my list of people who receive letters.", self.letter(person=OUTSIDER).text)

    def test_a_plan_that_is_no_longer_open_is_not_presented_as_waiting(self):
        for state in ("declined", "approved", "consumed", "withdrawn", "failed", "expired"):
            letter = self.letter(plan=make_plan(state=state))
            with self.subTest(state=state):
                self.assertIn("This request is closed:", letter.text)
                self.assertIn("Nothing can be answered now.", letter.text)
                self.assertIn("See the request", letter.html)
                self.assertNotIn(">Decide<", letter.html)

    def test_an_open_plan_past_its_time_says_so(self):
        letter = self.letter(plan=make_plan(expires_at="2026-11-05T10:00:00Z"))
        self.assertIn("This request is closed: expired.", letter.text)
        self.assertIn("See the request", letter.html)

    def test_a_time_that_cannot_be_read_is_not_shown_as_waiting(self):
        self.assertIn("This request is closed: expired.", self.letter(plan=make_plan(expires_at="soon")).text)

    def test_the_plan_id_in_the_link_must_be_an_opaque_id(self):
        for bad in ("", "../x", "a b", "p?x=1", "x" * 65, "p\n1", "p/../q"):
            with self.subTest(plan_id=bad):
                with self.assertRaises(ValueError):
                    self.letter(plan=make_plan(plan_id=bad))

    def test_long_texts_are_cut(self):
        letter = self.letter(plan=make_plan(resource_name="d" * 500, resource_group="g" * 500))
        self.assertLessEqual(max(len(line) for line in letter.text.splitlines() if not line.startswith("Decide:")), 300)
        self.assertIn("...", letter.text)

    def test_advice_is_a_decision_that_changes_nothing_and_does_not_talk_of_signing_in_to_azure(self):
        advice = make_plan(family="advise", approval_class="R1", title="Look at the disk disk-zq7-name in group rg-zq7-group", preconditions={"family": "advise", "caseStatus": "needs_human"})
        letter = self.letter(plan=advice, case=make_case(status="needs_human"))
        self.assertEqual(letter.subject, "[Meternaut] A decision waits for you")
        self.assertIn("If you answer: Nothing changes in Azure. Your answer is recorded with your name.", letter.text)
        self.assertNotIn("sign in to Azure", letter.text)
        self.assertNotIn("Undo: This cannot be undone.", letter.text)
        self.assertIn("Undo: Nothing is changed, so there is nothing to undo.", letter.text)
        self.assertIn("Decide: https://meternaut.example/ok/p1a2b3c4d5", letter.text)


class Digest(unittest.TestCase):
    def digest(self, count=3, **changes) -> Letter:
        found = letters.digest_letter(changes.pop("person", PERSON), BASE, NOW, changes.pop("waiting", waiting(count)), changes.pop("contacts", CONTACTS))
        assert found is not None
        return found

    def test_nothing_is_written_when_nothing_waits(self):
        self.assertIsNone(letters.digest_letter(PERSON, BASE, NOW, []))
        closed = [(dataclasses.replace(plan, state="declined"), case) for plan, case in waiting(2)]
        self.assertIsNone(letters.digest_letter(PERSON, BASE, NOW, closed))
        past = [(dataclasses.replace(plan, expires_at="2026-11-05T10:00:00Z"), case) for plan, case in waiting(2)]
        self.assertIsNone(letters.digest_letter(PERSON, BASE, NOW, past), "a request past its time does not wait")

    def test_it_lists_the_requests_that_wait_one_line_each_the_largest_saving_first(self):
        letter = self.digest(3)
        lines = [line for line in letter.text.splitlines() if line.startswith("- ")]
        self.assertEqual(lines, ["- Delete the unattached disk disk-3 in group rg-zq7-group. About 30.00 US dollars a month, Expected.",
                                 "- Delete the unattached disk disk-2 in group rg-zq7-group. About 20.00 US dollars a month, Expected.",
                                 "- Delete the unattached disk disk-1 in group rg-zq7-group. About 10.00 US dollars a month, Expected."])
        self.assertEqual(Parsed(letter.html).tags.count("li"), 3)

    def test_the_subject_counts_what_waits_and_never_an_amount(self):
        self.assertEqual(self.digest(1).subject, "[Meternaut] 1 decision waits for you")
        self.assertEqual(self.digest(2).subject, "[Meternaut] 2 decisions wait for you")
        self.assertEqual(self.digest(9).subject, "[Meternaut] 9 decisions wait for you")
        for count in (1, 2, 9):
            for word in ("US dollars", "USD", "$", "disk"):
                self.assertNotIn(word, self.digest(count).subject)

    def test_at_most_five_are_listed_and_the_rest_is_left_to_the_page(self):
        letter = self.digest(MAX_LISTED + 2)
        self.assertEqual(len([line for line in letter.text.splitlines() if line.startswith("- ")]), MAX_LISTED)
        self.assertIn("2 more wait on the page.", letter.text)
        self.assertIn("disk-7", letter.text)
        self.assertNotIn("disk-1 ", letter.text)
        self.assertNotIn("more wait", self.digest(MAX_LISTED).text)

    def test_one_request_links_to_its_page_and_several_to_the_page_that_lists_them(self):
        self.assertEqual(hrefs(self.digest(1)), [f"{BASE}/ok/p1"])
        self.assertIn(">Decide<", self.digest(1).html)
        self.assertEqual(hrefs(self.digest(3)), [f"{BASE}/"])
        self.assertIn(">Open the decisions<", self.digest(3).html)

    def test_a_request_without_a_figure_is_listed_without_one(self):
        plan, case = waiting(1)[0]
        letter = self.digest(waiting=[(dataclasses.replace(plan, saving_usd_month=None), dataclasses.replace(case, saving_usd_month=None, cost_usd_30d=None))])
        self.assertIn("- Delete the unattached disk disk-1 in group rg-zq7-group.\n", letter.text)

    def test_a_request_without_a_case_is_still_listed(self):
        plan, _ = waiting(1)[0]
        letter = self.digest(waiting=[(plan, None)])
        self.assertIn("disk-1", letter.text)

    def test_it_says_why_the_person_got_it_with_the_roles(self):
        self.assertIn("You got this because you are on my list of people, with the roles: approver, owner.", self.digest().text)


class Done(unittest.TestCase):
    def letter(self, **changes) -> Letter:
        return letters.done_letter(changes.pop("plan", make_plan()), changes.pop("action", make_action()), changes.pop("case", make_case()), changes.pop("person", PERSON), BASE, NOW,
                                   changes.pop("contacts", CONTACTS))

    def test_a_change_that_ran_says_what_ran_the_result_what_it_is_worth_so_far_and_that_it_cannot_be_undone(self):
        text = self.letter().text
        self.assertIn("Done: Delete the unattached disk disk-zq7-name in group rg-zq7-group.", text)
        self.assertIn("Result: Deleted. Azure no longer lists the resource.", text)
        self.assertEqual(text.count("Azure no longer lists the resource."), 1, "a line that the result holds is not said twice")
        self.assertIn("Expected saving: about 41.20 US dollars a month. Cost lines confirm it after a few days.", text)
        self.assertIn("This cannot be undone.", text)
        self.assertIn("See what happened: https://meternaut.example/ok/p1a2b3c4d5", text)

    def test_the_state_decides_the_subject_and_the_words(self):
        for state, subject in (("done", "A change to Azure has run"), ("verified", "A change to Azure has run"), ("failed", "A change to Azure did not run"),
                               ("unknown", "The result of a change to Azure is not known")):
            with self.subTest(state=state):
                self.assertEqual(self.letter(action=make_action(state=state)).subject, f"[Meternaut] {subject}")

    def test_a_change_that_did_not_complete_does_not_claim_that_it_ran(self):
        letter = self.letter(action=make_action(state="failed", result="", error="Azure refused the change (403, AuthorizationFailed).", verification={}))
        self.assertIn("The change was tried and did not complete: Delete the unattached disk disk-zq7-name in group rg-zq7-group.", letter.text)
        self.assertIn("What happened: Azure refused the change (403, AuthorizationFailed).", letter.text)
        self.assertIn("Look at the resource in Azure before anything else is done with it.", letter.text)
        for claim in ("Done:", "cannot be undone", "saving"):
            self.assertNotIn(claim, letter.text)
        unknown = self.letter(action=make_action(state="unknown", result="Azure accepted the delete and still lists the resource.", verification={}))
        self.assertIn("The change was started, and its result is not known:", unknown.text)

    def test_a_verified_saving_is_said_as_verified_and_nothing_more_is_awaited(self):
        action = make_action(state="verified", verification={"gone": True, "costAfterUsd": 0.0, "costBeforeUsd30d": 41.2, "currency": "USD"})
        text = self.letter(action=action).text
        self.assertIn("Verified saving: about 41.20 US dollars a month (the cost lines after the change show no cost for this resource).", text)
        self.assertNotIn("after a few days", text)
        self.assertIn("Cost lines since the change: 0.00 US dollars.", text)

    def test_a_result_without_a_figure_for_the_saving_does_not_invent_one(self):
        text = self.letter(plan=make_plan(saving_usd_month=None), case=make_case(saving_usd_month=None, cost_usd_30d=None)).text
        self.assertIn("No figure: no cost line of the last 30 days was read for this resource.", text)
        self.assertNotIn("a month", text)


class WhatComesFromAzureIsData(unittest.TestCase):
    @staticmethod
    def hostile() -> dict[str, Letter]:
        plan = make_plan(title=HOSTILE, resource_name=HOSTILE, resource_group=HOSTILE, what_changes=HOSTILE, could_go_wrong=HOSTILE, undo=HOSTILE, evidence_level=HOSTILE, code=HOSTILE)
        case = make_case(resource_name=HOSTILE, resource_group=HOSTILE, resource_type=HOSTILE, models={"detective": HOSTILE, "skeptic": HOSTILE}, guards=(HOSTILE,),
                         detector="unknown-detector", status="proposed", summary=HOSTILE, objections=(HOSTILE,),
                         owner={"tagOwner": HOSTILE, "createdBy": HOSTILE, "changedBy": HOSTILE, "lookedUp": True}, facts={"basis": HOSTILE, "sku": HOSTILE})
        action = make_action(result=HOSTILE, error=HOSTILE, verification={"gone": True, "note": HOSTILE, "costAfterUsd": 1.0}, state="failed")
        person = Person(OID, HOSTILE, (HOSTILE,), "maya@example.com")
        contacts = (HOSTILE, HOSTILE)
        return {
            "first contact": letters.first_contact_letter(person, BASE, NOW, contacts, plan.plan_id),
            "approval": letters.approval_letter(plan, case, person, BASE, NOW, contacts),
            "digest": letters.digest_letter(person, BASE, NOW, [(plan, case), (dataclasses.replace(plan, plan_id="p2"), dataclasses.replace(case, case_id="c2", status="needs_human"))], contacts),
            "done": letters.done_letter(plan, action, case, person, BASE, NOW, contacts),
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
                self.assertEqual(parsed.tags.count("a"), 1)
                self.assertEqual(len(hrefs(letter)), 1)
                for address in hrefs(letter):
                    self.assertRegex(address, LINK_PATHS)
                self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", letter.html)
                self.assertIn("&quot;&gt;&lt;script&gt;", letter.html)
                self.assertIn("&#x27;quote&#x27;", letter.html)

    def test_what_a_name_holds_is_cut_down_to_one_line_without_control_or_direction_characters(self):
        for kind, letter in self.hostile().items():
            with self.subTest(letter=kind):
                self.assertNotIn("\u202e", letter.text + letter.html)
                self.assertNotIn("\x00", letter.text + letter.html)
                self.assertIn(HOSTILE_ONE_LINE[:100].rstrip(), letter.text)
                self.assertEqual(len(letter.subject.splitlines()), 1)

    def test_the_subject_never_holds_what_came_from_azure_or_from_a_person(self):
        for kind, letter in self.hostile().items():
            with self.subTest(letter=kind):
                for piece in ("<", ">", '"', "script", "quote", "\u202e", "\x00", "\n", "\r"):
                    self.assertNotIn(piece, letter.subject)

    def test_the_address_of_the_console_must_be_an_address_and_nothing_more(self):
        for bad in ("", "host", "ftp://host", "http://host.example", "https://host/a b", "https://host/..", "https://host/a/../b", "https://host?x=1",
                    "https://host#x", "javascript:alert(1)", 'https://host"><script>', "https://user@host", "https://host.example\n/x"):
            with self.subTest(base=bad):
                with self.assertRaises(ValueError):
                    letters.first_contact_letter(PERSON, bad, NOW)
        for good, link in (("https://host.example", "https://host.example/"), ("https://host.example/", "https://host.example/"),
                           (" https://host.example/api\n", "https://host.example/api/"),
                           ("https://host.example:8443/api", "https://host.example:8443/api/"), ("http://localhost:7071", "http://localhost:7071/"),
                           ("http://127.0.0.1:7071/api", "http://127.0.0.1:7071/api/")):
            with self.subTest(base=good):
                self.assertEqual(hrefs(letters.first_contact_letter(PERSON, good, NOW)), [link])


class WhatTheModuleIs(unittest.TestCase):
    source = (Path(support.APP_ROOT) / "cases" / "letters.py").read_text(encoding="utf-8")

    def test_it_imports_only_the_standard_library_the_brief_and_the_records(self):
        allowed = {"__future__", "datetime", "html", "math", "re", "unicodedata", "dataclasses", "typing", "urllib"}
        for node in ast.walk(ast.parse(self.source)):
            if isinstance(node, ast.Import):
                self.assertLessEqual({a.name.split(".")[0] for a in node.names}, allowed)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 1:
                    self.assertLessEqual({a.name for a in node.names} if node.module is None else {node.module}, {"brief", "models", "people"})
                else:
                    self.assertIn((node.module or "").split(".")[0], allowed)

    def test_it_reads_no_clock_and_does_no_input_or_output(self):
        for pattern in (r"\.(now|utcnow|today)\(", r"\bimport time\b", r"\btime\.(time|sleep|monotonic)\(", r"\bopen\(", r"\bprint\(", r"\bos\.", r"\bsys\.", r"\burlopen",
                        r"\bsocket", r"\blogging"):
            self.assertIsNone(re.search(pattern, self.source), pattern)


if __name__ == "__main__":
    unittest.main()
