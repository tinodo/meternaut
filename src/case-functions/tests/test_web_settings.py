import datetime as dt
import json
import unittest

from test_web_support import (DISK, MAYA, NOW, OWNER, SUB, TINO, Console, FailingStore, at, make_action, make_decision, make_plan, make_run, snapshot)

from cases.models import TIME_FORMAT, NoteRecord, SettingsRecord, StoreError
from cases.web.settings import CHANNEL_HINT, NOT_APPLIED, WEEKLY_BUDGET_HINT

GOOD = {"channel": "desk", "language": "en", "timezone": "Europe/Berlin", "working_days": "1,2,3", "quiet_from": "20:00", "quiet_to": "07:30", "desk_day": "3",
        "weekly_budget": "5", "paused_until": "2026-12-01", "mutes": "digest, weekly-desk"}
STORED = SettingsRecord(oid=TINO, channel="desk", language="en", timezone="Europe/Berlin", working_days=(1, 2, 3), quiet_from="20:00", quiet_to="07:30", desk_day=3,
                        weekly_budget=5, paused_until="2026-12-01T00:00:00Z", mutes=("digest", "weekly-desk"), updated_at="2026-11-05T09:00:00Z")


class TheSettingsPage(unittest.TestCase):
    def setUp(self):
        self.console = Console()
        self.page = self.console.get("/me/settings")

    def save_form(self, page=None):
        return (page or self.page).form("/me/settings", has_button="Save settings")

    def test_every_setting_has_a_control_with_a_label(self):
        root = self.page.root
        legends = [l.text() for l in root.find_all("legend")]
        self.assertEqual(legends, ["Where Meternaut writes to you first", "Working days", "Quiet hours"])
        labels = {l.attrs["for"]: l.text() for l in root.find_all("label")}
        for field_id, text in (("language", "Language"), ("timezone", "Time zone"), ("quiet_from", "Quiet hours start"), ("quiet_to", "Quiet hours end"),
                               ("desk_day", "Day of the weekly desk"), ("weekly_budget", "Messages a week"), ("paused_until", "Pause messages until"), ("mutes", "Mutes"),
                               ("channel-email", "E-mail first"), ("channel-teams", "Teams first"), ("channel-desk", "Only the weekly desk")):
            self.assertEqual(labels[field_id], text)
        self.assertEqual([labels[f"working_days-{n}"] for n in range(1, 8)], ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])

    def test_one_line_says_what_is_stored_and_not_applied_yet_and_it_is_the_only_one(self):
        line = self.page.root.find("div", id="not-applied")
        self.assertEqual(line.text(), "Not applied yet: Teams first, working days, quiet hours and mutes. They are stored, and no message follows them yet.")
        self.assertEqual(NOT_APPLIED, "Teams first, working days, quiet hours and mutes. They are stored, and no message follows them yet.")
        content = self.page.content
        self.assertEqual(content.lower().count("not applied"), 1, "the words are in one place only")
        self.assertLess(content.index("Not applied yet:"), content.index("Where Meternaut writes to you first"), "the line comes before the inputs that it is about")
        for old in ("Stored. Not applied to approval requests yet.", "Stored. Not applied to messages yet.", "stored and not applied yet"):
            self.assertNotIn(old, content)
        self.assertIsNone(self.page.root.find("fieldset", id="quiet-hours").find("p", class_="hint"), "no second note under the quiet hours")
        self.assertIsNone(self.page.root.find("p", id="working_days-hint"), "no second note under the working days")

    def test_the_line_is_also_on_the_page_that_shows_a_refusal(self):
        form = self.save_form()
        reply = self.console.post("/me/settings", {**form.fields, **GOOD, "weekly_budget": "11"})
        self.assertEqual(reply.status, 400)
        self.assertEqual(reply.content.lower().count("not applied"), 1)
        self.assertEqual(reply.root.find("div", id="not-applied").text(), f"Not applied yet: {NOT_APPLIED}")

    def test_the_notes_under_the_inputs_say_what_the_sender_of_messages_does(self):
        root = self.page.root
        channel = root.find("p", id="channel-hint").text()
        self.assertEqual(channel, CHANNEL_HINT)
        self.assertEqual(channel, "With only the weekly desk, no message is sent except the weekly one. Requests that wait for your OK stay on the home page.")
        pause = root.find("p", id="paused_until-hint").text()
        self.assertIn("No message is sent before 00:00 UTC on this date.", pause)
        budget = root.find("p", id="weekly_budget-hint").text()
        self.assertEqual(budget, WEEKLY_BUDGET_HINT)
        self.assertEqual(budget, "How many other messages a week I may send you. 0 means only the weekly desk. Requests that wait for your OK, the first message to you, and "
                                 "messages that tell you what a change did are never counted or held by this number.")
        self.assertEqual(root.find("p", id="mutes-hint").text(), "Short words for kinds of messages to silence, separated by commas.")

    def test_the_starting_values_are_those_of_the_record(self):
        fields = self.save_form().fields
        self.assertEqual({k: v for k, v in fields.items() if k != "nonce"},
                         {"channel": "email", "language": "en", "timezone": "Europe/Amsterdam", "working_days": "1,2,3,4,5", "quiet_from": "18:00", "quiet_to": "08:00",
                          "desk_day": "2", "weekly_budget": "3", "paused_until": "", "mutes": ""})

    def test_the_stored_values_are_shown(self):
        self.console.store.settings_put(STORED)
        fields = self.save_form(self.console.get("/me/settings")).fields
        for name, value in GOOD.items():
            self.assertEqual(fields[name], value, name)

    def test_the_time_inputs_and_the_number_and_the_date_have_their_limits_in_the_page_too(self):
        root = self.page.root
        self.assertEqual(root.find("input", id="quiet_from").attrs["type"], "time")
        budget = root.find("input", id="weekly_budget")
        self.assertEqual((budget.attrs["type"], budget.attrs["min"], budget.attrs["max"]), ("number", "0", "10"))
        paused = root.find("input", id="paused_until")
        self.assertEqual((paused.attrs["type"], paused.attrs["min"], paused.attrs["max"]), ("date", "2026-11-06", "2027-11-06"))

    def test_a_person_sees_their_own_settings_and_nobody_elses(self):
        self.console.store.settings_put(STORED)
        self.console.store.settings_put(SettingsRecord(oid=MAYA, channel="teams", mutes=("maya-only",)))
        self.assertNotIn("maya-only", self.console.get("/me/settings").text)
        self.assertIn("maya-only", self.console.get("/me/settings", oid=MAYA).text)

    def test_settings_that_cannot_be_read_show_the_starting_values_and_say_so(self):
        console = Console(store=FailingStore(fail={"settings_get"}, clock=lambda: NOW))
        reply = console.get("/me/settings")
        self.assertEqual(reply.status, 200)
        self.assertIn("The values below are the starting values, not what you saved.", reply.content)


class SavingSettings(unittest.TestCase):
    def setUp(self):
        self.console = Console()

    def post(self, **changes):
        form = self.console.get("/me/settings").form("/me/settings", has_button="Save settings")
        return self.console.post("/me/settings", {**form.fields, **GOOD, **changes})

    def test_good_values_are_stored_as_a_record_of_this_person(self):
        reply = self.post()
        self.assertEqual(reply.status, 200)
        self.assertEqual(self.console.store.settings_get(TINO), STORED)
        self.assertIn("Your settings are saved.", reply.content)
        self.assertIn("Saved", [p.text() for p in reply.root.find_all("p", class_="notice-title")])
        self.assertEqual(reply.form("/me/settings", has_button="Save settings").fields["channel"], "desk")
        self.assertEqual(self.console.store.settings, {TINO: STORED}, "nothing was stored for anybody else")

    def test_the_boundaries_that_are_allowed(self):
        for changes in (dict(weekly_budget="0"), dict(weekly_budget="10"), dict(paused_until=""), dict(paused_until="2026-11-06"), dict(paused_until="2027-11-06"),
                        dict(mutes=""), dict(working_days="7"), dict(working_days="1,2,3,4,5,6,7"), dict(quiet_from="00:00", quiet_to="23:59"), dict(desk_day="1"),
                        dict(desk_day="7"), dict(timezone="UTC"), dict(channel="email"), dict(channel="teams")):
            with self.subTest(changes=changes):
                self.assertEqual(self.post(**changes).status, 200)

    def test_values_are_tidied_before_they_are_stored(self):
        self.post(working_days="5, 1,3", mutes="Digest  digest, Weekly-Desk", timezone="europe/berlin")
        stored = self.console.store.settings_get(TINO)
        self.assertEqual(stored.working_days, (1, 3, 5))
        self.assertEqual(stored.mutes, ("digest", "weekly-desk"))
        self.assertEqual(stored.timezone, "Europe/Berlin")

    def test_each_value_that_is_not_allowed_is_refused_with_the_field_named_and_nothing_is_stored(self):
        bad = (
            ("channel", ("sms", "", "EMAIL", "email,teams")), ("language", ("nl", "", "EN", "en,nl")),
            ("timezone", ("Mars/Olympus_Mons", "", "Europe", "../x", "UTC+1", "Europe/Amsterdam/extra/more/parts", "x" * 80, "<b>")),
            ("working_days", ("", "0", "8", "1,1", "a", "1;2", "1,2,3,4,5,6,7,8", "-1")), ("quiet_from", ("24:00", "7:00", "12:60", "noon", "", "08:00:00")),
            ("quiet_to", ("24:00", "7:00", "12:60", "noon", "", "08:00:00")), ("desk_day", ("0", "8", "x", "", "1,2")),
            ("weekly_budget", ("-1", "11", "14", "15", "x", "", "1.5", "007", "99")),
            ("paused_until", ("2026-11-05", "2026-11-04", "2027-11-07", "2026-02-30", "tomorrow", "20261201", "2026-1-5", "2026-12-01T10:00")),
            ("mutes", ("Two Words!", "a" * 25, "-start", ",".join(f"w{n}" for n in range(11)), "ünïcode")),
        )
        before = snapshot(self.console.store)
        for name, values in bad:
            for value in values:
                with self.subTest(field=name, value=value):
                    reply = self.post(**{name: value})
                    self.assertEqual(reply.status, 400)
                    self.assertIn("There is a problem", reply.headings(2))
                    self.assertIn("Nothing was saved.", reply.content)
                    links = [a.attrs["href"] for a in reply.root.find("h2", id="problem-title").parent.find_all("a")]
                    self.assertEqual(links, [f"#{name}"], "the list of problems links to the field")
                    self.assertIsNotNone(reply.root.find(id=name), "the link goes to an element of the page")
                    self.assertIsNotNone(reply.root.find("p", id=f"{name}-error"), "the field shows its own message")
        self.assertEqual(snapshot(self.console.store), before)

    def test_every_problem_is_reported_at_once_and_what_was_typed_is_kept(self):
        reply = self.post(channel="sms", timezone="Nowhere/Land", weekly_budget="99", mutes="Bad Word!")
        self.assertEqual(reply.status, 400)
        links = [a.attrs["href"] for a in reply.root.find("h2", id="problem-title").parent.find_all("a")]
        self.assertEqual(sorted(links), ["#channel", "#mutes", "#timezone", "#weekly_budget"])
        fields = reply.form("/me/settings", has_button="Save settings").fields
        self.assertEqual((fields["timezone"], fields["weekly_budget"], fields["mutes"]), ("Nowhere/Land", "99", "Bad Word!"))
        self.assertEqual(fields["quiet_from"], "20:00", "what was right is kept too")

    def test_the_messages_say_what_is_wrong(self):
        for name, value, message in (("channel", "sms", "Choose e-mail first, Teams first or only the weekly desk."), ("language", "nl", "English is the only language at present."),
                                     ("timezone", "Nowhere/Land", "Enter a time zone name that exists, for example Europe/Amsterdam."),
                                     ("working_days", "", "Choose at least one working day."), ("working_days", "9", "Choose working days from Monday (1) to Sunday (7), each once."),
                                     ("quiet_from", "25:00", "Quiet hours start must be a time as HH:MM, from 00:00 to 23:59."),
                                     ("quiet_to", "25:00", "Quiet hours end must be a time as HH:MM, from 00:00 to 23:59."),
                                     ("desk_day", "9", "Choose the day of the weekly desk, from Monday (1) to Sunday (7)."),
                                     ("weekly_budget", "11", "Enter a whole number from 0 to 10."),
                                     ("paused_until", "2026-11-05", "Enter a date from 2026-11-06 to 2027-11-06 as YYYY-MM-DD, or leave it empty."),
                                     ("mutes", "Bad Word!", "Use short words of letters, digits and hyphens, up to 24 characters each, separated by commas.")):
            with self.subTest(field=name, value=value):
                self.assertIn(message, self.post(**{name: value}).content)
        self.assertIn("Use at most 10 words.", self.post(mutes=",".join(f"w{n}" for n in range(11))).content)

    def test_a_person_cannot_save_for_somebody_else(self):
        reply = self.post(oid=MAYA, name="Maya")
        self.assertEqual(reply.status, 200)
        self.assertEqual(set(self.console.store.settings), {TINO})

    def test_the_time_comes_from_the_clock(self):
        self.console.now = dt.datetime(2026, 12, 24, 10, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(self.post(paused_until="2027-01-02").status, 200)
        self.assertEqual(self.console.store.settings_get(TINO).updated_at, "2026-12-24T10:00:00Z")
        self.assertEqual(self.post(paused_until="2026-12-25").status, 200)
        self.assertEqual(self.post(paused_until="2026-12-24").status, 400, "a pause that ends today would be no pause")
        self.assertEqual(self.post(paused_until="2026-12-23").status, 400)

    def test_a_pause_is_stored_as_a_time_that_the_sender_of_messages_reads(self):
        self.assertEqual(self.post(paused_until="2026-11-06").status, 200)
        until = self.console.store.settings_get(TINO).paused_until
        self.assertEqual(until, "2026-11-06T00:00:00Z")
        self.assertEqual(dt.datetime.strptime(until, TIME_FORMAT).replace(tzinfo=dt.timezone.utc), dt.datetime(2026, 11, 6, tzinfo=dt.timezone.utc))
        self.assertEqual(self.post(paused_until="").status, 200)
        self.assertIsNone(self.console.store.settings_get(TINO).paused_until)

    def test_a_pause_is_shown_as_its_date_and_only_while_it_is_ahead(self):
        def shown():
            return self.console.get("/me/settings").form("/me/settings", has_button="Save settings").fields["paused_until"]
        self.console.store.settings_put(STORED)
        self.assertEqual(shown(), "2026-12-01")
        self.console.now = dt.datetime(2026, 12, 1, 8, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(shown(), "", "a pause that has ended is not offered again")
        self.assertEqual(self.post(paused_until="").status, 200, "so a person can save other settings after it ended")

    def test_a_store_that_cannot_write_gives_a_plain_page_and_stores_nothing(self):
        def fail(record):
            raise StoreError("down", 503)
        self.console.store.settings_put = fail
        reply = self.post()
        self.assertEqual(reply.status, 503)
        self.assertIn("I cannot reach my records", reply.content)
        self.assertIn("Open the page again to see what was stored.", reply.content)
        self.assertEqual(self.console.store.settings, {})


class TheExport(unittest.TestCase):
    def setUp(self):
        self.console = Console()
        store = self.console.store
        store.settings_put(STORED)
        store.settings_put(SettingsRecord(oid=MAYA, channel="teams", mutes=("maya-only",)))
        store.note_put(NoteRecord("n1", TINO, "note", "Tino's note", DISK, "x", "you", at(days=-1), at(days=9), 2))
        store.note_put(NoteRecord("n2", MAYA, "note", "Maya's note", DISK, "x", "you", at(days=-1), at(days=9), 0))
        store.run_put(make_run())
        store.plan_put(make_plan(approvers=(TINO, MAYA)))
        store.decision_put(make_decision())
        store.decision_put(make_decision(approver_oid=MAYA, approver_name="Maya", note="Maya's answer"))

    def export(self, oid=TINO):
        form = self.console.get("/me/settings", oid=oid).form("/me/settings/export")
        return self.console.submit(form, oid=oid)

    def test_it_is_a_json_file_download(self):
        reply = self.export()
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(reply.headers["Content-Disposition"], 'attachment; filename="meternaut-my-data.json"')
        self.assertTrue(reply.text.endswith("\n"))
        self.assertIsInstance(reply.json(), dict)

    def test_it_holds_the_persons_settings_and_notes_and_nothing_of_anybody_else(self):
        document = self.export().json()
        self.assertEqual(set(document), {"exportedAt", "oid", "settings", "notes"})
        self.assertEqual(document["oid"], TINO)
        self.assertEqual(document["exportedAt"], "2026-11-05T09:00:00Z")
        self.assertEqual(document["settings"]["channel"], "desk")
        self.assertEqual(document["settings"]["mutes"], ["digest", "weekly-desk"])
        self.assertEqual(document["settings"]["working_days"], [1, 2, 3])
        self.assertEqual([n["note_id"] for n in document["notes"]], ["n1"])
        self.assertEqual(document["notes"][0]["text"], "Tino's note")
        text = self.export().text
        for other in (MAYA, "maya-only", "Maya's note", "Maya's answer"):
            self.assertNotIn(other, text)
        maya = self.export(MAYA).json()
        self.assertEqual(maya["oid"], MAYA)
        self.assertEqual(maya["settings"]["mutes"], ["maya-only"])
        self.assertEqual([n["note_id"] for n in maya["notes"]], ["n2"])
        self.assertNotIn(TINO, self.export(MAYA).text)

    def test_a_person_with_nothing_stored_gets_the_starting_values_and_no_notes(self):
        document = self.export(OWNER).json()
        self.assertEqual(document["notes"], [])
        self.assertEqual(document["settings"]["oid"], OWNER)

    def test_the_export_changes_nothing_and_is_not_a_page(self):
        before = snapshot(self.console.store)
        self.export()
        self.assertEqual(snapshot(self.console.store), before)
        self.assertEqual(self.console.get("/me/settings/export").status, 405)

    def test_the_decisions_are_not_in_the_file(self):
        text = self.export().text
        self.assertNotIn("plan0001", text)
        self.assertNotIn("approve", text)


class TheDeletion(unittest.TestCase):
    def setUp(self):
        self.console = Console(decider="loop")
        self.console.seed()
        store = self.console.store
        store.settings_put(STORED)
        store.settings_put(SettingsRecord(oid=MAYA, channel="teams"))
        store.note_put(NoteRecord("n1", TINO, "note", "one", DISK, "x", "you", at(days=-1), at(days=9), 0))
        store.note_put(NoteRecord("n2", TINO, "do_not_touch", "two", DISK, "x", "you", at(days=-1), at(days=9), 0))
        store.note_put(NoteRecord("n3", MAYA, "note", "hers", DISK, "x", "you", at(days=-1), at(days=9), 0))
        store.decision_put(make_decision())
        store.action_put(make_action())

    def delete(self, oid=TINO):
        form = self.console.get("/me/settings", oid=oid).form("/me/settings/delete")
        return self.console.submit(form, oid=oid)

    def test_it_deletes_the_settings_and_the_notes_of_the_person(self):
        reply = self.delete()
        self.assertEqual(reply.status, 200)
        self.assertEqual(self.console.store.notes_of(TINO), [])
        self.assertNotIn(TINO, self.console.store.settings)
        self.assertEqual(self.console.store.settings_get(TINO), SettingsRecord(oid=TINO), "the starting values are back")
        self.assertEqual(self.console.store.do_not_touch(), set(), "the do-not-touch mark of a deleted note is gone")

    def test_it_keeps_the_approval_records_and_says_so(self):
        reply = self.delete()
        self.assertEqual([d.decision for d in self.console.store.decisions_by(TINO)], ["approve"])
        self.assertEqual(self.console.store.action_get("plan0001").state, "queued")
        self.assertEqual(self.console.store.plan_get("plan0001").state, "open")
        self.assertIn("Your settings and your notes are deleted.", reply.content)
        self.assertIn("Approval records are kept. They hold only your directory object id, and they follow the retention of the organisation that runs Meternaut.", reply.content)
        self.assertIn("Approval records are not deleted", self.console.get("/me/settings").content)

    def test_it_leaves_everybody_else_alone(self):
        self.delete()
        self.assertEqual(self.console.store.settings_get(MAYA).channel, "teams")
        self.assertEqual([n.note_id for n in self.console.store.notes_of(MAYA)], ["n3"])

    def test_the_person_can_still_use_the_console_afterwards(self):
        self.delete()
        reply = self.console.get("/me/settings")
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.form("/me/settings", has_button="Save settings").fields["channel"], "email")
        self.assertEqual(self.console.get("/me/decisions").status, 200)

    def test_a_store_that_fails_on_the_way_says_that_something_may_remain(self):
        def fail(oid):
            raise StoreError("down", 503)
        self.console.store.settings_delete = fail
        reply = self.delete()
        self.assertEqual(reply.status, 503)
        self.assertIn("Open the page again to see what was stored.", reply.content)


class TheNotesPage(unittest.TestCase):
    RESOURCE = f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/Microsoft.Compute/disks/disk-1"

    def setUp(self):
        self.console = Console()

    def form(self, oid=TINO):
        return self.console.get("/me/notes", oid=oid).form("/me/notes", has_button="Save")

    def add(self, oid=TINO, **fields):
        base = {"kind": "note", "resource_id": self.RESOURCE, "text": "This disk is the standby.", "expires": "2026-12-01"}
        form = self.form(oid)
        return self.console.post("/me/notes", {**form.fields, **base, **fields}, oid=oid)

    def test_an_empty_page_says_so_and_has_the_form(self):
        reply = self.console.get("/me/notes")
        self.assertEqual(reply.headings(1), ["What I know about your resources"])
        self.assertIn("You have no note and no do-not-touch mark.", reply.content)
        self.assertIn("A note is about one resource and never more. Every note expires", reply.content)
        self.assertEqual(sorted(k for k in self.form().fields), ["expires", "kind", "nonce", "resource_id", "text"])
        self.assertEqual(self.form().fields["kind"], "note")
        expires = reply.root.find("input", id="expires")
        self.assertEqual((expires.attrs["type"], expires.attrs["min"], expires.attrs["max"]), ("date", "2026-11-05", "2027-11-05"))

    def test_a_note_is_stored_with_its_scope_source_and_expiry_and_listed(self):
        reply = self.add()
        self.assertEqual(reply.status, 200)
        notes = self.console.store.notes_of(TINO)
        self.assertEqual(len(notes), 1)
        note = notes[0]
        self.assertRegex(note.note_id, r"^n[0-9a-f]{12}$")
        self.assertEqual((note.oid, note.kind, note.text, note.scope_resource_id, note.source, note.created_at, note.expires_at, note.uses),
                         (TINO, "note", "This disk is the standby.", self.RESOURCE, "you, on the notes page", "2026-11-05T09:00:00Z", "2026-12-01T23:59:59Z", 0))
        self.assertEqual(note.understood_as, "A note about this one resource. It stops nothing.")
        row = reply.table("notes").rows[0]
        self.assertEqual(row["Kind"], "Note")
        self.assertEqual(row["Resource"], self.RESOURCE)
        self.assertEqual(row["What you wrote"], "This disk is the standby.")
        self.assertEqual(row["Source"], "you, on the notes page")
        self.assertEqual(row["Expires"], "Tue 1 Dec 2026 23:59 UTC (Wed 2 Dec 2026 00:59 CET)")
        self.assertEqual(row["Times used"], "0")
        self.assertIn("Saved", [p.text() for p in reply.root.find_all("p", class_="notice-title")])

    def test_a_do_not_touch_mark_is_one_that_the_store_reports(self):
        reply = self.add(kind="do_not_touch")
        self.assertEqual(reply.status, 200)
        self.assertEqual(self.console.store.do_not_touch(), {self.RESOURCE.lower()})
        note = self.console.store.notes_of(TINO)[0]
        self.assertEqual(note.kind, "do_not_touch")
        self.assertIn("No plan is made for it, and the runner makes no change to it, until the mark expires.", note.understood_as)
        self.assertEqual(reply.table("notes").rows[0]["Kind"], "Do-not-touch mark")
        self.console.now = dt.datetime(2026, 12, 2, 9, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(self.console.store.do_not_touch(), set(), "the mark ends at its expiry")
        self.assertIn("(expired)", self.console.get("/me/notes").table("notes").rows[0]["Expires"])

    def test_only_the_id_of_one_resource_is_accepted(self):
        good = (self.RESOURCE, self.RESOURCE.upper().replace("/SUBSCRIPTIONS/", "/subscriptions/"), f"/subscriptions/{SUB}/resourceGroups/rg_a.b-(c)/providers/Microsoft.Sql/servers/s1/databases/d1",
                f"  {self.RESOURCE}  ")
        bad = (f"/subscriptions/{SUB}", f"/subscriptions/{SUB}/resourceGroups/rg-app", f"/subscriptions/{SUB}/resourceGroups/rg-app/", f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/Microsoft.Compute",
               f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/Microsoft.Compute/disks", f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/Microsoft.Compute/disks/disk-1/extra",
               self.RESOURCE + "/", "/subscriptions/not-a-guid/resourceGroups/rg/providers/Microsoft.Compute/disks/d", f"/subscriptions/{SUB}/resourcegroups//providers/Microsoft.Compute/disks/d",
               "disk-1", "", "all resources", self.RESOURCE + " and more", self.RESOURCE.replace("rg-app", "rg app"), self.RESOURCE.replace("disk-1", "<b>"),
               self.RESOURCE.replace("rg-app", ".."), "https://example.test" + self.RESOURCE, "*", f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/Microsoft.Compute/disks/*")
        for index, value in enumerate(good):
            with self.subTest(good=value):
                self.assertEqual(self.add(resource_id=value, text=f"note {index}").status, 200)
        self.assertEqual(len(self.console.store.notes_of(TINO)), len(good))
        before = snapshot(self.console.store)
        for value in bad:
            with self.subTest(bad=value):
                reply = self.add(resource_id=value)
                self.assertEqual(reply.status, 400)
                self.assertIn("Enter the id of one resource: /subscriptions/<id>/resourceGroups/<name>/providers/<type>/<name>. A resource group or a subscription is not accepted.", reply.content)
        self.assertEqual(snapshot(self.console.store), before)

    def test_the_text_is_one_to_300_characters_and_clean(self):
        before = snapshot(self.console.store)
        for value, message in (("", "Write what you know about the resource."), ("   \t ", "Write what you know about the resource."),
                               ("a" * 301, "The text has 301 characters. The most is 300.")):
            with self.subTest(length=len(value)):
                reply = self.add(text=value)
                self.assertEqual(reply.status, 400)
                self.assertIn(message, reply.content)
        self.assertEqual(snapshot(self.console.store), before)
        self.assertEqual(self.add(text="a").status, 200)
        self.assertEqual(self.add(text="b" * 300).status, 200)
        self.assertEqual(self.add(text="line one\r\n\x00line   two").status, 200)
        self.assertIn("line one line two", [n.text for n in self.console.store.notes_of(TINO)])

    def test_the_expiry_is_required_and_at_most_a_year_away(self):
        before = snapshot(self.console.store)
        for value in ("", "2026-11-04", "2027-11-06", "2026-13-01", "tomorrow", "2026-12-1", "20261201", "2026-12-01T10:00"):
            with self.subTest(value=value):
                reply = self.add(expires=value)
                self.assertEqual(reply.status, 400)
                self.assertIn("Enter an expiry date from 2026-11-05 to 2027-11-05 as YYYY-MM-DD. A note always expires.", reply.content)
        self.assertEqual(snapshot(self.console.store), before)
        for value in ("2026-11-05", "2027-11-05"):
            with self.subTest(value=value):
                self.assertEqual(self.add(expires=value, text=f"until {value}").status, 200)
        self.assertEqual(sorted(n.expires_at for n in self.console.store.notes_of(TINO)), ["2026-11-05T23:59:59Z", "2027-11-05T23:59:59Z"])

    def test_the_kind_is_a_note_or_a_do_not_touch_mark(self):
        for value in ("", "wide", "NOTE", "note,do_not_touch"):
            with self.subTest(kind=value):
                reply = self.add(kind=value)
                self.assertEqual(reply.status, 400)
                self.assertIn("Choose a note or a do-not-touch mark.", reply.content)
        self.assertEqual(self.console.store.notes_of(TINO), [])

    def test_what_was_typed_is_kept_when_it_is_refused_and_each_problem_links_to_its_field(self):
        reply = self.add(resource_id="nope", text="my text", expires="")
        fields = reply.form("/me/notes", has_button="Save").fields
        self.assertEqual((fields["resource_id"], fields["text"], fields["expires"]), ("nope", "my text", ""))
        links = [a.attrs["href"] for a in reply.root.find("h2", id="problem-title").parent.find_all("a")]
        self.assertEqual(sorted(links), ["#expires", "#resource_id"])

    def test_a_note_is_for_one_person(self):
        self.add(oid=TINO)
        self.add(oid=MAYA, text="Maya's note")
        self.assertEqual([n.text for n in self.console.store.notes_of(TINO)], ["This disk is the standby."])
        self.assertEqual([n.text for n in self.console.store.notes_of(MAYA)], ["Maya's note"])
        self.assertNotIn("Maya's note", self.console.get("/me/notes").text)
        form = self.form(MAYA)
        self.console.post("/me/notes", {**form.fields, "kind": "note", "resource_id": self.RESOURCE, "text": "not for Tino", "expires": "2026-12-01", "oid": TINO}, oid=MAYA)
        self.assertEqual(len(self.console.store.notes_of(TINO)), 1)
        self.assertEqual(len(self.console.store.notes_of(MAYA)), 2)

    def test_a_person_may_have_at_most_100_notes(self):
        for n in range(100):
            self.console.store.note_put(NoteRecord(f"n{n}", TINO, "note", "t", None, "x", "you", at(days=-1), at(days=9), 0))
        reply = self.add()
        self.assertEqual(reply.status, 400)
        self.assertIn("You have 100 notes. Delete one before you add another.", reply.content)
        self.assertEqual(len(self.console.store.notes_of(TINO)), 100)

    def test_a_note_can_be_deleted_by_its_person_only(self):
        self.console.store.note_put(NoteRecord("n1", TINO, "note", "mine", self.RESOURCE, "x", "you", at(days=-1), at(days=9), 1))
        self.console.store.note_put(NoteRecord("n1", MAYA, "note", "hers", self.RESOURCE, "x", "you", at(days=-1), at(days=9), 1))
        page = self.console.get("/me/notes")
        delete = page.form("/me/notes/n1/delete")
        self.assertEqual(delete.buttons, [("", "", f"Delete the note about {self.RESOURCE}")])
        hers = self.console.get("/me/notes", oid=MAYA).form("/me/notes/n1/delete")
        reply = self.console.post("/me/notes/n1/delete", {"nonce": hers.fields["nonce"]}, oid=TINO)
        self.assertEqual(reply.status, 403, "her token is hers")
        reply = self.console.submit(delete)
        self.assertEqual(reply.status, 200)
        self.assertIn("The note is deleted.", reply.content)
        self.assertEqual(self.console.store.notes_of(TINO), [])
        self.assertEqual([n.text for n in self.console.store.notes_of(MAYA)], ["hers"], "the note of the same id of somebody else is still there")

    def test_a_note_that_does_not_exist_is_a_404_and_changes_nothing(self):
        self.console.store.note_put(NoteRecord("n1", TINO, "note", "mine", None, "x", "you", at(days=-1), at(days=9), 1))
        token = self.console.get("/me/notes").form("/me/notes/n1/delete").fields["nonce"]
        before = snapshot(self.console.store)
        reply = self.console.post("/me/notes/n2/delete", {"nonce": token})
        self.assertEqual(reply.status, 404)
        self.assertIn("I cannot find this note", reply.content)
        self.assertEqual(snapshot(self.console.store), before)

    def test_the_list_shows_the_use_count_the_source_and_how_it_was_understood(self):
        self.console.store.note_put(NoteRecord("n1", TINO, "do_not_touch", "Keep it", self.RESOURCE, "Do not touch this resource.", "the owner", at(days=-1), at(days=9), 4))
        row = self.console.get("/me/notes").table("notes").rows[0]
        self.assertEqual((row["Kind"], row["Resource"], row["What you wrote"], row["How it was understood"], row["Source"], row["Times used"]),
                         ("Do-not-touch mark", self.RESOURCE, "Keep it", "Do not touch this resource.", "the owner", "4"))
        self.assertEqual(row["Added"], "Wed 4 Nov 2026 09:00 UTC (10:00 CET)")
        self.assertEqual(row["Expires"], "Sat 14 Nov 2026 09:00 UTC (10:00 CET)")

    def test_a_note_that_names_no_resource_says_so(self):
        self.console.store.note_put(NoteRecord("n1", TINO, "note", "old", None, "", "x", at(days=-1), "", 0))
        row = self.console.get("/me/notes").table("notes").rows[0]
        self.assertEqual(row["Resource"], "no resource is named")

    def test_notes_that_cannot_be_read_are_said_plainly(self):
        console = Console(store=FailingStore(fail={"notes_of"}, clock=lambda: NOW))
        reply = console.get("/me/notes")
        self.assertEqual(reply.status, 200)
        self.assertIn("Your notes cannot be read", reply.content)


if __name__ == "__main__":
    unittest.main()
