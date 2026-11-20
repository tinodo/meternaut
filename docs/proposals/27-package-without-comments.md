# The package without comments: why the sources lost their comments, and why they have them again — a decision record

**Status: closed on 2026-11-20.** The strip of 2026-11-17 is gone, and so is the way of sending the sources that needed it. The Operator downloads the files of the commit from GitHub and publishes them as the repository holds them, with their comments and their docstrings. The first real run of that route passed on 2026-11-20 (below). What the run did not show is listed at the end.

## Why there was a strip

The Operator is the container that publishes the cases app from inside the network ([proposal 07](07-private-by-default.md)). Until 2026-11-19 it received the app's sources inside its request, and a request may carry 480,000 bytes of files at most (`MAX_FILE_BYTES` in [`tools/operator-run.py`](../../tools/operator-run.py)). The sources outgrew that. On 2026-11-16 the archive was 388,401 bytes, the request 418,444, and 61,556 stayed free. Five times before, words in the code had been shortened to make room, and the floor of free room in the tests had been lowered.

On 2026-11-17 the comments and the docstrings were taken out of the copy that was sent. They were 31 percent of the bytes of the app (106 files, measured on 2026-11-16). The Operator does not read them, and neither does the running app. The repository kept the commented files. A tool did the cutting, checked its own work for every file (the same lines, the same syntax tree) and stopped the pack when the check failed. Every line stayed where it was, so a traceback named the line of the repository.

Three things read the text of the app's own files, and each was made to give the same answer for a commented file and a stripped one. The lock of the agents hashes the syntax tree of a tool's code without its docstrings (`code_form` in `cases/lockfile.py`): a comment, a docstring or a line end is not part of that digest, and a change of the code is. The release digest (`PACKAGE_SHA256`, the control A-RELEASE) was worked out over the stripped text. Nothing else in the app reads its own source.

The room came back, and was used again within days. The floor of free room went from 61,250 to 150,000, then to 135,000, 130,000 and 120,000.

## Why it is gone

On 2026-11-19 the Hub got a second way to send the sources: the Operator downloads the archive of the run's commit from GitHub and holds the files in it against the digest that the workflow worked out over its own checkout, before it signs in. The request then carries the container script, the build script, the digest tool, the lock and the host file, and nothing of the app: 58,286 bytes at that commit. The cap no longer limits the code, so nothing needs the code to be small, and a tool that cuts the comments out of the files that run is a risk with nothing to buy.

On 2026-11-20 that route was run for real and passed, and the decision followed the same day: the fetch is the only way, and everything that existed to squeeze the sources into the request is deleted.

## What was decided

- **One way.** The Hub input `sources` and the pack step are gone. The release step always works out the digest with `tools/source-digest.py src/case-functions --as-held`, and the publish step always sets `PUBLISH_SOURCES_COMMIT`, `PUBLISH_SOURCES_REPOSITORY` and `PUBLISH_SOURCES_DIGEST`. The commit is the commit of the run. The token of the run goes to the container only for a private repository, as a secure value that is named and never given.
- **The container script** has no branch for an archive in its volume, no check of its size and no check for the `lzma` module. It keeps the download, the digest check before the sign-in, the caps of 64 MB for the archive and 2 MB for a file, and the list of what it takes from the archive: `function_app.py` and the `cases/` package, and nothing else. A file in `cases/` that the digest does not cover stops the run. The lock and the host file still come in the request and never from the archive.
- **No strip.** `tools/strip-sources.py` and its test are deleted, and so is the sources-only mode of `tools/build-function-app.sh`. The build script has two switches left: the folder of the files (`FUNCTION_APP_SOURCE_DIR`) and the build in the Operator (`FUNCTION_APP_BUILD_IN_OPERATOR`).
- **One digest.** `tools/source-digest.py` has one mode, the files as the repository holds them. It still accepts the flag `--as-held`, which the Hub's summaries name, and the flag changes nothing. `tools/drift-check.py` compares the app's tag with that one digest, and `cases/release.py` works out the same digest over the files that run. The app that was deployed on 2026-11-20 already carries it, so no drift shows.
- **No floor.** The tests that measured the archive and kept 120,000 bytes free below the cap are deleted. The cap stays as the limit of what a secret volume may carry: the probe's own request of 466,104 bytes is the largest that is known to work. The request of a publish is now about 51,000 bytes, so the cap is far away.
- **What stays.** The comment-proof digests of the lock of the agents stay: they were never a cost, and a comment is still no reason for a lock to be stale.

## What the run of 2026-11-20 showed

On main at commit `d4759dc`, the log of the publish said, in this order: the sources of the commit were fetched from GitHub through the API host, 9,606,614 bytes in 3 seconds; the app's files were taken from the archive, 115 files; the files match the digest of the workflow's checkout; the sign-in as the deploy identity worked; the package was built in the container, 273 files, 1.0 MB zipped in 2 seconds, with the hashes of the lock checked; the deployment site took it at the first attempt. The health address answered 200 at the first try. The `PACKAGE_SHA256` that the app carries equals the digest of the files as they are held, and the check of the log for leaked names and ids was clean.

## The cap in fetch mode (2026-11-19)

This is the record of the day before. The request of the new route was 58,286 bytes at that commit, the floor of 120,000 in `tools/tests/test_publish.py` belonged to the old way, and the strip stayed for it. All of that was left for the day when the new route had run in the real estate. That day was 2026-11-20, and what it decided is above.

## What is not proved

- **The route when `api.github.com` is slow or limited.** The container asks the API host twice, 30 seconds for each try, and then `codeload.github.com` twice, and it says what each host answered. An anonymous address may call the API 60 times an hour (GitHub's documentation; not measured from the container). The run of 2026-11-20 got its answer from the API at the first try. The fall back to the second host has run against a stand-in only.
- **The time that a slow download takes from the sign-in.** The token that the container signs in with lasts five minutes, and the container group takes one to two minutes to start. A download that used every try would take about two minutes more. Whether that can leave the token too old has not been seen: the download took 3 seconds. A sign-in that fails for that reason stops the run before anything is published, and running `cases` again is safe.
- **A private repository.** The route with the token of the run (the API with a bearer, from GitHub's documentation) has never run, because this repository is public. The tests prove that the token is passed by name, reaches curl on standard input only and is never printed. They do not prove that GitHub answers it.
- **A traceback read in Application Insights.** The files that run are the files of the repository, so a line number is the repository's own. No failure that happened has been read to show it.
- **An app that was published before 2026-11-20 by the old way** carries the digest of its stripped files. The drift check would call it drift until a run of `cases` publishes it again. The app that runs today was published by the new way.
