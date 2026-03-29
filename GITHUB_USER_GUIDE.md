# GitHub User Guide (Common Scenarios)

This guide is a practical command reference for common Git/GitHub workflows on Windows PowerShell.

---

## 0) Prerequisites

- Install Git: [https://git-scm.com/download/win](https://git-scm.com/download/win)
- Install GitHub CLI (`gh`) (optional but useful): [https://cli.github.com/](https://cli.github.com/)
- Have a GitHub account and repository access

Check tools:

```powershell
git --version
gh --version
```

Optional first-time identity setup:

```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

---

## 1) Create project locally and upload to GitHub

### A. Create a new local project folder

```powershell
mkdir MyProject
cd .\MyProject
```

### B. Initialize git and first commit

```powershell
git init
git add .
git commit -m "Initial commit"
```

### C. Create GitHub repo and push

#### Option 1: Use `gh` (recommended)

```powershell
gh repo create MyProject --private --source . --remote origin --push
```

Use `--public` if you want public visibility.

#### Option 2: Create repo on GitHub website, then connect

```powershell
git remote add origin https://github.com/<your-account>/MyProject.git
git branch -M main
git push -u origin main
```

---

## 2) Get project from GitHub to a new local path

```powershell
cd E:\
mkdir Work
cd .\Work
git clone https://github.com/<owner>/<repo>.git
cd .\<repo>
```

Clone into specific folder name:

```powershell
git clone https://github.com/<owner>/<repo>.git MyCustomFolder
```

---

## 3) Get project updates from GitHub to local

Inside your repo:

```powershell
git status
git pull
```

Safer explicit form:

```powershell
git pull origin main
```

If you have local uncommitted changes:

```powershell
git stash
git pull origin main
git stash pop
```

---

## 4) Get partial update from GitHub to local (specific files only)

Use this when you only need a few files from remote, not a full merge/pull.

### A. Get latest remote refs first

```powershell
git fetch origin
```

### B. Replace local file(s) with version from remote branch

```powershell
git restore --source origin/main -- .\path\to\file1.cs .\path\to\file2.md
```

Older equivalent command:

```powershell
git checkout origin/main -- .\path\to\file1.cs .\path\to\file2.md
```

### C. Review and commit (optional)

```powershell
git status
git diff -- .\path\to\file1.cs
git add .\path\to\file1.cs .\path\to\file2.md
git commit -m "Sync selected files from origin/main"
```

Notes:

- This updates only selected files in your working tree.
- It does not merge all branch changes.
- If local file has uncommitted edits, stash/commit first to avoid overwrite.

---

## 5) Upload local updates to GitHub

```powershell
git status
git add .
git commit -m "Describe your change"
git push
```

For first push of a new branch:

```powershell
git push -u origin <branch-name>
```

---

## 6) Upload local updates while excluding dedicated files (not in `.gitignore`)

Use this when you want to keep a file local only for a specific commit.

### A. Stage only selected files (best practice)

```powershell
git status
git add .\src\file1.cs .\README.md
git commit -m "Update feature and docs"
git push
```

### B. Unstage an accidentally staged file before commit

```powershell
git restore --staged .\path\to\local-only-file.txt
git commit -m "Commit without local-only file"
git push
```

### C. Temporarily mark tracked file as local-only (advanced)

If file is tracked but you want local edits not to appear in status:

```powershell
git update-index --skip-worktree .\path\to\file
```

Re-enable normal tracking later:

```powershell
git update-index --no-skip-worktree .\path\to\file
```

Note: use this carefully; it can confuse teams if forgotten.

---

## 7) Common branch workflow (feature -> PR -> merge)

```powershell
git checkout -b feature/my-change
# edit files
git add .
git commit -m "Add my change"
git push -u origin feature/my-change
```

Create PR:

```powershell
gh pr create --fill
```

After PR merged, sync local main:

```powershell
git checkout main
git pull origin main
git branch -d feature/my-change
```

---

## 8) Keep fork synced with upstream (if using fork model)

One-time setup:

```powershell
git remote add upstream https://github.com/<original-owner>/<repo>.git
```

Sync:

```powershell
git checkout main
git fetch upstream
git merge upstream/main
git push origin main
```

---

## 9) Resolve merge conflicts (basic flow)

```powershell
git pull
# resolve conflict markers in files
git add .
git commit -m "Resolve merge conflicts"
git push
```

If you want to abort current merge:

```powershell
git merge --abort
```

---

## 10) Undo git commit

**First decide:** was the commit **only local** (never `git push`), or **already on GitHub**?

- **Not pushed yet:** you can use `git reset` to move the branch pointer and optionally drop or keep changes.
- **Already pushed (especially `main`):** prefer `git revert` so you do not rewrite shared history. Use `reset` + force push only when your team agrees.

### A. Last commit not pushed — keep all changes staged (undo commit only)

```powershell
git reset --soft HEAD~1
```

### B. Last commit not pushed — keep changes in working tree, unstaged

```powershell
git reset --mixed HEAD~1
```

(`git reset HEAD~1` without `--soft` behaves like `--mixed`.)

### C. Last commit not pushed — discard commit and all its changes (destructive)

```powershell
git reset --hard HEAD~1
```

Warning: permanently loses uncommitted work in the working tree if it overlapped; use only when sure.

### D. Undo several local commits (not pushed)

Move branch back N commits (example: 3):

```powershell
git reset --soft HEAD~3
```

Replace `--soft` with `--mixed` or `--hard` as needed.

### E. Commit already pushed — add a new commit that undoes it (safe for shared branches)

Undo the last commit’s changes without rewriting history:

```powershell
git revert HEAD --no-edit
git push
```

Undo a specific older commit by SHA:

```powershell
git log --oneline -10
git revert <commit-sha> --no-edit
git push
```

### F. Already pushed — rewrite history (use with caution)

Only if the branch is yours or the team allows force push:

```powershell
git reset --hard HEAD~1
git push --force-with-lease
```

`--force-with-lease` is safer than `--force`; it fails if someone else pushed in the meantime.

### G. Other common undos (files, not commits)

Discard unstaged local changes to a file:

```powershell
git restore .\path\to\file
```

Restore a deleted tracked file:

```powershell
git restore .\path\to\deleted-file
```

---

## 11) Undo `git add` (unstage)

`git add` stages files; unstaging removes them from the index but **keeps your edits** in the working tree.

### A. Unstage one file

```powershell
git restore --staged .\path\to\file.cs
```

### B. Unstage everything (all files)

```powershell
git restore --staged .
```

### C. Older equivalent (`git reset`)

```powershell
git reset HEAD .\path\to\file.cs
git reset HEAD
```

`HEAD` can be omitted in newer Git (`git reset` unstages all).

### D. Unstage but you also want to discard working-tree changes

Unstage first, then discard file content (destructive for local edits):

```powershell
git restore --staged .\path\to\file.cs
git restore .\path\to\file.cs
```

Or reset index and working tree to `HEAD` in one step (Git 2.23+):

```powershell
git restore --source=HEAD --staged --worktree .\path\to\file.cs
```

---

## 12) View history and inspect changes

```powershell
git log --oneline --graph --decorate -20
git diff
git diff --staged
git show <commit-sha>
```

---

## 13) Rename default branch to `main` (if needed)

```powershell
git branch -M main
git push -u origin main
```

Then update default branch in GitHub repo settings.

---

## 14) Tags and releases (basic)

Create and push tag:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

Create release from tag (CLI):

```powershell
gh release create v1.0.0 --generate-notes
```

---

## 15) Recommended team practices

- Pull latest `main` before starting work
- Use feature branches, avoid direct commits to `main`
- Keep commits small and meaningful
- Write clear commit messages
- Use PR review before merge
- Add/update `.gitignore` for persistent local-only files
- Never commit secrets; use secret manager or environment variables

---

## 16) Quick command cheat sheet

```powershell
# clone
git clone <repo-url>

# branch
git checkout -b feature/x
git checkout main

# sync
git pull origin main

# commit and push
git add .
git commit -m "message"
git push

# undo git add (unstage)
git restore --staged .
git restore --staged .\path\to\file.cs

# undo last local commit (keep changes staged)
git reset --soft HEAD~1

# undo pushed commit safely (new commit)
git revert HEAD --no-edit

# status/history
git status
git log --oneline -20
```
