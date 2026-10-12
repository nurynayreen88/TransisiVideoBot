from io import BytesIO
from PIL import Image, ImageDraw
def fusion_gif(success=False):
    frames=[]
    for i in range(10):
        im=Image.new("RGB",(240,140),(24,24,55))
        d=ImageDraw.Draw(im)
        if success:
            d.ellipse((90,22,150,82),fill="#ffd38a")
            d.polygon([(89,30),(100,4),(116,19),(133,3),(152,30)],fill="#f5cf45")
            d.rectangle((92,83,148,126),fill="#9955e6")
            d.ellipse((69-i%4,6-i%4,171+i%4,135+i%4),outline="#f9e575",width=4)
            d.text((74,126),"FUSION!",fill="white")
        else:
            for x,color in [(65+i%5,"#39c5ff"),(175-i%5,"#f2779e")]:
                d.ellipse((x-18,30,x+18,66),fill="#ffd38a")
                d.polygon([(x-20,38),(x-10,10),(x,23),(x+11,9),(x+20,38)],fill=color)
                d.rectangle((x-22,70,x+22,116),fill=color)
                d.line((x-12,116,x-16,133),fill=color,width=8)
                d.line((x+12,116,x+16,133),fill=color,width=8)
            d.text((68,120),"FUSION LOADING",fill="white")
        frames.append(im)
    out=BytesIO()
    frames[0].save(out,format="GIF",save_all=True,append_images=frames[1:],duration=180,loop=0)
    out.seek(0)
    out.name="fusion.gif"
    return out
