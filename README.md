# synclinear

A Claude Code skill that keeps a git repo's Linear tickets in sync with
its real commit history — with a review step before anything writes to
Linear.

## What it does

1. A **Stop hook** (a script Claude Code runs automatically after every
   turn) cheaply checks the repo you're currently working in for commits
   that haven't been synced to Linear yet.
2. If it finds any, on your *next* message Claude will read the new
   commits, check Linear's currently-open tickets, and propose: which
   tickets should be marked Done (with the commit as evidence), and which
   commits need a brand-new ticket. Trivial commits — plan-doc edits,
   lint/CI fixes, a typo fix — are skipped, not turned into tickets.
3. You see the full proposal as a plain-text list **before anything
   touches Linear.** Nothing gets created or changed until you say OK
   (or edit the list, or reject it).

See [`DESIGN.md`](DESIGN.md) for the full design rationale and
[`SKILL.md`](SKILL.md) for the exact instructions Claude follows on each
sync run.

## Requirements

- [Claude Code](https://claude.com/claude-code), any recent version.
- A Linear workspace, and the Linear MCP server connected to Claude Code
  (steps below).
- Python 3 on your `PATH` (check with `python --version` or
  `python3 --version` in a terminal).
- Git.

## Step-by-step setup

### 1. Connect Linear to Claude Code

Open a terminal and run:

```
claude mcp add --transport http linear-server https://mcp.linear.app/mcp
```

Then start (or continue) a Claude Code session and run `/mcp`. A dialog
opens — **don't dismiss it**, walk through the login/authorize flow for
your Linear account. When it's done, ask Claude something like "list my
Linear teams" to confirm it's actually connected (Linear's tools should
show up; if Claude says it has no Linear tools, the auth step above
didn't complete — run `/mcp` again).

Full reference: [Linear's own MCP docs](https://linear.app/docs/mcp).

**Gotcha:** `claude mcp add` only registers the server for whichever
*directory* you ran it in (unless you pass `--scope user`). If you want
Linear available no matter which project you're in, either always run
that command with `--scope user` added, or just always run it from your
home directory once.

### 2. Copy this skill onto your machine

Clone this repo, then copy (not move — keep your own copy of the
original around) its contents into `~/.claude/skills/synclinear/`:

- **macOS/Linux:**
  ```
  git clone https://github.com/SabrinaCatpenter/synclinear.git
  mkdir -p ~/.claude/skills/synclinear
  cp -r synclinear/* ~/.claude/skills/synclinear/
  ```
- **Windows (PowerShell):**
  ```
  git clone https://github.com/SabrinaCatpenter/synclinear.git
  New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills\synclinear"
  Copy-Item -Recurse synclinear\* "$env:USERPROFILE\.claude\skills\synclinear\"
  ```

Nothing in the code is hardcoded to one machine or one person's home
directory — the hook script locates its own sibling files (`SKILL.md`,
the `lib/` modules) relative to its own location, so this works
regardless of where you put it, as long as it stays under
`~/.claude/skills/synclinear/`.

**Verify:** run the test suites once to confirm your Python setup can
actually run this code:

```
python ~/.claude/skills/synclinear/lib/test_config.py -v
python ~/.claude/skills/synclinear/lib/test_git_check.py -v
python ~/.claude/skills/synclinear/hooks/test_check_unsynced.py -v
```

Each should print `OK` at the end. If `python` isn't found, try
`python3` instead (and use `python3` in the hook command in step 3 too).

### 3. Register the Stop hook

This is the automatic-trigger part — the piece that means you never have
to remember to run a command yourself.

Open `~/.claude/settings.json` in a text editor (create it if it doesn't
exist — an empty file with just `{}` in it is a valid starting point).
**If it already has a `hooks` section, or a `hooks.Stop` array, add to it
— don't delete or replace what's already there.** A broken settings.json
silently disables everything else in the file, so double-check the
brackets match after you edit.

If the file is empty (`{}`), replace it with:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"<full-path-to>/.claude/skills/synclinear/hooks/check_unsynced.py\"",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

Replace `<full-path-to>` with your actual home directory. Examples:

- macOS/Linux: `"command": "python3 \"/Users/yourname/.claude/skills/synclinear/hooks/check_unsynced.py\""`
- Windows: `"command": "python \"C:\\Users\\yourname\\.claude\\skills\\synclinear\\hooks\\check_unsynced.py\""`
  (note the doubled backslashes — required inside a JSON string on
  Windows paths)

If `hooks.Stop` **already has an entry** (e.g. you have some other
Stop hook configured already, like a notification sound), add a new
object to the array instead of replacing the array — it should look
like this:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "<your existing hook command>" }
        ]
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"<full-path-to>/.claude/skills/synclinear/hooks/check_unsynced.py\"",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

**Verify the JSON is still valid** before moving on (a Python one-liner
works on any OS):

```
python -c "import json; json.load(open('<path-to-settings.json>'))" && echo OK
```

If that doesn't print `OK`, fix the JSON before continuing — nothing
past this point will work with a broken settings file.

### 4. Activate the hook

Claude Code only picks up hook changes when it (re-)reads settings.json.
Either:

- run the `/hooks` command inside a Claude Code session once, or
- fully quit and restart Claude Code.

You won't see any confirmation that it's "on" — that's expected. It's
silent until it actually finds something to report (step 6 below).

### 5. Point synclinear at a specific repo

The hook checks *every* repo you work in, but it only does anything in
repos you've explicitly opted in — this is per-repo, not global.

Open a Claude Code session **inside the git repo** you want to track,
and just ask: *"set up synclinear for this repo."* Claude will ask which
Linear team and project this repo's commits should sync into (it'll show
you your real options from Linear, not guess), then create
`.claude/synclinear.json` in that repo with:

```json
{
  "linear_team": "YourTeamName",
  "linear_project": "Your Project Name",
  "last_synced_commit": "<the repo's current HEAD commit hash>"
}
```

**Add `.claude/synclinear.json` to that repo's `.gitignore`** — it's your
own personal sync bookkeeping, not something the rest of the team needs
to see or that should live in the project's git history. (If you're
setting this up via Claude as described above, ask it to add the
gitignore line too, or just add `.claude/synclinear.json` to the file
yourself.)

Sync only covers commits made **from this point forward** — it does not
automatically go back and propose tickets for the repo's entire past
history. (If you want that once, as a one-time thing, just ask Claude
directly — "go through this whole repo's history and propose Linear
tickets" — same review-before-write rules apply, it's just a bigger list.)

## What using it actually looks like

Once it's set up, this is invisible until there's something to report.
Say you commit some real work, then keep chatting with Claude, then
eventually the turn ends (Stop hook fires). On your next message, Claude
might open with something like:

```
synclinear: 3 new commits in this repo aren't synced to Linear yet.

Proposed Linear sync (3 commits, 2 ticket changes):

- ENG-142 -> Done (evidence: a1b2c3d "Fix the thing that broke")
- NEW: "Add rate limiting to the export endpoint" -> Done
  (evidence: e4f5g6h "Add rate limiter", i7j8k9l "Add rate-limit tests")
- (no ticket) m0n1o2p "Fix typo in comment" — not ticket-worthy

Want me to go ahead with these two changes?
```

You reply "yep" (or "skip the second one" or whatever), and only then
does anything actually change in Linear.

## Troubleshooting

- **Nothing ever happens, even after real commits.** Confirm you did
  step 5 for *this specific repo* — the hook is silent by design in any
  repo without a `.claude/synclinear.json`. Also confirm step 4 (did you
  actually run `/hooks` or restart after editing settings.json?).
- **Claude says it has no Linear tools when it tries to sync.** Step 1's
  `/mcp` authorization didn't complete, or it was done in a different
  Claude Code session/directory than the one you're using now (MCP
  connections are loaded when a session starts — connecting Linear in a
  *new* session doesn't retroactively add it to a session you already had
  open). Start a fresh session after confirming `/mcp` shows Linear as
  connected.
- **The hook command errors out.** Run the exact command from your
  settings.json by hand in a terminal (drop the surrounding JSON quoting)
  and see what it actually prints — usually it's `python` vs `python3`,
  or a typo in the path.
- **You want to test it without waiting for a real commit.** Manually
  edit a test repo's `.claude/synclinear.json` to set `last_synced_commit`
  to an older commit hash (`git log --oneline` to find one), then end a
  turn — the hook should pick up everything after that commit.

## Development

Each module has its own test file, run directly (no pytest needed):

```
python lib/test_config.py -v
python lib/test_git_check.py -v
python hooks/test_check_unsynced.py -v
```
