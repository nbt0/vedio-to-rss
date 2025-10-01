import traceback
from utils.video_downloader import VideoDownloader

vd = VideoDownloader()
try:
    result = vd.extract_video_info('https://www.bilibili.com/video/BV1yNH7zbE8v/', fast_mode=True)
    print('Result:', result)
except Exception as e:
    print('Exception:', e)
    traceback.print_exc()