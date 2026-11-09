"""One figure on the page, in the letter and on the card (AGENTS.md rule 34 and 36), and the words that no letter and no card says any more.

The page of a request, the letter and the Teams card are renders of one brief. They show the figure in one language: the figure a year (whole dollars, twelve times the month) and a month
(cents), its label and its basis or its reason in one line, and once that money is in US dollars; the title with the place under it; the risk, how sure and what a change leaves behind as
words; and one footer line. cases/stake.py sets the words of the code of the pages (cases/web/figures.py) for the letter and the card, and these tests hold the three together for every state
of the figure, so that they can never differ. Every name and number is INVENTED.
"""
import dataclasses
import re
import unittest

import support  # noqa: F401  (puts the app on the path)
from test_cards import by_id, texts, walk
from test_unread import case_and_plan, run_investigation, workspace_toolbox
from test_web_support import NOW as WEB_NOW, SUB, TINO, VM, Console, at, make_action, make_advice, make_advice_case, make_case, make_decision, make_plan

from cases import brief as brief_mod, cardcheck, cards, letters, offers, stake
from cases.models import GROUP_FACT
from cases.people import People, Person
from cases.web import figures

BASE = "https://meternaut.example"
PERSON = Person(TINO, "Tino", ("owner", "approver", "ops"), "tino@example.com")
CONTACTS = ("Olga (olga@example.com)", "Tino (tino@example.com)")
NONCE = "N0nce-0123456789abcdefghijklmnop"
MONEY = "Money is in US dollars, and a year is twelve times the month."
BANNED = ("No figure", "No saving is shown", "Talk to a person", "Decide:", "saving: about")
WAITING = re.compile(r" Waiting costs about \$[\d,.]+ a day\.$")
YEAR = re.compile(r"(?:\$[\d,]+|under \$1) a year")


class Case:
    """One request in one state: its records, and how it is shown (a request that waits is a decision letter and a decision card, one that ran is a letter and a card of what became of it)."""

    def __init__(self, label, case, plan, action=None, decisions=(), basis_in_letter=True, verified=False):
        self.label, self.case, self.plan, self.action, self.decisions = label, case, plan, action, list(decisions)
        self.basis_in_letter, self.verified = basis_in_letter, verified

    @property
    def open(self) -> bool:
        return self.plan.state == "open"

    def brief(self):
        return brief_mod.build_brief(self.case, self.plan, self.action, self.decisions, now=WEB_NOW, may_answer=True)

    def letter(self):
        if self.open:
            return letters.approval_letter(self.plan, self.case, PERSON, BASE, WEB_NOW, CONTACTS)
        return letters.done_letter(self.plan, self.action, self.case, PERSON, BASE, WEB_NOW, CONTACTS)

    def card(self):
        b = self.brief()
        ctx = cards.CardContext(page_url=f"{BASE}/ok/{b.plan_id}", nonce=NONCE if self.open else "", contacts=CONTACTS)
        return cards.card_for(b, ctx)

    def page(self):
        console = Console()
        console.store.case_put(self.case)
        console.store.plan_put(self.plan)
        if self.action is not None:
            console.store.action_put(self.action)
        for decision in self.decisions:
            console.store.decision_put(decision)
        return console.get(f"/ok/{self.plan.plan_id}")


def storage_account(plan_id, saving, cost, **changes) -> tuple:
    """A finding about one storage account that nobody may change: a request to look at it."""
    case = make_advice_case(case_id=f"case-{plan_id}", resource_id=f"{VM}-{plan_id}", resource_name=f"st-{plan_id}", resource_type="microsoft.storage/storageaccounts", resource_group="rg-st",
                            saving_usd_month=saving, cost_usd_30d=cost, plan_id=plan_id, **changes)
    plan = make_advice(plan_id=plan_id, case_id=f"case-{plan_id}", resource_id=f"{VM}-{plan_id}", resource_name=f"st-{plan_id}", resource_group="rg-st", saving_usd_month=saving,
                       title=f"Look at the storage account st-{plan_id} in group rg-st")
    return case, plan


def private_endpoints() -> tuple:
    """One finding that stands for 50 private endpoints in 8 resource groups, and the one request about all of them."""
    rid = f"/subscriptions/{SUB}/resourceGroups/rg-pe/providers/Microsoft.Network/privateEndpoints/pe-1"
    group = {"count": 50, "groups": 8, "type": "microsoft.network/privateendpoints", "names": ["pe-2", "pe-3", "pe-4", "pe-5"], "costUsd30d": 358.11}
    case = make_advice_case(case_id="case6000", resource_id=rid, resource_name="pe-1", resource_type="microsoft.network/privateendpoints", resource_group="rg-pe", saving_usd_month=None,
                            cost_usd_30d=358.11, plan_id="plan6000", facts={"basis": "idle", GROUP_FACT: group})
    plan = make_advice(plan_id="plan6000", case_id="case6000", resource_id=rid, resource_name="pe-1", resource_group="rg-pe", saving_usd_month=None, title="Look at 50 private endpoints")
    return case, plan


def decision_cases() -> list[Case]:
    """The requests that wait, one for each state of the figure and each kind of request."""
    cost_only = storage_account("plan5000", None, 358.11)
    zero = storage_account("plan5001", None, 0.0)
    unknown = storage_account("plan5002", None, None)
    tier = (make_case(case_id="case8000", resource_name="premium-disk-1", saving_usd_month=None, cost_usd_30d=80.0, plan_id="plan8000"),
            make_plan(plan_id="plan8000", case_id="case8000", family="change-disk-tier", resource_name="premium-disk-1", saving_usd_month=None, waiting_costs_usd_day=None))
    workspace, workspace_plan = case_and_plan(run_investigation(workspace_toolbox()))
    return [
        Case("a saving that is Expected", make_case(plan_id="plan0001"), make_plan()),
        Case("a saving that is a Scenario", make_advice_case(), make_advice()),
        Case("a cost that nothing has measured a saving for", *cost_only),
        Case("no cost line in the last 30 days", *zero),
        Case("no cost line read yet", *unknown),
        Case("a reason of the finding's own", *tier),
        Case("one request for many resources", *private_endpoints()),
        Case("the data that nothing reads", workspace, workspace_plan, basis_in_letter=False),
    ]


def done_cases() -> list[Case]:
    """Changes that ran: one that cost lines confirmed, one that they did not yet, and the ones that did not run or changed nothing."""
    approval = make_decision(at=at(minutes=-40))
    done = dict(finished_at=at(minutes=-30), result="Deleted. Azure no longer lists the resource.", verification={"gone": True})
    consumed = make_plan(state="consumed")
    return [
        Case("a change that ran, not yet confirmed", make_case(plan_id="plan0001"), consumed, make_action(state="done", **done), [approval]),
        Case("a change that cost lines confirmed", make_case(plan_id="plan0001"), consumed,
             make_action(state="verified", verified_at=at(minutes=-5), **{**done, "verification": {"gone": True, "costAfterUsd": 0.0, "costBeforeUsd30d": 7.17, "currency": "USD"}}), [approval],
             verified=True),
        Case("a change with no figure", make_case(plan_id="plan0001", saving_usd_month=None, cost_usd_30d=None), make_plan(state="consumed", saving_usd_month=None),
             make_action(state="done", **done), [approval]),
        Case("a change that failed", make_case(plan_id="plan0001"), make_plan(state="failed"), make_action(state="failed", error="Azure refused the change.", finished_at=at(minutes=-30)), [approval]),
        Case("a change that is not known to have run", make_case(plan_id="plan0001"), consumed, make_action(state="unknown", result="Azure still lists it."), [approval]),
        Case("an approval that changed nothing", make_case(plan_id="plan0001"), consumed,
             make_action(state="done", finished_at=at(minutes=-30), result="The disk was already deleted. Nothing to delete.", verification={"gone": True, "noChange": True}), [approval]),
    ]


def page_figure(reply) -> tuple[str, str]:
    """What the card of the request page says about the figure: the large line (a dash when there is none) and the line under it, without what waiting costs."""
    card = reply.main.find("section", class_="focus")
    year = next(p.text() for p in card.find_all("p") if "fig" in p.classes())
    sub = next(p.text() for p in card.find_all("p") if "figsub" in p.classes())
    return year, WAITING.sub("", sub)


def letter_figure(letter) -> tuple[str, str, str]:
    """The year, the line under it and the line about money that a letter says, from its text ("" for what is not there)."""
    lines = letter.text.splitlines()
    for number, line in enumerate(lines):
        if re.match(r"(Saves, |Costs, saving not measured|Cost not visible)", line):
            year = lines[number - 1] if number and YEAR.fullmatch(lines[number - 1]) else ""
            money = lines[number + 1] if number + 1 < len(lines) and lines[number + 1] == MONEY else ""
            return year, line, money
    raise AssertionError("the letter has no figure")


def card_figure(card) -> tuple[str, str, str]:
    found = by_id(card)
    sub = f"{found['saving-word']['text']} {found['price-basis']['text']}"
    return found["value"]["text"] if "value" in found else "", sub, found["money"]["text"] if "money" in found else ""


def page_chips(reply) -> list[str]:
    return [span.text() for span in reply.main.find("p", class_="chips").find_all("span") if "chip" in span.classes()]


class ThePageTheLetterAndTheCardShowOneFigure(unittest.TestCase):
    def test_the_year_the_month_the_label_and_the_basis_are_the_same_on_all_three_in_every_state_of_the_figure(self):
        for fixture in decision_cases():
            with self.subTest(fixture.label):
                page_year, page_sub = page_figure(fixture.page())
                letter_year, letter_sub, letter_money = letter_figure(fixture.letter())
                card_year, card_sub, card_money = card_figure(fixture.card())
                shown = page_year != "—"
                self.assertEqual(letter_year, page_year if shown else "")
                self.assertEqual(card_year, page_year if shown else "")
                self.assertEqual(card_sub, page_sub)
                if fixture.basis_in_letter:
                    self.assertEqual(letter_sub, page_sub)
                else:
                    self.assertTrue(page_sub.startswith(letter_sub), "a letter that says the basis in the lines that follow leaves it out of the line of the figure")
                self.assertEqual((letter_money, card_money), (MONEY, MONEY) if shown else ("", ""), "said once, where an amount is shown")

    def test_a_change_that_ran_shows_the_figure_of_the_page_and_says_verified_only_when_the_cost_lines_confirm_it(self):
        for fixture in done_cases()[:3]:
            with self.subTest(fixture.label):
                page_year, page_sub = page_figure(fixture.page())
                letter_year, letter_sub, _ = letter_figure(fixture.letter())
                card_year, card_sub, _ = card_figure(fixture.card())
                shown = page_year != "—"
                self.assertEqual((letter_year, card_year), (page_year, page_year) if shown else ("", ""))
                self.assertEqual(card_sub, page_sub)
                self.assertTrue(letter_sub.startswith(page_sub), (letter_sub, page_sub))
                self.assertEqual("Verified" in letter_sub, fixture.verified)
                self.assertEqual("Verified" in card_sub, fixture.verified)

    def test_the_title_the_chips_and_the_place_are_those_of_the_page(self):
        for fixture in decision_cases():
            with self.subTest(fixture.label):
                reply, letter, found = fixture.page(), fixture.letter(), by_id(fixture.card())
                (title,) = reply.headings(1)
                self.assertEqual(letter.text.splitlines()[0], title)
                self.assertEqual(found["headline"]["text"], title)
                chips = page_chips(reply)
                self.assertEqual(found["chips"]["text"], ", ".join(chips))
                self.assertIn(", ".join(chips) + "\n", letter.text)
                if fixture.brief().group is None:
                    page_place = reply.main.find("div", class_="head").find("p").text().split(" · ")[:2]
                    self.assertEqual(found["place"]["text"], ", ".join(page_place))
                    self.assertIn(", ".join(page_place) + "\n", letter.text)
                else:
                    self.assertNotIn("place", found, "a request for many resources has no place of its own: its title counts the resources and the groups")

    def test_the_line_that_says_what_money_is_in_is_said_in_the_words_of_the_page(self):
        reply = decision_cases()[0].page()
        self.assertIn(MONEY, reply.main.text())
        self.assertEqual(stake.MONEY, MONEY)

    def test_the_title_is_the_one_of_the_code_of_the_pages_and_never_the_headline_with_its_place(self):
        for fixture in decision_cases():
            with self.subTest(fixture.label):
                b = fixture.brief()
                self.assertEqual(stake.title_text(b), figures.title_of(b)[1])
                self.assertNotIn(" in group ", stake.title_text(b))
                self.assertFalse(stake.title_text(b).startswith("Look at "))

    def test_the_cost_that_the_brief_holds_is_the_one_that_the_pages_read(self):
        for fixture in decision_cases() + done_cases():
            with self.subTest(fixture.label):
                b = fixture.brief()
                self.assertEqual(b.cost, figures.cost_of(b, fixture.case))
                self.assertEqual(stake.stake_of(b).state, figures.figure_of([b.saving], [figures.cost_of(b, fixture.case)]).state)
        self.assertIsNone(brief_mod.build_brief(None, make_plan(), now=WEB_NOW).cost, "no case, no cost line")
        self.assertEqual(brief_mod.build_brief(make_case(cost_usd_30d=float("nan")), None, now=WEB_NOW).cost, None, "a number that is not a number is not a cost")
        self.assertEqual(brief_mod.build_brief(make_case(cost_usd_30d=0.0), None, now=WEB_NOW).cost, 0.0)


class TheFigureInWords(unittest.TestCase):
    def of(self, **changes):
        case, plan = storage_account("plan5000", changes.pop("saving", 30.0), changes.pop("cost", 41.2), **changes)
        return stake.stake_of(brief_mod.build_brief(case, plan, now=WEB_NOW))

    def test_a_saving_is_a_year_in_whole_dollars_a_month_in_cents_its_label_and_its_basis(self):
        found = self.of()
        self.assertEqual((found.state, found.level, found.year, found.month, found.label), ("save", "Scenario", "$360 a year", "$30.00", "Saves, Scenario"))
        self.assertEqual(found.note, "Based on Azure Advisor's own estimate: no cost line of this resource backs it.")
        self.assertEqual(found.line, "Saves, Scenario. $30.00 a month. Based on Azure Advisor's own estimate: no cost line of this resource backs it.")
        self.assertEqual(found.short, "$360 a year, Scenario")
        self.assertEqual(found.money, MONEY)

    def test_a_cost_is_the_most_that_a_change_could_save_and_says_that_nothing_measured_a_saving(self):
        found = self.of(saving=None, cost=358.11)
        self.assertEqual((found.state, found.level, found.year, found.month, found.label), ("cost", "", "$4,297 a year", "$358.11", "Costs, saving not measured"))
        self.assertEqual(found.line, "Costs, saving not measured. $358.11 a month. The most that a change could save: what it would save was not worked out.")
        self.assertEqual(found.short, "costs $4,297 a year, saving not measured")
        self.assertEqual(found.money, MONEY)

    def test_nothing_that_can_be_shown_says_why_and_shows_no_year_no_month_and_no_money_line(self):
        for cost, why in ((0.0, "No cost line in the last 30 days."), (None, "No cost line was read yet.")):
            with self.subTest(cost=cost):
                found = self.of(saving=None, cost=cost)
                self.assertEqual((found.state, found.year, found.month, found.label, found.note), ("none", "", "", "Cost not visible", why))
                self.assertEqual((found.line, found.short, found.money), (f"Cost not visible. {why}", "cost not visible", ""))

    def test_a_year_is_twelve_times_the_month_in_whole_dollars(self):
        for monthly, year in ((7.17, "$86"), (41.2, "$494"), (140.16, "$1,682"), (358.11, "$4,297"), (0.03, "under $1")):
            with self.subTest(monthly=monthly):
                found = self.of(saving=monthly, cost=monthly)
                self.assertEqual(found.year, f"{year} a year")
                self.assertEqual(found.year, f"{figures.a_year(monthly)} a year")
                self.assertEqual(found.month, figures.dollars(monthly))

    def test_the_chips_are_words_the_risk_how_sure_and_what_a_change_leaves_behind(self):
        change = brief_mod.build_brief(make_case(), make_plan(), now=WEB_NOW)
        self.assertEqual(stake.chips_of(change), ("Medium risk", "High confidence", "Cannot be undone"))
        reversible = dataclasses.replace(change, undo=dataclasses.replace(change.undo, reversible=True), risk=dataclasses.replace(change.risk, level="low"))
        self.assertEqual(stake.chips_of(reversible), ("Low risk", "High confidence", "Can be undone"))
        advice = brief_mod.build_brief(make_advice_case(), make_advice(), now=WEB_NOW)
        self.assertEqual(stake.chips_of(advice)[2], "Changes nothing in Azure")
        odd = dataclasses.replace(change, risk=dataclasses.replace(change.risk, level="weird"))
        self.assertEqual(stake.chips_of(odd)[0], "Medium risk", "a risk that is not a risk is read as the middle one, as on the page")
        self.assertEqual(len(stake.chips_of(brief_mod.build_brief(make_case(), None, now=WEB_NOW))), 2, "a case without a request says nothing of an answer")

    def test_the_place_is_the_kind_of_resource_and_its_group_and_a_request_for_many_resources_has_none(self):
        case, plan = storage_account("plan5000", 30.0, 41.2)
        self.assertEqual(stake.place_of(brief_mod.build_brief(case, plan, now=WEB_NOW)), "Storage account, resource group rg-st")
        self.assertEqual(stake.place_of(brief_mod.build_brief(dataclasses.replace(case, resource_group=""), dataclasses.replace(plan, resource_group=""), now=WEB_NOW)), "Storage account")
        self.assertEqual(stake.place_of(brief_mod.build_brief(*private_endpoints(), now=WEB_NOW)), "")


class NoLetterAndNoCardSaysTheOldWords(unittest.TestCase):
    def gallery(self):
        """Every letter and every card of every state that the code makes, as (what it is, its text)."""
        found = []
        for fixture in decision_cases() + done_cases():
            found.append((f"letter, {fixture.label}", fixture.letter().text))
            found.append((f"card, {fixture.label}", " ".join(texts(fixture.card()))))
        waiting = [(fixture.plan, fixture.case) for fixture in decision_cases()]
        found.append(("digest of all", letters.digest_letter(PERSON, BASE, WEB_NOW, waiting, CONTACTS).text))
        for plan, case in waiting:
            found.append((f"digest of {plan.plan_id}", letters.digest_letter(PERSON, BASE, WEB_NOW, [(plan, case)], CONTACTS).text))
        found.append(("first contact", letters.first_contact_letter(PERSON, BASE, WEB_NOW, CONTACTS, "plan0001").text))
        found.append(("first contact, no request", letters.first_contact_letter(PERSON, BASE, WEB_NOW, CONTACTS).text))
        found.append(("first contact card", " ".join(texts(cards.first_contact_card("Tino", BASE, CONTACTS)))))
        closed = Case("declined", make_case(plan_id="plan0001"), make_plan(state="declined"), None, [make_decision(decision="decline")])
        found.append(("letter, a request that was answered", letters.approval_letter(closed.plan, closed.case, PERSON, BASE, WEB_NOW, CONTACTS).text))
        found.append(("card, a request that was answered", " ".join(texts(closed.card()))))
        return found

    def test_no_letter_and_no_card_says_no_figure_no_saving_is_shown_or_talk_to_a_person(self):
        gallery = self.gallery()
        self.assertGreaterEqual(len(gallery), 30)
        for what, text in gallery:
            with self.subTest(what):
                for old in BANNED:
                    self.assertNotIn(old, text)
                self.assertNotRegex(text, r"\bNo figure\b|\bNo saving is shown\b|(?i:\btalk to a person\b)|\bAbout \d[\d,.]* US dollars a month\b")

    def test_every_letter_text_is_plain_ascii_without_a_dash_between_figures_a_question_or_an_exclamation(self):
        for what, text in self.gallery():
            if "card" in what:
                continue
            with self.subTest(what):
                self.assertTrue(text.isascii())
                self.assertNotRegex(text, r"[?!]|\d\s*[\u2013\u2014]\s*\d|\u00b7")

    def test_the_old_source_words_are_gone_from_the_code_of_the_letters_and_the_cards(self):
        for name in ("letters.py", "cards.py", "stake.py"):
            source = (support.APP_ROOT / "cases" / name).read_text(encoding="utf-8")
            with self.subTest(name):
                for old in ("No figure", "No saving is shown", "Talk to a person", "saving_line", "usd_text"):
                    self.assertNotIn(old, source)

    def test_every_letter_and_card_ends_in_one_footer_line_with_the_models_why_and_who_is_responsible(self):
        for fixture in decision_cases() + done_cases():
            with self.subTest(fixture.label):
                letter, card = fixture.letter(), fixture.card()
                (footer,) = [line for line in letter.text.splitlines() if line.startswith("Written by an AI")]
                self.assertEqual(letter.text.rstrip().splitlines()[-1], footer)
                self.assertIn("a person approves every change.", footer)
                self.assertIn("You got this because", footer)
                self.assertTrue(footer.endswith("Responsible for Meternaut: Olga (olga@example.com)."), "the first of the contacts who is not the reader")
                last = card["body"][-1]
                self.assertEqual(last["id"], "ai-footer")
                self.assertTrue(last["text"].startswith("Written by an AI"))
                self.assertIn("a person approves every change.", last["text"])
                self.assertTrue(last["text"].endswith("Responsible for Meternaut: Olga (olga@example.com)."), last["text"])
                self.assertEqual(cardcheck.check(card), [])

    def test_a_subject_and_a_notification_text_hold_no_resource_name_and_no_amount(self):
        for fixture in decision_cases() + done_cases():
            with self.subTest(fixture.label):
                subject, summary = fixture.letter().subject, cards.message_activity(fixture.card(), "change" if fixture.open else "result")["summary"]
                for text in (subject, summary):
                    for name in (fixture.plan.resource_name, fixture.case.resource_name, fixture.plan.resource_group, fixture.plan.code):
                        self.assertNotIn(name, text)
                    self.assertNotRegex(text, r"[$\d]|US dollars|USD")
        waiting = [(fixture.plan, fixture.case) for fixture in decision_cases()]
        for count in (1, len(waiting)):
            digest = letters.digest_letter(PERSON, BASE, WEB_NOW, waiting[:count], CONTACTS)
            self.assertRegex(digest.subject, r"^\[Meternaut\] \d+ decisions? (waits?) for you$")
            self.assertNotRegex(digest.subject, r"[$]|US dollars|USD")

    def test_one_link_in_a_letter_and_one_in_a_card(self):
        for fixture in decision_cases() + done_cases():
            with self.subTest(fixture.label):
                letter = fixture.letter()
                self.assertEqual(letter.html.count('href="'), 1)
                self.assertEqual(re.findall(r'href="([^"]*)"', letter.html), [f"{BASE}/ok/{fixture.plan.plan_id}"])
                urls = {node["url"] for node in walk(fixture.card()) if "url" in node}
                self.assertEqual(urls, {f"{BASE}/ok/{fixture.plan.plan_id}"})

    def test_the_button_of_a_decision_is_review_and_decide_in_the_letter_and_on_the_card_and_a_card_keeps_its_actions(self):
        for fixture in decision_cases():
            with self.subTest(fixture.label):
                if fixture.brief().kind == "change":
                    self.assertIn(">Review and decide<", fixture.letter().html)
                    titles = [a["title"] for a in by_id(fixture.card())["decisions"]["actions"]]
                    self.assertEqual(titles[0], "Review and decide")
                else:
                    titles = [a["title"] for a in by_id(fixture.card())["decisions"]["actions"]]
                    self.assertEqual(titles[:2], ["Worth acting on", "Not worth it"])
                self.assertNotIn(">Decide<", fixture.letter().html)


class TheCardNamesOnePersonWhoIsResponsible(unittest.TestCase):
    PEOPLE = People((Person(TINO, "Tino", ("owner", "approver", "ops"), "tino@example.com"), Person("22222222-3333-4444-5555-666666666666", "Olga", ("owner",), "olga@example.com"),
                     Person("33333333-4444-5555-6666-777777777777", "Otto", ("ops",), "")))

    def test_it_is_the_first_of_the_owners_and_the_people_of_operations_who_is_not_the_reader(self):
        self.assertEqual(offers.contacts_of(self.PEOPLE, TINO), ("Olga (olga@example.com)", "Otto"))
        self.assertEqual(offers.contacts_of(self.PEOPLE, TINO.upper()), ("Olga (olga@example.com)", "Otto"), "an object id is the same in capitals")
        self.assertEqual(offers.contacts_of(self.PEOPLE, "22222222-3333-4444-5555-666666666666"), ("Tino (tino@example.com)", "Otto"))
        self.assertEqual(offers.contacts_of(self.PEOPLE), ("Tino (tino@example.com)", "Olga (olga@example.com)", "Otto"), "nobody is left out when there is no reader")

    def test_a_reader_who_is_the_only_one_listed_is_named_as_the_page_does(self):
        alone = People((Person(TINO, "Tino", ("owner", "approver"), "tino@example.com"),))
        self.assertEqual(offers.contacts_of(alone, TINO), ("Tino (tino@example.com)",))

    def test_the_footer_of_a_card_names_one_person_and_leaves_the_sentence_out_when_there_is_none(self):
        line = cards.footer(("m1",), "You got this because you are on my list of people.", ("Olga (olga@example.com)", "Otto"))["text"]
        self.assertEqual(line, "Written by an AI (models: m1); a person approves every change. You got this because you are on my list of people. Responsible for Meternaut: Olga (olga@example.com).")
        self.assertNotIn("Responsible", cards.footer((), "Why.", ())["text"])
        first = cards.first_contact_card("Maya", BASE, offers.contacts_of(self.PEOPLE, TINO))
        self.assertTrue(by_id(first)["ai-footer"]["text"].endswith("Responsible for Meternaut: Olga (olga@example.com)."))


if __name__ == "__main__":
    unittest.main()
