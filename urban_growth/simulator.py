from urban_growth.model import *

class simulator(settlement_model):

	def __init__(self, **kwargs):

		settlement_model.__init__(self, **kwargs)

	def sample(self, **kwargs):
		'''
			Forward step
		'''

		probs = self.density(**kwargs)
		prob = probs[0] + probs[1]
		rands = np.random.rand(*prob.shape)
		new_mat = (rands < prob) * 1

		return new_mat

	def dynamics(self, n_iters = 5, **kwargs):
		'''
			Defaults to model_1 for now
		'''
		times = np.arange(2, n_iters + 2)
		return_mat = self.M.copy()
		for i in times:
			s = self.sample(stage = 'current', **kwargs)
			self.M += s
			return_mat += i * s

		return_mat[return_mat == 0] = np.nan 	
		return_mat -= 1
		
		return return_mat