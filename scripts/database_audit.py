#!/usr/bin/env python3
"""
Database Audit Script - найти треки в базе, файлы которых не существуют на диске

Этот скрипт проверяет синхронизацию между базой данных и файловой системой.
"""

import sqlite3
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Optional

def load_env_config() -> Dict[str, str]:
    """Загрузить конфигурацию из .env файла."""
    config = {}
    
    # Ищем .env файл в корне проекта
    current_dir = Path(__file__).parent.parent
    env_path = current_dir / '.env'
    
    if env_path.exists():
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip().lstrip('\ufeff')  # Remove BOM
                    if line and '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
        except Exception as e:
            print(f"Warning: Failed to load .env file: {e}")
    
    return config

def find_missing_files(db_path: str, playlists_dir: str = None) -> List[Dict]:
    """Найти треки в базе данных, файлы которых не существуют."""
    missing_files = []
    
    try:
        # Подключение к базе данных
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # Найти все треки, которые НЕ помечены как удаленные
        query = """
        SELECT t.id, t.video_id, t.name, t.relpath, t.play_likes, t.play_starts, t.last_start_ts,
               t.channel_group, t.published_date
        FROM tracks t
        WHERE t.video_id NOT IN (
            SELECT dt.video_id FROM deleted_tracks dt
        )
        ORDER BY t.play_likes DESC, t.play_starts DESC
        """
        
        cur.execute(query)
        tracks = cur.fetchall()
        
        print(f"[INFO] Проверка {len(tracks)} треков в базе данных...")
        
        for i, track in enumerate(tracks):
            track_id, video_id, name, relpath, play_likes, play_starts, last_start_ts, channel_group, published_date = track
            
            # Показать прогресс каждые 100 треков
            if (i + 1) % 100 == 0:
                print(f"[INFO] Проверено {i + 1}/{len(tracks)} треков...")
            
            # Проверить существование файла
            if playlists_dir:
                # Строим полный путь: PLAYLISTS_DIR + relpath
                file_path = Path(playlists_dir) / relpath
            else:
                # Иначе используем путь как есть
                file_path = Path(relpath)
            
            if not file_path.exists():
                missing_files.append({
                    'track_id': track_id,
                    'video_id': video_id,
                    'name': name,
                    'relpath': relpath,
                    'full_path': str(file_path.resolve()),
                    'play_likes': play_likes or 0,
                    'play_starts': play_starts or 0,
                    'last_start_ts': last_start_ts,
                    'channel_group': channel_group,
                    'published_date': published_date
                })
        
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Ошибка при работе с базой данных: {e}")
        return []
    
    return missing_files

def print_full_list(missing_files: List[Dict]):
    """Вывести полный список всех отсутствующих треков."""
    print(f"\n{'='*100}")
    print(f"[ПОЛНЫЙ СПИСОК ОТСУТСТВУЮЩИХ ТРЕКОВ]")
    print(f"{'='*100}")
    
    if not missing_files:
        print("✅ Все треки в базе данных имеют соответствующие файлы на диске!")
        return
    
    print(f"❌ Найдено {len(missing_files)} треков без файлов на диске:")
    print()
    
    # Сортируем по количеству лайков и воспроизведений
    missing_files.sort(key=lambda x: (x['play_likes'], x['play_starts']), reverse=True)
    
    print(f"{'№':<4} {'Лайки':<6} {'Проигр.':<8} {'ID':<12} {'Полный путь'}")
    print("-" * 150)
    
    for i, track in enumerate(missing_files):
        print(f"{i+1:<4} {track['play_likes']:<6} {track['play_starts']:<8} {track['video_id']:<12} {track['full_path']}")
    
    print()
    print(f"Всего отсутствующих треков: {len(missing_files)}")

def print_audit_results(missing_files: List[Dict]):
    """Вывести результаты ревизии."""
    print(f"\n{'='*80}")
    print(f"[РЕЗУЛЬТАТЫ РЕВИЗИИ БАЗЫ ДАННЫХ]")
    print(f"{'='*80}")
    
    if not missing_files:
        print("✅ Все треки в базе данных имеют соответствующие файлы на диске!")
        return
    
    print(f"❌ Найдено {len(missing_files)} треков без файлов на диске:")
    print()
    
    # Сортируем по количеству лайков (самые важные сначала)
    missing_files.sort(key=lambda x: (x['play_likes'], x['play_starts']), reverse=True)
    
    # Статистика
    liked_tracks = [f for f in missing_files if f['play_likes'] > 0]
    played_tracks = [f for f in missing_files if f['play_starts'] > 0]
    
    print(f"📊 Статистика:")
    print(f"  - Треков с лайками: {len(liked_tracks)}")
    print(f"  - Треков с воспроизведениями: {len(played_tracks)}")
    print(f"  - Треков без активности: {len(missing_files) - len(played_tracks)}")
    print()
    
    # Показываем первые 20 самых важных треков
    print(f"🔍 Топ-20 важных треков без файлов:")
    print(f"{'№':<3} {'Лайки':<6} {'Проигр.':<8} {'Название':<60} {'ID'}")
    print("-" * 90)
    
    for i, track in enumerate(missing_files[:20]):
        name = track['name'][:55] + "..." if len(track['name']) > 58 else track['name']
        print(f"{i+1:<3} {track['play_likes']:<6} {track['play_starts']:<8} {name:<60} {track['video_id']}")
    
    if len(missing_files) > 20:
        print(f"... и еще {len(missing_files) - 20} треков")
    
    print()
    
    # Группировка по каналам
    by_channel = {}
    for track in missing_files:
        channel = track['channel_group'] or 'Unknown'
        if channel not in by_channel:
            by_channel[channel] = []
        by_channel[channel].append(track)
    
    print(f"📁 По каналам/группам:")
    for channel, tracks in sorted(by_channel.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  - {channel}: {len(tracks)} треков")
    
    print()
    print(f"💡 Рекомендации:")
    if liked_tracks:
        print(f"  - Треки с лайками стоит попробовать восстановить")
    print(f"  - Можно очистить записи без активности (0 лайков, 0 воспроизведений)")
    print(f"  - Рекомендуется проверить настройки путей и повторить сканирование")

def main():
    parser = argparse.ArgumentParser(description="Ревизия базы данных - поиск треков без файлов")
    parser.add_argument("--db-path", help="Путь к базе данных")
    parser.add_argument("--playlists-dir", help="Директория с плейлистами для проверки файлов")
    parser.add_argument("--export", help="Экспортировать результаты в CSV файл")
    parser.add_argument("--full-list", action="store_true", help="Показать полный список всех отсутствующих треков с путями")
    
    args = parser.parse_args()
    
    # Загружаем конфигурацию
    env_config = load_env_config()
    
    # Определяем путь к базе данных
    db_path = args.db_path
    if not db_path:
        db_path = env_config.get('DB_PATH')
    
    if not db_path or not Path(db_path).exists():
        print("[ERROR] Не удалось найти базу данных.")
        print("Укажите путь через --db-path или настройте DB_PATH в .env файле")
        sys.exit(1)
    
    # Определяем директорию плейлистов (важно!)
    playlists_dir = args.playlists_dir
    if not playlists_dir:
        # Приоритет: PLAYLISTS_DIR из .env
        playlists_dir = env_config.get('PLAYLISTS_DIR')
        
        # Если нет PLAYLISTS_DIR, используем ROOT_DIR/Playlists
        if not playlists_dir:
            root_dir = env_config.get('ROOT_DIR')
            if root_dir:
                playlists_dir = str(Path(root_dir) / 'Playlists')
    
    print(f"[INFO] База данных: {db_path}")
    if playlists_dir:
        print(f"[INFO] Директория плейлистов: {playlists_dir}")
    else:
        print(f"[INFO] Использую относительные пути из базы данных")
    
    # Выполняем ревизию
    missing_files = find_missing_files(db_path, playlists_dir)
    
    # Выводим результаты
    if args.full_list:
        print_full_list(missing_files)
    else:
        print_audit_results(missing_files)
    
    # Экспорт если requested
    if args.export and missing_files:
        try:
            import csv
            with open(args.export, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['video_id', 'name', 'relpath', 'full_path', 'play_likes', 'play_starts', 'channel_group']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for track in missing_files:
                    writer.writerow({k: track[k] for k in fieldnames})
            print(f"\n📄 Результаты экспортированы в: {args.export}")
        except Exception as e:
            print(f"\n[ERROR] Ошибка экспорта: {e}")

if __name__ == "__main__":
    main() 