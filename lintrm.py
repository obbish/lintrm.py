#!/usr/bin/env python3

import json
import os
import sys
import subprocess
from collections import defaultdict
from datetime import datetime

# --- rmlint Manager (Python) ---
# A menu-driven script to scan for, inspect, and execute rmlint deletion plans.
# Usage: python3 rmlint-view-json.py [optional_path_to_rmlint.json]

def format_bytes(byte_count):
    """Formats bytes into a human-readable string (e.g., KiB, MiB, GiB)."""
    if byte_count is None or byte_count == 0:
        return "0.00 B"
    power = 1024
    n = 0
    power_labels = {0: 'B', 1: 'KiB', 2: 'MiB', 3: 'GiB', 4: 'TiB'}
    while byte_count >= power and n < len(power_labels) - 1:
        byte_count /= power
        n += 1
    return f"{byte_count:.2f} {power_labels[n]}"

def get_b2sum(filepath):
    """Calculates and returns the b2sum checksum of a file, or None on error."""
    if not os.path.exists(filepath):
        return None
    try:
        result = subprocess.run(['b2sum', filepath], capture_output=True, text=True, check=True)
        return result.stdout.split()[0]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

class DataManager:
    """The single 'parsing engine' for the rmlint JSON data."""
    def __init__(self, data):
        self.raw_data = data
        self.originals = []
        self.duplicates = []
        self.duplicate_sets = {}
        self._process_data()

    def _process_data(self):
        temp_groups = defaultdict(list)
        for item in self.raw_data:
            if item.get("type") == "duplicate_file" and item.get("checksum"):
                temp_groups[item["checksum"]].append(item)

        for checksum, files in temp_groups.items():
            original = next((f for f in files if f.get("is_original")), None)
            if not original: continue
            dupes_in_group = [f for f in files if not f.get("is_original")]
            
            if dupes_in_group:
                self.duplicate_sets[checksum] = {"original": original, "duplicates": dupes_in_group}
                self.originals.append(original)
                self.duplicates.extend(dupes_in_group)
    
    def get_summary(self):
        summary = defaultdict(int)
        for item in self.raw_data:
            summary[item.get("type", "Unknown")] += 1
        return summary

    def calculate_space_to_free(self):
        return sum(item.get("size", 0) for item in self.duplicates)

    def get_top_ten_duplicates(self):
        sized_duplicates = [(item.get("size", 0), item.get("path", "N/A")) for item in self.duplicates]
        sized_duplicates.sort(key=lambda x: x[0], reverse=True)
        return sized_duplicates[:10]

def perform_deletion(data_manager, dry_run=True):
    """Processes duplicates, either for a dry run or actual deletion."""
    stats = defaultdict(int)
    total_items = len(data_manager.duplicates)
    
    for i, dup_item in enumerate(data_manager.duplicates):
        dup_path = dup_item.get("path")
        checksum = dup_item.get("checksum")
        print(f"\n--- Processing {i+1}/{total_items}: {dup_path} ---")
        
        if not (dup_path and checksum and os.path.exists(dup_path)):
            print("  INFO: Skipping (path is invalid or file already deleted).")
            stats["skipped_missing"] += 1
            continue

        group = data_manager.duplicate_sets.get(checksum)
        if not group or not group.get("original"):
            print("  WARNING: Skipping (could not find original file in data set).")
            stats["skipped_missing"] += 1
            continue
            
        orig_path = group["original"].get("path")
        print(f"  Verifying hashes against original: {orig_path}")
        orig_checksum = get_b2sum(orig_path)
        dup_checksum = get_b2sum(dup_path)

        if orig_checksum == checksum and dup_checksum == checksum:
            try:
                parent_dir = os.path.dirname(dup_path)
                parent_stat = os.stat(parent_dir)
                if dry_run:
                    print(f"  [DRY RUN] Would delete file.")
                    stats["would_delete"] += 1
                    stats["space_freed"] += dup_item.get("size", 0)
                else:
                    print(f"  OK: Deleting {dup_path}")
                    os.remove(dup_path)
                    stats["would_delete"] += 1
                    stats["space_freed"] += dup_item.get("size", 0)
                    try:
                        os.removedirs(parent_dir)
                        print(f"  Cleaned empty directory tree starting at: {parent_dir}")
                    except OSError:
                        print(f"  Restoring timestamp on: {parent_dir}")
                        os.utime(parent_dir, (parent_stat.st_atime, parent_stat.st_mtime))
            except OSError as e:
                print(f"  ERROR: An OS error occurred: {e}")
        else:
            print("  WARNING: Checksum mismatch. File may have changed. Skipping.")
            stats["skipped_mismatch"] += 1

    print("\n-----------------------------------")
    summary_title = "Dry Run Summary" if dry_run else "Deletion Summary"
    print(f">>> {summary_title}:")
    action_verb = "would be" if dry_run else "were"
    print(f"  - Files that {action_verb} deleted: {stats['would_delete']}")
    print(f"  - Total space that {action_verb} freed: {format_bytes(stats['space_freed'])}")
    print(f"  - Files skipped (hash mismatch): {stats['skipped_mismatch']}")
    print(f"  - Files skipped (missing/other): {stats['skipped_missing']}")
    print("-----------------------------------")

def run_new_scan():
    """Prompts user for paths and runs a new rmlint scan."""
    print("Enter the directory paths to scan, separated by spaces.")
    paths_input = input("Paths: ")
    paths = [p.strip() for p in paths_input.split()]
    
    if not paths:
        print("No paths provided. Aborting scan.")
        return None

    valid_paths = []
    for p in paths:
        if os.path.isdir(p):
            valid_paths.append(f"{p}//") # Add rmlint's recursive syntax
        else:
            print(f"Warning: '{p}' is not a valid directory. Skipping.")

    if not valid_paths:
        print("No valid directories to scan. Aborting.")
        return None
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_output = f"rmlint_{timestamp}.json"
    sh_output = f"rmlint_{timestamp}.sh"

    command = [
        'rmlint', '-g', '-T', 'df',
        '-o', f'json:{json_output}',
        '-o', f'sh:{sh_output}',
    ] + valid_paths

    print("\nAbout to run the following command:")
    print(" ".join(command))
    confirm = input("Continue? [y/N]: ")
    
    if confirm.lower() == 'y':
        try:
            subprocess.run(command, check=True)
            print(f"\nScan complete. Output saved to '{json_output}' and '{sh_output}'.")
            return json_output
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"\nError during scan: {e}")
            print("Please ensure 'rmlint' is installed and in your PATH.")
            return None
    else:
        print("Scan cancelled.")
        return None

def main(initial_file=None):
    data_manager = None
    json_file = initial_file

    if json_file:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            data_manager = DataManager(data)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Error loading initial file '{json_file}': {e}")
            json_file = None

    while True:
        os.system('clear')
        print("--- rmlint Manager (Python) ---")
        if json_file:
            print(f"Loaded Report: {json_file}")
        else:
            print("No report loaded.")
        print("-----------------------------------")
        print("\n--- Main Menu ---")
        print("  s. Run a new rmlint scan")
        print("  l. Load an existing rmlint.json file")

        if data_manager:
            print("\n--- Views & Actions (on loaded report) ---")
            print("  1. Overall Summary")
            print("  2. Calculate Total Space to be Freed")
            print("  3. List ALL Files Marked for Deletion")
            print("  4. List ALL Files Marked as Originals")
            print("  5. Show Top 10 BIGGEST Files to be Deleted")
            print("  6. [SAFE] Perform a DRY RUN of the deletion plan")
            print("  7. [ACTION] Execute Deletion Plan")
        
        print("\n  q. Quit\n")
        choice = input("Enter your choice: ")
        print("-----------------------------------")

        if choice.lower() == 's':
            new_file = run_new_scan()
            if new_file and os.path.exists(new_file):
                json_file = new_file
                print(f"Loading new scan results from {json_file}...")
                with open(json_file, 'r') as f:
                    data = json.load(f)
                data_manager = DataManager(data)
        
        elif choice.lower() == 'l':
            path = input("Enter path to rmlint.json file: ")
            if os.path.exists(path):
                json_file = path
                print(f"Loading {json_file}...")
                with open(json_file, 'r') as f:
                    data = json.load(f)
                data_manager = DataManager(data)
            else:
                print("File not found.")

        elif data_manager:
            if choice == '1':
                print(">>> Overall Summary:")
                for lint_type, count in data_manager.get_summary().items():
                    print(f"  - {str(lint_type):<15}: {count} items")
            elif choice == '2':
                print(">>> Calculating total size of duplicates to be removed...")
                total_size = data_manager.calculate_space_to_free()
                print(f"Total space to be freed: {format_bytes(total_size)}")
            elif choice == '3':
                print(">>> Listing all files marked for deletion (press 'q' to exit view):")
                paths = "\n".join([item.get("path", "N/A") for item in data_manager.duplicates])
                if paths:
                    process = subprocess.Popen(['less'], stdin=subprocess.PIPE, text=True)
                    process.communicate(input=paths)
            elif choice == '4':
                print(">>> Listing all original files (press 'q' to exit view):")
                paths = "\n".join([item.get("path", "N/A") for item in data_manager.originals])
                if paths:
                    process = subprocess.Popen(['less'], stdin=subprocess.PIPE, text=True)
                    process.communicate(input=paths)
            elif choice == '5':
                print(">>> Top 10 largest files marked for deletion:")
                top_ten = data_manager.get_top_ten_duplicates()
                if not top_ten:
                    print("No duplicates to display.")
                else:
                    for size, path in top_ten:
                        print(f"  {format_bytes(size):>10}  {path}")
            elif choice == '6':
                print(">>> Performing a DRY RUN. No files will be deleted.")
                perform_deletion(data_manager, dry_run=True)
            elif choice == '7':
                print(">>> This will PERMANENTLY delete all files marked as duplicates.")
                total_size_str = format_bytes(data_manager.calculate_space_to_free())
                confirm = input(f"Are you sure you want to delete {len(data_manager.duplicates)} files ({total_size_str})? [y/N]: ")
                if confirm.lower() == 'y':
                    perform_deletion(data_manager, dry_run=False)
                else:
                    print("Deletion cancelled.")
        
        if choice.lower() == 'q':
            print("Exiting.")
            break
        
        if choice not in ['s', 'l', 'q']:
             input("\nPress Enter to return to the menu...")


if __name__ == "__main__":
    initial_file = sys.argv[1] if len(sys.argv) > 1 else None
    main(initial_file)

