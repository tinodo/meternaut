import re
import unittest

from support import APP_ROOT, REPO_ROOT
from test_web_accessibility import gallery
from test_web_pages import busy

from cases.web import layout, style

WEB = APP_ROOT / "cases" / "web"
GUIDE = REPO_ROOT / "docs" / "ui"
SHEET = GUIDE / "meternaut-ui.css"


def pages() -> dict:
    """Every page of the gallery of the accessibility tests (the page of the decisions with every part that it has is one of them), and that page again with all its rows."""
    return {**gallery(), "busy decisions, all": busy().get("/", query={"all": "1", "sort": "age"})}


class TheStylesheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = pages()

    def test_the_style_of_every_page_is_the_one_stylesheet_of_the_style_guide(self):
        sheet = SHEET.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertEqual(style.STYLE, sheet, "docs/ui/meternaut-ui.css and cases/web/style.py are the same text: a change is made in both")
        self.assertIs(layout.STYLE, style.STYLE)
        for name, reply in self.pages.items():
            with self.subTest(page=name):
                self.assertEqual(re.findall(r"<style>(.*?)</style>", reply.text, re.S), [style.STYLE])
                self.assertNotIn("<link", reply.text, "nothing is loaded from outside")
        for guide in ("style-guide.html", "decisions-preview.html"):
            with self.subTest(guide=guide):
                (href,) = re.findall(r'<link rel="stylesheet" href="([^"]+)"', (GUIDE / guide).read_text(encoding="utf-8"))
                self.assertEqual((GUIDE / href).resolve(), SHEET.resolve(), "the guide shows the file that the pages carry")

    def test_the_stylesheet_has_a_colour_only_in_a_token(self):
        rest = re.sub(r"--[A-Za-z0-9]+:#[0-9a-fA-F]{6}|--shadow[48]:[^;}]+", "", style.STYLE)
        self.assertNotRegex(rest, r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(")

    def test_every_class_that_a_page_uses_is_a_part_of_the_stylesheet(self):
        used = {cls for reply in self.pages.values() for node in reply.root.walk() for cls in node.classes()}
        missing = sorted(cls for cls in used if not re.search(rf"\.{re.escape(cls)}(?![A-Za-z0-9_-])", layout.STYLE))
        self.assertEqual(missing, [], "a part that is missing is drawn in the style guide first and added to the stylesheet")

    def test_a_page_has_no_style_attribute_and_no_page_says_talk_to_a_person(self):
        for name, reply in self.pages.items():
            with self.subTest(page=name):
                self.assertNotRegex(reply.text, r"\sstyle\s*=")
                if name != "denied":
                    self.assertNotIn("Talk to a person", reply.text)

    def test_the_code_of_a_page_has_no_style_attribute_no_colour_and_no_pixel_size(self):
        for path in sorted(WEB.glob("*.py")):
            if path.name == "style.py":
                continue  # the stylesheet is where the colours and the sizes are
            with self.subTest(module=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"""style\s*=\s*["']""")
                self.assertNotRegex(text, r"""["'(]#[0-9a-fA-F]{3,8}["')]""")
                self.assertNotRegex(text, r"\b\d+px\b")


if __name__ == "__main__":
    unittest.main()
