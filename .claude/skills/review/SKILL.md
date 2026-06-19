# Skill: review

Run a code review on the current branch diff.

## Usage
/review

## Steps
```bash
git diff main...HEAD
```
Analyse the diff against `.claude/rules/` and report issues grouped by file.
