# Share on GitHub

Publish this source folder, never an existing personal workspace. It contains blank
context and fictional examples, authored separately. Review tracked files first:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_public.py
git status --short
git diff --cached --stat
```

Choose name, visibility and license. This starter uses MIT; review LICENSE. After
reviewing and approving publication, from this source repository with an initial commit:

```sh
gh repo create life-kit --public --source=. --remote=origin --push
```

Use --private for private review. That command publishes committed source to the
currently authenticated account. Setup never runs it. Ignored workspaces aren't a
backup and can still be force-added, so inspect changes before every push.

You can mark the GitHub repository as a template. Everyone generates a private
workspace and connects their own accounts. Use fictional data in issues and examples.
The built-in public check is a narrow guard, not a full secret scanner or guarantee.
