import json
import unittest

from cases import loop_config, people
from cases.models import Principal

OID = "aaaaaaaa-1111-4222-8333-444444444444"
OTHER = "11111111-2222-3333-4444-555555555555"
SUBSCRIPTION = "bbbbbbbb-2222-4333-9444-555555555555"
WRITER = "55555555-4444-3333-2222-111111111111"


def person(**changes):
    value = {"oid": OID, "name": "Tino", "roles": ["owner", "approver", "ops"], "mail": "tino@example.com"}
    value.update(changes)
    return value


def env(*persons):
    return {people.SETTING: json.dumps(list(persons))}


class LoadPeople(unittest.TestCase):
    def test_a_list_is_read_with_lower_case_ids_and_each_role_once(self):
        found = people.load(env(person(oid=OID.upper(), roles=["approver", "approver", "ops"]), person(oid=OTHER, name="Ada", roles=["ops"], mail="")))
        self.assertEqual([p.oid for p in found.persons], [OID, OTHER])
        self.assertEqual(found.persons[0].roles, ("approver", "ops"))
        self.assertEqual(found.persons[1].mail, "")

    def test_a_person_is_found_by_object_id_in_any_case_and_only_that(self):
        found = people.load(env(person()))
        self.assertEqual(found.by_oid(OID.upper()).name, "Tino")
        self.assertIsNone(found.by_oid(OTHER))
        self.assertIsNone(found.by_oid(""))
        self.assertIsNone(found.by_oid(None))

    def test_the_signed_in_person_is_a_principal_only_when_listed(self):
        found = people.load(env(person()))
        self.assertEqual(found.principal(OID.upper()), Principal(OID, "Tino", ("owner", "approver", "ops")))
        self.assertIsNone(found.principal(OTHER))
        self.assertIsNone(found.principal(None))

    def test_who_holds_a_role_and_which_addresses_may_get_a_letter(self):
        found = people.load(env(person(), person(oid=OTHER, name="Ada", roles=["ops"], mail="Ada@Example.com"), person(oid="22222222-3333-4444-5555-666666666666", name="Bo", roles=["owner"], mail="")))
        self.assertEqual([p.name for p in found.with_role("ops")], ["Tino", "Ada"])
        self.assertEqual([p.name for p in found.with_role("approver")], ["Tino"])
        self.assertEqual(found.allowed_addresses(), frozenset({"tino@example.com", "ada@example.com"}))

    def test_a_setting_that_is_missing_or_wrong_is_refused_and_says_what(self):
        cases = (
            ({}, "is not set"),
            ({people.SETTING: "   "}, "is not set"),
            ({people.SETTING: "{not json"}, "is not JSON"),
            ({people.SETTING: json.dumps({"oid": OID})}, "list of one to"),
            ({people.SETTING: "[]"}, "list of one to"),
            (env(*[person(oid=f"{n:08d}-2222-3333-4444-555555555555", name=f"P{n}") for n in range(21)]), "list of one to"),
            ({people.SETTING: json.dumps(["Tino"])}, "person 1 is not an object"),
            (env(person(oid=None)), "person 1 has no object id"),
            (env(person(oid="not-a-guid")), "person 1 has no object id"),
            (env(person(name="")), "person 1 has no name"),
            (env(person(name="x" * 81)), "person 1 has no name"),
            (env(person(roles=[])), "roles that are not among"),
            (env(person(roles="owner")), "roles that are not among"),
            (env(person(roles=["owner", "root"])), "roles that are not among"),
            (env(person(mail="not an address")), "not an address"),
            (env(person(mail=5)), "not an address"),
            (env(person(), person(name="Again")), "listed twice"),
        )
        for setting, word in cases:
            with self.assertRaises(people.PeopleError, msg=str(setting)[:80]) as raised:
                people.load(setting)
            self.assertIn(word, str(raised.exception))

    def test_an_error_never_holds_an_address(self):
        with self.assertRaises(people.PeopleError) as raised:
            people.load(env(person(mail="secret person@example.com")))
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("example.com", str(raised.exception))


FULL = {
    "STORE_ACCOUNT_NAME": "stexample", "WRITER_RESOURCE_GROUP": "rg-meternaut", "WRITER_SUBSCRIPTION_ID": SUBSCRIPTION.upper(), "WRITER_CLIENT_ID": WRITER,
    "CONSOLE_HOST": "Func-Example.azurewebsites.net",
}


class LoadLoopSettings(unittest.TestCase):
    def test_the_loop_is_off_when_no_store_is_named(self):
        for value in ({}, {"STORE_ACCOUNT_NAME": ""}, {"STORE_ACCOUNT_NAME": "   ", "WRITER_CLIENT_ID": WRITER}):
            self.assertIsNone(loop_config.load(value))

    def test_a_full_set_is_read_with_the_defaults_and_in_lower_case(self):
        settings = loop_config.load(FULL)
        self.assertEqual((settings.store_account, settings.writer_group, settings.writer_subscription, settings.writer_client_id),
                         ("stexample", "rg-meternaut", SUBSCRIPTION, WRITER))
        self.assertEqual((settings.console_host, settings.base_url), ("func-example.azurewebsites.net", "https://func-example.azurewebsites.net"))
        self.assertEqual((settings.mail_sender, settings.planted_tag, settings.plan_ttl_hours, settings.approval_delay_seconds, settings.recheck_days),
                         (None, "meternaut-planted", 72, 120, 7))

    def test_the_optional_settings_are_read(self):
        settings = loop_config.load({**FULL, "MAIL_SENDER": "meternaut-ai@example.com", "PLANTED_TAG": "planted", "PLAN_TTL_HOURS": "24", "APPROVAL_DELAY_SECONDS": "60",
                                     "RECHECK_DAYS": "3"})
        self.assertEqual((settings.mail_sender, settings.planted_tag, settings.plan_ttl_hours, settings.approval_delay_seconds, settings.recheck_days),
                         ("meternaut-ai@example.com", "planted", 24, 60, 3))

    def test_a_half_configured_loop_is_refused_and_every_missing_setting_is_listed(self):
        with self.assertRaises(loop_config.LoopConfigError) as raised:
            loop_config.load({"STORE_ACCOUNT_NAME": "stexample"})
        for name in ("WRITER_RESOURCE_GROUP", "WRITER_SUBSCRIPTION_ID", "WRITER_CLIENT_ID", "CONSOLE_HOST"):
            self.assertIn(f"{name} is not set", str(raised.exception))

    def test_each_setting_is_checked(self):
        for name, value, word in (
            ("STORE_ACCOUNT_NAME", "Not_Valid", "a storage account name"),
            ("WRITER_RESOURCE_GROUP", "rg with spaces", "a resource group name"),
            ("WRITER_SUBSCRIPTION_ID", "not-a-guid", "a subscription id"),
            ("WRITER_CLIENT_ID", "not-a-guid", "a client id"),
            ("CONSOLE_HOST", "https://func.example.net", "a host name"),
            ("MAIL_SENDER", "not an address", "an address"),
            ("MAIL_SENDER", "meternaut+ai@example.com", "an address"),
            ("PLANTED_TAG", "has space", "a tag name"),
            ("PLAN_TTL_HOURS", "0", "between 1 and 336"),
            ("PLAN_TTL_HOURS", "337", "between 1 and 336"),
            ("PLAN_TTL_HOURS", "many", "not a whole number"),
            ("APPROVAL_DELAY_SECONDS", "29", "between 30 and 3600"),
            ("APPROVAL_DELAY_SECONDS", "3601", "between 30 and 3600"),
            ("RECHECK_DAYS", "0", "between 1 and 90"),
            ("RECHECK_DAYS", "91", "between 1 and 90"),
        ):
            with self.assertRaises(loop_config.LoopConfigError, msg=f"{name}={value}") as raised:
                loop_config.load({**FULL, name: value})
            self.assertIn(word, str(raised.exception))
            self.assertIn(name, str(raised.exception))

    def test_all_the_problems_are_in_one_message(self):
        with self.assertRaises(loop_config.LoopConfigError) as raised:
            loop_config.load({**FULL, "WRITER_CLIENT_ID": "x", "PLAN_TTL_HOURS": "0", "MAIL_SENDER": "x"})
        self.assertEqual(str(raised.exception).count(";"), 2)


if __name__ == "__main__":
    unittest.main()
