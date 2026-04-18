## Release metadata prompt rule
- After finishing any task or subtask in this repository, the agent must ask the user this exact prompt:
  Say "Update" if you want me to update release_info.json with:
  version: "v1.0.x" (where x is always the current value in the file + 1)
  date: YYYY-MM-DD (where the date is today)
  nickname: xx (where xx is a 1-5 word summary of the most important changes)
- The agent must not change `release_info.json` unless the user explicitly says "Update".
- If the user says "Update", compute the next patch version from the current file value and use today's date.

## Request history and conflict-check rule
- Keep a record of all requested changes in `build_instructions.txt`, summarized in the agent's own words.
- Before implementing any new request, read `build_instructions.txt` and check whether the new request aligns with previous requests.
- If the new request conflicts with previous requests, do not implement immediately; ask the user for clarification first.
- After the request is clarified and implemented, append a new summarized entry to `build_instructions.txt`.
