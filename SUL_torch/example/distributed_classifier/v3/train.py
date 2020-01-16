import os
os.environ['CUDA_VISIBLE_DEVICES'] = '0,1,2,3'
import torch 
import torch.nn as nn 
import torch.nn.functional as F 
import Model as M 
import numpy as np 
from tqdm import tqdm 
import resnet 
import losses 
import datareader 
import time 

if __name__=='__main__':
	devices = (0,1,2,3)

	BSIZE = 512 * 4
	reader = datareader.get_datareader('../datasetemoreasia/emore_asia_outs.txt', BSIZE, processes=16)

	BackboneRes50 = resnet.Res50()
	classifier = losses.DistributedClassifier(reader.max_label + 1, devices)

	# init 
	dumb_x = torch.from_numpy(np.float32(np.zeros([1,3,112,112])))
	dumb_y = torch.from_numpy(np.int64(np.zeros(1)))
	_ = BackboneRes50(dumb_x)
	_ = classifier(_, dumb_y)

	# restore 
	if devices is not None: BackboneRes50 = nn.DataParallel(BackboneRes50, device_ids=devices).cuda()
	saver = M.Saver(BackboneRes50)
	saver_classifier = M.Saver(classifier)
	# saver.restore('./model/')
	# saver_classifier.restore('./classifier/')

	# define optim 
	optim = torch.optim.SGD([{'params':BackboneRes50.parameters()}, {'params':classifier.parameters()}], lr=0.1, momentum=0.9, weight_decay=0.0005)
	classifier.train()
	BackboneRes50.train()

	MAXEPOCH = 10

	

	for ep in range(MAXEPOCH):
		bar = tqdm(range(reader.iter_per_epoch))
		for it in bar:
			t0 = time.time()
			imgs, labels = reader.get_next()
			t01 = time.time()
			imgs = torch.from_numpy(imgs)
			labels = torch.from_numpy(labels)
			t02 = time.time()
			# training loop 
			optim.zero_grad()
			t1 = time.time()
			feats = BackboneRes50(imgs)
			t2 = time.time()
			loss, acc = classifier(feats, labels)
			t3 = time.time()
			loss.backward()
			t4 = time.time()
			# print(list(BackboneRes50.parameters())[0])
			optim.step()
			# print(list(BackboneRes50.parameters())[0])
			# input()
			t41 = time.time()
			# output string 
			lr = optim.param_groups[0]['lr']
			loss = loss.cpu().detach().numpy()
			# acc = acc.cpu().detach().numpy()

			outstr = 'Ep:%d Ls:%.3f Ac:%.3f Lr:%.1e'%(ep, loss, acc, lr)
			bar.set_description(outstr)
			t5 = time.time()
			# print(t01-t0, t02-t01, t1-t02,t2-t1, t3-t2, t4-t3, t41-t4, t5-t41, t5-t0)

			# save model 
			if it%2000==0 and it>0:
				saver.save('./model/res50_%d_%d.pth'%(ep, it))
				saver_classifier.save('./classifier/classifier_%d_%d.pth'%(ep,it))
		saver.save('./model/res50_%d_%d.pth'%(ep, it))
		saver_classifier.save('./classifier/classifier_%d_%d.pth'%(ep,it))

		if ep%4==3:
			newlr = lr * 0.1 
			for param_group in optim.param_groups:
				param_group['lr'] = newlr
