## lintrm.py

**Shell app for rmlint workflows**

Uses program 'rmlint' to scan folders for duplicate files.
Saves results to json.
Loads json result files and performs operations of choice:
* Investigate results
* Dry-run deletion
* Actual deletion of duplicate files

Requires python and that rmlint program is installed.

Demo:
```
--- rmlint Manager (Python) ---
Loaded Report: rmlint.json
-----------------------------------

--- Main Menu ---
  s. Run a new rmlint scan
  l. Load an existing rmlint.json file

--- Views & Actions (on loaded report) ---
  1. Overall Summary
  2. Calculate Total Space to be Freed
  3. List ALL Files Marked for Deletion
  4. List ALL Files Marked as Originals
  5. Show Top 10 BIGGEST Files to be Deleted
  6. [SAFE] Perform a DRY RUN of the deletion plan
  7. [ACTION] Execute Deletion Plan

  q. Quit

Enter your choice:
```
