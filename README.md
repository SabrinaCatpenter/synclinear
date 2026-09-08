# synclinear

A Claude Code skill that keeps a git repo's Linear tickets in sync with
its real commit history — with a review step before anything writes to
Linear.

## What it does

1. A Stop hook (fires after every Claude Code turn) cheaply checks the
   current repo for commits that haven't been synced to Linear yet.
2. If it finds any, Claude reads them, checks Linear's open tickets, and
   proposes: which tickets should be marked Done, and which commits need
   a brand-new ticket. Trivial commits (plan-doc edits, lint fixes) are
   skipped.
3. You see the full proposal as a plain-text list before anything
   touches Linear. Nothing writes until you approve.

See `DESIGN.md` for the full design rationale and `SKILL.md` for the
exact instructions Claude follows on each sync.

## Requirements

- Claude Code, with the Linear MCP server connected
  (`claude mcp add --transport http linear-server https://mcp.linear.app/mcp`,
  then `/mcp` to authenticate — see
  [Linear's MCP docs](https://linear.app/docs/mcp)).
- Python 3 on `PATH`.
- Git.

## Install

1. Copy this folder to `~/.claude/skills/synclinear/` (any OS — the hook
   script locates its own sibling files via `__file__`, nothing is
   hardcoded to one machine).
2. Register the Stop hook in `~/.claude/settings.json` (merge into any
   existing `hooks.Stop` array — don't replace it):

   ```json
   {
     "hooks": {
       "Stop": [
         {
           "hooks": [
             {
               "type": "command",
               "command": "python \"<path-to-this-folder>/hooks/check_unsynced.py\"",
               "timeout": 15
             }
           ]
         }
       ]
     }
   }
   ```

   Windows paths need escaped backslashes in the JSON string, e.g.
   `"python \"C:\\Users\\you\\.claude\\skills\\synclinear\\hooks\\check_unsynced.py\""`.

3. Open `/hooks` once (or restart Claude Code) so it picks up the new
   registration.

## Set up a repo

Ask Claude (in a session open on that repo) to "set up synclinear for
this repo." It'll ask which Linear team/project to sync into, then
create `.claude/synclinear.json` there (gitignore it — it's your personal
sync bookkeeping, not project state) with `last_synced_commit` set to the
repo's current `HEAD`. Sync only covers commits from that point forward —
it doesn't backfill history automatically.

## Development

Each module has its own test file, run directly (no pytest needed):

```
python lib/test_config.py -v
python lib/test_git_check.py -v
python hooks/test_check_unsynced.py -v
```
