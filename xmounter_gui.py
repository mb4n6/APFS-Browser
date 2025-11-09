#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xmount AFF4 to DMG GUI
----------------------
Simple GUI for mounting AFF4 images as DMG using xmount
with optional cache support
"""

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime


class XmountAFF4GUI(tk.Tk):
    """GUI for xmount AFF4 to DMG conversion and mounting."""
    
    def __init__(self):
        super().__init__()
        
        self.title("xmount Image Converter")
        self.geometry("1400x800")
        self.resizable(True, True)
        
        # State variables for xmount
        self.image_format = tk.StringVar(value="aff4")  # aff4, e01, or dmg
        self.aff4_file = tk.StringVar()
        self.mount_point = tk.StringVar(value="/Volumes/aff4_mount")
        self.cache_file = tk.StringVar()
        self.use_cache = tk.BooleanVar(value=False)
        self.is_mounted = False  # xmount status only
        self.dmg_filename = None  # Store actual DMG filename created by xmount
        
        # DMG-specific state (completely separate from xmount)
        self.dmg_file = tk.StringVar()  # DMG file to attach
        self.dmg_use_shadow = tk.BooleanVar(value=False)
        self.dmg_use_nomount = tk.BooleanVar(value=False)
        self.is_dmg_attached = False  # DMG attach status (separate from xmount)
        self.hdiutil_device = None  # Store hdiutil device path for detach
        
        # Build UI
        self._build_ui()
        
        # Check for xmount
        self._check_xmount()
    
    def _build_ui(self):
        """Build the user interface."""
        # Main container with padding
        main_frame = ttk.Frame(self, padding=8)
        main_frame.pack(fill="both", expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="xmount: Forensic Image → DMG Converter", 
                               font=("", 14, "bold"))
        title_label.pack(pady=(0, 10))
        
        # === TWO COLUMN LAYOUT ===
        columns_frame = ttk.Frame(main_frame)
        columns_frame.pack(fill="both", expand=True)
        
        # LEFT COLUMN: xmount Operations
        left_column = ttk.Frame(columns_frame)
        left_column.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        # RIGHT COLUMN: DMG Operations
        right_column = ttk.Frame(columns_frame)
        right_column.pack(side="right", fill="both", expand=True, padx=(5, 0))
        
        # ============================================
        # LEFT COLUMN CONTENT: xmount
        # ============================================
        
        xmount_title = ttk.Label(left_column, text="xmount Operations", 
                                font=("", 12, "bold"), foreground="#2E7D32")
        xmount_title.pack(pady=(0, 10))
        
        # === Image Format Selection ===
        format_frame = ttk.LabelFrame(left_column, text="Image Format", padding=6)
        format_frame.pack(fill="x", pady=(0, 6))
        
        format_container = ttk.Frame(format_frame)
        format_container.pack(fill="x")
        
        ttk.Radiobutton(format_container, text="AFF4", 
                       variable=self.image_format, value="aff4",
                       command=self._on_format_change).pack(side="left", padx=(0, 10))
        ttk.Radiobutton(format_container, text="E01", 
                       variable=self.image_format, value="e01",
                       command=self._on_format_change).pack(side="left")
        
        # === AFF4 File Selection ===
        self.file_frame = ttk.LabelFrame(left_column, text="AFF4 Image File", padding=6)
        self.file_frame.pack(fill="x", pady=(0, 6))
        
        file_container = ttk.Frame(self.file_frame)
        file_container.pack(fill="x")
        
        ttk.Entry(file_container, textvariable=self.aff4_file, width=40).pack(
            side="left", fill="x", expand=True, padx=(0, 5)
        )
        ttk.Button(file_container, text="📁", command=self._browse_aff4).pack(
            side="left", ipadx=5
        )
        
        # === Mount Point ===
        self.mount_frame = ttk.LabelFrame(left_column, text="Mount Point", padding=6)
        self.mount_frame.pack(fill="x", pady=(0, 6))
        
        mount_container = ttk.Frame(self.mount_frame)
        mount_container.pack(fill="x")
        
        ttk.Entry(mount_container, textvariable=self.mount_point, width=40).pack(
            side="left", fill="x", expand=True, padx=(0, 5)
        )
        ttk.Button(mount_container, text="📁", command=self._browse_mount).pack(
            side="left", ipadx=5
        )
        
        ttk.Label(self.mount_frame, text="💡 DMG file will be created here", 
                 foreground="blue", font=("", 8, "italic")).pack(anchor="w", pady=(5, 0))
        
        # === Cache Configuration ===
        self.cache_frame = ttk.LabelFrame(left_column, text="Cache (Optional)", padding=6)
        self.cache_frame.pack(fill="x", pady=(0, 6))
        
        # Cache checkbox
        ttk.Checkbutton(self.cache_frame, text="Use cache file", 
                       variable=self.use_cache, command=self._toggle_cache).pack(
            anchor="w", pady=(0, 5)
        )
        
        # Cache file selection
        self.cache_container = ttk.Frame(self.cache_frame)
        self.cache_container.pack(fill="x")
        
        ttk.Label(self.cache_container, text="File:").pack(side="left", padx=(0, 5))
        self.cache_entry = ttk.Entry(self.cache_container, textvariable=self.cache_file, 
                                     width=30, state="disabled")
        self.cache_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.cache_browse_btn = ttk.Button(self.cache_container, text="📁", 
                                           command=self._browse_cache, state="disabled")
        self.cache_browse_btn.pack(side="left", ipadx=5)
        
        # Cache info
        ttk.Label(self.cache_frame, 
                 text="ℹ️ Improves performance, requires disk space",
                 foreground="gray", font=("", 8)).pack(anchor="w", pady=(5, 0))
        
        # === Action Buttons ===
        button_frame = ttk.Frame(left_column)
        button_frame.pack(fill="x", pady=(6, 6))
        
        # Row 1: Mount, Unmount, Check Status
        row1 = ttk.Frame(button_frame)
        row1.pack(fill="x", pady=(0, 5))
        
        self.mount_btn = ttk.Button(row1, text="🚀 Mount", 
                                    command=self._mount, style="Accent.TButton")
        self.mount_btn.pack(side="left", padx=(0, 5), ipadx=10, ipady=5, fill="x", expand=True)
        
        self.unmount_btn = ttk.Button(row1, text="✖️ Unmount", 
                                      command=self._unmount, state="disabled")
        self.unmount_btn.pack(side="left", padx=(0, 5), ipadx=10, ipady=5, fill="x", expand=True)
        
        ttk.Button(row1, text="🔄 Status", 
                  command=self._check_status).pack(side="left", ipadx=10, ipady=5, fill="x", expand=True)
        
        # Row 2: Finder, APFS Browser, Help
        row2 = ttk.Frame(button_frame)
        row2.pack(fill="x")
        
        self.finder_btn = ttk.Button(row2, text="📁 Finder", 
                                     command=self._open_in_finder, state="disabled")
        self.finder_btn.pack(side="left", padx=(0, 5), ipadx=10, ipady=5, fill="x", expand=True)
        
        self.browser_btn = ttk.Button(row2, text="🔍 APFS", 
                                      command=self._open_apfs_browser, state="disabled")
        self.browser_btn.pack(side="left", padx=(0, 5), ipadx=10, ipady=5, fill="x", expand=True)
        
        ttk.Button(row2, text="ℹ️ Help", 
                  command=self._show_help).pack(side="left", ipadx=10, ipady=5, fill="x", expand=True)
        
        # === Status ===
        status_frame = ttk.LabelFrame(left_column, text="Status", padding=6)
        status_frame.pack(fill="x", pady=(0, 6))
        
        self.status_label = ttk.Label(status_frame, text="⚪ Ready - Select image", 
                                     font=("", 10, "bold"))
        self.status_label.pack(anchor="w")
        
        # === xmount Log Output ===
        log_frame = ttk.LabelFrame(left_column, text="xmount Log", padding=5)
        log_frame.pack(fill="both", expand=True)
        
        # Text widget with scrollbar
        log_container = ttk.Frame(log_frame)
        log_container.pack(fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(log_container)
        scrollbar.pack(side="right", fill="y")
        
        self.log_text = tk.Text(log_container, wrap="word", height=15,
                               background="#0a0a0a", foreground="#00ff00",
                               font=("Courier", 9), yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.log_text.yview)
        
        ttk.Button(log_frame, text="Clear Log", command=self._clear_log).pack(pady=(5, 0))
        
        ttk.Button(log_frame, text="Clear Log", command=self._clear_log).pack(pady=(5, 0))
        
        # Initial messages
        self._log("=" * 80)
        self._log("xmount Image Converter initialized")
        self._log("Supported formats: AFF4, E01")
        self._log("=" * 80)
        
        # ============================================
        # RIGHT COLUMN CONTENT: DMG Operations
        # ============================================
        
        # DMG Title
        dmg_title = ttk.Label(right_column, 
                             text="DMG Operations (hdiutil)", 
                             font=("", 12, "bold"), foreground="#1976D2")
        dmg_title.pack(pady=(0, 10))
        
        ttk.Label(right_column, 
                font=("", 8, "italic"), foreground="gray").pack(pady=(0, 8))
        
        # === DMG File Selection ===
        dmg_file_frame = ttk.LabelFrame(right_column, text="DMG File to Attach", padding=6)
        dmg_file_frame.pack(fill="x", pady=(0, 6))
        
        dmg_file_container = ttk.Frame(dmg_file_frame)
        dmg_file_container.pack(fill="x")
        
        ttk.Entry(dmg_file_container, textvariable=self.dmg_file, width=40).pack(
            side="left", fill="x", expand=True, padx=(0, 5)
        )
        ttk.Button(dmg_file_container, text="📁", command=self._browse_dmg_file).pack(
            side="left", ipadx=5
        )
        
        ttk.Label(dmg_file_frame, 
                 text="💡 Any DMG (xmount or standalone)",
                 foreground="blue", font=("", 8, "italic")).pack(anchor="w", pady=(5, 0))
        
        # === DMG Options ===
        dmg_options_frame = ttk.LabelFrame(right_column, text="hdiutil Options", padding=6)
        dmg_options_frame.pack(fill="x", pady=(0, 6))
        
        ttk.Checkbutton(dmg_options_frame, 
                       text="-shadow (temp writes)", 
                       variable=self.dmg_use_shadow).pack(anchor="w")
        
        ttk.Checkbutton(dmg_options_frame, 
                       text="-nomount (no filesystem)", 
                       variable=self.dmg_use_nomount).pack(anchor="w")
        
        ttk.Label(dmg_options_frame, 
                 text="ℹ️ -shadow for modifications, -nomount for no mount",
                 foreground="gray", font=("", 8)).pack(anchor="w", pady=(5, 0))
        
        # === DMG Action Buttons ===
        dmg_button_frame = ttk.Frame(right_column)
        dmg_button_frame.pack(fill="x", pady=(0, 6))
        
        self.attach_dmg_btn = ttk.Button(dmg_button_frame, text="📎 Attach", 
                                        command=self._attach_dmg, style="Accent.TButton")
        self.attach_dmg_btn.pack(side="left", padx=(0, 5), ipadx=10, ipady=5, fill="x", expand=True)
        
        self.detach_dmg_btn = ttk.Button(dmg_button_frame, text="✖️ Detach", 
                                        command=self._detach_dmg, state="disabled")
        self.detach_dmg_btn.pack(side="left", padx=(0, 5), ipadx=10, ipady=5, fill="x", expand=True)
        
        ttk.Button(dmg_button_frame, text="🔄 Status", 
                  command=self._check_dmg_status).pack(side="left", ipadx=10, ipady=5, fill="x", expand=True)
        
        # === DMG Status ===
        dmg_status_frame = ttk.LabelFrame(right_column, text="DMG Status", padding=6)
        dmg_status_frame.pack(fill="x", pady=(0, 6))
        
        self.dmg_status_label = ttk.Label(dmg_status_frame, text="⚪ Ready - Select DMG", 
                                         font=("", 10, "bold"))
        self.dmg_status_label.pack(anchor="w")
        
        # === DMG Log Output ===
        dmg_log_frame = ttk.LabelFrame(right_column, text="DMG Log", padding=5)
        dmg_log_frame.pack(fill="both", expand=True)
        
        # Text widget with scrollbar
        dmg_log_container = ttk.Frame(dmg_log_frame)
        dmg_log_container.pack(fill="both", expand=True)
        
        dmg_scrollbar = ttk.Scrollbar(dmg_log_container)
        dmg_scrollbar.pack(side="right", fill="y")
        
        self.dmg_log_text = tk.Text(dmg_log_container, wrap="word", height=15,
                                   background="#0a0a0a", foreground="#00ccff",
                                   font=("Courier", 9), yscrollcommand=dmg_scrollbar.set)
        self.dmg_log_text.pack(side="left", fill="both", expand=True)
        dmg_scrollbar.config(command=self.dmg_log_text.yview)
        
        ttk.Button(dmg_log_frame, text="Clear DMG Log", command=self._clear_dmg_log).pack(pady=(5, 0))
        
        # Initial DMG messages
        self._log_dmg("=" * 80)
        self._log_dmg("DMG Operations (hdiutil) initialized")
        self._log_dmg("Independent from xmount - use for any DMG file")
        self._log_dmg("=" * 80)
    
    def _toggle_cache(self):
        """Enable/disable cache file selection."""
        if self.use_cache.get():
            self.cache_entry.config(state="normal")
            self.cache_browse_btn.config(state="normal")
            self._log("Cache enabled")
        else:
            self.cache_entry.config(state="disabled")
            self.cache_browse_btn.config(state="disabled")
            self._log("Cache disabled")
    
    def _on_format_change(self):
        """Handle format selection change."""
        fmt = self.image_format.get()
        if fmt == "aff4":
            self.file_frame.config(text="AFF4 Image File")
            # Update mount point suggestion
            if self.mount_point.get() == "/Volumes/e01_mount":
                self.mount_point.set("/Volumes/aff4_mount")
            self._log("Format selected: AFF4 (Advanced Forensic Format)")
            self._log("  → Uses xmount with custom mount point")
        elif fmt == "e01":
            self.file_frame.config(text="E01 Image File")
            # Update mount point suggestion
            if self.mount_point.get() == "/Volumes/aff4_mount":
                self.mount_point.set("/Volumes/e01_mount")
            self._log("Format selected: E01 (Expert Witness / EnCase)")
            self._log("  → Uses xmount with custom mount point")
    
    def _browse_aff4(self):
        """Browse for image file."""
        fmt = self.image_format.get()
        
        if fmt == "aff4":
            title = "Select AFF4 Image"
            filetypes = [
                ("AFF4 Images", "*.aff4"),
                ("All Files", "*.*")
            ]
        else:  # e01
            title = "Select E01 Image"
            filetypes = [
                ("E01 Images", "*.e01 *.E01"),
                ("All Files", "*.*")
            ]
        
        filename = filedialog.askopenfilename(title=title, filetypes=filetypes)
        
        if filename:
            self.aff4_file.set(filename)
            self._log(f"Selected image: {filename}")
            
            # Auto-suggest cache file name in /tmp/
            if not self.cache_file.get():
                base_name = os.path.basename(filename)
                cache_name = f"/tmp/{base_name}.cache"
                self.cache_file.set(cache_name)
    
    def _browse_mount(self):
        """Browse for mount point directory."""
        directory = filedialog.askdirectory(title="Select Mount Point Directory")
        if directory:
            self.mount_point.set(directory)
            self._log(f"Mount point: {directory}")
    
    def _browse_cache(self):
        """Browse for cache file."""
        filename = filedialog.asksaveasfilename(
            title="Select Cache File Location",
            defaultextension=".cache",
            filetypes=[
                ("Cache Files", "*.cache"),
                ("All Files", "*.*")
            ]
        )
        if filename:
            self.cache_file.set(filename)
            self._log(f"Cache file: {filename}")
    
    def _check_xmount(self):
        """Check if xmount is available."""
        result = subprocess.run(["which", "xmount"], capture_output=True)
        if result.returncode == 0:
            path = result.stdout.decode().strip()
            self._log(f"✓ xmount found at: {path}")
            
            # Get xmount version
            try:
                version_result = subprocess.run(["xmount", "--version"], 
                                               capture_output=True, text=True)
                version_line = version_result.stdout.split('\n')[0] if version_result.stdout else "unknown"
                self._log(f"  Version: {version_line}")
            except:
                pass
        else:
            self._log("✗ xmount NOT FOUND!")
            self._log("  Installation:")
            self._log("    macOS: brew install xmount")
            self._log("    Linux: apt-get install xmount")
            messagebox.showwarning("xmount Not Found",
                "xmount is not installed or not in PATH.\n\n"
                "Please install it:\n"
                "  macOS: brew install xmount\n"
                "  Linux: apt-get install xmount")
        
        # Check if /Volumes exists (macOS standard, might not exist on Linux)
        if not os.path.exists("/Volumes"):
            self._log("⚠️ Warning: /Volumes directory does not exist")
            self._log("  This is normal on Linux. You can use any mount point.")
            self._log("  On macOS, /Volumes is the standard location.")
    
    def _mount(self):
        """Mount image using xmount."""
        image = self.aff4_file.get()
        mount_point = self.mount_point.get()
        
        # Validation
        if not image:
            messagebox.showwarning("No File", "Please select an image file.")
            return
        
        if not os.path.exists(image):
            messagebox.showerror("Error", f"Image file does not exist:\n{image}")
            return
        
        if not mount_point:
            messagebox.showwarning("No Mount Point", "Please specify a mount point.")
            return
        
        # Check if already mounted
        if self._is_mounted():
            messagebox.showinfo("Already Mounted", "Image is already mounted.")
            return
        
        # Create mount point if needed
        if not os.path.exists(mount_point):
            try:
                # Check if parent directory exists, if not create with sudo
                parent_dir = os.path.dirname(mount_point)
                if parent_dir and not os.path.exists(parent_dir):
                    self._log(f"Creating parent directory with sudo: {parent_dir}")
                    subprocess.run(["sudo", "mkdir", "-p", parent_dir], check=True)
                
                # Create mount point
                self._log(f"Creating mount point with sudo: {mount_point}")
                subprocess.run(["sudo", "mkdir", "-p", mount_point], check=True)
                self._log(f"✓ Created mount point: {mount_point}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create mount point:\n{e}")
                return
        
        # Check if mount point is empty
        if os.listdir(mount_point):
            response = messagebox.askyesno("Mount Point Not Empty",
                "The mount point directory is not empty.\n\n"
                "Continue anyway?")
            if not response:
                return
        
        # Build command based on format
        fmt = self.image_format.get()
        
        # Use xmount for AFF4/E01
        if fmt == "aff4":
            cmd = ["sudo", "xmount", "--in", "aff4", image, "--out", "dmg"]
        else:  # e01
            cmd = ["sudo", "xmount", "--in", "ewf", image, "--out", "dmg"]
        
        # Add cache if enabled
        if self.use_cache.get():
            cache = self.cache_file.get()
            if cache:
                cmd.extend(["--cache", cache])
                self._log(f"Cache file: {cache}")
            else:
                messagebox.showwarning("No Cache File", 
                    "Cache is enabled but no cache file specified.\n"
                    "Proceeding without cache.")
        
        cmd.append(mount_point)
        
        # Log and execute
        self._log("=" * 80)
        self._log("MOUNTING...")
        self._log(f"Format: {fmt.upper()}")
        self._log(f"Command: {' '.join(cmd)}")
        self._log("Note: This will prompt for sudo password")
        self._log("-" * 80)
        
        self.status_label.config(text="🔄 Mounting...", foreground="orange")
        self.update()
        
        try:
            # Run mount command
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            # Handle xmount output
            if result.returncode == 0 or self._is_mounted():
                # Find the actual DMG file created by xmount
                import time
                time.sleep(0.5)  # Give xmount a moment to create the file
                
                dmg_filename = self._find_dmg_file()
                if dmg_filename:
                    self.dmg_filename = dmg_filename
                    dmg_path = os.path.join(mount_point, dmg_filename)
                    
                    self._log("✓ MOUNT SUCCESSFUL!")
                    self._log(f"✓ Mount point: {mount_point}")
                    self._log(f"✓ DMG file: {dmg_filename}")
                    self._log(f"✓ Full path: {dmg_path}")
                else:
                    self._log("⚠️ Warning: DMG file not found yet")
                    dmg_path = os.path.join(mount_point, "*.dmg")
            
                if result.stdout:
                    self._log(f"Output: {result.stdout}")
                
                self.status_label.config(text=f"✓ Mounted - DMG: {self.dmg_filename or '*.dmg'}", 
                                       foreground="green")
                self.is_mounted = True
                self.mount_btn.config(state="disabled")
                self.unmount_btn.config(state="normal")
                self.finder_btn.config(state="normal")
                self.browser_btn.config(state="normal")
                
                # Show DMG location
                messagebox.showinfo("Mount Successful",
                    f"Image mounted successfully!\n\n"
                    f"Format: {fmt.upper()}\n"
                    f"Mount point: {mount_point}\n"
                    f"DMG file: {self.dmg_filename or 'Check mount point for .dmg file'}\n\n"
                    f"You can now:\n"
                    f"• Open in Finder\n"
                    f"• Use APFS Browser\n"
                    f"• Use with other tools")
                
            else:
                self._log("✗ MOUNT FAILED!")
                self._log(f"Return code: {result.returncode}")
                if result.stderr:
                    self._log(f"Error: {result.stderr}")
                if result.stdout:
                    self._log(f"Output: {result.stdout}")
                
                self.status_label.config(text="✗ Mount failed", foreground="red")
                messagebox.showerror("Mount Failed", 
                    f"Failed to mount image.\n\n"
                    f"Error:\n{result.stderr or result.stdout or 'Unknown error'}")
        
        except subprocess.TimeoutExpired:
            self._log("✗ Mount operation timed out")
            self.status_label.config(text="✗ Timeout", foreground="red")
            messagebox.showerror("Timeout", "Mount operation timed out after 60 seconds.")
        
        except Exception as e:
            self._log(f"✗ Exception: {e}")
            self.status_label.config(text="✗ Error", foreground="red")
            messagebox.showerror("Error", str(e))
    
    def _unmount(self):
        """Unmount the filesystem."""
        # Use fusermount/umount for xmount
        mount_point = self.mount_point.get()
            
        if not mount_point:
            messagebox.showwarning("No Mount Point", "Please specify a mount point.")
            return
        
        # Confirm unmount
        response = messagebox.askyesno("Confirm Unmount",
            f"Unmount xmount filesystem at:\n{mount_point}\n\nAre you sure?")
        if not response:
            return
        
        # Try different unmount methods
        self._log("=" * 80)
        self._log("UNMOUNTING...")
        self._log(f"Mount point: {mount_point}")
        self.status_label.config(text="🔄 Unmounting...", foreground="orange")
        self.update()
        
        success = False
        
        # Try fusermount first (recommended for FUSE)
        for cmd in [["fusermount", "-u", mount_point], 
                   ["umount", mount_point],
                   ["sudo", "umount", mount_point]]:
            try:
                self._log(f"Trying: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0 or not self._is_mounted():
                    success = True
                    self._log("✓ UNMOUNT SUCCESSFUL!")
                    break
                else:
                    if result.stderr:
                        self._log(f"  Failed: {result.stderr.strip()}")
            except FileNotFoundError:
                self._log(f"  Command not found: {cmd[0]}")
                continue
            except Exception as e:
                self._log(f"  Error: {e}")
                continue
            
            if success:
                self.status_label.config(text="✓ Unmounted", foreground="green")
                self.is_mounted = False
                self.dmg_filename = None  # Reset DMG filename
                self.mount_btn.config(state="normal")
                self.unmount_btn.config(state="disabled")
                self.finder_btn.config(state="disabled")
                self.browser_btn.config(state="disabled")
                messagebox.showinfo("Success", "Filesystem unmounted successfully!")
            else:
                self._log("✗ All unmount attempts failed")
                self.status_label.config(text="✗ Unmount failed", foreground="red")
                messagebox.showerror("Unmount Failed",
                    "Failed to unmount filesystem.\n\n"
                    "Try manually:\n"
                    f"  fusermount -u {mount_point}\n"
                    f"or\n"
                    f"  sudo umount {mount_point}")
    
    def _attach_dmg(self):
        """Attach DMG using hdiutil with optional parameters."""
        image = self.dmg_file.get()
        
        # Validation
        if not image:
            messagebox.showwarning("No File", "Please select a DMG file.")
            self._log_dmg("⚠️ No DMG file selected")
            return
        
        if not os.path.exists(image):
            messagebox.showerror("Error", f"DMG file does not exist:\n{image}")
            self._log_dmg(f"✗ DMG file not found: {image}")
            return
        
        # Check if already attached
        if self.is_dmg_attached:
            messagebox.showinfo("Already Attached", "A DMG is already attached.\nPlease detach first.")
            self._log_dmg("⚠️ DMG already attached")
            return
        
        # Build hdiutil command
        cmd = ["hdiutil", "attach", "-readonly"]
        
        # Add optional parameters
        if self.dmg_use_shadow.get():
            cmd.append("-shadow")
            self._log_dmg("Using -shadow option (temporary writes enabled)")
        
        if self.dmg_use_nomount.get():
            cmd.append("-nomount")
            self._log_dmg("Using -nomount option (attach without mounting)")
        
        cmd.append(image)
        
        # Log and execute
        self._log_dmg("=" * 80)
        self._log_dmg("ATTACHING DMG...")
        self._log_dmg(f"File: {image}")
        self._log_dmg(f"Command: {' '.join(cmd)}")
        self._log_dmg("Note: Using hdiutil (macOS native tool)")
        self._log_dmg("-" * 80)
        
        self.dmg_status_label.config(text="🔄 Attaching...", foreground="orange")
        self.update()
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # Parse hdiutil output to get device and mount point
                # Output format: /dev/diskXsY   Apple_HFS   /Volumes/VolumeName
                lines = result.stdout.strip().split('\n')
                mount_info = None
                device = None
                
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 1 and parts[0].startswith('/dev/disk'):
                        device = parts[0]
                        # Find mount point (last part, may contain spaces)
                        if not self.dmg_use_nomount.get():
                            mount_idx = line.rfind('/Volumes/')
                            if mount_idx != -1:
                                mount_info = line[mount_idx:].strip()
                        break
                
                if device:
                    self.hdiutil_device = device
                    
                    self._log_dmg("✓ ATTACH SUCCESSFUL!")
                    self._log_dmg(f"✓ Device: {device}")
                    if mount_info:
                        self._log_dmg(f"✓ Mount point: {mount_info}")
                    else:
                        self._log_dmg(f"✓ Attached without mounting (-nomount used)")
                    self._log_dmg(f"✓ DMG attached and ready to use")
                    
                    status_text = f"✓ Attached - {os.path.basename(mount_info) if mount_info else device}"
                    self.dmg_status_label.config(text=status_text, foreground="green")
                    self.is_dmg_attached = True
                    self.attach_dmg_btn.config(state="disabled")
                    self.detach_dmg_btn.config(state="normal")
                    
                    msg = f"DMG attached successfully!\n\nDevice: {device}"
                    if mount_info:
                        msg += f"\nMount point: {mount_info}\n\nYou can now access the mounted volume."
                    else:
                        msg += f"\n\nAttached without mounting (-nomount)."
                    messagebox.showinfo("Attach Successful", msg)
                else:
                    self._log_dmg("⚠️ Warning: Could not parse hdiutil output")
                    self._log_dmg(f"Output: {result.stdout}")
                    # Still mark as attached if command succeeded
                    self.is_dmg_attached = True
                    self.attach_dmg_btn.config(state="disabled")
                    self.detach_dmg_btn.config(state="normal")
                    messagebox.showinfo("Attach Successful", 
                        f"DMG attached successfully!\n\nCheck /Volumes/ for the mounted volume.")
            else:
                self._log_dmg("✗ ATTACH FAILED!")
                self._log_dmg(f"Return code: {result.returncode}")
                if result.stderr:
                    self._log_dmg(f"Error: {result.stderr}")
                self.dmg_status_label.config(text="✗ Attach failed", foreground="red")
                messagebox.showerror("Attach Failed", 
                    f"Failed to attach DMG:\n\n{result.stderr or 'Unknown error'}")
        
        except subprocess.TimeoutExpired:
            self._log_dmg("✗ Attach operation timed out")
            self.dmg_status_label.config(text="✗ Timeout", foreground="red")
            messagebox.showerror("Timeout", "Attach operation timed out after 60 seconds.")
        
        except Exception as e:
            self._log_dmg(f"✗ Exception: {e}")
            self.dmg_status_label.config(text="✗ Error", foreground="red")
            messagebox.showerror("Error", str(e))
            messagebox.showerror("Attach Failed", 
            f"Failed to attach DMG:\n\n{result.stderr or 'Unknown error'}")
        
        except subprocess.TimeoutExpired:
            self._log("✗ Attach operation timed out")
            self.status_label.config(text="✗ Timeout", foreground="red")
            messagebox.showerror("Timeout", "Attach operation timed out after 60 seconds.")
        
        except Exception as e:
            self._log(f"✗ Exception: {e}")
            self.status_label.config(text="✗ Error", foreground="red")
            messagebox.showerror("Error", str(e))
    
    def _detach_dmg(self):
        """Detach DMG using hdiutil."""
        if not self.hdiutil_device:
            messagebox.showwarning("No Device", 
                "No device information found.\n"
                "The DMG may already be detached.")
            self._log_dmg("⚠️ No device to detach")
            return
        
        # Confirm detach
        response = messagebox.askyesno("Confirm Detach",
            f"Detach DMG device:\n{self.hdiutil_device}\n\nAre you sure?")
        if not response:
            self._log_dmg("Detach cancelled by user")
            return
        
        cmd = ["hdiutil", "detach", self.hdiutil_device]
        
        self._log_dmg("=" * 80)
        self._log_dmg("DETACHING DMG...")
        self._log_dmg(f"Device: {self.hdiutil_device}")
        self._log_dmg(f"Command: {' '.join(cmd)}")
        self.dmg_status_label.config(text="🔄 Detaching...", foreground="orange")
        self.update()
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self._log_dmg("✓ DETACH SUCCESSFUL!")
                self.dmg_status_label.config(text="✓ Detached", foreground="green")
                self.is_dmg_attached = False
                self.hdiutil_device = None
                self.attach_dmg_btn.config(state="normal")
                self.detach_dmg_btn.config(state="disabled")
                messagebox.showinfo("Success", "DMG detached successfully!")
            else:
                self._log_dmg(f"Detach returned code {result.returncode}")
                if result.stderr:
                    self._log_dmg(f"Error: {result.stderr}")
                self.dmg_status_label.config(text="✗ Detach failed", foreground="red")
                messagebox.showerror("Detach Failed", 
                    f"Failed to detach DMG:\n\n{result.stderr or 'Unknown error'}")
        
        except subprocess.TimeoutExpired:
            self._log_dmg("✗ Detach operation timed out")
            self.dmg_status_label.config(text="✗ Timeout", foreground="red")
            messagebox.showerror("Timeout", "Detach operation timed out")
        except Exception as e:
            self._log_dmg(f"✗ Exception: {e}")
            self.dmg_status_label.config(text="✗ Error", foreground="red")
            messagebox.showerror("Error", str(e))
    
    def _find_dmg_file(self):
        """Find the actual DMG file in the mount point."""
        mount_point = self.mount_point.get()
        if not mount_point or not os.path.exists(mount_point):
            return None
        
        try:
            # List all files in mount point
            files = os.listdir(mount_point)
            # Find .dmg files
            dmg_files = [f for f in files if f.endswith('.dmg')]
            
            if dmg_files:
                # Return the first DMG file found
                return dmg_files[0]
            return None
        except Exception as e:
            self._log(f"Error finding DMG file: {e}")
            return None
    
    def _get_dmg_path(self):
        """Get the full path to the DMG file."""
        mount_point = self.mount_point.get()
        if not mount_point:
            return None
        
        # Try stored filename first
        if self.dmg_filename:
            dmg_path = os.path.join(mount_point, self.dmg_filename)
            if os.path.exists(dmg_path):
                return dmg_path
        
        # Search for DMG file
        dmg_filename = self._find_dmg_file()
        if dmg_filename:
            self.dmg_filename = dmg_filename
            return os.path.join(mount_point, dmg_filename)
        
        return None
    
    def _is_mounted(self):
        """Check if the mount point is currently mounted."""
        mount_point = self.mount_point.get()
        if not mount_point or not os.path.exists(mount_point):
            return False
        
        try:
            # Check mount command output for xmount
            result = subprocess.run(["mount"], capture_output=True, text=True)
            if mount_point in result.stdout:
                return True
            
            # Also check if DMG file exists as fallback
            dmg_path = self._get_dmg_path()
            if dmg_path and os.path.exists(dmg_path):
                return True
                
            return False
        except Exception:
            return False
    
    def _check_status(self):
        """Check and display current mount status."""
        self._log("=" * 80)
        self._log("CHECKING STATUS...")
        
        mount_point = self.mount_point.get()
        
        if self._is_mounted():
            dmg_path = self._get_dmg_path()
            
            if dmg_path:
                self._log("✓ Status: MOUNTED")
                self._log(f"  Mount point: {mount_point}")
                self._log(f"  DMG file: {os.path.basename(dmg_path)}")
                self._log(f"  Full path: {dmg_path}")
                
                # Get DMG file size
                try:
                    size = os.path.getsize(dmg_path)
                    size_gb = size / (1024**3)
                    self._log(f"  DMG size: {size_gb:.2f} GB")
                except:
                    pass
                
                self.status_label.config(text=f"✓ Mounted - DMG: {os.path.basename(dmg_path)}", 
                                       foreground="green")
            else:
                self._log("⚠️ Status: MOUNTED but DMG file not found")
                self.status_label.config(text=f"⚠️ Mounted - searching for DMG...", 
                                       foreground="orange")
            
            self.is_mounted = True
            self.mount_btn.config(state="disabled")
            self.unmount_btn.config(state="normal")
            self.finder_btn.config(state="normal")
            self.browser_btn.config(state="normal")
        else:
            self._log("⚪ Status: NOT MOUNTED")
            self.status_label.config(text="⚪ Not mounted", foreground="black")
            self.is_mounted = False
            self.mount_btn.config(state="normal")
            self.unmount_btn.config(state="disabled")
            self.finder_btn.config(state="disabled")
            self.browser_btn.config(state="disabled")
    
    def _show_help(self):
        """Show help dialog."""
        help_text = """
xmount & hdiutil Forensic Image Converter

LAYOUT:
Two-column interface:
• LEFT: xmount Operations (AFF4, E01)
• RIGHT: DMG Operations (hdiutil - independent)

WHAT IT DOES:
This tool mounts forensic images and disk images as accessible volumes.
Supports AFF4, E01 (EnCase/Expert Witness), and DMG (Mac Disk Image) formats.

SUPPORTED FORMATS:
• AFF4 - Advanced Forensic Format 4 (via xmount → DMG)
• E01  - Expert Witness / EnCase Evidence File (via xmount → DMG)
• DMG  - Mac Disk Image / Sparse Image (via hdiutil directly)

WORKFLOW - xmount (LEFT COLUMN):
1. Select format (AFF4 or E01)
2. Select your image file
3. Choose mount point and optional cache
4. Click "Mount (xmount)" - prompts for sudo password
5. Creates virtual DMG file in mount point
6. Use "Open in Finder" or "APFS Browser" buttons
7. Click "Unmount" when done

WORKFLOW - DMG Operations (RIGHT COLUMN):
1. Select any DMG file (created by xmount or standalone)
2. Choose optional parameters:
   • -shadow: allows temporary writes
   • -nomount: attach without mounting filesystem
3. Click "Attach DMG" - uses native hdiutil (no sudo)
4. Click "Detach DMG" when done

DMG OPTIONS:
• -shadow: Mount with shadow file (allows temporary writes)
• -nomount: Attach device without mounting filesystem

CACHE (xmount only):
- Cache improves performance for repeated access
- Requires disk space (similar to image size)
- Recommended for large images or frequent access
- Cache file can be reused across sessions
- Stored in /tmp/ by default

REQUIREMENTS:
- For AFF4/E01: xmount must be installed
  macOS: brew install xmount
  Linux: apt-get install xmount
- For DMG: hdiutil (included with macOS)
- sudo privileges required for xmount only

NOTES:
- xmount and DMG operations are completely independent
- Both can be used simultaneously
- Separate log windows for each operation
- xmount creates virtual DMG → can then be attached with DMG operations
- All operations are read-only by default (unless -shadow used)
- Always unmount/detach before closing the application

EXAMPLE WORKFLOW:
1. LEFT: Convert E01 to DMG with xmount
2. RIGHT: Select the created DMG file
3. RIGHT: Enable -shadow for temporary writes
4. RIGHT: Attach with hdiutil
5. Work with the image
6. RIGHT: Detach when done
7. LEFT: Unmount xmount
        """
        
        messagebox.showinfo("Help", help_text)
        self._log("Help displayed")
    
    def _open_in_finder(self):
        """Open the mount point in Finder and select the DMG file."""
        if not self._is_mounted():
            messagebox.showwarning("Not Mounted", "Please mount the image first.")
            return
        
        # For xmount formats, show the created DMG file
        dmg_path = self._get_dmg_path()
        
        if not dmg_path or not os.path.exists(dmg_path):
            messagebox.showerror("DMG Not Found", 
                f"DMG file not found in mount point.\n"
                f"Please check: {self.mount_point.get()}")
            return
        
        try:
            # Open Finder and select the file (macOS)
            if sys.platform == "darwin":
                subprocess.run(["open", "-R", dmg_path])
                self._log(f"Opened in Finder: {dmg_path}")
            else:
                # Linux - open file manager
                subprocess.run(["xdg-open", os.path.dirname(dmg_path)])
                self._log(f"Opened file manager: {os.path.dirname(dmg_path)}")
        except Exception as e:
            self._log(f"Error opening Finder: {e}")
            messagebox.showerror("Error", f"Failed to open Finder:\n{e}")
    
    def _open_apfs_browser(self):
        """Open the APFS Browser with the DMG file."""
        if not self._is_mounted():
            messagebox.showwarning("Not Mounted", "Please mount the image first.")
            return
        
        # For xmount formats, use the created DMG file
        dmg_path = self._get_dmg_path()
        
        if not dmg_path or not os.path.exists(dmg_path):
            messagebox.showerror("DMG Not Found", 
                f"DMG file not found.\n"
                f"Path: {dmg_path or 'Unknown'}")
            return
        
        # Try to find apfs_browser_tool_enhanced.py
        browser_paths = [
            "apfs_browser_tool_enhanced.py",
            "./apfs_browser_tool_enhanced.py",
            os.path.join(os.path.dirname(__file__), "apfs_browser_tool_enhanced.py"),
            os.path.expanduser("~/apfs_browser_tool_enhanced.py"),
            "/usr/local/bin/apfs_browser_tool_enhanced.py"
        ]
        
        browser_path = None
        for path in browser_paths:
            if os.path.exists(path):
                browser_path = path
                break
        
        if not browser_path:
            response = messagebox.askyesno("Browser Not Found",
                "apfs_browser_tool_enhanced.py not found in standard locations.\n\n"
                "Would you like to select the file manually?")
            if response:
                browser_path = filedialog.askopenfilename(
                    title="Select apfs_browser_tool_enhanced.py",
                    filetypes=[("Python Files", "*.py"), ("All Files", "*.*")]
                )
                if not browser_path:
                    return
            else:
                return
        
        try:
            self._log(f"Opening APFS Browser: {browser_path}")
            self._log(f"With DMG: {dmg_path}")
            
            # Launch browser with DMG path as argument
            subprocess.Popen(["python3", browser_path, "-i", dmg_path])
            
            self._log("✓ APFS Browser launched")
            messagebox.showinfo("Browser Launched",
                f"APFS Browser has been launched with:\n{dmg_path}")
        
        except Exception as e:
            self._log(f"Error launching APFS Browser: {e}")
            messagebox.showerror("Error", 
                f"Failed to launch APFS Browser:\n{e}\n\n"
                f"You can manually run:\n"
                f"python3 apfs_browser_tool_enhanced.py -i {dmg_path}")
    
    def _log(self, message):
        """Add message to log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.update()
    
    def _clear_log(self):
        """Clear the log."""
        self.log_text.delete("1.0", "end")
        self._log("Log cleared")
    
    def _log_dmg(self, message):
        """Add message to DMG log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.dmg_log_text.insert("end", f"[{timestamp}] {message}\n")
        self.dmg_log_text.see("end")
        self.update()
    
    def _clear_dmg_log(self):
        """Clear the DMG log."""
        self.dmg_log_text.delete("1.0", "end")
        self._log_dmg("DMG Log cleared")
    
    def _browse_dmg_file(self):
        """Browse for DMG file to attach."""
        filename = filedialog.askopenfilename(
            title="Select DMG File to Attach",
            filetypes=[
                ("DMG Images", "*.dmg *.DMG"),
                ("Sparse Images", "*.sparseimage *.sparsebundle"),
                ("All Images", "*.dmg *.sparseimage *.sparsebundle"),
                ("All Files", "*.*")
            ]
        )
        
        if filename:
            self.dmg_file.set(filename)
            self._log_dmg(f"Selected DMG: {filename}")
    
    def _check_dmg_status(self):
        """Check and display DMG attach status."""
        self._log_dmg("=" * 80)
        self._log_dmg("CHECKING DMG STATUS...")
        
        if self.is_dmg_attached and self.hdiutil_device:
            self._log_dmg("✓ Status: DMG ATTACHED")
            self._log_dmg(f"  Device: {self.hdiutil_device}")
            
            # Try to find mount point from diskutil
            try:
                result = subprocess.run(["diskutil", "info", self.hdiutil_device], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'Mount Point:' in line:
                            mount = line.split(':', 1)[1].strip()
                            if mount:
                                self._log_dmg(f"  Mount point: {mount}")
                            break
            except:
                pass
            
            self.dmg_status_label.config(text=f"✓ Attached - {self.hdiutil_device}", 
                                        foreground="green")
        else:
            self._log_dmg("⚪ Status: NOT ATTACHED")
            self.dmg_status_label.config(text="⚪ Not attached", foreground="black")


def main():
    """Main entry point."""
    app = XmountAFF4GUI()
    app.mainloop()


if __name__ == "__main__":
    main()