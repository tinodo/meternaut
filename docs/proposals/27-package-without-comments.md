# The package without comments: the sources that go to the Operator lose their comments and the text of their docstrings — a decision record

**Status: decided on 2026-11-17 by the orchestrator, for the owner's repair programme; built and tested on this machine, not yet run in the Hub.** The repository keeps the commented sources. Only the copy that is shipped is stripped, by a tool that is deterministic and checks its own work, and that stops the pack when the check fails.

## Why

The Operator's request may carry 480,000 bytes of files at most ([proposal 07](07-private-by-default.md), `MAX_FILE_BYTES` in [`tools/operator-run.py`](../../tools/operator-run.py)): the sources archive and the two scripts. On 2026-11-16 the archive was 388,401 bytes, the request 418,444 and 61,556 stayed free. Five times before that, words in the code were shortened to make room, and the floor of the free room was lowered. The repair programme adds about 100 KB of new source in a day. It would not have fitted, and one more round of shorter words would have made the code worse for the people who read it.

The comments and the docstrings are 31 percent of the bytes of the cases app (106 files, measured on 2026-11-16). The Operator does not read them, and neither does the running app.

## What was decided

- **The strip.** `tools/strip-sources.py` runs in the sources-only branch of `tools/build-function-app.sh`, on the copy of the app that is about to be zipped. It cuts every comment with the white space in front of it, except a comment in the braces of an f-string (allowed since Python 3.12): there the white space in front of it can be text that Python keeps (an `=` expression keeps it; Python 3.12 and 3.13 do, and leave the comment out), so only the comment is cut. It turns every docstring (the first statement of a module, a class or a function, when it is a string) into `""` and keeps the empty lines that its text took. It touches nothing else: a string that is data stays as it is, with a hash, a quote or a line break in it. A docstring that has code after its closing quotes on the same line is left as it is.
- **Every line stays where it was.** A traceback in Application Insights names a file and a line number, and the number is the same as in the repository. *How to read it:* open the file of the repository at that line. The text that Python prints under a line is from the stripped file, so it has no comment.
- **The check, for every file, before anything is written.** The number of lines is the same, every node of the syntax tree starts on the same line, and the tree is the same once the docstrings of both are left out. One file that fails stops the pack: the exit code is 1, the message says which file and why, and no archive is left (the archive of an earlier run is removed before the strip runs, so that nothing can take it for the new one). The strip gives the same bytes for the same text, and the same bytes under Python 3.12 and 3.13 (the 103 files were compared on 2026-11-17).
- **Only the pack of the sources strips.** The Operator unpacks the stripped files and builds the libraries in the container with the same script, which does not strip (the container has no such tool). The runner's own full build, which the checks run, does not strip either.

## The digests do not notice

Three things read the text of the app's own files. Each was made to give the same answer for the file of the repository and for the stripped file.

1. **The lock of the agents.** `cases/lockfile.py` and `cases/harness.py` hashed the text of each tool's method and of three modules. They now hash the syntax tree without docstrings (`code_form`), in a form of its own, because the text of `ast.dump` differs between Python 3.12 and 3.13. A comment, a docstring, white space and a line end are no longer part of a digest. A change of the code still is. The lock was written again with `python tools/agents-lock.py write`, and every digest moved once, because the form of the hash changed and not the code. A test runs the app from a stripped copy and holds all 20 tool digests and the module digest to the lock.
2. **The release.** The action `cases` sets `PACKAGE_SHA256` from `tools/source-digest.py` over the checkout, and the app works out the same digest over the files that run (`cases/release.py`, control A-RELEASE, which pulls the switch of the investigation when they differ). The files that run are the stripped ones, so `tools/source-digest.py` now takes the comments out in memory with the same function as the pack. A test holds the two to each other for the real app, stripped.
3. **Nothing else.** `cases/lockfile.py` also reads `agents.lock.json`, which is not stripped. A search of the app (2026-11-17) for `inspect`, `__doc__`, `getsource`, `__file__` and the reading of a module found no other reader of its own source text. The container's script reads none.

*When two pull requests change the toolbox at the same time,* the lock is written again at the merge: `python tools/agents-lock.py write`, and the result is committed with the merge.

## The room

| | Before | After |
|---|---|---|
| Sources archive | 388,401 bytes | about 255,600 bytes |
| Request (archive and two scripts) | 418,444 bytes | about 285,900 bytes |
| Free below 480,000 | 61,556 bytes | about 194,000 bytes |
| Floor in `tools/tests/test_publish.py` | 61,250 | 150,000 |

The cap is not raised. The floor is now a round 150,000 and says in its message what it protects. The ceiling of the archive has a margin of 20,000 bytes, which is room for the next days of code, and which an archive that is no longer stripped (130,000 bytes more) breaks at once.

### The floor, lowered twice

The floor is 135,000 since the escalation of unanswered requests, the prices of alternatives and the deeper investigation grew the request to about 337,000 bytes (about 143,000 free). The cap of 480,000 is not raised, and the largest request known to work, 466,104 bytes, is far above the request. A floor that moves with every pull request is no plan: the next change that leaves less than 135,000 free looks at what can leave the package (a module that nothing uses, a table that is written twice) before the floor moves again.

The floor is 130,000 since the list prices that code reads for every beat, the requests that end when the bill shows what they suggested, the rule that a finding is asked about only when a saving was priced, and the plain words of the pages grew the request to about 346,000 bytes. The change that crossed 135,000 looked first at what can leave the package: a scan for definitions that nothing in the package uses found about 2,500 bytes, nearly all of them helpers that only the tests use, and no module that no other module imports. The floor moves by 5,000 bytes and no more. The next step is not a lower floor: it is a better encoder for the archive (`zipfile` writes the entry with the default settings of LZMA, and the length of a match and the depth of its search are settings of the encoder alone, so the unpacking does not change), or the helpers that only the tests use leaving the package.

## What is not proved

- **No run in the Hub yet.** The orchestrator runs `cases` and then `cases-run` after the merge. Until then the container's unpacking of a stripped archive on Python 3.12, the start of the app from stripped files, and a live pass of the control A-RELEASE are proved only against copies on this machine.
- **No traceback of the stripped app has been read in Application Insights.** The line numbers are proved by a test (the line of every instruction, every file), not by a failure that happened.
- **Adding or changing a docstring, a comment or white space no longer moves a digest of the lock.** That is by design, and it means a docstring cannot be what makes a lock stale.
- **The check runs on the sources of this repository.** A new construct of the language that the strip does not know would stop the pack with the plain message above, and not ship a wrong file.
- **The time.** Stripping and checking the 103 files takes between 15 and 60 seconds on this machine, which is loaded; the Hub's runner is faster.

## The cap in fetch mode (2026-11-19)

The Hub input `sources` has a second value, `fetch` ([proposal 07](07-private-by-default.md#the-operator-fetches-the-sources-built-on-2026-11-19-not-run-yet)). With it the Operator fetches the files of the commit from GitHub, and the request carries only the two scripts, the digest tool, the lock and the host file: 58,286 bytes at this commit. The cap of 480,000 bytes does not limit the code on that path. What it means for this record:

- **No strip by fetch.** The reason for the strip, the size of the request, is gone on that path, so the files are published as the repository holds them, with their comments and docstrings. A traceback names the same lines either way. The strip stays for `request`, which is still the default, and the decision above stands for it.
- **The digest follows the files.** The app works out its digest over the files that it runs from ([item 2 above](#the-digests-do-not-notice)), so by fetch `PACKAGE_SHA256` is the digest of the files as they are held (`tools/source-digest.py --as-held`), and by request it is still the digest of the stripped files. `tools/drift-check.py` accepts either form of main's digest.
- **The floor belongs to the request way.** The container script is part of every request, and it grew by 6,109 bytes with the fetch (20,894 to 27,003). Measured on an LF copy, the request of the request way went from 348,624 to 354,733 bytes (the archive varies by about 40 bytes with the times of its files) and the free room from 131,376 to 125,267, so the floor of 130,000 in `tools/tests/test_publish.py` has to move to 125,000, which is one step of 5,000 as above. That pin was not changed here. When `fetch` has run on the real estate and is the way, the request way, the strip and this floor can go together.
- **Not proved.** No run of `fetch` on the real estate yet. What it has to show is listed in proposal 07.
