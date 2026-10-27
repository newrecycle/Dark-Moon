"""Bounded public-media acquisition for reference review, without cookies/login.

Only contact sheets and a diagnostic manifest are retained. Full videos remain
in a temporary directory. Site-served bot restrictions stop YouTube acquisition.
"""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request
import re
from PIL import Image, ImageDraw
import yt_dlp

ROOT = Path('review-media')
ROOT.mkdir(exist_ok=True)
items = json.loads(Path('docs/handoff/video-source-coverage.json').read_text())['coverage']
results = []
blocked = False


def fetch(url, limit):
    with urllib.request.urlopen(url, timeout=20) as r:
        raw = r.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Media exceeds bounded download size')
    if raw[:500].lstrip().lower().startswith((b'<html', b'<!doctype')):
        raise ValueError('HTML response instead of media')
    return raw


for item in items:
    vid = item['id']
    record = {'id': vid, 'status': 'unavailable', 'avenues': []}
    if blocked:
        record['reason'] = 'Not attempted after site-served bot restriction'
        results.append(record)
        continue
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'socket_timeout': 12,
                              'retries': 0, 'extractor_retries': 0, 'noplaylist': True,
                              'cachedir': False}) as ydl:
            info = ydl.extract_info(item['url'], download=False)
        record['duration'] = info.get('duration')
        with tempfile.TemporaryDirectory(prefix='dm-reference-') as temp:
            tmp = Path(temp)
            formats = info.get('formats', [])
            # A native public storyboard is preferable to downloading full video.
            boards = [f for f in formats if f.get('protocol') == 'mhtml' and f.get('fragments')]
            if boards:
                board = max(boards, key=lambda f: f.get('width', 0))
                canvas = Image.new('RGB', (1280, 1040), '#10131b')
                draw = ImageDraw.Draw(canvas)
                fragments = board['fragments']
                cols, rows = board['columns'], board['rows']
                fps = board.get('fps') or 0.5
                total = max(1, int(info.get('duration', 1) * fps))
                images = {}
                for slot in range(12):
                    index = min(total - 1, round(slot * (total - 1) / 11))
                    board_index = min(len(fragments) - 1, index // (cols * rows))
                    if board_index not in images:
                        body = fetch(fragments[board_index]['url'], 8 * 1024 * 1024)
                        image = Image.open(io.BytesIO(body)); image.load()
                        images[board_index] = image.convert('RGB')
                    image = images[board_index]
                    w, h = image.width // cols, image.height // rows
                    tile = index % (cols * rows)
                    crop = image.crop(((tile % cols)*w, (tile // cols)*h, (tile % cols+1)*w, (tile // cols+1)*h))
                    crop.thumbnail((426, 235))
                    x, y = (slot % 3)*426, (slot // 3)*260
                    canvas.paste(crop, (x, y+25))
                    draw.text((x+3,y+3), f'{vid} ~{index/fps:.1f}s', fill='white')
                canvas.save(ROOT / (vid + '-contact.jpg'))
                record.update(status='storyboard_decoded', samples=12, tile_width=board['width'], tile_height=board['height'])
                record['avenues'].append('native public storyboard decoded with Pillow')
            else:
                record['avenues'].append('no native storyboard')
            if record['status'] == 'unavailable':
                candidates = [f for f in formats if f.get('ext') == 'mp4' and f.get('height') and f['height'] <= 720 and f.get('protocol') == 'https']
                if candidates:
                    fmt = max(candidates, key=lambda f: f['height'])
                    media = tmp / 'reference.mp4'
                    media.write_bytes(fetch(fmt['url'], 100 * 1024 * 1024))
                    probe = subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type,width,height','-of','json',str(media)],capture_output=True,text=True,timeout=20,check=True)
                    streams = json.loads(probe.stdout)['streams']
                    if not any(s.get('codec_type')=='video' for s in streams):
                        raise ValueError('No video stream decoded')
                    interval = max(1, info['duration']/12)
                    subprocess.run(['ffmpeg','-v','error','-i',str(media),'-vf',f'fps=1/{interval},scale=426:-1,tile=3x4','-frames:v','1',str(ROOT/(vid+'-contact.jpg'))],capture_output=True,timeout=45,check=True)
                    record.update(status='video_decoded',streams=streams,samples=12)
    except Exception as exc:
        message = str(exc)
        if re.search(r'confirm you.re not a bot|automated (?:queries|traffic)|unusual traffic',message,re.I):
            blocked = True
            record['status'] = 'site_bot_restriction'
        record['reason'] = re.sub(r'https?://\S+', '[URL]', message)[:600]
    results.append(record)
    (ROOT/'manifest.json').write_text(json.dumps({'results':results,'full_media_retained':False,'cookies_used':False},indent=2)+'\n')
    print(json.dumps(record),flush=True)
(ROOT/'manifest.json').write_text(json.dumps({'results':results,'full_media_retained':False,'cookies_used':False},indent=2)+'\n')
