import numpy as np 
import cv2 

def color_map(N=256, normalized=False):
    def bitget(byteval, idx):
        return ((byteval & (1 << idx)) != 0)

    dtype = 'float32' if normalized else 'uint8'
    cmap = np.zeros((N, 3), dtype=dtype)
    for i in range(N):
        r = g = b = 0
        c = i
        for j in range(8):
            r = r | (bitget(c, 0) << 7-j)
            g = g | (bitget(c, 1) << 7-j)
            b = b | (bitget(c, 2) << 7-j)
            c = c >> 3

        cmap[i] = np.array([b,g,r])

    cmap = cmap/255 if normalized else cmap
    return cmap

def draw_label(lb, msk):
	lb = np.argmax(lb, axis=-1)
	lb += 1
	lb = np.int32(lb)
	msk = np.int32(msk)
	lb = lb*msk
	cmap = color_map()
	lb = cmap[lb]
	return lb
