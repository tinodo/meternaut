"""What a person reads never calls the function app a console: not a page, a message of the sign-in, a letter or a card, and no text in the code.

The module and the function that are named `console`, the trigger `console` of a check that a person started and the name of its logger are names and stored values. They stay, and
they are no sentence: only those exact strings are allowed in the code.
"""
import ast
import re
import unittest

import test_delegated as sign_in
from support import APP_ROOT
from test_web_accessibility import gallery
from test_web_ops import check_console
from test_web_support import HOST, NOW, PEOPLE, TINO, Console, at

from cases import cards, delegated, letters
from cases.models import CheckRecord

WORD = re.compile(r"\bconsole\b", re.IGNORECASE)
NAMES = {"console", "meternaut.console"}


def operations_pages() -> dict:
    """The Operations page in the states that have words of their own: no check or file service, a check that a person started (with and without a name), one of the timer."""
    plain = Console()
    pages = {"no service": plain.get("/ops"), "start refused": plain.post("/ops/drift", {"nonce": plain.store.nonce_new(TINO, "drift")}),
             "file refused": plain.post("/ops/answers", {"nonce": plain.store.nonce_new(TINO, "answers")})}
    for label, trigger, by in (("a person", "console", "Tino"), ("a person without a name", "console", ""), ("the timer", "timer", "")):
        for reported in (False, True):
            console = check_console()
            console.store.check_put(CheckRecord(started_at=at(minutes=-5), trigger=trigger, by=by, finished_at=at(minutes=-4) if reported else "", results=()))
            pages[f"started by {label}, reported {reported}"] = console.get("/ops")
    return pages


def strings_of_the_code():
    """Every string in the code of the app that is no docstring: what the code shows, sends or logs."""
    for path in [APP_ROOT / "function_app.py", *sorted((APP_ROOT / "cases").rglob("*.py"))]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {id(node.body[0].value) for node in ast.walk(tree) if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                      and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                yield path.name, node.value


class Says:
    def said(self, texts: dict) -> None:
        for label, text in texts.items():
            with self.subTest(text=label):
                found = WORD.search(text)
                self.assertFalse(found, found and f"{label}: ...{text[max(0, found.start() - 40):found.end() + 40]}...")


class TheWordsOfTheFunctionApp(Says, unittest.TestCase):
    def test_no_page_says_it(self):
        self.said({name: reply.text for name, reply in {**gallery(), **operations_pages()}.items()})

    def test_no_letter_or_card_says_it(self):
        letter = letters.first_contact_letter(PEOPLE.by_oid(TINO), f"https://{HOST}", NOW)
        self.said({"letter subject": letter.subject, "letter text": letter.text, "letter page": letter.html, "card": repr(cards.first_contact_card("Tino", f"https://{HOST}"))})

    def test_no_text_in_the_code_says_it(self):
        self.said({f"{name}: {text[:60]}": text for name, text in strings_of_the_code() if text not in NAMES})


class TheWordsOfTheSignIn(Says, sign_in.Flow):
    def test_no_message_of_the_sign_in_says_it(self):
        texts = {}
        for label, claims in (("another account", {"oid": sign_in.OTHER}), ("another tenant", {"tid": sign_in.OTHER}), ("a token that is not accepted", {"exp": None})):
            self.setUp()
            self.claims = sign_in.good_claims(**claims)
            texts[label] = self.whole().message
        for number in ("", *delegated.CONSENT, *delegated.AGAIN, *delegated.POLICY, *delegated.USED, *delegated.SETUP):
            for error in ("", "access_denied", "interaction_required", "consent_required"):
                texts[f"explain {error} {number}"] = delegated.explain(error, number)
                texts[f"step-up {error} {number}"] = delegated.explain_stepup(error, number)
        self.said(texts)
