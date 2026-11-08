import importlib.util
import io
import json
import re
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("teams_package", ROOT / "tools" / "teams-package.py")
tp = importlib.util.module_from_spec(spec)
sys.modules["teams_package"] = tp
spec.loader.exec_module(tp)

BOT = "0f6a4c2e-7b1d-4e35-9a58-3c2d1b0e9f47"
SITE = "https://meternaut.example.net"


def files(**changes) -> dict[str, bytes]:
    return {**tp.files_of(BOT, SITE), **changes}


def manifest_of(package: dict[str, bytes]) -> dict:
    return json.loads(package["manifest.json"])


def with_manifest(**changes) -> dict[str, bytes]:
    document = manifest_of(files())
    for key, value in changes.items():
        if value is KeyError:
            document.pop(key)
        else:
            document[key] = value
    return files(**{"manifest.json": json.dumps(document).encode()})


class TheManifest(unittest.TestCase):
    def setUp(self):
        self.document = manifest_of(files())

    def test_it_is_the_current_schema_and_one_bot_in_the_personal_scope(self):
        self.assertEqual(self.document["$schema"], "https://developer.microsoft.com/json-schemas/teams/v1.30/MicrosoftTeams.schema.json")
        self.assertEqual(self.document["manifestVersion"], "1.30")
        (bot,) = self.document["bots"]
        self.assertEqual(bot, {"botId": BOT, "scopes": ["personal"], "isNotificationOnly": False, "supportsFiles": False})

    def test_it_loads_nothing_inside_teams_and_has_no_single_sign_on(self):
        self.assertEqual(self.document["validDomains"], [])
        self.assertNotIn("webApplicationInfo", self.document)
        self.assertNotIn("permissions", self.document)

    def test_the_name_says_that_an_ai_wrote_every_message(self):
        self.assertEqual((self.document["name"]["short"], self.document["name"]["full"]), ("Meternaut (AI)", "Meternaut (AI)"))
        self.assertIn("Written by an AI", self.document["description"]["full"])
        self.assertIn("never made from a card", self.document["description"]["full"])

    def test_the_lengths_are_the_ones_teams_takes(self):
        self.assertLessEqual(len(self.document["name"]["short"]), 30)
        self.assertLessEqual(len(self.document["description"]["short"]), 80)
        self.assertLessEqual(len(self.document["description"]["full"]), 4000)
        self.assertLessEqual(len(self.document["developer"]["name"]), 32)

    def test_the_developer_addresses_are_pages_of_the_web_page(self):
        self.assertEqual(self.document["developer"], {"name": "Meternaut", "websiteUrl": f"{SITE}/", "privacyUrl": f"{SITE}/me/settings", "termsOfUseUrl": f"{SITE}/"})

    def test_the_id_of_the_app_is_a_fixed_function_of_the_bot_and_can_be_given(self):
        self.assertEqual(self.document["id"], tp.app_id_of(BOT))
        self.assertEqual(tp.app_id_of(BOT.upper()), tp.app_id_of(BOT))
        self.assertNotEqual(tp.app_id_of(BOT), tp.app_id_of("1f6a4c2e-7b1d-4e35-9a58-3c2d1b0e9f47"))
        self.assertNotEqual(tp.app_id_of(BOT), BOT)
        self.assertEqual(tp.manifest(BOT, SITE, app_id="AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE")["id"], "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")

    def test_bad_arguments_are_refused_in_words(self):
        for kwargs in (dict(bot_id="not-a-guid", site=SITE), dict(bot_id="", site=SITE), dict(bot_id=BOT, site="http://meternaut.example.net"), dict(bot_id=BOT, site=f"{SITE}/path"),
                       dict(bot_id=BOT, site="https://METERNAUT.example"), dict(bot_id=BOT, site=""), dict(bot_id=BOT, site=SITE, version="1.0"), dict(bot_id=BOT, site=SITE, version="v1.0.0"),
                       dict(bot_id=BOT, site=SITE, app_id="x")):
            with self.assertRaises(tp.PackageError, msg=kwargs):
                tp.manifest(**kwargs)


class TheIcons(unittest.TestCase):
    def test_they_are_pngs_of_the_sizes_that_teams_asks(self):
        for name, size in (("color.png", 192), ("outline.png", 32)):
            data = files()[name]
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", data[16:24]), (size, size))
            width, height, pixels = tp.read_png(data)
            self.assertEqual((width, height, len(pixels)), (size, size, size * size))

    def test_the_outline_is_white_on_transparent_and_has_a_mark(self):
        _, _, pixels = tp.read_png(files()["outline.png"])
        self.assertEqual(set(pixels), {(255, 255, 255, 255), (0, 0, 0, 0)})
        self.assertGreater(pixels.count((255, 255, 255, 255)), 50)

    def test_the_color_icon_is_the_accent_colour_with_a_white_mark(self):
        _, _, pixels = tp.read_png(files()["color.png"])
        self.assertEqual(set(pixels), {(255, 255, 255, 255), (0x0B, 0x5C, 0xAD, 255)})
        self.assertEqual(pixels[0], (0x0B, 0x5C, 0xAD, 255))

    def test_a_png_that_is_cut_or_altered_is_not_read(self):
        data = files()["outline.png"]
        for broken in (data[:-12], data[:40] + b"\x00" + data[41:], b"GIF89a", b""):
            with self.assertRaises(tp.PackageError):
                tp.read_png(broken)

    def test_a_png_with_another_colour_type_or_a_filter_is_not_read(self):
        def chunk(kind, body):
            return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        grey = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x00\x00")) + chunk(b"IEND", b"")
        filtered = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x01\x00\x00\x00\x00")) + chunk(b"IEND", b"")
        for data in (grey, filtered):
            with self.assertRaises(tp.PackageError):
                tp.read_png(data)


class TheZip(unittest.TestCase):
    def test_the_same_arguments_give_the_same_bytes(self):
        self.assertEqual(tp.zip_bytes(files()), tp.zip_bytes(files()))
        self.assertNotEqual(tp.zip_bytes(files()), tp.zip_bytes(tp.files_of(BOT, SITE, "1.0.1")))

    def test_it_holds_the_three_files_at_the_root_with_the_time_of_the_epoch(self):
        with zipfile.ZipFile(io.BytesIO(tp.zip_bytes(files()))) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual([i.filename for i in archive.infolist()], ["manifest.json", "color.png", "outline.png"])
            self.assertTrue(all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in archive.infolist()))

    def test_the_package_is_small(self):
        self.assertLess(len(tp.zip_bytes(files())), 20000)


class TheCheck(unittest.TestCase):
    def says(self, package, words):
        found = tp.problems_of(package)
        self.assertTrue(any(words in problem for problem in found), (words, found))

    def test_a_package_that_is_built_here_passes(self):
        self.assertEqual(tp.problems_of(files()), [])

    def test_what_the_zip_holds_is_exactly_the_three_files(self):
        self.says({**files(), "extra.txt": b"x"}, "has to hold exactly")
        self.says({k: v for k, v in files().items() if k != "outline.png"}, "has to hold exactly")
        self.says({}, "holds nothing")

    def test_a_manifest_that_is_not_json_or_not_an_object_is_refused(self):
        self.says(files(**{"manifest.json": b"{"}), "not JSON")
        self.says(files(**{"manifest.json": b"[]"}), "not a JSON object")
        self.says(files(**{"manifest.json": b"\xff"}), "not JSON")

    def test_the_choices_of_meternaut_are_held(self):
        self.says(with_manifest(name={"short": "Meternaut", "full": "Meternaut (AI)"}), "name.short ends with")
        self.says(with_manifest(name={"short": "Meternaut (AI)", "full": "Meternaut"}), "name.full ends with")
        self.says(with_manifest(bots=[{"botId": BOT, "scopes": ["personal", "team"], "isNotificationOnly": False, "supportsFiles": False}]), "scopes")
        self.says(with_manifest(bots=[{"botId": BOT, "scopes": ["personal"], "isNotificationOnly": True, "supportsFiles": False}]), "isNotificationOnly")
        self.says(with_manifest(bots=[{"botId": BOT, "scopes": ["personal"], "isNotificationOnly": False, "supportsFiles": False, "commandLists": []}]), "isNotificationOnly")
        self.says(with_manifest(bots=[]), "exactly one bot")
        self.says(with_manifest(validDomains=["example.com"]), "validDomains")
        self.says(with_manifest(webApplicationInfo={"id": BOT, "resource": "api://x"}), "keys")
        self.says(with_manifest(permissions=["identity"]), "keys")

    def test_the_limits_of_teams_are_held(self):
        self.says(with_manifest(name={"short": "M" * 27 + " (AI)", "full": "Meternaut (AI)"}), "name.short is a text of 1 to 30")
        self.says(with_manifest(description={"short": "x" * 81, "full": "x"}), "description.short")
        self.says(with_manifest(description={"short": "x", "full": "x" * 4001}), "description.full")
        self.says(with_manifest(developer={"name": "x" * 33, "websiteUrl": f"{SITE}/", "privacyUrl": f"{SITE}/p", "termsOfUseUrl": f"{SITE}/"}), "developer.name")
        self.says(with_manifest(developer={"name": "x", "websiteUrl": "http://example.net/", "privacyUrl": f"{SITE}/p", "termsOfUseUrl": f"{SITE}/"}), "developer.websiteUrl")
        self.says(with_manifest(version="1.0"), "version")
        self.says(with_manifest(id="x"), "id is a GUID")
        self.says(with_manifest(accentColor="blue"), "accentColor")
        self.says(with_manifest(manifestVersion="1.17"), "schema")
        self.says(with_manifest(icons={"color": "a.png", "outline": "b.png"}), "icons")
        self.says(with_manifest(bots=[{"botId": "x", "scopes": ["personal"], "isNotificationOnly": False, "supportsFiles": False}]), "botId")

    def test_the_icons_are_checked(self):
        self.says(files(**{"color.png": files()["outline.png"]}), "color.png is 192 by 192")
        self.says(files(**{"outline.png": files()["color.png"]}), "outline.png is 32 by 32")
        self.says(files(**{"outline.png": b"not a png"}), "outline.png: not a PNG")
        colored = tp.png(32, 32, lambda x, y: (255, 0, 0, 255))
        self.says(files(**{"outline.png": colored}), "white on a transparent ground")

    def test_a_package_over_a_mebibyte_is_refused(self):
        self.says(files(**{"manifest.json": files()["manifest.json"] + b" " * (tp.MAX_PACKAGE + 1)}), "larger than 1 MiB")


class TheCommandLine(unittest.TestCase):
    def run_main(self, *argv):
        out = io.StringIO()
        return tp.main(list(argv), out), out.getvalue()

    def test_build_writes_a_zip_that_check_passes_and_does_not_replace_one_unasked(self):
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "teams-app.zip")
            code, text = self.run_main("build", "--bot-id", BOT, "--site", SITE, "--out", target)
            self.assertEqual(code, 0, text)
            self.assertIn(f"for the bot {BOT}", text)
            first = Path(target).read_bytes()
            self.assertEqual(self.run_main("check", target), (0, "The package passes.\n"))
            code, text = self.run_main("build", "--bot-id", BOT, "--site", SITE, "--out", target, "--version", "1.0.1")
            self.assertEqual((code, Path(target).read_bytes()), (1, first))
            self.assertIn("--force replaces it", text)
            self.assertEqual(self.run_main("build", "--bot-id", BOT, "--site", SITE, "--out", target, "--version", "1.0.1", "--force")[0], 0)
            self.assertEqual(json.loads(zipfile.ZipFile(target).read("manifest.json"))["version"], "1.0.1")

    def test_check_says_every_problem_and_exits_1(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "bad.zip"
            target.write_bytes(tp.zip_bytes(with_manifest(name={"short": "Meternaut", "full": "Meternaut"}, validDomains=["x.example"])))
            code, text = self.run_main("check", str(target))
            self.assertEqual(code, 1)
            self.assertIn("problem: name.short ends with", text)
            self.assertIn("problem: validDomains is empty", text)
            self.assertIn("problem(s).", text)

    def test_check_refuses_what_is_not_a_zip_or_not_there(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "x.zip"
            target.write_bytes(b"not a zip")
            self.assertEqual(self.run_main("check", str(target))[0], 1)
            self.assertEqual(self.run_main("check", str(Path(folder) / "missing.zip"))[0], 1)

    def test_check_refuses_a_zip_that_holds_a_name_twice_or_a_huge_file(self):
        with tempfile.TemporaryDirectory() as folder:
            twice = Path(folder) / "twice.zip"
            with zipfile.ZipFile(twice, "w") as archive:
                archive.writestr("manifest.json", b"{}")
                with self.assertWarns(UserWarning):
                    archive.writestr("manifest.json", b"{}")
            self.assertEqual(self.run_main("check", str(twice))[0], 1)

    def test_the_manifest_command_prints_the_manifest(self):
        code, text = self.run_main("manifest", "--bot-id", BOT, "--site", SITE)
        self.assertEqual((code, json.loads(text)["bots"][0]["botId"]), (0, BOT))

    def test_bad_arguments_exit_1_with_a_line(self):
        code, text = self.run_main("manifest", "--bot-id", "nope", "--site", SITE)
        self.assertEqual(code, 1)
        self.assertRegex(text, r"^error: the bot id is the client id")

    def test_nothing_in_the_tool_reads_the_network_or_a_key(self):
        source = (ROOT / "tools" / "teams-package.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"urllib|http\.client|\bsocket\b|requests|subprocess|-----BEGIN")


if __name__ == "__main__":
    unittest.main()
