import ast
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("aigateway_check", ROOT / "tools" / "aigateway-check.py")
ac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ac)

HOST = "aigw-meternaut-1a2b3c4d.swedencentral-02.ai.gateway.azure.com"
URL = f"https://{HOST}/default/models/openai/v1/chat/completions"
TOKEN = "eyJhbGciOiJub25lIn0.eyJzZWNyZXQiOiJ4In0.SECRET-SIGNATURE-VALUE"
ALIASES = ("gpt-6-luna", "gpt-6.1-sol")
ENV = {"GITHUB_ACTIONS": "true"}


def completion(model="gpt-6-luna-2026-09-22", prompt=14, completion_=9, total=23, text="SECRET-MODEL-TEXT"):
    return json.dumps({"id": "chatcmpl-SECRET-ID", "model": model, "choices": [{"message": {"role": "assistant", "content": text}}],
                       "usage": {"prompt_tokens": prompt, "completion_tokens": completion_, "total_tokens": total}}).encode("utf-8")


class Network:
    """The Azure CLI and the gateway, as stand-ins. `answers` maps the kind of request to a status and a body: alias NAME, no-token, wrong-alias."""

    def __init__(self, answers=None, token=(0, TOKEN + "\n", "")):
        self.token_answer = token
        self.cli, self.posts = [], []
        self.answers = {"alias": (200, completion()), "no-token": (401, b'{"error":"SECRET-ERROR-BODY"}'), "wrong-alias": (404, b'{"error":"SECRET-NOT-FOUND-BODY"}')}
        self.answers.update(answers or {})

    def runner(self, args):
        self.cli.append(args)
        return self.token_answer

    def post(self, url, headers, body):
        document = json.loads(body.decode("utf-8"))
        self.posts.append({"url": url, "headers": dict(headers), "body": document})
        if "Authorization" not in headers:
            kind = "no-token"
        elif document["model"] == ac.WRONG_ALIAS:
            kind = "wrong-alias"
        else:
            kind = ("alias", document["model"])
        answer = self.answers.get(kind) or self.answers["alias"]
        return answer(document) if callable(answer) else answer

    def gateway(self):
        return ac.Gateway(runner=self.runner, post=self.post)


def run_tool(network, *arguments, env=ENV):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err), mock.patch.dict(os.environ, env, clear=False):
        if "GITHUB_ACTIONS" not in env:
            os.environ.pop("GITHUB_ACTIONS", None)
        try:
            code = ac.main(["run", *arguments], gateway=network.gateway())
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


def good_arguments():
    return ["--host", HOST, "--alias", ALIASES[0], "--alias", ALIASES[1]]


class AGoodRun(unittest.TestCase):
    def test_it_calls_each_alias_and_sends_the_two_requests_that_must_be_refused_and_prints_status_model_and_usage_only(self):
        network = Network()
        code, out, err = run_tool(network, *good_arguments())
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(out.splitlines(), [
            "ok: alias gpt-6-luna: status 200 (expected 200), model gpt-6-luna-2026-09-22, usage prompt 14, completion 9, total 23",
            "ok: alias gpt-6.1-sol: status 200 (expected 200), model gpt-6-luna-2026-09-22, usage prompt 14, completion 9, total 23",
            "ok: no token: status 401 (expected 401)",
            "ok: wrong alias: status 404 (expected a status of 400 to 499)",
            "All 4 checks passed."])

    def test_the_requests_it_builds_are_the_ones_of_the_gateway_s_openai_route_with_the_alias_as_the_model(self):
        network = Network()
        run_tool(network, *good_arguments())
        self.assertEqual([p["url"] for p in network.posts], [URL] * 4)
        first, second, no_token, wrong = network.posts
        for post, alias in ((first, ALIASES[0]), (second, ALIASES[1])):
            self.assertEqual(post["headers"]["Authorization"], f"Bearer {TOKEN}")
            self.assertEqual(post["headers"]["Content-Type"], "application/json")
            self.assertEqual(post["body"], {"model": alias, "messages": [{"role": "user", "content": "Reply with the word ok."}], "max_completion_tokens": 256})
        self.assertNotIn("Authorization", no_token["headers"], "the second request carries no token at all")
        self.assertEqual(no_token["body"]["model"], ALIASES[0])
        self.assertEqual(wrong["headers"]["Authorization"], f"Bearer {TOKEN}", "the wrong alias is asked for with a good token, so that only the alias is wrong")
        self.assertEqual(wrong["body"]["model"], "meternaut-no-such-alias")
        for post in network.posts:
            self.assertNotIn("max_tokens", post["body"], "these models reason before they answer, and a small max_tokens is refused: the cap is max_completion_tokens")
            self.assertNotIn("api-key", {k.lower() for k in post["headers"]}, "no key: the token is the only credential")

    def test_the_token_is_asked_for_once_for_the_audience_of_the_gateway_and_never_printed(self):
        network = Network()
        code, out, err = run_tool(network, *good_arguments())
        self.assertEqual(network.cli, [["account", "get-access-token", "--resource", "https://azure-api.net/aigateway", "--query", "accessToken", "--output", "tsv", "--only-show-errors"]])
        for text in (out, err):
            self.assertNotIn(TOKEN, text)
            self.assertNotIn("SECRET-SIGNATURE-VALUE", text)
            self.assertNotIn("Bearer", text)

    def test_nothing_of_an_answer_is_printed_beyond_the_status_the_model_name_and_the_usage(self):
        # a header, a body, an id and the text of a model must never reach the log, whatever the answers hold
        answers = {("alias", "gpt-6-luna"): (200, completion(text="SECRET-MODEL-TEXT")), "no-token": (401, b"SECRET-HEADER-AND-BODY"), "wrong-alias": (400, b'{"message":"SECRET-DETAIL"}')}
        code, out, err = run_tool(Network(answers), *good_arguments())
        self.assertEqual(code, 0)
        for word in ("SECRET-MODEL-TEXT", "SECRET-ID", "SECRET-HEADER-AND-BODY", "SECRET-DETAIL", "chatcmpl"):
            self.assertNotIn(word, out + err, word)

    def test_a_model_name_that_is_not_a_plain_name_is_not_printed(self):
        answers = {("alias", "gpt-6-luna"): (200, completion(model="SECRET <script> ${x}"))}
        code, out, _ = run_tool(Network(answers), *good_arguments())
        self.assertEqual(code, 0)
        self.assertIn("alias gpt-6-luna: status 200 (expected 200), no model name that is a plain name, usage prompt 14", out)
        self.assertNotIn("SECRET", out)

    def test_the_lines_go_to_the_summary_file_when_one_is_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            code, out, _ = run_tool(Network(), *good_arguments(), "--summary", str(summary))
            text = summary.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn("### The AI Gateway, called from inside the network", text)
        self.assertIn(f"Host: `{HOST}`", text)
        self.assertIn("ok: alias gpt-6.1-sol: status 200", text)
        self.assertNotIn(TOKEN, text)


class WhenAnAnswerIsNotTheExpectedOne(unittest.TestCase):
    def test_a_status_that_is_not_200_for_an_alias_fails_the_check_and_gives_a_fixed_hint_and_no_body(self):
        for status, words in ((401, "service principal"), (403, "AI Gateway Models User"), (404, "no alias of this name"), (429, "rate limit"), (0, "could not be reached")):
            with self.subTest(status=status):
                code, out, err = run_tool(Network({("alias", "gpt-6-luna"): (status, b"SECRET-BODY")}), *good_arguments())
                self.assertEqual(code, 1)
                shown = f"status {status}" if status else "no answer"
                self.assertIn(f"FAILED: alias gpt-6-luna: {shown} (expected 200)", out)
                self.assertIn("  hint: ", out)
                self.assertIn(words, out)
                self.assertNotIn("SECRET-BODY", out + err)
                self.assertIn("1 of 4 checks failed.", err)

    def test_other_statuses_fail_without_a_hint_and_the_other_aliases_are_still_checked(self):
        code, out, _ = run_tool(Network({("alias", "gpt-6-luna"): (500, b"")}), *good_arguments())
        self.assertEqual(code, 1)
        self.assertIn("FAILED: alias gpt-6-luna: status 500 (expected 200)\nok: alias gpt-6.1-sol", out)
        self.assertNotIn("hint", out)

    def test_a_200_without_usage_fails_because_the_limits_of_the_gateway_count_tokens(self):
        for body in (b"{}", b"not json", b"[]", b'{"usage":{"prompt_tokens":1,"completion_tokens":1}}', b'{"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":0}}',
                     b'{"usage":{"prompt_tokens":"1","completion_tokens":1,"total_tokens":2}}', b'{"usage":{"prompt_tokens":true,"completion_tokens":1,"total_tokens":2}}'):
            with self.subTest(body=body):
                code, out, _ = run_tool(Network({("alias", "gpt-6-luna"): (200, body)}), *good_arguments())
                self.assertEqual(code, 1)
                self.assertIn("FAILED: alias gpt-6-luna: status 200 (expected 200 with usage), and the answer carries no usage numbers", out)

    def test_a_gateway_that_takes_a_request_without_a_token_fails_the_check(self):
        for status in (200, 400, 403, 404, 500):
            with self.subTest(status=status):
                code, out, _ = run_tool(Network({"no-token": (status, completion())}), *good_arguments())
                self.assertEqual(code, 1)
                self.assertIn(f"FAILED: no token: status {status} (expected 401)", out)
                self.assertIn("Microsoft Entra is not the only way in", out)

    def test_a_wrong_alias_must_be_answered_with_a_status_of_400_to_499(self):
        for status, passes in ((400, True), (404, True), (422, True), (499, True), (200, False), (500, False), (0, False)):
            with self.subTest(status=status):
                code, out, _ = run_tool(Network({"wrong-alias": (status, b"")}), *good_arguments())
                self.assertEqual(code == 0, passes, out)
                self.assertIn(f"{'ok' if passes else 'FAILED'}: wrong alias: ", out)


class WhatItRefusesToRun(unittest.TestCase):
    def refused(self, *arguments, env=ENV):
        network = Network()
        code, out, err = run_tool(network, *arguments, env=env)
        self.assertEqual(code, 2, (arguments, out, err))
        self.assertEqual((network.cli, network.posts), ([], []), "nothing was asked for and nothing was sent")
        self.assertEqual(out, "")
        return err

    def test_it_refuses_without_the_host_name_of_the_gateway(self):
        err = self.refused("--alias", "gpt-6-luna")
        self.assertIn("--host", err)
        err = self.refused("--host", "", "--alias", "gpt-6-luna")
        self.assertIn("there is none", err)
        err = self.refused("--host", "   ", "--alias", "gpt-6-luna")
        self.assertIn("there is none", err)

    def test_it_sends_a_token_only_to_a_host_under_the_gateway_s_domain(self):
        for bad in ("example.com", "ai.gateway.azure.com", f"{HOST}.evil.example", f"evil.example/{HOST}", f"https://{HOST}", f"{HOST}/default", f"{HOST}:8443", "x.azure-api.net",
                    "aigw..ai.gateway.azure.com", "-x.ai.gateway.azure.com", "x_y.ai.gateway.azure.com", "x y.ai.gateway.azure.com", f"user@{HOST}", "localhost", "10.0.0.4"):
            with self.subTest(host=bad):
                err = self.refused(f"--host={bad}", "--alias", "gpt-6-luna")
                self.assertIn("under .ai.gateway.azure.com", err)
                self.assertNotIn(TOKEN, err)

    def test_the_host_name_is_not_case_sensitive(self):
        network = Network()
        code, _, err = run_tool(network, "--host", HOST.upper(), "--alias", "gpt-6-luna")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(network.posts[0]["url"], URL)

    def test_it_refuses_without_an_alias_or_with_a_name_that_is_not_one(self):
        self.assertIn("at least one is needed", self.refused("--host", HOST))
        for bad in ("", "a b", "a/b", "-a", "a-", ".a", "a" * 300, "gpt?", 'a"b', "meternaut-no-such-alias"):
            with self.subTest(alias=bad):
                self.assertIn("--alias", self.refused("--host", HOST, "--alias", bad))
        self.assertIn("each given once", self.refused("--host", HOST, "--alias", "a", "--alias", "a"))

    def test_it_refuses_a_cap_of_the_completion_that_is_outside_its_bounds(self):
        for bad in ("0", "-1", "1025", "x"):
            with self.subTest(cap=bad):
                network = Network()
                code, out, err = run_tool(network, *good_arguments(), "--max-completion-tokens", bad)
                self.assertEqual(code, 2)
                self.assertEqual(network.posts, [])
        network = Network()
        run_tool(network, *good_arguments(), "--max-completion-tokens", "64")
        self.assertEqual({p["body"]["max_completion_tokens"] for p in network.posts}, {64})

    def test_it_refuses_outside_a_github_actions_run_because_a_call_to_a_model_bills(self):
        err = self.refused(*good_arguments(), env={"SOMETHING": "else"})
        self.assertIn("only a GitHub Actions run may start it (AGENTS.md rule 18)", err)

    def test_it_takes_nothing_but_the_run_command(self):
        for arguments in ([], ["call"], ["--host", HOST]):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err), self.assertRaises(SystemExit) as raised:
                ac.main(arguments)
            self.assertEqual(raised.exception.code, 2)


class WhenThereIsNoToken(unittest.TestCase):
    def test_a_tenant_without_the_service_principal_is_told_how_to_get_one_and_nothing_is_sent(self):
        network = Network(token=(1, "", "ERROR: AADSTS500011: The resource principal named https://azure-api.net/aigateway was not found in the tenant named Contoso (aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee).\nTrace ID: x\n"))
        code, out, err = run_tool(network, *good_arguments())
        self.assertEqual(code, 1)
        self.assertEqual(network.posts, [])
        self.assertIn("the tenant has no service principal for the gateway's audience", err)
        self.assertIn("18550318-e177-4205-a743-6816d6fcdc3f", err)
        self.assertIn("Azure AI Gateway Dataplane", err)
        self.assertIn("docs/proposals/08-ai-gateway.md", err)
        self.assertNotIn("Contoso", err + out, "what the CLI said about the tenant is not repeated")
        self.assertNotIn("aaaaaaaa-bbbb", err + out)

    def test_another_failure_gives_its_first_line_with_ids_and_long_strings_hidden(self):
        message = "ERROR: Please run 'az login' to setup account for aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee " + "x" * 60 + "\nsecond line SECRET"
        code, out, err = run_tool(Network(token=(1, "", message)), *good_arguments())
        self.assertEqual(code, 1)
        self.assertIn("no token for https://azure-api.net/aigateway: ERROR: Please run 'az login' to setup account for <id> <hidden>", err)
        self.assertNotIn("second line", err)
        self.assertNotIn("aaaaaaaa", err)

    def test_an_empty_token_is_no_token(self):
        network = Network(token=(0, "\n", ""))
        code, _, err = run_tool(network, *good_arguments())
        self.assertEqual(code, 1)
        self.assertEqual(network.posts, [])
        self.assertIn("no token for", err)


class TheCode(unittest.TestCase):
    SOURCE = (ROOT / "tools" / "aigateway-check.py").read_text(encoding="utf-8")

    def test_it_uses_the_standard_library_only(self):
        tree = ast.parse(self.SOURCE)
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or "").split(".")[0])
        self.assertEqual(sorted(m for m in modules if m not in sys.stdlib_module_names), [])

    def test_a_redirect_is_not_followed_because_it_would_carry_the_bearer_token_along(self):
        handler = ac.NoRedirect()
        request = urllib.request.Request(URL, data=b"{}", headers={"Authorization": f"Bearer {TOKEN}"}, method="POST")
        self.assertIsNone(handler.redirect_request(request, None, 307, "Temporary Redirect", {}, "https://evil.example/"))
        self.assertIn(ac.NoRedirect, {type(h) for h in ac.OPENER.handlers})

    def test_the_constants_are_the_ones_of_the_service(self):
        self.assertEqual(ac.AUDIENCE, "https://azure-api.net/aigateway")
        self.assertEqual(ac.HOST_SUFFIX, ".ai.gateway.azure.com")
        self.assertEqual(ac.CHAT_PATH, "/default/models/openai/v1/chat/completions")
        self.assertEqual(ac.SERVICE_PRINCIPAL, "18550318-e177-4205-a743-6816d6fcdc3f")

    def test_it_holds_no_key_and_asks_for_no_key(self):
        code = re.sub(r'""".*?"""', "", re.sub(r"(?m)^\s*#.*$", "", self.SOURCE), flags=re.S)
        for word in ("api-key", "listKeys", "listSecrets", "primaryKey", "x-api-key", "Ocp-Apim"):
            self.assertNotIn(word, code, word)

    def test_it_is_small_enough_for_the_secret_volume_of_a_container_group(self):
        self.assertLess((ROOT / "tools" / "aigateway-check.py").stat().st_size, 100_000, "the whole request of a container group takes at most 480,000 bytes of files")

    def test_its_arguments_pass_the_input_check_of_the_script_that_runs_it_in_the_operator(self):
        script = (ROOT / "operator" / "run-tool.sh").read_text(encoding="utf-8")
        allowed = re.search(r"argument_characters='(.+?)'", script).group(1)
        command = re.search(r"command_word='(.+?)'", script).group(1)
        args = f"run --host {HOST} --alias gpt-6-luna --alias gpt-6.1-sol"
        self.assertRegex(args, allowed)
        self.assertRegex(args.split(" ")[0], command)
        self.assertLessEqual(len(args), 600)
        self.assertRegex("aigateway-check", r"^[a-z][a-z0-9-]{0,39}$")


if __name__ == "__main__":
    unittest.main()
