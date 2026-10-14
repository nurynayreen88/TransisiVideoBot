"""Lightweight optional white motion-graphics overlays for storyboard videos."""
import subprocess
import hashlib
import random
from pathlib import Path
from PIL import Image, ImageDraw

CHOICES = ('auto','black','white','gold','pastel','sparkle','motion','circle','pop','all','none')

def make_overlay(path: Path, width: int, height: int, choice: str, background='original', seed=''):
    if choice not in CHOICES: raise ValueError('Unknown doodle option')
    rng_seed = hashlib.sha256((str(seed)+choice+background).encode()).digest()
    if choice == 'auto':
        # Contrast-aware palettes selected for the actual chosen studio background.
        palettes = {
            'dark': ((255,244,220,235),(255,195,104,235),(187,225,255,235)),
            'white': ((38,53,72,225),(66,115,130,225),(156,83,116,225)),
            'beige': ((84,61,49,230),(143,86,64,225),(76,103,88,225)),
            'pastel': ((75,62,91,225),(122,72,107,225),(56,99,105,225)),
            'gradient': ((86,63,59,230),(123,79,105,225),(55,102,108,225)),
            'mist': ((42,62,81,230),(77,88,130,225),(102,63,89,225)),
            'duotone': ((46,57,72,235),(93,63,101,225),(47,100,94,225)),
            'pattern': ((53,67,82,235),(117,76,89,225),(48,103,97,225)),
            'original': ((36,42,52,230),(86,63,101,225),(51,91,100,225)),
        }
        white = palettes.get(background, palettes['original'])[rng_seed[0] % 3]
        choice = 'all'
    else:
        ink = choice if choice in ('black','white','gold','pastel') else ('white' if background == 'dark' else 'black')
        white = {'black':(30,33,38,215),'white':(255,255,255,225),'gold':(212,155,45,230),'pastel':(218,102,158,225)}[ink]
    if choice in ('black','white','gold','pastel'):
        choice = 'all'
    rng = random.Random(hashlib.sha256((str(seed)+choice+background).encode()).digest())
    variant = rng.randrange(5)
    img = Image.new('RGBA',(width,height),(0,0,0,0))
    d = ImageDraw.Draw(img)
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
    if choice in ('circle','all'):
        d.arc((width*.06,height*.31,width*.32,height*.48),30,320,fill=white,width=thin)
        d.arc((width*.70,height*.49,width*.94,height*.65),195,485,fill=white,width=thin)
    if choice in ('pop','all'):
        for x,y in ((.18,.25),(.83,.72)):
            cx,cy=int(width*x),int(height*y)
            for dx,dy in ((-1,0),(1,0),(0,-1),(0,1),(-.7,-.7),(.7,.7)):
                d.line((cx+int(dx*12),cy+int(dy*12),cx+int(dx*26),cy+int(dy*26)),fill=white,width=thin)
    # Product-specific peripheral accents; deterministic for the same source, varied across products.
    for j in range(3 + variant):
        side = j % 2
        x = width * (rng.uniform(.07,.23) if side == 0 else rng.uniform(.77,.93))
        y = height * rng.uniform(.16,.84)
        radius = max(5, int(width*rng.uniform(.009,.023)))
        motif = (j + variant) % 4
        if motif == 0:
            d.arc((x-radius*2,y-radius*2,x+radius*2,y+radius*2),rng.randrange(0,90),rng.randrange(220,340),fill=white,width=thin)
        elif motif == 1:
            d.line((x-radius,y,x+radius,y),fill=white,width=thin)
            d.line((x,y-radius,x,y+radius),fill=white,width=thin)
        elif motif == 2:
            d.ellipse((x-radius/2,y-radius/2,x+radius/2,y+radius/2),outline=white,width=thin)
        else:
            d.arc((x-radius,y-radius,x+radius,y+radius),25,280,fill=white,width=thin)
    img.save(path)

def apply_overlay(source: Path, target: Path, choice: str, width: int, height: int, duration: int, background='original', seed=''):
    if choice == 'none':
        raise ValueError('No overlay requested')
    overlay=target.with_suffix('.overlay.png')
    make_overlay(overlay,width,height,choice,background,seed=seed)
    # Animate appearance/disappearance in brief beats rather than covering the whole video.
    enable="+".join(f"between(t,{start:.2f},{min(duration,start+0.65):.2f})"
                    for start in (0.55, duration*.34, duration*.68) if start<duration)
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(source),
         '-loop','1','-i',str(overlay),
         '-filter_complex',f"[0:v][1:v]overlay=0:0:shortest=1:enable='{enable}',format=yuv420p[v]",
         '-map','[v]','-an','-t',str(duration),'-c:v','libx264','-preset','veryfast',
         '-crf','18','-pix_fmt','yuv420p',str(target)]
    subprocess.run(cmd,check=True,timeout=240)
