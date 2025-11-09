#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example: Programmatic Usage of APFS Tool

This script demonstrates how to use the tool's components
programmatically without the GUI.
"""

import sys
import os

# Add parent directory to path to import the tool
sys.path.insert(0, os.path.dirname(__file__))

from apfs_cellebrite_tool import (
    SignatureScanner,
    APFSFilesystemAccess,
    parse_fsstat,
    FSSTAT
)
import subprocess


def find_and_validate_volumes(image_path, blocksize=4096):
    """
    Find all APFS volumes in an image and validate them.
    
    Args:
        image_path: Path to DMG/RAW image
        blocksize: Block size (default 4096)
    
    Returns:
        List of tuples (block_number, volume_info_dict)
    """
    print(f"Scanning {image_path} for APFS volumes...")
    
    volumes = []
    
    def on_hit(block):
        print(f"Found potential VSUPER at block {block}")
        
        # Validate with fsstat
        try:
            result = subprocess.run(
                [FSSTAT, "-B", str(block), image_path],
                capture_output=True, text=True, timeout=30
            )
            output = result.stdout or result.stderr
            ok, name, enc, uuid, oid, xid = parse_fsstat(output)
            
            if ok:
                print(f"  ✓ Valid: {name} (Encrypted: {enc})")
                volumes.append((block, {
                    "name": name,
                    "encrypted": enc,
                    "uuid": uuid,
                    "oid": oid,
                    "xid": xid
                }))
            else:
                print(f"  ✗ Invalid VSUPER")
        except Exception as e:
            print(f"  ✗ Validation error: {e}")
    
    # Scan using internal method (start=0, end=-1, step=8)
    SignatureScanner.internal_scan(
        image_path, blocksize, 0, -1, 8,
        stop_evt=None,
        progress_cb=None,
        hit_cb=on_hit
    )
    
    print(f"\nFound {len(volumes)} valid volumes")
    return volumes


def list_directory_tree(image_path, block, path="/", max_depth=2, current_depth=0):
    """
    Recursively list directory tree.
    
    Args:
        image_path: Path to image
        block: APSB block number
        path: Current path
        max_depth: Maximum recursion depth
        current_depth: Current depth (internal)
    """
    if current_depth >= max_depth:
        return
    
    fs = APFSFilesystemAccess(image_path, block)
    
    # Parse path to get inode
    if path == "/":
        entries = fs.list_dir(inode=None)
        print("/")
    else:
        # Navigate to path
        parts = [p for p in path.split("/") if p]
        inode = None
        
        for part in parts:
            if inode is None:
                entries = fs.list_dir(inode=None)
            else:
                entries = fs.list_dir(inode=inode)
            
            found = next((e for e in entries if e["name"] == part and e["kind"] == "dir"), None)
            if not found:
                print(f"Path not found: {path}")
                return
            inode = found["inode"]
        
        entries = fs.list_dir(inode=inode)
        print(path)
    
    # List entries
    indent = "  " * (current_depth + 1)
    for entry in sorted(entries, key=lambda x: (0 if x["kind"] == "dir" else 1, x["name"])):
        if entry["kind"] == "dir":
            print(f"{indent}📁 {entry['name']}/")
            # Recurse into subdirectories
            if current_depth + 1 < max_depth:
                subpath = path.rstrip("/") + "/" + entry["name"]
                try:
                    list_directory_tree(image_path, block, subpath, 
                                      max_depth, current_depth + 1)
                except:
                    pass
        else:
            print(f"{indent}📄 {entry['name']}")


def export_file_by_path(image_path, block, source_path, dest_path):
    """
    Export a specific file by its path.
    
    Args:
        image_path: Path to image
        block: APSB block number
        source_path: Path in filesystem (e.g., "/Users/john/file.txt")
        dest_path: Destination path on local system
    """
    fs = APFSFilesystemAccess(image_path, block)
    
    # Navigate to file
    parts = [p for p in source_path.split("/") if p]
    if not parts:
        print("Invalid path")
        return False
    
    filename = parts[-1]
    dir_parts = parts[:-1]
    
    # Navigate to directory
    inode = None
    for part in dir_parts:
        if inode is None:
            entries = fs.list_dir(inode=None)
        else:
            entries = fs.list_dir(inode=inode)
        
        found = next((e for e in entries if e["name"] == part and e["kind"] == "dir"), None)
        if not found:
            print(f"Directory not found: {part}")
            return False
        inode = found["inode"]
    
    # Find file in directory
    if inode is None:
        entries = fs.list_dir(inode=None)
    else:
        entries = fs.list_dir(inode=inode)
    
    file_entry = next((e for e in entries if e["name"] == filename and e["kind"] == "file"), None)
    if not file_entry:
        print(f"File not found: {filename}")
        return False
    
    # Export file
    try:
        data = fs.read_file(file_entry["inode"])
        with open(dest_path, "wb") as f:
            f.write(data)
        print(f"Exported: {source_path} -> {dest_path}")
        return True
    except Exception as e:
        print(f"Export error: {e}")
        return False


def main():
    """Example usage."""
    if len(sys.argv) < 2:
        print("Usage: python3 example_programmatic.py <image_path>")
        print("\nExample:")
        print("  python3 example_programmatic.py /mnt/forensics/case.dd")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    if not os.path.exists(image_path):
        print(f"Error: Image not found: {image_path}")
        sys.exit(1)
    
    # Step 1: Find volumes
    print("=" * 60)
    print("Step 1: Finding APFS Volumes")
    print("=" * 60)
    volumes = find_and_validate_volumes(image_path)
    
    if not volumes:
        print("No volumes found!")
        sys.exit(1)
    
    # Step 2: List directory tree of first volume
    print("\n" + "=" * 60)
    print("Step 2: Listing Directory Tree (first volume, depth=2)")
    print("=" * 60)
    first_volume_block = volumes[0][0]
    list_directory_tree(image_path, first_volume_block, "/", max_depth=2)
    
    # Step 3: Export example file
    print("\n" + "=" * 60)
    print("Step 3: Export Example File")
    print("=" * 60)
    # Modify this path to match a file in your image
    # export_file_by_path(
    #     image_path,
    #     first_volume_block,
    #     "/Users/username/.bash_history",
    #     "./exported_bash_history.txt"
    # )
    print("(Uncomment and modify the path in the script to export files)")


if __name__ == "__main__":
    main()
