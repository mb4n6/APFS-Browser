# APFS Browser Tool

Educational tool for working with Cellebrite AFF4 acquisitions of macOS systems that exhibit the "encrypted flags paradox."

## Authors

Marc Brandt\
Hochschule für Polizei Baden-Württemberg

## Overview

This tool addresses a specific challenge when working with Cellebrite Digital Collector acquisitions of modern macOS systems (especially M1/M2 Macs with APFS): the filesystem metadata indicates encryption despite the data being decrypted during acquisition.

## The Problem: Encrypted Flags Paradox

### Background

When Cellebrite Digital Collector creates an AFF4 acquisition of a Mac with FileVault enabled:

1. **During acquisition**: The data is decrypted (hardware-assisted decryption)
2. **In the image**: The actual data blocks are in plaintext
3. **In metadata**: The filesystem flags still indicate "encrypted" status
4. **Result**: A paradox - decrypted data with encrypted flags

### Technical Details

```
┌─────────────────────────────────────────────────────────┐
│  Cellebrite AFF4 Acquisition                            │
│  ┌───────────────────────────────────────────────────┐  │
│  │ APFS Volume Super Block (APSB)                    │  │
│  │ ┌─────────────────────────────────────────────┐   │  │
│  │ │ Flags: ENCRYPTED = True  ← Problem!         │   │  │
│  │ └─────────────────────────────────────────────┘   │  │
│  │                                                     │  │
│  │ ┌─────────────────────────────────────────────┐   │  │
│  │ │ Data Blocks: PLAINTEXT   ← Actually works!  │   │  │
│  │ └─────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Why Traditional Tools Fail

**Kernel-Space Mounting (hdiutil)**:
```bash
$ hdiutil attach image.dmg
# Result: Password prompt - but there's no password!
# Why: Kernel driver reads encrypted flag and enforces policy
```

**SleuthKit pstat**:
```bash
$ pstat image.dmg
# Result: "General pool error"
# Why: Can't parse container due to inconsistent flags
```

## The Solution: User-Space Parsing

This tool uses **user-space filesystem tools** from SleuthKit that read raw filesystem structures without enforcing kernel policies.

### How It Works

```
Traditional Approach (FAILS):
┌─────────┐    mount    ┌──────────┐    policy    ┌──────────┐
│ Image   │ ──────────→ │  Kernel  │ ───────────→ │ Password │
│         │             │  Driver  │   check      │  Prompt  │
└─────────┘             └──────────┘              └──────────┘
                             ↓
                        Reads flags
                        Enforces encryption

User-Space Approach (WORKS):
┌─────────┐   direct    ┌──────────┐   parse      ┌──────────┐
│ Image   │ ──────────→ │ SleuthKit│ ───────────→ │   Data   │
│         │    read     │  Tools   │   raw        │          │
└─────────┘             └──────────┘              └──────────┘
                             ↓
                        Ignores policy flags
                        Reads data directly
```

### Key Components

1. **sigfind**: Searches for APFS Volume Super Block (APSB) signatures
   - Signature: 0x41505342 ("APSB")
   - Locates volume metadata without mounting

2. **fsstat**: Validates and reads volume metadata
   - Extracts volume name, UUID, encryption status
   - Works despite inconsistent flags

3. **fls**: Lists directory contents
   - Reads directory inodes directly
   - No kernel mounting required

4. **icat**: Extracts file contents
   - Direct inode to data block reading
   - Bypasses filesystem driver

5. **istat**: Reads inode metadata
   - File attributes, timestamps, permissions
   - Raw structure parsing

## Installation

### Prerequisites

**SleuthKit** (required):
```bash
# macOS
brew install sleuthkit

# Ubuntu/Debian
sudo apt-get install sleuthkit

# RHEL/CentOS
sudo yum install sleuthkit
```

**xmount** (for AFF4 conversion):
```bash
# macOS
brew install xmount

# Ubuntu/Debian
sudo apt-get install xmount

# From source
git clone https://github.com/daniel-k/xmount
```

**Python 3** (3.7+):
```bash
# Usually pre-installed on macOS/Linux
python3 --version
```

### Tool Installation

```bash
# Clone or download this repository
cd apfs_cellebrite_browser

# Make executable (optional)
chmod +x apfs_cellebrite_tool.py

# Run
python3 apfs_cellebrite_tool.py
```

## Workflow

### Step 1: Convert AFF4 to DMG

```bash
# Mount AFF4 as DMG using xmount
xmount --in aff4 /path/to/acquisition.aff4 /mnt/point

# The resulting file will be at /mnt/point/acquisition.dd or .dmg
```

### Step 2: Launch Tool

```bash
python3 apfs_cellebrite_tool.py

# Or with direct image/block
python3 apfs_cellebrite_tool.py -i /mnt/point/image.dd -B 1155171
```

### Step 3: Scan for Volumes

1. **Open Image**: Click "Open Image" and select your DMG/RAW file
2. **Choose Scan Method**:
   - **Fast (sigfind)**: Uses SleuthKit's sigfind tool (recommended)
   - **Internal Scan**: Python-based scanning (slower, no dependencies)
3. **Start Scan**: Click "Start Scan"
4. **Wait for Results**: Found APFS volumes will appear in the table

### Step 4: Validate Volumes

- **Auto-validate**: Enable "Auto-validate with fsstat" for automatic validation
- **Manual validate**: Click "Validate All" to check all found blocks
- **Try pstat**: Click "Try pstat" to attempt automatic detection

### Step 5: Browse Filesystem

1. **Select Volume**: Click on a volume in the table
2. **Open Browser**: Click "Open Browser for Selected Volume"
3. **Navigate**: Double-click folders to navigate, double-click files to preview
4. **Export**: Use "Export File" or "Export Folder" buttons

## Usage Examples

### Example 1: Complete Workflow

```bash
# 1. Convert AFF4 to DMG
xmount --in aff4 case_2025.aff4 /mnt/forensics

# 2. Launch tool
python3 apfs_cellebrite_tool.py

# 3. In GUI:
#    - Open Image: /mnt/forensics/case_2025.dd
#    - Select "Fast (sigfind)"
#    - Click "Start Scan"
#    - Wait for volumes to appear
#    - Select "Data (Role)" volume
#    - Click "Open Browser for Selected Volume"
#    - Navigate and export files
```

### Example 2: Direct Volume Access

If you already know the APSB block number:

```bash
python3 apfs_cellebrite_tool.py -i /mnt/forensics/image.dd -B 1155171
```

This opens directly in browser mode.

### Example 3: Manual Block Addition

If pstat shows a block but scan doesn't find it:

```bash
$ pstat image.dmg
# Shows: APSB Block Number: 1155171

# In GUI:
# - Click "Add Block Manually"
# - Enter: 1155171
# - Click "Add"
```

## Educational Context

This tool is designed for forensic education and demonstrates:

### Key Concepts

1. **Kernel-Space vs User-Space**
   - Kernel drivers enforce policies
   - User-space tools read raw data
   - Different access paradigms

2. **APFS Structure**
   - Container vs Volume super blocks
   - APSB signature location
   - Metadata vs data separation

3. **Forensic Challenges**
   - Encryption vs decryption paradox
   - Metadata inconsistencies
   - Tool limitations

4. **Problem-Solving Approach**
   - Understand the root cause
   - Find alternative access methods
   - Validate data integrity

### Learning Objectives

Students using this tool will learn:

- How APFS filesystem structures work
- The difference between logical and physical access
- Why kernel-space tools may fail
- How to use user-space alternatives
- Forensic methodology for problem-solving

## Technical Details

### APFS Volume Super Block (APSB)

```
Offset  Size  Description
------  ----  -----------
0x00    8     Checksum
0x08    8     Object ID (OID)
0x10    8     Transaction ID (XID)
0x18    4     Object Type (0x0D for VSUPER)
0x1C    4     Object Subtype (0x00 for VSUPER)
0x20    4     Signature ("APSB")
...
```

### Scanning Strategy

**sigfind Method**:
- Searches entire image for 0x41505342 signature
- Fast: ~2-5 minutes for 256GB image
- Depends on SleuthKit installation

**Internal Method**:
- Python-based block-by-block reading
- Configurable start, end, step
- Slower but no dependencies
- Useful for specific ranges

### Why Step Size Matters

```python
# Step = 1: Check every block (slow but thorough)
# Step = 8: Check every 8th block (8x faster)
# Step = 16: Check every 16th block (16x faster)

# APFS volumes are usually well-aligned
# Step = 8 is a good balance
```

## Troubleshooting

### "sigfind not found"

```bash
# Check installation
which sigfind

# Install SleuthKit
brew install sleuthkit  # macOS
sudo apt-get install sleuthkit  # Linux
```

### "fls failed"

- Verify block number is correct
- Try different block from scan results
- Check if image is corrupted

### No Volumes Found

1. Try both scan methods (sigfind and internal)
2. Reduce step size for internal scan
3. Try "Try pstat" button
4. Manually add known block numbers

### Password Prompt on Mount

This is the exact problem this tool solves! Use the tool instead of mounting.

## Limitations

- **Read-only**: This tool only reads data, cannot modify
- **APFS only**: Designed specifically for APFS filesystems
- **Performance**: Large volumes may take time to scan
- **Dependencies**: Requires SleuthKit tools

## Best Practices

1. **Always validate**: Use fsstat to verify found blocks
2. **Multiple methods**: Try both sigfind and internal scanning
3. **Document findings**: Note which volumes you access
4. **Verify exports**: Check exported files for completeness
5. **Legal compliance**: Only use on authorized images

## License

This tool is provided for educational and forensic research purposes.
Use only on systems you own or have explicit authorization to examine.
It is not a replacement for certified forensic software and must not be used in operational casework or legal evidence processing.

## References

- [SleuthKit Documentation](https://www.sleuthkit.org/sleuthkit/)
- [APFS Reference](https://developer.apple.com/support/apple-file-system/)
