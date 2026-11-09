import re
import unittest

from test_web_pages import busy
from test_web_support import (MAYA, NOW, STRANGER, TINO, Console, FailingStore, ScriptedDecider, ScriptedDelegate, at, make_action, make_advice, make_advice_case, make_case,
                              make_decision, make_plan, make_run)

from cases.models import Begun, DecideResult, NoteRecord, SwitchRecord
from cases.web import approval, layout

APPROVE = "Approve and sign in to Azure"
KINDS = ("declined", "asked", "later", "acknowledged", "not_mine", "ran", "ran_unconfirmed", "running", "unchanged", "stopped", "azure_refused", "failed", "signin_failed",
         "step_up_failed", "refused_code", "refused_state", "refused_role", "refused_paused", "expired", "duplicate", "error")
SUCCESSES = ("declined", "asked", "later", "acknowledged", "not_mine", "ran", "ran_unconfirmed", "running", "unchanged")
# The pages that show text that an AI wrote, or a list of requests: their footer says that an AI wrote them. The others (the settings, the notes, Operations, the permissions and the
# kill switch) hold no AI text and their footer has no such sentence.
NOT_AI = ("GET /me/settings", "GET /me/notes", "GET /ops", "GET /ops/permissions", "GET /ops/pause", "settings with problems", "settings saved", "notes with problems",
          "kill switch paused", "pause degraded", "ops degraded", "store down case", "store down plan", "GET wrong role", "no such note", "no token", "413", "415", "405",
          "GET /nothing", "denied")
# What each step says in practice, for the kinds whose page shows the message of the result.
MESSAGES = {
    "ran": "Deleted. Azure no longer lists the resource.",
    "ran_unconfirmed": "Azure accepted the delete and still lists the resource. The next check will look again.",
    "running": "Azure accepted the change and is still making it. Meternaut reads the resource again in a few minutes and records what it finds. It makes no second try: if it does not "
               "work, a new try is a new approval by a person.",
    "unchanged": "The machine was already stopped and released when Meternaut looked. Nothing to change.",
    "stopped": "Stopped before the change: the disk is not unattached any more. Nothing was changed.",
    "azure_refused": "Azure refused to delete the resource (403, AuthorizationFailed): your account has no right to do this here. Nothing was changed.",
    "failed": "The delete was refused or failed (500 InternalError). Check the resource before anything is tried again.",
    "signin_failed": "The sign-in to Azure was cancelled or refused. Nothing is approved.",
    "step_up_failed": "The extra sign-in check that Azure asked for was not completed. It was cancelled or refused. The change was not made. Nothing was changed. The request is closed.",
    "refused_state": "This sign-in is not valid any more: it was used already, it ran out of time, or somebody else started it. Nothing was changed.",
    "error": "This form is no longer valid. Open the link in the message again. Nothing is approved.",
}
RETURN = {"code": "0.AbCdEfGhIjKlMnOpQrSt-code-from-the-sign-in", "state": "state-of-the-sign-in_0123456789"}
LIGHT_DARK_PAIRS = (
    ("colorNeutralForeground1", "colorNeutralBackground1", 4.5), ("colorNeutralForeground2", "colorNeutralBackground1", 4.5), ("colorNeutralForeground3", "colorNeutralBackground1", 4.5),
    ("colorNeutralForeground1", "colorNeutralBackground2", 4.5), ("colorNeutralForeground2", "colorNeutralBackground2", 4.5), ("colorNeutralForeground1", "colorNeutralBackground3", 4.5),
    ("colorNeutralForeground2", "colorNeutralBackground3", 4.5), ("colorNeutralForegroundOnBrand", "colorBrandBackground", 4.5),
    ("colorNeutralForegroundOnBrand", "colorBrandBackgroundHover", 4.5), ("colorBrandForegroundLink", "colorNeutralBackground1", 4.5),
    ("colorBrandForegroundLink", "colorNeutralBackground3", 4.5), ("colorNeutralForeground1", "colorPaletteBlueBackground1", 4.5),
    ("colorNeutralForeground1", "colorPaletteGreenBackground1", 4.5), ("colorNeutralForeground1", "colorPaletteYellowBackground1", 4.5),
    ("colorNeutralForeground1", "colorPaletteRedBackground1", 4.5), ("colorPaletteRedForeground1", "colorNeutralBackground1", 4.5),
    ("colorPaletteRedForeground1", "colorNeutralBackground3", 4.5),
    # parts of a control or a state, which need 3 to 1
    ("colorNeutralStrokeAccessible", "colorNeutralBackground1", 3.0), ("colorStrokeFocus2", "colorNeutralBackground1", 3.0), ("colorBrandStroke1", "colorNeutralBackground1", 3.0),
    ("colorPaletteRedBorder1", "colorNeutralBackground1", 3.0), ("colorBrandStroke1", "colorNeutralBackground2", 3.0),
)


def luminance(colour: str) -> float:
    colour = colour.lstrip("#")
    channels = [int(colour[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"--([A-Za-z0-9]+):(#[0-9a-fA-F]{6})", block))


def style_blocks() -> tuple[dict[str, str], dict[str, str]]:
    """The tokens of the light theme and of the dark theme (which is the light one with the dark values over it)."""
    style = layout.STYLE
    dark_block = style[style.index("@media (prefers-color-scheme:dark)"):style.index("*,*::before")]
    light_block = style[:style.index("@media (prefers-color-scheme:dark)")]
    light = tokens(light_block)
    dark = {**light, **tokens(dark_block)}
    return light, dark


def gallery() -> dict:
    """Pages of every kind: every page of the console, an approval in each state, every kind of answer, forms with problems, and the errors."""
    pages = {}
    console = Console(decider=ScriptedDecider(), delegate=ScriptedDelegate())
    console.seed()
    console.store.action_put(make_action())
    console.store.decision_put(make_decision())
    console.store.note_put(NoteRecord("n1", TINO, "note", "A note", f"/subscriptions/{'1' * 8}-1111-1111-1111-{'1' * 12}/resourceGroups/g/providers/p.q/t/n", "x", "you", at(days=-1), at(days=9), 1))
    console.store.case_put(make_case(case_id="case0002", status="error", summary="a reason", models={}, run_id="run00001"))
    console.store.run_put(make_run(run_id="run00002", ok=False, reason="a reason", finished_at=None))
    console.store.case_put(make_advice_case(case_id="case0005", plan_id="plan0005"))
    console.store.plan_put(make_advice(plan_id="plan0005", case_id="case0005"))
    for path in ("/", "/ok/plan0001", "/ok/plan0005", "/why/case0001", "/why/case0002", "/why/case0005", "/history", "/me/decisions", "/me/activity", "/me/settings",
                 "/me/notes", "/ops", "/ops/runs", "/ops/runs?run=run00001", "/ops/runs?run=%3C", "/ops/permissions", "/ops/pause", "/nothing", "/ok/nothing", "/why/nothing"):
        pages[f"GET {path}"] = console.get(path)
    pages["busy decisions"] = busy().get("/")
    pages["GET refused"] = console.get("/ok/plan0001", oid=MAYA)
    pages["GET wrong role"] = console.get("/ops/pause", oid=MAYA)
    pages["denied"] = console.get("/", oid=STRANGER)
    pages["405"] = console.post("/", {})
    pages["413"] = console.post("/me/notes", body=b"x" * 20000)
    pages["415"] = console.send("POST", "/me/notes", body="x", content_type="text/plain")
    pages["no token"] = console.post("/me/settings", {})
    pages["no such note"] = console.post("/me/notes/none/delete", {"nonce": "x"})
    for kind in KINDS:
        result = DecideResult(kind in SUCCESSES, kind, MESSAGES.get(kind, "a message of the result"), make_plan())
        console.decider.result = result
        console.delegate.begun = Begun(refusal=result)
        console.delegate.finished = result
        main = console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE)
        pages[f"answer {kind}"] = console.submit(main, "Decline")
        pages[f"begin {kind}"] = console.submit(main, APPROVE)
        pages[f"return {kind}"] = console.get("/arm/return", query=RETURN)
    form = console.get("/ok/plan0001").form("/ok/plan0001")
    pages["ask too long"] = console.submit(form, "Ask or tell", note="x" * 400)
    pages["ask empty"] = console.submit(form, "Ask or tell", note="")
    form = console.get("/ok/plan0005").form("/ok/plan0005")
    pages["advice ask too long"] = console.submit(form, "Ask or tell", note="x" * 400)
    form = console.get("/me/settings").form("/me/settings", has_button="Save settings")
    pages["settings with problems"] = console.post("/me/settings", {**form.fields, "channel": "x", "weekly_budget": "99"})
    pages["settings saved"] = console.post("/me/settings", console.get("/me/settings").form("/me/settings", has_button="Save settings").fields)
    form = console.get("/me/notes").form("/me/notes", has_button="Save")
    pages["notes with problems"] = console.post("/me/notes", {**form.fields, "kind": "x"})
    console.store.switch_put(SwitchRecord("changes", True, "Otto", at(minutes=-5), "drill"))
    pages["paused plan"] = console.get("/ok/plan0001")
    pages["kill switch paused"] = console.get("/ops/pause")
    console.store.switch_put(SwitchRecord("all", True, "Otto", at(minutes=-5), "drill"))
    pages["paused advice"] = console.get("/ok/plan0005")
    console.store.switch_put(SwitchRecord("all"))
    console.store.plan_put(make_advice(plan_id="plan0005", case_id="case0005", state="consumed"))
    pages["answered advice"] = console.get("/ok/plan0005")
    console.store.plan_put(make_advice(plan_id="plan0005", case_id="case0005", state="declined"))
    pages["declined advice"] = console.get("/ok/plan0005")
    console.store.plan_put(make_advice(plan_id="plan0005", case_id="case0005", expires_at=at(minutes=-1)))
    pages["expired advice"] = console.get("/ok/plan0005")
    console.store.plan_put(make_plan(state="approved"))
    pages["approved plan"] = console.get("/ok/plan0001")
    console.store.plan_put(make_plan(expires_at=at(minutes=-1)))
    pages["expired plan"] = console.get("/ok/plan0001")
    console.store.plan_put(make_plan(state="consumed"))
    console.store.action_put(make_action(state="done", finished_at=at(), result="Deleted.", verification={"gone": True}))
    pages["consumed plan"] = console.get("/ok/plan0001")
    console.store.plan_put(make_plan(state="failed"))
    console.store.action_put(make_action(state="failed", finished_at=at(), result=MESSAGES["azure_refused"], error=MESSAGES["azure_refused"]))
    pages["failed plan"] = console.get("/ok/plan0001")
    broken = Console(store=FailingStore(fail={"case_get", "plan_get"}, clock=lambda: NOW))
    broken.seed(case=False, plan=False, run=False)
    pages["store down case"] = broken.get("/why/x")
    pages["store down plan"] = broken.get("/ok/x")
    degraded = Console(store=FailingStore(fail={"plans_open", "runs_recent", "cases_recent", "switch_get"}, clock=lambda: NOW))
    pages["home degraded"] = degraded.get("/")
    pages["history degraded"] = degraded.get("/history")
    pages["ops degraded"] = degraded.get("/ops")
    pages["runs degraded"] = degraded.get("/ops/runs")
    pages["pause degraded"] = degraded.get("/ops/pause")
    return pages


class EveryPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = gallery()

    def each(self):
        for name, reply in self.pages.items():
            with self.subTest(page=name):
                yield name, reply

    def test_the_gallery_has_every_kind_of_page(self):
        self.assertGreaterEqual(len(self.pages), 85)
        statuses = {reply.status for reply in self.pages.values()}
        for status in (200, 400, 403, 404, 405, 409, 410, 413, 415, 500, 502, 503):
            self.assertIn(status, statuses)

    def test_the_gallery_has_the_page_of_every_kind_of_result_after_each_of_the_three_steps(self):
        self.assertEqual(set(KINDS), set(approval.STATUS), "the kinds of the tests are the kinds that the pages know")
        for kind in KINDS:
            for step in ("answer", "begin", "return"):
                with self.subTest(step=step, kind=kind):
                    self.assertIn(f"{step} {kind}", self.pages)

    def test_the_language_and_direction_are_set_and_the_page_has_a_title_and_a_viewport(self):
        for name, reply in self.each():
            html = reply.root.find("html")
            self.assertEqual((html.attrs["lang"], html.attrs["dir"]), ("en", "ltr"))
            title = reply.root.find("title").text()
            self.assertTrue(title)
            if name != "denied":
                self.assertTrue(title.endswith(" - Meternaut"), title)
            self.assertEqual(reply.root.find("meta", name="viewport").attrs["content"], "width=device-width, initial-scale=1")
            self.assertEqual(reply.root.find("meta", charset="utf-8").attrs["charset"], "utf-8")

    def test_one_h1_and_headings_that_do_not_skip_a_level(self):
        for name, reply in self.each():
            self.assertEqual(len(reply.headings(1)), 1, f"{name}: {reply.headings()}")
            levels = [int(n.tag[1]) for n in reply.root.walk() if re.fullmatch(r"h[1-6]", n.tag)]
            self.assertEqual(levels[0], 1)
            for before, after in zip(levels, levels[1:]):
                self.assertLessEqual(after, before + 1, f"{name}: h{before} then h{after}")

    def test_the_landmarks_are_there_once_each_and_the_skip_link_leads_to_the_main_part(self):
        for name, reply in self.each():
            counts = {tag: len(reply.root.find_all(tag)) for tag in ("header", "nav", "main", "footer")}
            if name == "denied":
                self.assertEqual(counts, {"header": 0, "nav": 0, "main": 1, "footer": 0})
                continue
            self.assertEqual(counts, {"header": 1, "nav": 1, "main": 1, "footer": 1}, name)
            self.assertEqual(reply.root.find("nav").attrs["aria-label"], "Pages")
            skip = reply.root.find("a", class_="skip")
            self.assertEqual(skip.attrs["href"], "#main")
            self.assertEqual(reply.root.find("main").attrs["id"], "main")
            self.assertEqual(reply.root.find("body").children[1].tag, "a", "the skip link comes first")

    def test_every_control_has_a_label_and_every_group_a_legend(self):
        for name, reply in self.each():
            labels = {}
            for label in reply.root.find_all("label"):
                self.assertIn("for", label.attrs, f"{name}: a label without for")
                labels[label.attrs["for"]] = label
            ids = [n.attrs["id"] for n in reply.root.walk() if "id" in n.attrs]
            self.assertEqual(len(ids), len(set(ids)), f"{name}: an id is used twice: {sorted(i for i in ids if ids.count(i) > 1)}")
            for control in reply.root.walk():
                if control.tag in ("input", "select", "textarea") and control.attrs.get("type") != "hidden":
                    self.assertIn(control.attrs.get("id"), labels, f"{name}: a {control.tag} without a label")
            for fieldset in reply.root.find_all("fieldset"):
                self.assertEqual(fieldset.children[0].tag, "legend", f"{name}: a fieldset without a legend first")
            for label_for in labels:
                self.assertIn(label_for, ids, f"{name}: a label for something that is not there")

    def test_every_reference_in_the_page_points_at_something_that_is_there(self):
        for name, reply in self.each():
            ids = {n.attrs["id"] for n in reply.root.walk() if "id" in n.attrs}
            for node in reply.root.walk():
                for reference in (node.attrs.get("aria-describedby", "") + " " + node.attrs.get("aria-labelledby", "")).split():
                    self.assertIn(reference, ids, f"{name}: {reference}")
                href = node.attrs.get("href", "")
                if node.tag == "a" and href.startswith("#"):
                    self.assertIn(href[1:], ids, f"{name}: {href}")

    def test_tables_have_a_caption_header_cells_with_a_scope_and_a_region_that_can_be_scrolled_with_the_keyboard(self):
        for name, reply in self.each():
            for table in reply.root.find_all("table"):
                caption = table.find("caption")
                self.assertTrue(caption.text() and caption.attrs["id"], name)
                region = table.parent
                self.assertEqual((region.attrs["role"], region.attrs["tabindex"], region.attrs["aria-labelledby"]), ("region", "0", caption.attrs["id"]), name)
                headers = table.find("thead").find_all("th")
                for th in table.find_all("th"):
                    self.assertIn(th.attrs.get("scope"), ("col", "row"), f"{name}: a th without scope")
                for row in table.find("tbody").find_all("tr"):
                    self.assertEqual(len([c for c in row.children if hasattr(c, "tag")]), len(headers), f"{name}: a row with a cell too many or too few")

    def test_every_page_is_well_formed(self):
        for name, reply in self.each():
            reply.root
            self.assertEqual(reply.problems, [], name)

    def test_every_form_is_a_post_with_a_token_and_every_button_has_a_type_and_a_name_for_a_person(self):
        for name, reply in self.each():
            for form in reply.root.find_all("form"):
                self.assertEqual(form.attrs.get("method"), "post", name)
                self.assertTrue(form.attrs.get("action", "").startswith("/"), name)
                self.assertTrue(any(i.attrs.get("name") == "nonce" and i.attrs.get("type") == "hidden" and len(i.attrs.get("value", "")) >= 16 for i in form.find_all("input")),
                                f"{name}: a form without a token")
            for button in reply.root.find_all("button"):
                self.assertEqual(button.attrs.get("type"), "submit")
                self.assertTrue(button.text())
            self.assertEqual(reply.root.find_all("form", method="get"), [])

    def test_links_have_words_and_tab_order_is_the_page_order(self):
        for name, reply in self.each():
            for link in reply.root.find_all("a"):
                self.assertTrue(link.text(), f"{name}: a link with no words: {link.attrs}")
            for node in reply.root.walk():
                self.assertIn(node.attrs.get("tabindex", "0"), ("0", "-1"), "no positive tabindex")

    def test_nothing_changes_or_moves_by_itself(self):
        for name, reply in self.each():
            self.assertEqual([n for n in reply.root.walk() if n.tag == "meta" and n.attrs.get("http-equiv")], [], "no refresh")
            self.assertNotIn("autofocus", reply.text)
            self.assertNotIn("autoplay", reply.text)

    def test_what_is_in_the_text_and_not_in_colour_alone(self):
        for name, reply in self.each():
            for notice in reply.root.find_all("div"):
                classes = notice.classes()
                if "notice" in classes:
                    first = notice.children[0]
                    self.assertTrue(first.text(), f"{name}: a notice has a title in words")


class TheStyle(unittest.TestCase):
    def test_the_fluent_2_tokens_are_custom_properties_with_a_light_and_a_dark_theme(self):
        light, dark = style_blocks()
        for token in ("colorNeutralBackground1", "colorNeutralForeground1", "colorNeutralStroke1", "colorNeutralStrokeAccessible", "colorBrandBackground", "colorBrandForegroundLink",
                      "colorStrokeFocus1", "colorStrokeFocus2", "colorPaletteRedBackground1", "colorPaletteRedForeground1", "colorPaletteGreenBackground1"):
            self.assertIn(token, light)
            self.assertNotEqual(light[token], dark[token], f"{token} has a dark value")
        for token in ("fontFamilyBase", "fontSizeBase300", "borderRadiusMedium", "strokeWidthThin"):
            self.assertRegex(layout.STYLE, rf"--{token}:")
        self.assertIn("@media (prefers-color-scheme:dark)", layout.STYLE)
        self.assertIn("color-scheme:light dark", layout.STYLE)
        self.assertEqual(set(tokens(layout.STYLE[layout.STYLE.index("@media (prefers-color-scheme:dark)"):layout.STYLE.index("*,*::before")])) - set(light), set())

    def test_the_text_and_the_parts_of_controls_have_enough_contrast_in_both_themes(self):
        light, dark = style_blocks()
        for theme, values in (("light", light), ("dark", dark)):
            for foreground, background, wanted in LIGHT_DARK_PAIRS:
                with self.subTest(theme=theme, foreground=foreground, background=background):
                    self.assertGreaterEqual(contrast(values[foreground], values[background]), wanted)

    def test_there_is_a_block_for_forced_colors_that_uses_the_persons_own_colours(self):
        block = layout.STYLE[layout.STYLE.index("@media (forced-colors:active)"):]
        for word in ("LinkText", "ButtonText", "ButtonFace", "Highlight", "CanvasText"):
            self.assertIn(word, block)

    def test_the_focus_is_visible_and_not_hidden_behind_anything_that_sticks(self):
        self.assertRegex(layout.STYLE, r":focus-visible\{outline:3px solid var\(--colorStrokeFocus2\)")
        self.assertNotIn("position:sticky", layout.STYLE)
        self.assertNotIn("position:fixed", layout.STYLE)
        self.assertNotIn("outline:none", layout.STYLE)
        self.assertNotIn("outline:0", layout.STYLE)

    def test_the_buttons_stack_on_a_narrow_screen(self):
        narrow = layout.STYLE[layout.STYLE.index("@media (max-width:40em)"):layout.STYLE.index("@media (forced-colors")]
        self.assertIn(".actions{flex-direction:column}", narrow)
        self.assertIn(".actions>*{flex:none;width:100%;max-width:none}", narrow)
        self.assertIn("dl.summary{grid-template-columns:1fr}", narrow)

    def test_controls_are_at_least_24_by_24_css_pixels(self):
        for selector, minimum in ((r"\.btn,button\{[^}]*min-height:([0-9.]+)rem", 1.5), (r"input\[type=text\][^{]*\{[^}]*min-height:([0-9.]+)rem", 1.5),
                                  (r"\.choice input\{[^}]*width:([0-9.]+)rem;height:([0-9.]+)rem", 1.5), (r"nav a\{[^}]*min-height:([0-9.]+)rem", 1.5)):
            match = re.search(selector, layout.STYLE)
            self.assertIsNotNone(match, selector)
            for value in match.groups():
                self.assertGreaterEqual(float(value), minimum, selector)

    def test_the_style_has_no_motion_and_loads_nothing(self):
        for word in ("animation", "transition", "@keyframes", "url(", "@import", "@font-face"):
            self.assertNotIn(word, layout.STYLE)

    def test_text_is_sized_in_relative_units(self):
        for size in re.findall(r"font-size:([^;}]+)", layout.STYLE):
            self.assertTrue(size.strip().endswith(("rem", "em", "%")) or size.startswith(("var(", "inherit", ".9em")), size)
        self.assertNotRegex(layout.STYLE, r"font-size:\d+px")


class TheWords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = {name: reply for name, reply in gallery().items() if name != "denied"}

    def test_a_page_asks_the_reader_nothing(self):
        for name, reply in self.pages.items():
            with self.subTest(page=name):
                self.assertNotIn("?", reply.root.find("main").text())

    def test_nothing_is_called_saved_where_money_is_in_question_and_money_is_in_us_dollars(self):
        names = ["GET /history", "GET /me/decisions", "GET /me/activity"] + [name for name in self.pages if name.startswith(("answer ", "begin ", "return "))]
        for name in names:
            with self.subTest(page=name):
                content = self.pages[name].content
                self.assertNotRegex(content, r"\b(?:saved|saves|savings|save)\b", name)
                self.assertNotRegex(content, r"[$€£]|\bEUR\b|\bUSD\b", name)
                self.assertNotRegex(content.replace("US dollars", ""), r"\bdollars?\b", name)

    def test_a_request_page_says_once_that_money_is_in_us_dollars_and_calls_a_saving_one_only_with_its_level(self):
        names = ["GET /ok/plan0001", "GET /ok/plan0005", "GET /why/case0001", "GET /why/case0005", "paused plan", "paused advice", "approved plan", "expired plan", "consumed plan",
                 "failed plan", "answered advice"]
        for name in names:
            with self.subTest(page=name):
                content = self.pages[name].content
                self.assertEqual(content.count("Money is in US dollars, and a year is twelve times the month."), 1, name)
                self.assertNotRegex(content, r"[€£]|\bEUR\b|\bUSD\b", name)
                self.assertNotRegex(content, r"\b(?:saved|savings|save)\b", name)
                for found in re.findall(r"\bSaves\b[^.]*", content):
                    self.assertRegex(found, r"^Saves, (?:Expected|Scenario|Verified)$", name)

    def test_no_figure_of_speech_and_no_fake_politeness(self):
        for name, reply in self.pages.items():
            text = reply.content.lower()
            for word in ("journey", "magic", "seamless", "supercharge", "unlock", "leverage", "game-changer", "robust", "delight", "oops", "uh-oh", "sorry", "please", "thank you",
                         "happy to help", "great question", "awesome", "simply", "just click", "dive into"):
                self.assertNotIn(word, text, f"{name}: {word}")

    def test_no_page_names_a_runner_a_start_time_or_a_way_to_cancel_an_approval(self):
        for name, reply in self.pages.items():
            with self.subTest(page=name):
                text = reply.content.lower()
                for word in ("runner", "cancel my ok", "the change starts at", "start time", "120 seconds"):
                    self.assertNotIn(word, text)
                self.assertNotIn("/withdraw", reply.text)

    def test_the_footer_has_about_this_page_with_why_the_person_sees_it_and_who_is_responsible_as_plain_text_on_every_page_that_has_a_footer(self):
        for name, reply in self.pages.items():
            with self.subTest(page=name):
                footer = reply.root.find("footer")
                (about,) = footer.find_all("details")
                self.assertEqual(about.find("summary").text(), "About this page")
                text = about.find("p").text()
                self.assertIn("You see this because ", text)
                self.assertRegex(text, r"Responsible for Meternaut: [A-Z][a-z]+ \([a-z]+@example\.com\)\.$")
                self.assertEqual(footer.find_all("a"), [], "no link in the footer")
                self.assertNotIn("Talk to a person", footer.text())

    def test_the_pages_that_show_ai_text_say_so_in_one_quiet_line_and_name_the_models_and_the_others_do_not(self):
        line = "Recommendations written by AI. A person approves every change."
        for name, reply in self.pages.items():
            with self.subTest(page=name):
                footer = reply.root.find("footer")
                paragraphs = [p.text() for p in footer.find_all("p")]
                about = paragraphs[-1]
                if name in NOT_AI:
                    self.assertEqual(len(paragraphs), 1, paragraphs)
                    self.assertNotIn("written by AI", footer.text())
                    self.assertTrue(about.startswith("You see this because "), about)
                else:
                    self.assertEqual(paragraphs[0], line)
                    self.assertTrue(about.startswith("Models: model-detective-x, model-skeptic-y. You see this because "), about)

    def test_a_page_that_refuses_says_that_nothing_changed(self):
        refusing = ("refused_code", "refused_state", "refused_paused", "expired", "duplicate", "stopped", "azure_refused", "signin_failed", "step_up_failed")
        names = [f"{step} {kind}" for step in ("answer", "begin", "return") for kind in refusing]
        for name in names + ["no token", "413", "415", "405", "GET /nothing", "GET /why/nothing"]:
            with self.subTest(page=name):
                content = self.pages[name].content.lower()
                self.assertTrue(any(phrase in content for phrase in ("nothing has changed", "nothing was changed", "nothing was sent", "nothing is approved")), content[:300])

    def test_a_request_of_advice_says_that_nothing_changes_in_azure_and_never_talks_of_signing_in(self):
        page = self.pages["GET /ok/plan0005"]
        self.assertIn("Nothing changes in Azure.", page.content)
        for gone in ("sign in to Azure", "Approve and sign in"):
            self.assertNotIn(gone, page.main.text())
        self.assertEqual([b[2] for f in page.forms() for b in f.buttons], ["Worth acting on", "Not worth it", "This is not mine", "Ask or tell", "Decide later"])


if __name__ == "__main__":
    unittest.main()
