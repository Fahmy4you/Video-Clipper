"""Optional cache preparation; downloads weights without loading an inference model."""
import argparse,os,time

def main():
    parser=argparse.ArgumentParser(description='Siapkan Whisper small sebelum membuat highlight; tidak memakai Gemini.')
    parser.add_argument('--offline',action='store_true',help='Hanya periksa cache lokal tanpa mengunduh')
    args=parser.parse_args()
    os.environ['HF_HUB_DISABLE_XET']='1'
    from faster_whisper.utils import download_model
    from app.config import STORAGE
    started=time.monotonic()
    print('Memeriksa cache Whisper small. Unduhan pertama memerlukan internet; aplikasi tetap bisa digunakan.',flush=True)
    from pathlib import Path
    root=Path(download_model('small',cache_dir=str(STORAGE/'models'),local_files_only=args.offline))
    if not (root/'model.bin').is_file() or not (root/'config.json').is_file():raise SystemExit('Cache model belum lengkap. Jalankan kembali tanpa --offline untuk melanjutkan unduhan.')
    print(f'Whisper small tersedia di cache ({time.monotonic()-started:.1f} detik).',flush=True)
if __name__=='__main__':main()
