"""Lightweight optional white motion-graphics overlays for storyboard videos."""
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw

CHOICES = ('auto','white','sparkle','motion','all','none')

def make_overlay(path: Path, width: int, height: int, choice: str):
    if choice not in CHOICES: raise ValueError('Unknown doodle option')
    if choice == 'auto': choice = 'white'
    img = Image.new('RGBA',(width,height),(0,0,0,0))
    d = ImageDraw.Draw(img)
    white=(255,255,255,215)
    thin=max(2,width//180)
    # Restrict decorative strokes to peripheral safe zones, away from central labels.
    if choice in ('white','all'):
        d.arc((width*.07,height*.23,width*.31,height*.42),185,335,fill=white,width=thin)
        d.arc((width*.69,height*.53,width*.94,height*.75),5,155,fill=white,width=thin)
        d.arc((width*.08,height*.66,width*.29,height*.79),195,325,fill=white,width=thin)
    if choice in ('motion','all'):
        for j in range(3):
            y=int(height*(.30+j*.035))
            d.arc((int(width*.035),y,int(width*.27),y+int(height*.12)),200,300,fill=white,width=thin)
            y2=int(height*(.60+j*.035))
            d.arc((int(width*.73),y2,int(width*.96),y2+int(height*.12)),20,120,fill=white,width=thin)
    if choice in ('sparkle','all'):
        for x,y,r in ((.15,.20,.017),(.86,.35,.014),(.13,.81,.012),(.87,.79,.019)):
            cx,cy,rr=int(width*x),int(height*y),max(4,int(width*r))
            d.line((cx-rr,cy,cx+rr,cy),fill=white,width=thin)
            d.line((cx,cy-rr,cx,cy+rr),fill=white,width=thin)
    img.save(path)

def apply_overlay(source: Path, target: Path, choice: str, width: int, height: int, duration: int):
    if choice == 'none':
        raise ValueError('No overlay requested')
    overlay=target.with_suffix('.overlay.png')
    make_overlay(overlay,width,height,choice)
    # Animate appearance/disappearance in brief beats rather than covering the whole video.
    enable="+".join(f"between(t,{start:.2f},{min(duration,start+1.15):.2f})"
                    for start in (0.55, duration*.34, duration*.68) if start<duration)
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(source),
         '-loop','1','-i',str(overlay),
         '-filter_complex',f"[0:v][1:v]overlay=0:0:shortest=1:enable='{enable}',format=yuv420p[v]",
         '-map','[v]','-an','-t',str(duration),'-c:v','libx264','-preset','veryfast',
         '-crf','25','-pix_fmt','yuv420p',str(target)]
    subprocess.run(cmd,check=True,timeout=240)
