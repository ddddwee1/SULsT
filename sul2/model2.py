import layers2 as L 
import tensorflow as tf 
import numpy as np 
import os 
import random

PARAM_RELU = 0
PARAM_LRELU = 1
PARAM_ELU = 2
PARAM_TANH = 3
PARAM_MFM = 4
PARAM_MFM_FC = 5
PARAM_SIGMOID = 6

######## util functions ###########
def loadSess(modelpath=None,sess=None,var_list=None,init=False, init_dict=None):
	# load session if there exist any models, and initialize the sess if not
	if init:
		if not modelpath is None:
			if not os.path.exists(modelpath):
				os.makedirs(modelpath)
		print('Initializing...')
		sess.run(tf.global_variables_initializer(),feed_dict=init_dict)
	
	if not modelpath is None:
		saver = tf.train.Saver(var_list)
		ckpt = tf.train.get_checkpoint_state(modelpath)
		if modelpath.endswith('.ckpt'):
			saver.restore(sess,modelpath)
		elif ckpt:
			mod = ckpt.model_checkpoint_path
			print('loading from model:',mod)
			saver.restore(sess,mod)
		else:
			print('No checkpoint in folder, use initial graph...')
		return saver 

def accuracy(pred,y,name='acc'):
	with tf.variable_scope(name):
		correct = tf.equal(tf.cast(tf.argmax(pred,-1),tf.int64),tf.cast(y,tf.int64))
		acc = tf.reduce_mean(tf.cast(correct,tf.float32))
	return acc

def get_trainable_vars(scope=None):
	return tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES,scope=scope)

def get_all_vars(scope=None):
	return tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES,scope=scope)

def get_update_ops(scope=None):
	return tf.get_collection(tf.GraphKeys.UPDATE_OPS,scope=scope)

##########################
# ETA class. I want to see the ETA. It's too boring to wait here.
class ETA():
	def __init__(self,max_value):
		self.start_time = time.time()
		self.max_value = max_value
		self.current = 0

	def start(self):
		self.start_time = time.time()
		self.current = 0

	def sec2hms(self,sec):
		hm = sec//60
		s = sec%60
		h = hm//60
		m = hm%60
		return h,m,s

	def get_ETA(self,current,is_string=True):
		self.current = current
		time_div = time.time() - self.start_time
		time_remain = time_div * float(self.max_value - self.current) / float(self.current + 1)
		h,m,s = self.sec2hms(int(time_remain))
		if is_string:
			return '%d:%d:%d'%(h,m,s)
		else:
			return h,m,s

#########################
# make a trainer to support gradient accumulation
trainer_cnt = 0
class Trainer():
	def __init__(self,learning_rate,loss,scope=None,**kwargs):
		global trainer_cnt
		with tf.variable_scope('Trainer_%d'%trainer_cnt):
			trainer_cnt += 1
			opt = tf.train.AdamOptimizer(learning_rate,**kwargs)

			tv = tf.trainable_variables(scope)

			self.accum = [tf.Variable(tf.zeros_like(v.initialized_value()), trainable=False) for v in tv]
			self.zero_op = [v.assign(tf.zeros_like(v)) for v in self.accum]

			gs = opt.compute_gradients(loss, tv)

			self.accum_op = [self.accum[i].assign_add(g[0]) for i,g in enumerate(gs)]
			with tf.control_dependencies(self.accum_op):
				self.apply = opt.apply_gradients([(self.accum[i],g[1]) for i,g in enumerate(gs)])
				with tf.control_dependencies([self.apply]):
					self.train_op = [v.assign(tf.zeros_like(v)) for v in self.accum]

	def accumulate(self):
		return self.accum_op

	def train(self):
		return self.train_op

	def apply_gradients(self):
		return self.apply

	def zero(self):
		return self.zero_op

########### model class ##########
class Model():
	def __init__(self, inp):
		self.layernum = 0
		self.result = inp
		self.layers = []
		self.bntraining = True
		self.epsilon = None

	def get_current_layer(self):
		return self.result

	def get_variables(self,start=0, end=None):
		if end is None:
			end = len(self.layers)
		res = []
		for scope in self.layers[start:end]:
			res += get_all_vars(scope)
		return res 

	def reset_layernum(self):
		self.layernum = 0

	def set_current_layer(self,layer):
		self.result = layer

	def activate(self,param, **kwarg):
		act = L.activation(self.result, param, 'conv_'+str(self.layernum), **kwarg)
		self.result = act.output
		return self.result

	def batch_norm(self):
		bn = L.batch_norm(self.result,training=self.bntraining,epsilon=self.epsilon,name='batch_norm_'+str(self.layernum))
		self.result = bn.output
		return self.result

	def convLayer(self,size,outchn,dilation_rate=1,stride=1,pad='SAME',activation=-1,batch_norm=False,layerin=None,usebias=True,kernel_data=None,bias_data=None,weight_norm=False):
		with tf.variable_scope('conv_'+str(self.layernum)):
			self.layers.append(tf.get_variable_scope().name)
			if not layerin is None:
				self.result = layerin

			# conv
			conv = L.conv2D(self.result,size,outchn,'conv_'+str(self.layernum),stride=stride,pad=pad,usebias=usebias,kernel_data=kernel_data,bias_data=bias_data,dilation_rate=dilation_rate,weight_norm=weight_norm)
			self.result = conv.output

			# bn
			if batch_norm:
				bn = self.batch_norm()
			# act
			act = self.activate(activation)

			self.layernum += 1
		return self.result

	def maxpoolLayer(self,size,stride=None,pad='SAME'):
		pool = L.maxpoolLayer(self.result,size,stride,'maxpool_'+str(self.layernum),pad=pad)
		self.result = pool.output
		return self.result

	def fcLayer(self,outsize,activation=-1,usebias=True,batch_norm=False):
		with tf.variable_scope('fc_'+str(self.layernum)):
			self.layers.append(tf.get_variable_scope().name)
			fc = L.fcLayer(self.result,outsize,name='fc_'+str(self.layernum),usebias=usebias)
			self.result = fc.output
			
			# bn
			if batch_norm:
				self.batch_norm()
			# act
			self.activate(activation)

			self.layernum+=1
		return self.result

	def flatten(self):
		size = self.result.get_shape().as_list()
		if len(size)==5:
			self.result = tf.reshape(self.result,[-1,size[1]*size[2]*size[3]*size[4]])
		else:
			self.result = tf.reshape(self.result,[-1,size[1]*size[2]*size[3]])
		return self.result

	def reshape(self,shape):
		self.result = tf.reshape(self.result, shape)
		return self.result

	def deconvLayer(self, size, outchn, activation=-1, stride=1, usebias=True, pad='SAME', batch_norm=False):
		with tf.variable_scope('deconv_'+str(self.layernum)):
			self.layers.append(tf.get_variable_scope().name)
			deconv = L.deconv2D(self.result, size, outchn, stride, usebias, pad, 'deconv_'+str(self.layernum))
			self.result = deconv.output
			if batch_norm:
				self.batch_norm()

			self.activate(activation)

			self.layernum += 1
		return self.result

########### Network Template #########
class Network():
	def __init__(self):
		if self.model_path[-1]!='/':
			self.model_path += '/'
		self.build_structure()
		self.build_loss()
		self.config_tensors()
		self.start_sess()

	def build_structure(self):
		pass 

	def build_loss(self):
		pass 

	def config_tensors(self):
		pass

	def start_sess(self):
		self.sess = tf.Session()
		self.saver = loadSess(self.model_path, self.sess, init=True)

	def train(self):
		pass

	def eval(self):
		pass 

	def get_feat(self):
		pass 

	def load(self, path, var_list=None):
		loadSess(path, self.sess, var_list=var_list)

	def save(self, path):
		self.saver.save(self.sess, self.model_path + path)


######### Data Reader Template ##########
class data_reader():
	def __init__(self, one_hot=None):
		self.data_pos = 0
		self.val_pos = 0
		self.data = []
		self.val = []
		self.one_hot = False
		if one_hot is not None:
			self.one_hot = True
			self.eye = np.eye(one_hot)
		self.load_data()
		
	def get_next_batch(self,BSIZE):
		if self.data_pos + BSIZE > len(self.data):
			random.shuffle(self.data)
			self.data_pos = 0
		batch = self.data[self.data_pos : self.data_pos+BSIZE]
		x = [i[0] for i in batch]
		y = [i[1] for i in batch]
		if self.one_hot:
			y = self.eye[np.array(y)]
		self.data_pos += BSIZE
		return x,y

	def get_val_next_batch(self, BSIZE):
		if self.val_pos + BSIZE >= len(self.val):
			batch = self.val[self.val_pos:]
			random.shuffle(self.val)
			self.val_pos = 0
			is_end = True
		else:
			batch = self.data[self.data_pos : self.data_pos+BSIZE]
			is_end = False
		x = [i[0] for i in batch]
		y = [i[1] for i in batch]
		if self.one_hot:
			y = self.eye[np.array(y)]
		self.val_pos += BSIZE
		return x,y, is_end

	def get_train_iter(self, BSIZE):
		return len(self.data)//BSIZE

	def get_val_iter(self, BSIZE):
		return len(self.val)//BSIZE + 1

class list_reader():
	def __init__(self, one_hot=None):
		self.data_pos = 0
		self.val_pos = 0
		self.data = []
		self.val = []
		self.one_hot = False
		if one_hot is not None:
			self.one_hot = True
			self.eye = np.eye(one_hot)
		self.load_data()
		
	def get_next_batch(self,BSIZE):
		if self.data_pos + BSIZE > len(self.data):
			random.shuffle(self.data)
			self.data_pos = 0
		batch = self.data[self.data_pos : self.data_pos+BSIZE]
		x = [i[0] for i in batch]
		y = [i[1] for i in batch]
		if self.one_hot:
			y = self.eye[np.array(y)]
		self.data_pos += BSIZE

		x = [self.process_img(i) for i in x]
		return x,y

	def get_val_next_batch(self, BSIZE):
		if self.val_pos + BSIZE >= len(self.val):
			batch = self.val[self.val_pos:]
			random.shuffle(self.val)
			self.val_pos = 0
			is_end = True
		else:
			batch = self.data[self.data_pos : self.data_pos+BSIZE]
			is_end = False
		x = [i[0] for i in batch]
		y = [i[1] for i in batch]
		if self.one_hot:
			y = self.eye[np.array(y)]
		self.val_pos += BSIZE
		x = [self.process_img(i) for i in x]
		return x,y, is_end

	def get_train_iter(self, BSIZE):
		return len(self.data)//BSIZE

	def get_val_iter(self, BSIZE):
		return len(self.val)//BSIZE + 1
