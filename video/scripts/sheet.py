import sys, glob
from PIL import Image, ImageDraw
files = sorted(glob.glob(sys.argv[1] + "/f*.png"))
cols = int(sys.argv[3]) if len(sys.argv) > 3 else 2
w = 960
ims = [Image.open(f) for f in files]
h = int(ims[0].height * w / ims[0].width)
rows = (len(ims) + cols - 1) // cols
g = Image.new("RGB", (w * cols, h * rows), "white")
for i, (f, im) in enumerate(zip(files, ims)):
    im = im.convert("RGB").resize((w, h))
    d = ImageDraw.Draw(im); d.text((10, 10), f.split("/")[-1], fill=(255, 0, 0))
    g.paste(im, ((i % cols) * w, (i // cols) * h))
g.save(sys.argv[2])
