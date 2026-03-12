# Repo Sharing Checklist

Use this checklist before sending the repository to ChatGPT or collaborators.

## 1) Keep Repository Lightweight

1. Confirm large artifacts are ignored (videos, outputs, archives, environments, model weights).
2. Keep only code, configs, docs, key reports, and selected figures.
3. If a large file is necessary, prefer Git LFS.

## 2) Prepare Core Docs

1. Update `README.md` with:
   - problem statement
   - architecture summary
   - run instructions
   - key results snapshot
2. Fill `docs/PROJECT_OVERVIEW_FOR_CHATGPT.md` TODO fields.
3. Verify `docs/FOLDER_STRUCTURE.md` still matches actual directories.

## 3) Quick Sanity Commands

```bash
# Show current status
git status

# See top-level sizes
du -sh ./* | sort -h

# Check ignored files quickly
git check-ignore -v venv output garage_lab_combined/output || true
```

## 4) Push To Remote

```bash
# If remote not set
git remote add origin <YOUR_REPO_URL>

# Stage full Project_Cam (heavy files remain excluded by .gitignore)
git add .

# Review staged changes
git diff --cached --stat

# Commit and push
git commit -m "Share full Project_Cam workspace structure for external analysis"
git push -u origin <branch_name>
```

## 5) Send This To ChatGPT

1. Repository link.
2. `docs/PROJECT_OVERVIEW_FOR_CHATGPT.md` content.
3. `docs/FOLDER_STRUCTURE.md` content.
4. 3-5 key references/papers + 3-10 result screenshots.

## 6) If You Need A Smaller Alternative

If a full push is still too large, send this reduced set:

- `README.md`
- `docs/*.md`
- `src/`
- `scripts/`
- `config/`
- `GARAGE_CAMERAS/README.md` (+ key scripts)
- `garage_lab_combined/config/*`
- `garage_lab_combined/scripts/*`
- key `gt_eval` reports (`.md`, `.csv`)
- key thesis draft sections
