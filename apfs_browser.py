#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APFS Browser Tool - Enhanced Version
With TSK output integration and APFS Snapshot support
"""

import os
import re
import sys
import struct
import shutil
import tempfile
import threading
import subprocess
import time
import argparse
import pathlib
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from datetime import datetime


# =====================================================================
# CONSTANTS AND CONFIGURATION
# =====================================================================

# SleuthKit tool paths
SIGFIND = shutil.which("sigfind") or "sigfind"
FLS = shutil.which("fls") or "fls"
FSSTAT = shutil.which("fsstat") or "fsstat"
PSTAT = shutil.which("pstat") or "pstat"
ISTAT = shutil.which("istat") or "istat"
ICAT = shutil.which("icat") or "icat"
XXD = shutil.which("xxd") or "xxd"

# APFS signature patterns
APSB_SIGNATURE = b"APSB"
VSUPER_TYPE = 0x0D
VSUPER_SUBTYPE = 0

# Configuration
DEFAULT_BLOCKSIZE = 4096
HEAD_PREVIEW_BYTES = 512 * 1024  # 512 KiB

# Regex patterns for parsing
NAME_ROLE_RE = re.compile(r"^Name \(Role\):\s*(.+)$", re.M)
UUID_RE = re.compile(r"^Volume UUID\s+([0-9a-fA-F-]{36})", re.M)
APSB_OID_RE = re.compile(r"^APSB oid:\s*(\d+)", re.M)
APSB_XID_RE = re.compile(r"^APSB xid:\s*(\d+)", re.M)
ENC_Y_RE = re.compile(r"^Encrypted:\s*Yes", re.M)
ENC_N_RE = re.compile(r"^Encrypted:\s*No", re.M)
FS_OK_RE = re.compile(r"^File System Type:\s*APFS", re.M)
SIG_LINE_RE = re.compile(r"^Block:\s*([0-9]+)")
FLS_RE = re.compile(r"^\s*([a-zA-Z\-]/[a-zA-Z\-])\s+(\d+):\s*(.+?)\s*$")

# Snapshot parsing patterns
# Format: [249423] 2025-10-05 15:13:48.465854438 (CEST) com.apple.TimeMachine.2025-10-05-151348.local
SNAPSHOT_SECTION_RE = re.compile(r"Snapshots\s*\n-+\n(.+?)(?=\n\n|\Z)", re.DOTALL | re.M)
SNAPSHOT_ENTRY_RE = re.compile(r"^\[(\d+)\]\s+(.+)$", re.M)

HELP_TEXT = """
=== Understanding the Cellebrite AFF4 Encrypted Flags Problem ===

BACKGROUND:
When Cellebrite Digital Collector creates an AFF4 acquisition of an M1 Mac,
it decrypts the data during acquisition. However, the filesystem metadata flags
still indicate "encrypted" status.

THE PROBLEM:
1. Kernel-space mounting (hdiutil attach) reads these flags
2. macOS requests a decryption password
3. The data is already decrypted, creating a paradox
4. Traditional mounting fails

THE SOLUTION - USER SPACE PARSING:
This tool uses SleuthKit's user-space tools to bypass kernel checks:

• SIGFIND: Searches for APFS Volume Super Block (APSB) signatures
• FSSTAT: Validates and reads volume metadata (including snapshots)
• FLS: Lists directory contents without mounting
• ICAT: Extracts file contents directly
• ISTAT: Reads inode metadata
• PSTAT: Analyzes partition table

WORKFLOW:
1. Convert AFF4 to DMG using xmount
2. Scan DMG for APFS volume super blocks (APSB)
3. Validate blocks using fsstat
4. View snapshots and TSK outputs
5. Browse filesystem using user-space tools
6. Export files without kernel mounting

APFS SNAPSHOTS:
APFS supports copy-on-write snapshots that preserve the filesystem state
at a specific point in time. This tool allows you to:
• List all snapshots for a volume
• Browse snapshot contents
• Export files from snapshots
• Compare live system vs snapshots

ADVANTAGES:
✓ No kernel mounting required
✓ Works with "encrypted" flag paradox
✓ Direct filesystem access
✓ Access to APFS snapshots
✓ Educational insight into APFS structure
✓ Compatible with Cellebrite acquisitions

TOOLS REQUIRED:
• SleuthKit (sigfind, fsstat, fls, icat, istat, pstat)
• xmount (for AFF4 to DMG conversion)

EDUCATIONAL NOTE:
This demonstrates the difference between kernel-space and user-space
filesystem access. Kernel drivers enforce policy; user-space tools
read raw structures, bypassing problematic metadata.
"""


# =====================================================================
# UTILITY FUNCTIONS
# =====================================================================

def run_command(cmd, timeout=60):
    """Execute command and return result."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def parse_fsstat(output: str):
    """Parse fsstat output to extract volume information and snapshots."""
    ok = FS_OK_RE.search(output) is not None
    name = NAME_ROLE_RE.search(output).group(1).strip() if NAME_ROLE_RE.search(output) else "-"
    enc = "Yes" if ENC_Y_RE.search(output) else ("No" if ENC_N_RE.search(output) else "-")
    uuid = UUID_RE.search(output).group(1) if UUID_RE.search(output) else "-"
    apsb_oid = APSB_OID_RE.search(output).group(1) if APSB_OID_RE.search(output) else "-"
    apsb_xid = APSB_XID_RE.search(output).group(1) if APSB_XID_RE.search(output) else "-"
    
    # Parse snapshots
    # Format: [249423] 2025-10-05 15:13:48.465854438 (CEST) com.apple.TimeMachine.2025-10-05-151348.local
    snapshots = []
    snapshot_section = SNAPSHOT_SECTION_RE.search(output)
    if snapshot_section:
        snapshot_text = snapshot_section.group(1)
        for match in SNAPSHOT_ENTRY_RE.finditer(snapshot_text):
            xid = match.group(1)
            rest = match.group(2).strip()
            
            # Extract timestamp and name
            # Format: "2025-10-05 15:13:48.465854438 (CEST) com.apple.TimeMachine.2025-10-05-151348.local"
            parts = rest.split(None, 3)  # Split on whitespace, max 4 parts
            if len(parts) >= 4:
                # parts[0] = date, parts[1] = time, parts[2] = (timezone), parts[3] = name
                timestamp = f"{parts[0]} {parts[1]} {parts[2]}"
                name_part = parts[3] if len(parts) > 3 else ""
            elif len(parts) >= 2:
                timestamp = f"{parts[0]} {parts[1]}"
                name_part = parts[2] if len(parts) > 2 else ""
            else:
                timestamp = rest
                name_part = ""
            
            snapshots.append({
                "xid": xid,
                "timestamp": timestamp,
                "name": name_part,
                "full_info": rest  # Keep full line for display
            })
    
    return ok, name, enc, uuid, apsb_oid, apsb_xid, snapshots


def read_vsuper_header(image_path, block, blocksize=DEFAULT_BLOCKSIZE):
    """Read and validate APFS Volume Super Block header."""
    with open(image_path, "rb") as f:
        f.seek(block * blocksize)
        hdr = f.read(0x60)
    
    if len(hdr) < 0x24:
        return False
    if hdr[0x20:0x24] != APSB_SIGNATURE:
        return False
    
    o_type = struct.unpack_from("<I", hdr, 0x18)[0]
    o_subt = struct.unpack_from("<I", hdr, 0x1C)[0]
    return (o_type == VSUPER_TYPE and o_subt == VSUPER_SUBTYPE)


def parse_fls_listing(text):
    """Parse fls output to extract file/directory entries."""
    entries = []
    for line in text.splitlines():
        m = FLS_RE.match(line)
        if not m:
            continue
        
        meta, inode, name = m.group(1), int(m.group(2)), m.group(3)
        
        # Determine entry type
        kind = "file"
        if meta.startswith("d/"):
            kind = "dir"
        elif meta.lower().startswith("l/"):
            kind = "link"
        
        entries.append({
            "name": name,
            "inode": inode,
            "kind": kind,
            "meta": meta
        })
    
    return entries


def hexdump(data, max_len=4096):
    """Generate hexdump of binary data."""
    if XXD and shutil.which(XXD):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(data[:max_len])
            tmp.flush()
            cp = run_command([XXD, "-g", "1", "-l", str(max_len), tmp.name])
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
        return cp.stdout
    
    # Simple fallback
    out = []
    chunk = data[:max_len]
    for i in range(0, len(chunk), 16):
        slice_data = chunk[i:i+16]
        hexs = " ".join(f"{b:02x}" for b in slice_data)
        txt = "".join(chr(b) if 32 <= b < 127 else "." for b in slice_data)
        out.append(f"{i:08x}: {hexs:<48}  {txt}")
    return "\n".join(out)


# =====================================================================
# SCANNER CLASSES
# =====================================================================

class SignatureScanner:
    """Scans for APFS signatures using sigfind or internal method."""
    
    @staticmethod
    def run_sigfind(image_path, blocksize, offset, stop_evt, on_block, on_progress, on_log):
        """Run sigfind in separate process and monitor output."""
        if not shutil.which(SIGFIND):
            raise RuntimeError("sigfind not found. Please install SleuthKit.")
        
        tmpf = tempfile.NamedTemporaryFile(prefix="sigfind_", suffix=".txt", delete=False)
        tmp_path = tmpf.name
        tmpf.close()
        
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        
        cmd = [SIGFIND, "-o", str(offset), "-b", str(blocksize), "41505342", image_path]
        on_log(f"[sigfind] {' '.join(cmd)}")
        
        with open(tmp_path, "w", buffering=1) as out:
            proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, env=env)
        
        # Monitor output file
        tail_stop = threading.Event()
        
        def tail_file():
            seen = set()
            last_size = 0
            hits = 0
            
            while not tail_stop.is_set():
                try:
                    sz = os.path.getsize(tmp_path)
                    if sz > last_size:
                        with open(tmp_path, "r", errors="ignore") as f:
                            f.seek(last_size)
                            for line in f:
                                m = SIG_LINE_RE.match(line.strip())
                                if m:
                                    blk = int(m.group(1))
                                    if blk not in seen:
                                        seen.add(blk)
                                        hits += 1
                                        on_block(blk)
                        last_size = sz
                        on_progress(len(seen), hits)
                except Exception as e:
                    on_log(f"[sigfind tail] {e}")
                time.sleep(0.2)
        
        t = threading.Thread(target=tail_file, daemon=True)
        t.start()
        
        # Wait for process
        try:
            while proc.poll() is None:
                if stop_evt.is_set():
                    on_log("[sigfind] Abort requested - terminating process...")
                    proc.terminate()
                    break
                time.sleep(0.15)
        finally:
            try:
                proc.kill()
            except Exception:
                pass
            tail_stop.set()
            t.join(timeout=1.0)
        
        return tmp_path
    
    @staticmethod
    def internal_scan(image_path, blocksize, start_block, end_block, step,
                     stop_evt=None, progress_cb=None, hit_cb=None):
        """Scan image internally (slower but no dependencies)."""
        img_size = os.path.getsize(image_path)
        total_blocks = img_size // blocksize
        
        if end_block is None or end_block < 0 or end_block >= total_blocks:
            end_block = total_blocks - 1
        if start_block < 0:
            start_block = 0
        if step <= 0:
            step = 1
        if start_block > end_block:
            start_block, end_block = end_block, start_block
        
        planned = ((end_block - start_block) // step) + 1
        done = 0
        hits = 0
        
        with open(image_path, "rb") as f:
            b = start_block
            while b <= end_block:
                if stop_evt and stop_evt.is_set():
                    break
                
                f.seek(b * blocksize + 0x20)
                sig = f.read(4)
                
                if sig == APSB_SIGNATURE:
                    f.seek(b * blocksize)
                    hdr = f.read(0x60)
                    if len(hdr) >= 0x24:
                        o_type = struct.unpack_from("<I", hdr, 0x18)[0]
                        o_subt = struct.unpack_from("<I", hdr, 0x1C)[0]
                        if o_type == VSUPER_TYPE and o_subt == VSUPER_SUBTYPE:
                            hits += 1
                            if hit_cb:
                                hit_cb(b)
                
                done += 1
                if progress_cb and (done % 256 == 0 or done == planned):
                    progress_cb(done, planned, hits)
                
                b += step
        
        if progress_cb:
            progress_cb(done, planned, hits)
        
        return hits


# =====================================================================
# FILESYSTEM ACCESS CLASS
# =====================================================================

class APFSFilesystemAccess:
    """Provides user-space access to APFS filesystem using SleuthKit."""
    
    def __init__(self, image, block, sector_offset=0, snapshot_xid=None):
        self.image = image
        self.block = block
        self.sector_offset = sector_offset
        self.snapshot_xid = snapshot_xid  # XID for snapshot access
    
    def _build_base_args(self):
        """Build base arguments for TSK commands."""
        args = []
        if self.sector_offset and self.sector_offset > 0:
            args += ["-o", str(self.sector_offset)]
        if self.block:
            args += ["-B", str(self.block)]
        if self.snapshot_xid:
            args += ["-s", str(self.snapshot_xid)]
        return args
    
    def list_dir(self, inode=None):
        """List directory contents."""
        cmd = [FLS] + self._build_base_args()
        if inode is not None:
            cmd += ["-f", "apfs", str(self.image), str(inode)]
        else:
            cmd += [str(self.image)]
        
        cp = run_command(cmd)
        if cp.returncode != 0 and not cp.stdout:
            raise RuntimeError(cp.stderr or cp.stdout or "fls failed")
        
        return parse_fls_listing(cp.stdout)
    
    def get_inode_info(self, inode):
        """Get inode information using istat."""
        cmd = [ISTAT] + self._build_base_args()
        cmd += [self.image, str(inode)]
        
        cp = run_command(cmd)
        return cp.stdout if cp.returncode == 0 else (cp.stderr or cp.stdout)
    
    def read_file(self, inode, max_bytes=None):
        """Read file contents using icat."""
        cmd = [ICAT] + self._build_base_args()
        cmd += [self.image, str(inode)]
        
        if max_bytes is None:
            return subprocess.run(cmd, capture_output=True).stdout
        
        # Limit with head
        p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        p2 = subprocess.run(["head", "-c", str(max_bytes)], 
                          stdin=p1.stdout, capture_output=True)
        try:
            p1.stdout.close()
        except Exception:
            pass
        return p2.stdout
    
    def export_recursive(self, inode, output_dir):
        """Export folder recursively."""
        cmd = [FLS] + self._build_base_args()
        cmd += ["-r", "-f", "apfs", self.image, str(inode)]
        
        cp = run_command(cmd, timeout=600)
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr or cp.stdout)
        
        exported = 0
        for line in cp.stdout.splitlines():
            m = FLS_RE.match(line)
            if not m:
                continue
            
            meta, file_inode, path = m.group(1), int(m.group(2)), m.group(3)
            is_dir = meta.startswith("d/")
            target = os.path.join(output_dir, path)
            
            if is_dir:
                os.makedirs(target, exist_ok=True)
                continue
            
            try:
                data = self.read_file(file_inode, max_bytes=None)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as f:
                    f.write(data)
                exported += 1
            except Exception:
                continue
        
        return exported


# =====================================================================
# GUI: HELP/ABOUT DIALOG
# =====================================================================

class HelpDialog(tk.Toplevel):
    """Display help and methodology explanation."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Help - Cellebrite AFF4 Encrypted Flags Problem")
        self.geometry("800x600")
        
        # Text widget with scrollbar
        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.text = scrolledtext.ScrolledText(text_frame, wrap="word", 
                                             font=("Courier", 10))
        self.text.pack(fill="both", expand=True)
        
        # Insert help text
        self.text.insert("1.0", HELP_TEXT)
        self.text.config(state="disabled")
        
        # Close button
        ttk.Button(self, text="Close", command=self.destroy).pack(pady=10)


# =====================================================================
# GUI: TSK OUTPUT VIEWER
# =====================================================================

class TSKOutputDialog(tk.Toplevel):
    """Display TSK command outputs in a tabbed interface."""
    
    def __init__(self, parent, image, block):
        super().__init__(parent)
        self.image = image
        self.block = block
        self.title(f"TSK Outputs - Block {block}")
        self.geometry("900x700")
        
        # Notebook for different outputs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create tabs
        self.create_pstat_tab()
        self.create_fsstat_tab()
        
        # Close button
        ttk.Button(self, text="Close", command=self.destroy).pack(pady=10)
    
    def create_pstat_tab(self):
        """Create tab for pstat output."""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="pstat (Partition)")
        
        # Toolbar
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", padx=5, pady=5)
        ttk.Button(toolbar, text="Run pstat", 
                  command=self.run_pstat).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Copy to Clipboard", 
                  command=lambda: self.copy_to_clipboard(self.pstat_text)).pack(side="left", padx=2)
        
        # Text area
        self.pstat_text = scrolledtext.ScrolledText(frame, wrap="none", 
                                                    font=("Courier", 9))
        self.pstat_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Auto-run
        self.run_pstat()
    
    def create_fsstat_tab(self):
        """Create tab for fsstat output."""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="fsstat (Volume)")
        
        # Toolbar
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", padx=5, pady=5)
        ttk.Button(toolbar, text="Run fsstat", 
                  command=self.run_fsstat).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Copy to Clipboard", 
                  command=lambda: self.copy_to_clipboard(self.fsstat_text)).pack(side="left", padx=2)
        
        # Text area
        self.fsstat_text = scrolledtext.ScrolledText(frame, wrap="none", 
                                                     font=("Courier", 9))
        self.fsstat_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Auto-run
        self.run_fsstat()
    
    def run_pstat(self):
        """Run pstat command."""
        self.pstat_text.delete("1.0", "end")
        self.pstat_text.insert("1.0", "Running pstat...\n\n")
        self.update()
        
        try:
            cmd = [PSTAT, self.image]
            result = run_command(cmd, timeout=30)
            output = result.stdout or result.stderr
            
            self.pstat_text.delete("1.0", "end")
            self.pstat_text.insert("1.0", f"Command: {' '.join(cmd)}\n\n")
            self.pstat_text.insert("end", output)
        except Exception as e:
            self.pstat_text.delete("1.0", "end")
            self.pstat_text.insert("1.0", f"Error: {e}")
    
    def run_fsstat(self):
        """Run fsstat command."""
        self.fsstat_text.delete("1.0", "end")
        self.fsstat_text.insert("1.0", "Running fsstat...\n\n")
        self.update()
        
        try:
            cmd = [FSSTAT, "-B", str(self.block), self.image]
            result = run_command(cmd, timeout=30)
            output = result.stdout or result.stderr
            
            self.fsstat_text.delete("1.0", "end")
            self.fsstat_text.insert("1.0", f"Command: {' '.join(cmd)}\n\n")
            self.fsstat_text.insert("end", output)
        except Exception as e:
            self.fsstat_text.delete("1.0", "end")
            self.fsstat_text.insert("1.0", f"Error: {e}")
    
    def copy_to_clipboard(self, text_widget):
        """Copy text to clipboard."""
        content = text_widget.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(content)
        messagebox.showinfo("Copied", "Output copied to clipboard")


# =====================================================================
# GUI: SNAPSHOT LIST DIALOG
# =====================================================================

class SnapshotListDialog(tk.Toplevel):
    """Display list of snapshots for a volume."""
    
    def __init__(self, parent, image, block, snapshots, on_browse_snapshot):
        super().__init__(parent)
        self.image = image
        self.block = block
        self.snapshots = snapshots
        self.on_browse_snapshot = on_browse_snapshot
        
        self.title(f"Snapshots - Block {block}")
        self.geometry("900x450")
        
        # Info label
        info_text = f"Found {len(snapshots)} snapshot(s) for this volume"
        ttk.Label(self, text=info_text, font=("", 11, "bold")).pack(pady=10)
        
        # Snapshot table
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        cols = ("xid", "timestamp", "name")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings")
        self.tree.heading("xid", text="XID")
        self.tree.heading("timestamp", text="Timestamp")
        self.tree.heading("name", text="Name / Description")
        
        self.tree.column("xid", width=100, anchor="w")
        self.tree.column("timestamp", width=300, anchor="w")
        self.tree.column("name", width=450, anchor="w")
        
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        
        # Populate table
        for snap in snapshots:
            self.tree.insert("", "end", values=(
                snap["xid"], 
                snap.get("timestamp", ""), 
                snap.get("name", "")
            ))
        
        # Buttons
        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Button(button_frame, text="Browse Selected Snapshot", 
                  command=self.browse_selected).pack(side="left", padx=2)
        ttk.Button(button_frame, text="Close", 
                  command=self.destroy).pack(side="right", padx=2)
    
    def browse_selected(self):
        """Browse selected snapshot."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select a snapshot")
            return
        
        values = self.tree.item(sel[0], "values")
        xid = values[0]
        timestamp = values[1]
        name = values[2]
        
        # Create display name
        display_name = f"{timestamp}"
        if name:
            display_name += f" - {name}"
        
        self.on_browse_snapshot(xid, display_name)
        self.destroy()


# =====================================================================
# GUI: VOLUME INSPECTOR (ENHANCED)
# =====================================================================

class VolumeInspectorFrame(ttk.Frame):
    """Frame for scanning and validating APFS volumes with snapshot support."""
    
    def __init__(self, parent, on_volume_selected):
        super().__init__(parent)
        self.on_volume_selected = on_volume_selected
        self.image = None
        self.blocksize = DEFAULT_BLOCKSIZE
        self.stop_evt = threading.Event()
        self.temp_sig_file = None
        self._fsstat_worker_running = False
        self._fsstat_queue = []
        self.volume_snapshots = {}  # Store snapshots per block
        
        self.build_ui()
    
    def build_ui(self):
        # Top toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=8)
        
        ttk.Button(toolbar, text="Open Image", 
                  command=self.open_image).pack(side="left", padx=2)
        
        # Scan mode
        self.mode = tk.StringVar(value="sigfind")
        ttk.Radiobutton(toolbar, text="Fast (sigfind)", 
                       variable=self.mode, value="sigfind").pack(side="left", padx=6)
        ttk.Radiobutton(toolbar, text="Internal Scan", 
                       variable=self.mode, value="internal").pack(side="left")
        
        ttk.Button(toolbar, text="Start Scan", 
                  command=self.start_scan).pack(side="left", padx=(12,2))
        ttk.Button(toolbar, text="Abort", 
                  command=self.abort_scan).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Validate All", 
                  command=self.validate_all).pack(side="left", padx=(12,2))
        ttk.Button(toolbar, text="Try pstat", 
                  command=self.try_pstat).pack(side="left", padx=2)
        
        # Options frame
        opts_frame = ttk.LabelFrame(self, text="Scan Options")
        opts_frame.pack(fill="x", padx=8, pady=(0,8))
        
        # Blocksize
        ttk.Label(opts_frame, text="Block size:").grid(row=0, column=0, 
                                                       padx=6, pady=6, sticky="w")
        self.ent_bsize = ttk.Entry(opts_frame, width=12)
        self.ent_bsize.insert(0, str(DEFAULT_BLOCKSIZE))
        self.ent_bsize.grid(row=0, column=1, padx=6, pady=6, sticky="w")
        
        # Internal scan options
        ttk.Label(opts_frame, text="Start block:").grid(row=0, column=2, 
                                                        padx=6, pady=6, sticky="w")
        self.ent_start = ttk.Entry(opts_frame, width=12)
        self.ent_start.insert(0, "0")
        self.ent_start.grid(row=0, column=3, padx=6, pady=6, sticky="w")
        
        ttk.Label(opts_frame, text="End block:").grid(row=0, column=4, 
                                                      padx=6, pady=6, sticky="w")
        self.ent_end = ttk.Entry(opts_frame, width=12)
        self.ent_end.insert(0, "-1")
        self.ent_end.grid(row=0, column=5, padx=6, pady=6, sticky="w")
        
        ttk.Label(opts_frame, text="Step:").grid(row=0, column=6, 
                                                 padx=6, pady=6, sticky="w")
        self.ent_step = ttk.Entry(opts_frame, width=12)
        self.ent_step.insert(0, "8")
        self.ent_step.grid(row=0, column=7, padx=6, pady=6, sticky="w")
        
        # Auto-validate checkbox
        self.chk_autoval = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts_frame, text="Auto-validate with fsstat", 
                       variable=self.chk_autoval).grid(row=1, column=0, columnspan=4, 
                                                       padx=6, pady=6, sticky="w")
        
        # Results table
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=8, pady=(0,8))
        
        cols = ("block", "name", "enc", "snapshots", "uuid", "apsb_oid", "apsb_xid")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=12)
        self.tree.heading("block", text="Block")
        self.tree.heading("name", text="Name (Role)")
        self.tree.heading("enc", text="Encrypted")
        self.tree.heading("snapshots", text="Snapshots")
        self.tree.heading("uuid", text="Volume UUID")
        self.tree.heading("apsb_oid", text="APSB OID")
        self.tree.heading("apsb_xid", text="APSB XID")
        
        self.tree.column("block", width=80, anchor="w")
        self.tree.column("name", width=150, anchor="w")
        self.tree.column("enc", width=80, anchor="w")
        self.tree.column("snapshots", width=80, anchor="center")
        self.tree.column("uuid", width=250, anchor="w")
        self.tree.column("apsb_oid", width=100, anchor="w")
        self.tree.column("apsb_xid", width=100, anchor="w")
        
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        
        # Action buttons
        action_frame = ttk.Frame(self)
        action_frame.pack(fill="x", padx=8, pady=(0,8))
        
        ttk.Button(action_frame, text="Browse Volume", 
                  command=self.open_browser).pack(side="left", padx=2)
        ttk.Button(action_frame, text="View TSK Outputs", 
                  command=self.view_tsk_outputs).pack(side="left", padx=2)
        ttk.Button(action_frame, text="View Snapshots", 
                  command=self.view_snapshots).pack(side="left", padx=2)
        ttk.Button(action_frame, text="Add Block Manually", 
                  command=self.manual_add).pack(side="left", padx=2)
        
        # Progress bar
        prog_frame = ttk.Frame(self)
        prog_frame.pack(fill="x", padx=8, pady=(0,8))
        
        self.progress = ttk.Progressbar(prog_frame, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(0,6))
        self.prog_lbl = ttk.Label(prog_frame, text="0.0%", width=8)
        self.prog_lbl.pack(side="left")
        
        # Status label
        self.status = ttk.Label(self, text="Ready", relief="sunken", anchor="w")
        self.status.pack(fill="x", padx=8, pady=(0,8))
    
    def open_image(self):
        """Open image file."""
        path = filedialog.askopenfilename(
            title="Select DMG/RAW Image",
            filetypes=[("Disk Images", "*.dmg *.raw *.dd *.img"), ("All Files", "*.*")]
        )
        if not path:
            return
        
        self.image = path
        self.tree.delete(*self.tree.get_children())
        self.volume_snapshots = {}
        self.status.config(text=f"Loaded: {os.path.basename(path)}")
    
    def start_scan(self):
        """Start volume scan."""
        if not self.image:
            messagebox.showwarning("No Image", "Please open an image first.")
            return
        
        try:
            self.blocksize = int(self.ent_bsize.get().strip() or str(DEFAULT_BLOCKSIZE))
        except Exception:
            self.blocksize = DEFAULT_BLOCKSIZE
            self.ent_bsize.delete(0, "end")
            self.ent_bsize.insert(0, str(DEFAULT_BLOCKSIZE))
        
        self.stop_evt.clear()
        self.tree.delete(*self.tree.get_children())
        self.volume_snapshots = {}
        self.progress["value"] = 0
        self.prog_lbl.config(text="0.0%")
        self.status.config(text="Scanning...")
        
        threading.Thread(target=self._scan_thread, daemon=True).start()
    
    def _scan_thread(self):
        """Thread function for scanning."""
        try:
            if self.mode.get() == "sigfind":
                tmp = SignatureScanner.run_sigfind(
                    self.image, self.blocksize, 32, self.stop_evt,
                    on_block=lambda b: self.after(0, self._add_hit_row, b),
                    on_progress=lambda d, h: self.after(0, self._set_progress_unknown, d, h),
                    on_log=lambda msg: None
                )
                self.temp_sig_file = tmp
            else:
                start_txt = self.ent_start.get().strip()
                end_txt = self.ent_end.get().strip()
                step_txt = self.ent_step.get().strip()
                
                try:
                    start_b = int(start_txt) if start_txt else 0
                except:
                    start_b = 0
                try:
                    end_b = int(end_txt) if end_txt else -1
                except:
                    end_b = -1
                try:
                    step_b = int(step_txt) if step_txt else 8
                except:
                    step_b = 8
                
                SignatureScanner.internal_scan(
                    self.image, self.blocksize, start_b, end_b, step_b,
                    stop_evt=self.stop_evt,
                    progress_cb=lambda done, total, h: self.after(0, self._set_progress_ratio, done, total, h),
                    hit_cb=lambda b: self.after(0, self._add_hit_row, b)
                )
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Scan Error", str(e)))
        finally:
            self.after(0, self._scan_finished)
    
    def _scan_finished(self):
        """Called when scan completes."""
        self.status.config(text="Scan completed")
    
    def abort_scan(self):
        """Abort running scan."""
        self.stop_evt.set()
        self.status.config(text="Aborting scan...")
    
    def _add_hit_row(self, block: int):
        """Add found block to table."""
        # Check if already exists
        for iid in self.tree.get_children():
            if str(self.tree.item(iid, "values")[0]) == str(block):
                return
        
        iid = self.tree.insert("", "end", values=(block, "(pending)", "-", "?", "-", "-", "-"))
        
        if self.chk_autoval.get():
            self._enqueue_fsstat(iid, block)
    
    def _enqueue_fsstat(self, iid, block):
        """Queue fsstat validation."""
        self._fsstat_queue.append((iid, block))
        if not self._fsstat_worker_running:
            threading.Thread(target=self._fsstat_worker, daemon=True).start()
    
    def _fsstat_worker(self):
        """Worker thread for fsstat validation."""
        self._fsstat_worker_running = True
        try:
            while self._fsstat_queue:
                iid, blk = self._fsstat_queue.pop(0)
                try:
                    res = subprocess.run(
                        [FSSTAT, "-B", str(blk), self.image],
                        capture_output=True, text=True, timeout=30
                    )
                    out = res.stdout or res.stderr
                    ok, name, enc, uuid, apsb_oid, apsb_xid, snapshots = parse_fsstat(out)
                    
                    if ok:
                        self.tree.set(iid, "name", name)
                        self.tree.set(iid, "enc", enc)
                        self.tree.set(iid, "snapshots", str(len(snapshots)))
                        self.tree.set(iid, "uuid", uuid)
                        self.tree.set(iid, "apsb_oid", apsb_oid)
                        self.tree.set(iid, "apsb_xid", apsb_xid)
                        
                        # Store snapshots
                        self.volume_snapshots[str(blk)] = snapshots
                    else:
                        self.tree.set(iid, "name", "(invalid)")
                        self.tree.set(iid, "snapshots", "0")
                    
                    self.update_idletasks()
                except Exception:
                    pass
        finally:
            self._fsstat_worker_running = False
    
    def _set_progress_unknown(self, done, hits):
        """Update progress for unknown total."""
        self.prog_lbl.config(text=f"{hits} hits")
    
    def _set_progress_ratio(self, done, total, hits):
        """Update progress with known total."""
        pct = (done / total * 100.0) if total > 0 else 0
        self.progress["value"] = pct
        self.prog_lbl.config(text=f"{pct:.1f}%")
    
    def validate_all(self):
        """Validate all entries with fsstat."""
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo("Validate", "No volumes found")
            return
        
        ok_count = 0
        for i, iid in enumerate(items, 1):
            blk = str(self.tree.item(iid, "values")[0])
            try:
                r = subprocess.run(
                    [FSSTAT, "-B", blk, self.image],
                    capture_output=True, text=True
                )
                out = r.stdout or r.stderr
                ok, name, enc, uuid, oid, xid, snapshots = parse_fsstat(out)
                
                if ok:
                    ok_count += 1
                    self.tree.set(iid, "name", name)
                    self.tree.set(iid, "enc", enc)
                    self.tree.set(iid, "snapshots", str(len(snapshots)))
                    self.tree.set(iid, "uuid", uuid)
                    self.tree.set(iid, "apsb_oid", oid)
                    self.tree.set(iid, "apsb_xid", xid)
                    
                    # Store snapshots
                    self.volume_snapshots[blk] = snapshots
                else:
                    self.tree.set(iid, "name", "(invalid)")
                    self.tree.set(iid, "snapshots", "0")
                
                pct = (i / len(items)) * 100.0
                self.progress["value"] = pct
                self.prog_lbl.config(text=f"{pct:.1f}%")
                self.update_idletasks()
            except Exception:
                pass
        
        messagebox.showinfo("Validation Complete", 
                          f"Checked: {len(items)}, Valid: {ok_count}")
    
    def try_pstat(self):
        """Try running pstat to find volumes."""
        if not self.image:
            return
        
        try:
            r = subprocess.run([PSTAT, self.image], capture_output=True, text=True)
            out = r.stdout or r.stderr
            
            for line in out.splitlines():
                if "APSB Block Number:" in line:
                    m = re.search(r"APSB Block Number:\s*(\d+)", line)
                    if m:
                        self._add_hit_row(int(m.group(1)))
        except Exception as e:
            messagebox.showerror("pstat Error", str(e))
    
    def manual_add(self):
        """Manually add a block number."""
        if not self.image:
            return
        
        dialog = tk.Toplevel(self)
        dialog.title("Add Block Manually")
        dialog.geometry("300x100")
        
        ttk.Label(dialog, text="APSB Block Number:").pack(pady=10)
        entry = ttk.Entry(dialog, width=20)
        entry.pack(pady=5)
        entry.focus_set()
        
        def add_block():
            value = entry.get().strip()
            if not value.isdigit():
                messagebox.showwarning("Invalid Input", "Please enter a valid block number")
                return
            self._add_hit_row(int(value))
            dialog.destroy()
        
        ttk.Button(dialog, text="Add", command=add_block).pack(pady=10)
    
    def open_browser(self):
        """Open filesystem browser for selected volume."""
        cur = self.tree.focus()
        if not cur:
            messagebox.showinfo("No Selection", "Please select a volume")
            return
        
        blk = str(self.tree.item(cur, "values")[0])
        self.on_volume_selected(self.image, blk, None)
    
    def view_tsk_outputs(self):
        """View TSK outputs for selected volume."""
        cur = self.tree.focus()
        if not cur:
            messagebox.showinfo("No Selection", "Please select a volume")
            return
        
        blk = str(self.tree.item(cur, "values")[0])
        TSKOutputDialog(self, self.image, blk)
    
    def view_snapshots(self):
        """View snapshots for selected volume."""
        cur = self.tree.focus()
        if not cur:
            messagebox.showinfo("No Selection", "Please select a volume")
            return
        
        blk = str(self.tree.item(cur, "values")[0])
        snapshots = self.volume_snapshots.get(blk, [])
        
        if not snapshots:
            messagebox.showinfo("No Snapshots", 
                              "No snapshots found for this volume.\n\n"
                              "Run 'Validate All' if you haven't yet.")
            return
        
        def on_browse(xid, name):
            self.on_volume_selected(self.image, blk, xid)
        
        SnapshotListDialog(self, self.image, blk, snapshots, on_browse)


# =====================================================================
# GUI: FILESYSTEM BROWSER (ENHANCED WITH SNAPSHOT SUPPORT)
# =====================================================================

class FilesystemBrowserFrame(ttk.Frame):
    """Frame for browsing APFS filesystem with snapshot support."""
    
    def __init__(self, parent, image=None, block=None, snapshot_xid=None):
        super().__init__(parent)
        self.image = image
        self.block = block
        self.snapshot_xid = snapshot_xid
        self.sector_offset = 0
        self.fs_access = None
        
        # Navigation state
        self.stack = []
        self.cwd_inode = None
        self.cwd_entries = []
        
        self.build_ui()
        
        if image and block:
            self.load_volume(image, block, snapshot_xid)
    
    def build_ui(self):
        # Info bar (shows if browsing snapshot)
        self.info_bar = ttk.Label(self, text="", relief="solid", anchor="w", 
                                 font=("", 10, "bold"), foreground="blue")
        
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=8)
        
        ttk.Label(toolbar, text="Path:").pack(side="left")
        self.path_var = tk.StringVar(value="/")
        self.path_entry = ttk.Entry(toolbar, textvariable=self.path_var)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=6)
        
        ttk.Button(toolbar, text="Go", command=self.open_path).pack(side="left")
        ttk.Button(toolbar, text="↑ Up", command=self.go_up).pack(side="left", padx=(6,0))
        ttk.Button(toolbar, text="Export File", 
                  command=self.export_file).pack(side="left", padx=(12,0))
        ttk.Button(toolbar, text="Export Folder", 
                  command=self.export_folder).pack(side="left", padx=6)
        
        # Main content area
        content = ttk.PanedWindow(self, orient="horizontal")
        content.pack(fill="both", expand=True, padx=8, pady=(0,8))
        
        # Left: File list
        list_frame = ttk.Frame(content)
        
        cols = ("name", "type")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings")
        self.tree.heading("name", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.column("name", width=400, anchor="w")
        self.tree.column("type", width=100, anchor="w")
        
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.bind("<Double-1>", self.on_double_click)
        
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        
        content.add(list_frame, weight=2)
        
        # Right: Tabs for preview, info, and TSK outputs
        right_frame = ttk.Notebook(content)
        
        self.preview_text = scrolledtext.ScrolledText(right_frame, wrap="none")
        self.info_text = scrolledtext.ScrolledText(right_frame, wrap="none")
        self.fls_text = scrolledtext.ScrolledText(right_frame, wrap="none", font=("Courier", 9))
        self.istat_text = scrolledtext.ScrolledText(right_frame, wrap="none", font=("Courier", 9))
        
        right_frame.add(self.preview_text, text="Preview")
        right_frame.add(self.info_text, text="Info")
        right_frame.add(self.fls_text, text="fls Output")
        right_frame.add(self.istat_text, text="istat Output")
        
        content.add(right_frame, weight=1)
        
        # Status bar
        self.status = ttk.Label(self, text="Ready", relief="sunken", anchor="w")
        self.status.pack(fill="x", padx=8, pady=(0,8))
    
    def load_volume(self, image, block, snapshot_xid=None):
        """Load a specific volume and optionally a snapshot."""
        self.image = image
        self.block = block
        self.snapshot_xid = snapshot_xid
        self.fs_access = APFSFilesystemAccess(image, block, self.sector_offset, snapshot_xid)
        
        # Show info bar if browsing snapshot
        if snapshot_xid:
            self.info_bar.config(text=f"  SNAPSHOT MODE: Browsing snapshot XID {snapshot_xid}  ")
            self.info_bar.pack(fill="x", padx=8, pady=(8,0))
        else:
            self.info_bar.pack_forget()
        
        self.list_root()
    
    def list_root(self):
        """List root directory."""
        if not self.fs_access:
            return
        
        try:
            self.cwd_entries = self.fs_access.list_dir(inode=None)
            # Update fls output
            self._update_fls_output(None)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read root directory:\n{e}")
            return
        
        self.cwd_inode = None
        self.stack = []
        self.path_var.set("/")
        self.fill_list(self.cwd_entries)
        self.status.config(text=f"OK: / ({len(self.cwd_entries)} entries)")
    
    def list_inode(self, name, inode):
        """List specific inode (directory)."""
        if not self.fs_access:
            return
        
        try:
            entries = self.fs_access.list_dir(inode=inode)
            # Update fls output
            self._update_fls_output(inode)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read '{name}':\n{e}")
            return
        
        self.stack.append((name, inode))
        self.cwd_inode = inode
        self.cwd_entries = entries
        
        path = "/" + "/".join(n for n, _ in self.stack)
        self.path_var.set(path)
        self.fill_list(entries)
        self.status.config(text=f"OK: {path} ({len(entries)} entries)")
    
    def _update_fls_output(self, inode):
        """Update fls output tab with raw command output."""
        if not self.fs_access:
            return
        
        try:
            cmd = [FLS] + self.fs_access._build_base_args()
            if inode is not None:
                cmd += ["-f", "apfs", self.image, str(inode)]
            else:
                cmd += [self.image]
            
            result = run_command(cmd, timeout=30)
            output = result.stdout or result.stderr
            
            self.fls_text.delete("1.0", "end")
            self.fls_text.insert("1.0", f"Command: {' '.join(cmd)}\n\n")
            self.fls_text.insert("end", output)
        except Exception as e:
            self.fls_text.delete("1.0", "end")
            self.fls_text.insert("1.0", f"Error running fls: {e}")
    
    def go_up(self):
        """Navigate to parent directory."""
        if not self.stack:
            self.list_root()
            return
        
        self.stack.pop()
        
        if not self.stack:
            self.list_root()
            return
        
        # Re-list parent
        pname, pinode = self.stack[-1]
        try:
            entries = self.fs_access.list_dir(inode=pinode)
            self._update_fls_output(pinode)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read parent directory:\n{e}")
            return
        
        self.cwd_inode = pinode
        self.cwd_entries = entries
        
        path = "/" + "/".join(n for n, _ in self.stack)
        self.path_var.set(path)
        self.fill_list(entries)
        self.status.config(text=f"OK: {path} ({len(entries)} entries)")
    
    def open_path(self):
        """Navigate to specific path."""
        if not self.fs_access:
            return
        
        target = self.path_var.get().strip() or "/"
        if target == "/":
            self.list_root()
            return
        
        # Navigate from root
        parts = [p for p in target.split("/") if p]
        inode = None
        entries = None
        self.stack = []
        
        for part in parts:
            if inode is None:
                entries = self.fs_access.list_dir(inode=None)
            else:
                entries = self.fs_access.list_dir(inode=inode)
            
            found = next((e for e in entries if e["name"] == part and e["kind"] == "dir"), None)
            if not found:
                messagebox.showerror("Error", f"Path component not found: {part}")
                return
            
            self.stack.append((part, found["inode"]))
            inode = found["inode"]
        
        self.cwd_inode = inode
        self.cwd_entries = entries if entries is not None else []
        self._update_fls_output(inode)
        self.fill_list(self.cwd_entries)
        self.status.config(text=f"OK: {target} ({len(self.cwd_entries)} entries)")
    
    def fill_list(self, entries):
        """Populate file list."""
        self.tree.delete(*self.tree.get_children())
        
        # Sort: directories first, then alphabetically
        for e in sorted(entries, key=lambda x: (0 if x["kind"] == "dir" else 1, x["name"].lower())):
            self.tree.insert("", "end", values=(e["name"], e["kind"]), tags=(e["kind"],))
        
        self.tree.tag_configure("dir", font=("", 10, "bold"))
    
    def get_selected_entry(self):
        """Get currently selected entry."""
        sel = self.tree.selection()
        if not sel:
            return None
        
        name, kind = self.tree.item(sel[0], "values")
        entry = next((e for e in self.cwd_entries if e["name"] == name and e["kind"] == kind), None)
        return entry
    
    def on_double_click(self, event=None):
        """Handle double-click on entry."""
        entry = self.get_selected_entry()
        if not entry:
            return
        
        if entry["kind"] == "dir":
            self.list_inode(entry["name"], entry["inode"])
        else:
            self.show_file(entry["name"], entry["inode"])
    
    def show_file(self, name, inode):
        """Show file information and preview."""
        if not self.fs_access:
            return
        
        # Get inode info and update istat tab
        info = self.fs_access.get_inode_info(inode)
        self.info_text.delete("1.0", "end")
        self.info_text.insert("1.0", info)
        
        # Update istat tab with raw output
        try:
            cmd = [ISTAT] + self.fs_access._build_base_args()
            cmd += [self.image, str(inode)]
            result = run_command(cmd, timeout=30)
            output = result.stdout or result.stderr
            
            self.istat_text.delete("1.0", "end")
            self.istat_text.insert("1.0", f"Command: {' '.join(cmd)}\n\n")
            self.istat_text.insert("end", output)
        except Exception as e:
            self.istat_text.delete("1.0", "end")
            self.istat_text.insert("1.0", f"Error running istat: {e}")
        
        # Get file preview
        try:
            raw = self.fs_access.read_file(inode, max_bytes=HEAD_PREVIEW_BYTES)
            if not raw:
                self.preview_text.delete("1.0", "end")
                self.preview_text.insert("1.0", "(No data or empty file)")
                return
            
            try:
                text = raw.decode("utf-8", errors="strict")
                self.preview_text.delete("1.0", "end")
                self.preview_text.insert("1.0", text)
            except UnicodeDecodeError:
                # Binary file - show hexdump
                self.preview_text.delete("1.0", "end")
                self.preview_text.insert("1.0", hexdump(raw))
        except Exception as e:
            self.preview_text.delete("1.0", "end")
            self.preview_text.insert("1.0", f"Error reading file: {e}")
    
    def export_file(self):
        """Export selected file."""
        entry = self.get_selected_entry()
        if not entry or entry["kind"] == "dir":
            messagebox.showinfo("Export", "Please select a file")
            return
        
        dest = filedialog.asksaveasfilename(
            title="Export File As",
            initialfile=entry["name"]
        )
        if not dest:
            return
        
        try:
            data = self.fs_access.read_file(entry["inode"], max_bytes=None)
            with open(dest, "wb") as f:
                f.write(data)
            self.status.config(text=f"Exported: {dest}")
            messagebox.showinfo("Success", f"File exported to:\n{dest}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))
    
    def export_folder(self):
        """Export current folder recursively."""
        if self.cwd_inode is None:
            messagebox.showinfo("Export", "Please navigate to a folder first")
            return
        
        outdir = filedialog.askdirectory(title="Select Destination Folder")
        if not outdir:
            return
        
        try:
            exported = self.fs_access.export_recursive(self.cwd_inode, outdir)
            messagebox.showinfo("Export Complete", 
                              f"Exported {exported} files to:\n{outdir}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))


# =====================================================================
# MAIN APPLICATION
# =====================================================================

class APFSCellebriteToolApp(tk.Tk):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.title("APFS Browser Tool - Enhanced")
        self.geometry("1400x800")
        
        # Check for SleuthKit tools
        self.check_dependencies()
        
        # Menu bar
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About / Methodology", command=self.show_help)
        help_menu.add_separator()
        help_menu.add_command(label="Check SleuthKit Tools", command=self.check_tools)
        
        # Main notebook
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        
        # Inspector tab
        self.inspector = VolumeInspectorFrame(self.notebook, self.on_volume_selected)
        self.notebook.add(self.inspector, text="Volume Inspector")
        
        # Browser tab
        self.browser = FilesystemBrowserFrame(self.notebook)
        self.notebook.add(self.browser, text="Filesystem Browser")
    
    def check_dependencies(self):
        """Check if required tools are available."""
        missing = []
        for tool in [SIGFIND, FLS, FSSTAT, ICAT, ISTAT, PSTAT]:
            if not shutil.which(tool):
                missing.append(tool)
        
        if missing:
            msg = "Missing SleuthKit tools:\n" + "\n".join(f"• {t}" for t in missing)
            msg += "\n\nPlease install SleuthKit:\n"
            msg += "macOS: brew install sleuthkit\n"
            msg += "Linux: apt-get install sleuthkit or yum install sleuthkit"
            messagebox.showwarning("Missing Dependencies", msg)
    
    def check_tools(self):
        """Display tool availability status."""
        tools = {
            "sigfind": SIGFIND,
            "fls": FLS,
            "fsstat": FSSTAT,
            "istat": ISTAT,
            "icat": ICAT,
            "pstat": PSTAT,
            "xxd": XXD
        }
        
        status = []
        for name, path in tools.items():
            found = shutil.which(path) or "NOT FOUND"
            status.append(f"{name}: {found}")
        
        messagebox.showinfo("Tool Status", "\n".join(status))
    
    def show_help(self):
        """Show help dialog."""
        HelpDialog(self)
    
    def on_volume_selected(self, image, block, snapshot_xid=None):
        """Called when user wants to browse a volume or snapshot."""
        self.browser.load_volume(image, int(block), snapshot_xid)
        self.notebook.select(1)  # Switch to browser tab


# =====================================================================
# ENTRY POINT
# =====================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="APFS Browser Tool - Enhanced with Snapshot Support"
    )
    parser.add_argument("-i", "--image", help="Image file to open directly")
    parser.add_argument("-B", "--block", type=int, help="APSB block to browse directly")
    parser.add_argument("-s", "--snapshot", help="Snapshot XID to browse")
    
    args = parser.parse_args()
    
    app = APFSCellebriteToolApp()
    
    # If image and block provided, load directly
    if args.image and args.block:
        app.inspector.image = args.image
        snapshot_xid = int(args.snapshot) if args.snapshot else None
        app.browser.load_volume(args.image, args.block, snapshot_xid)
        app.notebook.select(1)
    
    app.mainloop()


if __name__ == "__main__":
    main()
