import numpy as np
from skimage import morphology
from scipy.spatial import distance
from scipy.special import expit
from scipy.ndimage.filters import gaussian_filter

class settlement_model:

	def __init__(self, M0 = None, geo = None, D = None):

		if geo is not None:
			self.geo = geo
		elif M0 is not None:
			self.geo = np.ones(self.M0.shape)

		if D is not None: 
			self.D = D

		self.dists     = None
		self.dist_type = None

	def set_M0(self, M0 = None, **kwargs):
		if M0 is not None:
			self.M0 = M0
		else:
			self.M0 = random_mat(**kwargs)

		self.M = self.M0.copy()

	def get_M0(self):
		return self.M0

	def get_M(self):
		return self.M

	def settlement_type_matrix(self, thresh, stage = 'current'):
		if stage == 'current': 
			M_d = self.M

		elif stage == 'initial':
			M_d = self.M0

		rural, urban, unsettled = settlement_types(M_d, thresh = thresh)
		types = np.zeros(M_d.shape)

		for i in range(urban.shape[0]):
		    types[tuple(urban[i,])] =  1
		for i in range(rural.shape[0]):
		    types[tuple(rural[i,])] = -1		

		return types

	def set_dists(self, thresh, stage = 'current'):
		
		print 'recalculating distances'
		if stage == 'initial': 
			self.dists = get_dists(self.M0, thresh)	
			self.dist_type = 'initial'
		elif stage == 'current':
			self.dists = get_dists(self.M, thresh)
			self.dist_type = 'current'

	def density(self, thresh, pars, use_geo = False, stage = 'current'):
		
		pars = {k : float(pars[k]) for k in pars}  # had a float bug in here somewhere

		if stage == 'current':
			self.set_dists(thresh, stage)
		elif (stage == 'initial') & (self.dist_type != 'initial'):
			self.set_dists(thresh, stage)
		
		gammas = ('gamma_r', 'gamma_u')
		g_pars = {k: pars[k] for k in gammas}
		p_pars = {k: pars[k] for k in pars if k not in gammas}
		
		if stage == 'initial': 
			M_d = self.M0
		elif stage == 'current':
			M_d = self.M

		w_rural, w_urban = distance_weights(M_d, self.dists, thresh, **g_pars) 
		
		probs = model_1_probs(w_rural, w_urban, **p_pars) 
		if use_geo:
			probs = probs * self.geo

		return probs

	def sample(self, thresh, pars, use_geo = False, stage = 'current'):
		'''
			Forward step
		'''

		probs = self.density(thresh, pars, use_geo, stage)
		prob = probs[0] + probs[1]
		rands = np.random.rand(*prob.shape)
		new_mat = (rands < prob) * 1

		return new_mat

	def dynamics(self, thresh, pars, use_geo = False, n_iters = 5):
			
		times = np.arange(2, n_iters + 2)
		return_mat = self.M.copy()
		for i in times:
			s = self.sample(thresh, pars, use_geo, 'current')
			self.M += s
			return_mat += i * s

		return_mat[return_mat == 0] = np.nan 	
		return_mat -= 1
		
		return return_mat

	def infer(self, model_type, M1, return_trace = True):
		'''
			Backward step
		'''
		print 'not implemented'


	def log_likelihood(self, M1, thresh, pars, model_type, normalized = False, use_geo = False):
		'''
			Correct for both of the supervised models
		'''
		
		probs = self.density(thresh, pars, use_geo, stage = 'initial')
		prob = probs[0] + probs[1]
		
		X = M1 

		ll = np.nansum(X * np.log(prob) + (1 - X) * np.log(1 - prob))
		
		if normalized:
			N = (1 - 
			     np.isnan(M1)).sum()
			return 1.0 / N * ll
		
		else:
			return ll

def model_1_probs(w_rural, w_urban, alpha_r, beta_r, alpha_u, beta_u):
	p_r = expit(alpha_r * w_rural + beta_r)
	p_u = expit(alpha_u * w_urban + beta_u)

	denom = p_r + p_u

	return p_r ** 2 / denom, p_u ** 2 / denom

def id_clusters(M):

	mask = morphology.label(M, connectivity = 1)
	return mask

def cluster_areas(mask):
	
	u = np.unique(mask, return_counts = True)
	area_dict = {u[0][i] : u[1][i] for i in range(len(u[0]))} # needs to be sorted?
	area_dict.pop(0) # ignore background
	return area_dict

def settlement_types(M,  return_type = 'cell', thresh = 0):
	'''
		Compute the types of cells and return the results at either the cluster or cell level. 
	'''

	mask      = id_clusters(M)
	area_dict = cluster_areas(mask)
	
	urban_clusters = {key : area_dict[key] for key in area_dict if area_dict[key] >= thresh}

	rural_clusters = area_dict
	for key in urban_clusters:
		rural_clusters.pop(key, None) 

	if return_type == 'cluster':
		return rural_clusters, urban_clusters
	else:
		ix = np.in1d(mask.ravel(), urban_clusters.keys()).reshape(mask.shape)
		a = np.where(ix)

		urban_cells = np.array([[a[0][i], a[1][i]] for i in range(len(a[0]))])

		ix = np.in1d(mask.ravel(), rural_clusters.keys()).reshape(mask.shape)
		a = np.where(ix)

		rural_cells = np.array([[a[0][i], a[1][i]] for i in range(len(a[0]))])

		a = np.where(mask == 0)
		unsettled_cells = np.array([[a[0][i], a[1][i]] for i in range(len(a[0]))])

		return rural_cells, urban_cells, unsettled_cells

# Distance computations. An alternative way to approach this would be to compute the distance to the centroid weighted by the size of the cluster, which would have slightly different physics but would likely be MUCH faster. Would need to check for weird behavior -- as cluster gets larger, weight should increase, but this is not prima facie guaranteed under the centroid scheme. 

def get_dists(M, thresh = 0):
	
	def f(j, arr):
		a = np.unique(arr[j,], return_counts=True)
		return [(a[0][i], a[1][i]) for i in range(a[0].shape[0])]

	rural, urban, unsettled = settlement_types(M, 'cell', thresh)
	
	rural_dist_mat = distance.cdist(unsettled, rural, 'euclidean').astype(int)
	rural_dists    = {i : f(i, rural_dist_mat) for i in range(rural_dist_mat.shape[0])}

	urban_dist_mat = distance.cdist(unsettled, urban, 'euclidean').astype(int)
	urban_dists    = {i : f(i, urban_dist_mat) for i in range(urban_dist_mat.shape[0])}

	return rural_dists, urban_dists

def distance_weights(M, dists, thresh, gamma_r, gamma_u):
	def f(i, gamma_r, gamma_u):
		
		a = np.array(dists[0][i])
		r = np.dot(a[:,0] ** (-gamma_r), a[:,1])

		b = np.array(dists[1][i])
		u = np.dot(b[:,0] ** (-gamma_u), b[:,1])
		
		return r, u
	
	rural, urban, unsettled = settlement_types(M, 'cell', thresh)
	
	weights_rural = np.empty(M.shape)
	weights_urban = np.empty(M.shape)
	weights_rural.fill(np.nan)
	weights_urban.fill(np.nan)

	weight_tuples = [f(i, gamma_r, gamma_u) for i in range(len(dists[0]))]

	for i in range(unsettled.shape[0]):
		weights_urban[unsettled[i][0], unsettled[i][1]] = weight_tuples[i][1]
		weights_rural[unsettled[i][0], unsettled[i][1]] = weight_tuples[i][0]

	return weights_rural, weights_urban


def random_mat(L, density = .5, blurred = True, blur = 3, central_city = True):
    
    M = np.random.rand(L, L)

    if central_city:

        M[(1 * L/2 - L / 10):(1 * L/2 + L/10),(1 * L/2 - L / 10):(1 * L/2 + L/10)] = 0

    if blurred: 
        M = gaussian_filter(M, blur)
        
    ix_low = M < density  # Where values are low
    M[ix_low]  = 1

    M[M < 1] = 0
        
    return M

