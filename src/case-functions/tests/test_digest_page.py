"""The weekly letter counts and lists the decisions as the Decisions page does, for the same requests of the same person.

The weekly desk of cases/notify.py is run on the store that the page reads. The letter takes its rows from the code of the page (cases/stake.decisions_of over cases/web/home.py), so the number
in its subject is the number that the page says, findings of one kind about several resources are one line ("3 storage accounts in 3 resource groups") and not one line for each, what a person
put off is last, and a request that a person may not answer is not counted. The real mail of 2026-11-10 said "8 decisions" while the page said 5, and listed two of four storage accounts.
"""
import html
import json
import re
import unittest

import support  # noqa: F401  (puts the app on the path)
from cases import loop_config, notify, people as people_mod
from cases.models import SettingsRecord
from test_letters import make_run
from test_notify import ENV, Graph
from test_web_pages import busy, rows, seeded, storage
from test_web_support import NOW, OWNER, TINO, Console, make_advice, make_advice_case, make_case, make_decision, make_plan


def desk(console: Console, env: dict = ENV) -> Graph:
    """The weekly desk of the people of `env`, run at the moment of the page, on the store that the page reads. Returns what Graph was asked to send."""
    graph = Graph()
    people = people_mod.load(env)
    for person in people.persons:
        console.store.settings_put(SettingsRecord(oid=person.oid, desk_day=NOW.isoweekday()))
    _, _, on_run = notify.hooks(env, loop_config.load(env), console.store, people, lambda resource: "token", lambda text: text, transport=graph, sleep=lambda s: None,
                                monotonic=lambda: 0.0, clock=lambda: NOW)
    on_run(make_run())
    return graph


def listed(content: str) -> list[str]:
    """The lines of the list of a letter, as a person reads them."""
    return [html.unescape(re.sub(r"<[^>]+>", "", item)) for item in re.findall(r"<li[^>]*>(.*?)</li>", content, re.S)]


def page_count(reply) -> int:
    return int(re.match(r"(\d+) decisions?\.", reply.main.find("div", class_="head").find("p").text()).group(1))


def page_titles(reply) -> list[str]:
    focus = reply.main.find("article", class_="focus")
    return [focus.find("h3").text()] + [row.find("span", class_="t").text() for lane in ("ready", "look") for row in rows(reply, lane)]


class TheLetterCountsWhatThePageCounts(unittest.TestCase):
    def test_the_number_in_the_subject_is_the_number_of_the_page_and_the_lines_are_rows_of_the_page(self):
        console = busy()
        reply = console.get("/")
        graph = desk(console)
        (subject,) = graph.subjects()
        content = graph.sent[0][1]["body"]["content"]
        self.assertEqual(page_count(reply), 8, "three storage accounts are one row")
        self.assertEqual(subject, "[Meternaut] 8 decisions wait for you")
        lines = listed(content)
        self.assertEqual(len(lines), 5)
        on_the_page = page_titles(reply)
        self.assertEqual(len(on_the_page), 8)
        for line in lines:
            self.assertIn(re.sub(r": [^:]*\.$", "", line), on_the_page, "a line of the letter has the title of a row of the page")
        self.assertIn("3 more wait on the page.", html.unescape(re.sub(r"<[^>]+>", " ", content)))
        self.assertEqual(content.count("https://"), 1)

    def test_findings_of_one_kind_about_several_resources_are_one_line_and_never_one_for_each(self):
        console = seeded()
        storage(console, 4)
        graph = desk(console)
        (subject,) = graph.subjects()
        self.assertEqual(subject, "[Meternaut] 2 decisions wait for you", "a change, and the four storage accounts as one decision")
        self.assertEqual(listed(graph.sent[0][1]["body"]["content"]),
                         ["4 storage accounts in 4 resource groups: costs $216 a year, saving not measured.", "Delete the unattached disk planted-disk-1: $86 a year, Expected."])
        self.assertEqual(page_count(console.get("/")), 2)

    def test_a_request_that_a_person_put_off_is_counted_and_last_as_on_the_page(self):
        console = seeded()
        console.store.case_put(make_advice_case())
        console.store.plan_put(make_advice())
        earlier = listed(desk(console).sent[0][1]["body"]["content"])
        self.assertEqual([line.split(":")[0] for line in earlier], ["Consider changing the virtual machine oversized-vm-1", "Delete the unattached disk planted-disk-1"], "the larger saving first")
        console.store.decision_put(make_decision(plan_id="plan0002", decision="later"))
        console.store.mails.clear()
        later = desk(console)
        self.assertEqual([line.split(":")[0] for line in listed(later.sent[0][1]["body"]["content"])],
                         ["Delete the unattached disk planted-disk-1", "Consider changing the virtual machine oversized-vm-1"], "what a person put off is last")
        self.assertIn("You chose to decide later", console.get("/").content)
        self.assertEqual(page_count(console.get("/")), 2, "it is counted, as the page counts it")
        self.assertEqual(later.subjects(), ["[Meternaut] 2 decisions wait for you"])

    def test_a_person_who_may_not_answer_a_request_is_not_told_of_it_and_may_answer_advice_as_an_owner(self):
        env = {**ENV, "CONSOLE_PEOPLE": json.dumps([{"oid": OWNER, "name": "Olga", "roles": ["owner"], "mail": "olga@example.com"}])}
        console = Console()
        console.store.case_put(make_case(plan_id="plan0001"))
        console.store.plan_put(make_plan(plan_id="plan0001", case_id="case0001", approvers=(OWNER,)))
        console.store.case_put(make_advice_case(plan_id="plan0002"))
        console.store.plan_put(make_advice(approvers=(OWNER,)))
        reply = console.get("/", oid=OWNER)
        self.assertEqual(page_count(reply), 1, "an owner who is no approver sees the advice and not the change")
        graph = desk(console, env)
        self.assertEqual(graph.subjects(), ["[Meternaut] 1 decision waits for you"])
        self.assertEqual([line.split(":")[0] for line in listed(graph.sent[0][1]["body"]["content"])], ["Consider changing the virtual machine oversized-vm-1"])


if __name__ == "__main__":
    unittest.main()
