"""
Fix MP4 files by moving moov atom to the beginning (faststart).
This is required for browser streaming - without moov at the start,
the browser cannot play the video until fully downloaded.

Also re-encodes using a Python-based approach if needed.
"""
import struct
import os
import sys
import shutil


def find_atoms(f, end_pos=None):
    """Find all top-level atoms in an MP4 file."""
    atoms = []
    if end_pos is None:
        f.seek(0, 2)
        end_pos = f.tell()
    f.seek(0)
    while f.tell() < end_pos:
        pos = f.tell()
        header = f.read(8)
        if len(header) < 8:
            break
        size = struct.unpack('>I', header[:4])[0]
        atom_type = header[4:8].decode('ascii', errors='replace')
        if size == 0:
            # Atom extends to end of file
            size = end_pos - pos
        elif size == 1:
            # 64-bit extended size
            ext = f.read(8)
            size = struct.unpack('>Q', ext)[0]
        atoms.append({'type': atom_type, 'pos': pos, 'size': size})
        f.seek(pos + size)
    return atoms


def fix_moov_position(input_path, output_path=None):
    """Move moov atom before mdat for streaming compatibility."""
    if output_path is None:
        output_path = input_path + '.tmp'
        replace_original = True
    else:
        replace_original = False

    with open(input_path, 'rb') as f:
        atoms = find_atoms(f)

    atom_types = [a['type'] for a in atoms]
    print(f"  Atoms found: {atom_types}")

    moov_idx = None
    mdat_idx = None
    for i, a in enumerate(atoms):
        if a['type'] == 'moov':
            moov_idx = i
        if a['type'] == 'mdat':
            mdat_idx = i

    if moov_idx is None:
        print("  ERROR: No moov atom found")
        return False

    if mdat_idx is None:
        print("  ERROR: No mdat atom found")
        return False

    if moov_idx < mdat_idx:
        print("  moov is already before mdat — no fix needed")
        if not replace_original:
            shutil.copy2(input_path, output_path)
        return True

    print(f"  moov is at index {moov_idx}, mdat at {mdat_idx} — need to move moov before mdat")

    # Read moov atom data
    with open(input_path, 'rb') as f:
        moov_atom = atoms[moov_idx]
        f.seek(moov_atom['pos'])
        moov_data = f.read(moov_atom['size'])

    # Calculate offset adjustment: moov will be placed before mdat
    # All chunk offsets in moov need to be adjusted by moov_size
    moov_size = len(moov_data)

    # Update chunk offsets in moov (stco and co64 atoms)
    moov_data = update_offsets(moov_data, moov_size)

    # Write output: ftyp + other pre-mdat atoms + moov + mdat + post-mdat atoms
    with open(input_path, 'rb') as fin, open(output_path, 'wb') as fout:
        # Write atoms before mdat
        for a in atoms:
            if a['type'] == 'mdat':
                break
            if a['type'] == 'moov':
                continue  # Skip moov in its original position
            fin.seek(a['pos'])
            fout.write(fin.read(a['size']))

        # Write moov (with updated offsets)
        fout.write(moov_data)

        # Write mdat and everything after
        for a in atoms[mdat_idx:]:
            if a['type'] == 'moov':
                continue  # Skip moov in its original position
            fin.seek(a['pos'])
            fout.write(fin.read(a['size']))

    if replace_original:
        os.replace(output_path, input_path)
        print(f"  Fixed: moov moved to front of {input_path}")
    else:
        print(f"  Fixed: {output_path}")

    return True


def update_offsets(moov_data, offset_adjustment):
    """Update stco/co64 chunk offset tables inside moov atom."""
    result = bytearray(moov_data)

    # Find and update stco atoms (32-bit chunk offsets)
    pos = 0
    while True:
        idx = result.find(b'stco', pos)
        if idx == -1:
            break
        # stco format: [size(4)][type(4)][version(1)][flags(3)][entry_count(4)][offsets...]
        # idx points to 'stco' which is at offset 4 in the atom (after size)
        atom_start = idx - 4
        version_flags = result[idx + 4: idx + 8]
        entry_count = struct.unpack('>I', result[idx + 8: idx + 12])[0]
        offset_start = idx + 12
        for i in range(entry_count):
            o = offset_start + i * 4
            if o + 4 > len(result):
                break
            old_offset = struct.unpack('>I', result[o:o + 4])[0]
            new_offset = old_offset + offset_adjustment
            struct.pack_into('>I', result, o, new_offset)
        pos = idx + 12 + entry_count * 4

    # Find and update co64 atoms (64-bit chunk offsets)
    pos = 0
    while True:
        idx = result.find(b'co64', pos)
        if idx == -1:
            break
        entry_count = struct.unpack('>I', result[idx + 8: idx + 12])[0]
        offset_start = idx + 12
        for i in range(entry_count):
            o = offset_start + i * 8
            if o + 8 > len(result):
                break
            old_offset = struct.unpack('>Q', result[o:o + 8])[0]
            new_offset = old_offset + offset_adjustment
            struct.pack_into('>Q', result, o, new_offset)
        pos = idx + 12 + entry_count * 8

    return bytes(result)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "static/uploads/20260516_051526_video_fixxx_annotated.mp4"
    print(f"Fixing: {path}")
    fix_moov_position(path)
