#!/usr/bin/env python3
"""
Script to clean up development files before making repository public.
Moves development files to _local_dev/ folder to keep them locally but exclude from repository.
"""

import os
import shutil
import sys

def move_file_or_dir(source, dest_folder):
    """Move a file or directory to the destination folder if it exists."""
    if os.path.exists(source):
        # Create destination folder if it doesn't exist
        os.makedirs(dest_folder, exist_ok=True)
        
        dest_path = os.path.join(dest_folder, os.path.basename(source))
        
        # If destination already exists, add a number suffix
        counter = 1
        original_dest = dest_path
        while os.path.exists(dest_path):
            name, ext = os.path.splitext(original_dest)
            dest_path = f"{name}_{counter}{ext}"
            counter += 1
        
        shutil.move(source, dest_path)
        print(f"✓ Moved: {source} → {dest_path}")
        return True
    else:
        print(f"⚠ Not found (already moved or doesn't exist): {source}")
        return False

def main():
    """Main cleanup function."""
    print("🧹 Preparing repository for public release...\n")
    print("This script will MOVE development files to '_local_dev/' folder")
    print("Files will be kept locally but excluded from the repository.\n")
    
    # Destination folder for moved files
    dest_folder = "_local_dev"
    
    # Files and directories to move
    files_to_move = [
        '.env',  # Move actual .env file (keep .env.example)
        'CLEANUP_CANDIDATES.md',
        'cleanup_project.py',
        'git_commit_commands.txt',
        'ProductRequirements.txt',
        'replace_redirects.py',
        'replace_templates.py',
        'simple_check.py',
        'TeamSchedule Notes.txt',
        'testdata/',
        'TESTING/',
        '.vscode/',
        'SECURITY_CHECKLIST.md',  # Move after completing checklist
    ]
    
    print("Files/directories to be moved to '_local_dev/':")
    for item in files_to_move:
        print(f"  - {item}")
    
    print(f"\n📁 Files will be moved to: {os.path.abspath(dest_folder)}")
    print("⚠️  These files will be removed from the repository but kept locally.")
    confirm = input("\nDo you want to continue? (y/N): ").lower().strip()
    
    if confirm != 'y':
        print("❌ Cleanup cancelled.")
        return
    
    print(f"\n🧹 Moving files to {dest_folder}...")
    
    moved_count = 0
    # Move each file/directory
    for item in files_to_move:
        if move_file_or_dir(item, dest_folder):
            moved_count += 1
    
    print(f"\n✅ Moved {moved_count} items to {dest_folder}!")
    
    # Update .gitignore to exclude the local dev folder
    gitignore_line = "\n# Local development files\n_local_dev/\n"
    try:
        with open('.gitignore', 'r') as f:
            content = f.read()
        
        if '_local_dev/' not in content:
            with open('.gitignore', 'a') as f:
                f.write(gitignore_line)
            print(f"✓ Added '_local_dev/' to .gitignore")
    except Exception as e:
        print(f"⚠ Could not update .gitignore: {e}")
    
    print("\n📋 Next steps:")
    print("1. Create your .env file from .env.example")
    print("2. Generate a new SECRET_KEY for your .env file")
    print("3. Review and test your application")
    print("4. Commit the changes to git")
    print("5. Push to your public repository")
    print(f"6. Your development files are safely stored in {dest_folder}/")
    
    print("\n💡 To generate a SECRET_KEY, run:")
    print("python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\"")
    
    print(f"\n📝 Note: You can access your moved files anytime in the '{dest_folder}' folder.")

if __name__ == "__main__":
    main()
