# Remove all KOLA videos from downloaded archive
archive_path = 'D:/music/Youtube/Playlists/downloaded.txt'

# Read all lines
with open(archive_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Get KOLA video IDs from recent channel scan
kola_videos = [
    'd1qcuiUCNZ0', 'xIOQhUC3uHU', 'Se9rnTPsTBc', 'EEe9lViKwXs', 
    'k5qBtZCphJM', 'MRtm-gWDzJA', 'WeKIE8BX5BM', 'VaQaUMGzDdY',
    '4tLRsTyZqkM', 'tQWzqNMCiGk', '4jpx5ysp26s', 'H7F1Dz_fYWg',
    'pJkh6GXLa-g', 'b5QPX5IFuEc', '6IUQK6bthaA'
]

# Remove KOLA video lines
original_count = len(lines)
filtered_lines = []

for line in lines:
    should_keep = True
    for video_id in kola_videos:
        if video_id in line:
            should_keep = False
            print(f"Removing: {line.strip()}")
            break
    if should_keep:
        filtered_lines.append(line)

removed_count = original_count - len(filtered_lines)

# Write back
with open(archive_path, 'w', encoding='utf-8') as f:
    f.writelines(filtered_lines)

print(f'\nResult:')
print(f'Removed {removed_count} KOLA entries from archive')
print(f'Total lines before: {original_count}')
print(f'Total lines after: {len(filtered_lines)}')
print('KOLA channel ready for re-download!') 